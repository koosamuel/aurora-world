"""UCI Online Retail II acquisition, auditable aggregation and policy replay.

Chen, D. (2012), DOI 10.24432/C5CG6D, CC BY 4.0.
This is observed UK invoice quantity, not Aurora, inventory, or latent demand.
Only acquisition/Excel conversion requires optional openpyxl. Evaluation is stdlib.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import re
import statistics
import urllib.request
import zipfile
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from .forecast import config_for,digest,mase_scale,usable
from .decisions import choose,forecast,quantile,summary
from .inventory import replay,policy_for

PAGE='https://archive.ics.uci.edu/dataset/502/online+retail+ii'
URL='https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip'
ARCHIVE_SHA256='572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb'
START=date(2009,12,7);STOP=date(2011,12,5);OVERLAP=date(2010,12,1)
SCHEMA='aurora-public-retail-weekly-v1'
STOCK=re.compile(r'[0-9]{5}[A-Z]{0,2}\Z')
MAX_DOWNLOAD=60*1024*1024


def filehash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def writejson(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def acquire(dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    archive=dest/'online-retail-ii.zip'
    if not archive.exists():
        partial=dest/'download.part'
        try:
            with urllib.request.urlopen(URL,timeout=60) as response,partial.open('wb') as f:
                size=0
                while b:=response.read(1024*1024):
                    size+=len(b)
                    if size>MAX_DOWNLOAD:raise ValueError('Source exceeds 60 MiB')
                    f.write(b)
            if filehash(partial)!=ARCHIVE_SHA256:raise ValueError('Downloaded source hash changed; review before replacing')
            partial.replace(archive)
        finally:partial.unlink(missing_ok=True)
    if filehash(archive)!=ARCHIVE_SHA256:raise ValueError('Archive hash mismatch')
    workbook=dest/'online_retail_II.xlsx'
    with zipfile.ZipFile(archive) as z:
        if z.namelist()!=['online_retail_II.xlsx']:raise ValueError('Unexpected archive members')
        info=z.getinfo('online_retail_II.xlsx')
        if info.file_size>MAX_DOWNLOAD:raise ValueError('Workbook exceeds limit')
        content=z.read(info)
    if workbook.exists() and hashlib.sha256(workbook.read_bytes()).digest()!=hashlib.sha256(content).digest():raise ValueError('Existing workbook differs; do not overwrite')
    if not workbook.exists():workbook.write_bytes(content)
    manifest=dest/'manifest.json'
    info=dict(dataset='UCI Online Retail II',citation='Chen, D. (2012). Online Retail II. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D.',doi='10.24432/C5CG6D',license='CC-BY-4.0',license_url='https://creativecommons.org/licenses/by/4.0/',landing_page=PAGE,download_url=URL,
              files=[dict(path=f.name,bytes=f.stat().st_size,sha256=filehash(f)) for f in [archive,workbook]],raw_contains_customer_ids=True,raw_published_to_git=False)
    if manifest.exists():
        existing=json.loads(manifest.read_text())
        if existing.get('files')!=info['files']:raise ValueError('Manifest source hash mismatch')
        return existing
    info['acquired_at']=datetime.now(timezone.utc).isoformat();writejson(manifest,info);return info


def excel_rows(workbook):
    try:from openpyxl import load_workbook
    except ImportError:raise RuntimeError('Install aurora-world[retail] for Excel conversion') from None
    w=load_workbook(workbook,read_only=True,data_only=True)
    try:
        if w.sheetnames!=['Year 2009-2010','Year 2010-2011']:raise ValueError('Unexpected workbook sheets')
        for sheet in w:
            it=sheet.iter_rows(values_only=True);header=next(it)
            expected=('Invoice','StockCode','Description','Quantity','InvoiceDate','Price','Customer ID','Country')
            if header!=expected:raise ValueError('Unexpected workbook columns')
            for row in it:
                # Customer ID and product descriptions are deliberately never exported.
                yield sheet.title,dict(invoice=row[0],sku=row[1],quantity=row[3],when=row[4],price=row[5],country=row[7])
    finally:w.close()


def aggregate(rows,source,*,sku_limit=100,evaluation_weeks=32,warmup=4):
    if type(sku_limit) is not int or not 1<=sku_limit<=100:raise ValueError('1..100 SKUs required')
    if type(evaluation_weeks) is not int or evaluation_weeks<8 or type(warmup) is not int or warmup<0:raise ValueError('Invalid replay window')
    periods=[(START+timedelta(weeks=i)).isoformat() for i in range((STOP-START).days//7)]
    cutoff=len(periods)-evaluation_weeks-warmup
    if cutoff<64:raise ValueError('Reserve at least 64 training/selection weeks')
    counts=collections.Counter();sheets=collections.Counter();gross=collections.defaultdict(collections.Counter);cancel=collections.defaultdict(collections.Counter)
    for sheet,r in rows:
        if sheet not in ('Year 2009-2010','Year 2010-2011'):raise ValueError('Unknown worksheet')
        counts['raw_rows']+=1;sheets[sheet]+=1
        if all(v is None for v in r.values()):counts['empty_rows']+=1;continue
        when=r['when']
        if not isinstance(when,(date,datetime)):counts['invalid_date']+=1;continue
        d=when.date() if isinstance(when,datetime) else when
        # The first sheet also contains Dec 1-9 2010. Keep the second sheet for that overlap.
        if sheet=='Year 2009-2010' and d>=OVERLAP:counts['overlap_first_sheet_excluded']+=1;continue
        if sheet=='Year 2010-2011' and d<OVERLAP:counts['second_sheet_before_boundary_excluded']+=1;continue
        if not START<=d<STOP:counts['partial_boundary_week_excluded']+=1;continue
        if r['country']!='United Kingdom':counts['other_country']+=1;continue
        code=str(r['sku']).strip().upper()
        if not STOCK.fullmatch(code):counts['non_product_code']+=1;continue
        q=r['quantity'];price=r['price'];invoice=r['invoice']
        if invoice is None or not isinstance(q,(int,float)) or type(q) is bool or not math.isfinite(q) or q==0 or not isinstance(price,(int,float)) or type(price) is bool or not math.isfinite(price) or price<=0:
            counts['invalid_quantity_price_invoice']+=1;continue
        week=(d-START).days//7
        if str(invoice).strip().upper().startswith('C') or q<0:
            if q>=0:counts['cancellation_positive_quantity_excluded']+=1;continue
            cancel[code][week]+=abs(q);counts['cancellation_or_negative_rows']+=1
        else:gross[code][week]+=q;counts['positive_invoice_rows']+=1
    rank=sorted(((sum(v for w,v in weeks.items() if w<cutoff),code) for code,weeks in gross.items()),key=lambda x:(-x[0],x[1]))
    chosen=[code for volume,code in rank if volume>0][:sku_limit]
    if not chosen:raise ValueError('No eligible prefix products')
    series=[]
    for code in chosen:
        first=min(gross[code]);values=[gross[code].get(i,0) if i>=first else None for i in range(len(periods))]
        series.append(dict(sku='UCI-'+code,values=values,statuses=['observed' if i>=first else 'not_started' for i in range(len(periods))],
                           cancellations=[cancel[code].get(i,0) for i in range(len(periods))],stockouts=[None]*len(periods),unit_cost=None))
    payload=dict(schema_version=SCHEMA,synthetic=False,version='uci-retail-ii-uk-weekly-v1',target='positive_invoice_quantity',unit='each',currency='GBP',periods=periods,series=series,
                 source=source,selection=dict(cutoff=cutoff,information_end=periods[cutoff-1],method='Top positive-quantity products on prefix only; ties stock code ascending',sku_limit=sku_limit),
                 replay=dict(evaluation_weeks=evaluation_weeks,warmup=warmup),audit=dict(counts=dict(counts),sheet_rows=dict(sheets),eligible_product_count=len(gross)),
                 assumptions=['UK invoices only; boundary partial weeks removed','Year 2010-2011 takes precedence from 2010-12-01; within-sheet repeated invoice lines retained',
                 'No recorded invoice after first recorded positive sale means zero recorded sales under transaction-log coverage assumption, not proven zero demand',
                 'not_started means before first recorded sale, not a known product launch date','Negative/cancelled quantities retained separately, not subtracted from gross sales or treated as physical inventory receipts',
                 'Stockouts, supplier lead time, procurement costs and initial inventory unknown; sale price in GBP is not procurement cost'])
    validate(payload);return payload


def validate(p):
    if not isinstance(p,dict) or p.get('schema_version')!=SCHEMA or p.get('synthetic') is not False or p.get('target')!='positive_invoice_quantity' or p.get('currency')!='GBP' or p.get('unit')!='each':raise ValueError('Public retail contract required')
    dates=[date.fromisoformat(v) for v in p['periods']]
    if not 20<=len(dates)<=520 or any(d.weekday()!=0 for d in dates) or any(b-a!=timedelta(days=7) for a,b in zip(dates,dates[1:])):raise ValueError('Continuous Monday grid required')
    if not 1<=len(p['series'])<=100:raise ValueError('Invalid SKU count')
    seen=set()
    for item in p['series']:
        if not re.fullmatch(r'UCI-[0-9]{5}[A-Z]{0,2}',item['sku']) or item['sku'] in seen:raise ValueError('Duplicate/invalid product ID')
        seen.add(item['sku'])
        if any(len(item[k])!=len(dates) for k in ['values','statuses','cancellations','stockouts']):raise ValueError('Incomplete weekly grid')
        for value,status,returned,stockout in zip(item['values'],item['statuses'],item['cancellations'],item['stockouts']):
            if status not in ('observed','not_started') or (status=='observed' and (type(value) not in (int,float) or not usable(value))) or (status=='not_started' and value is not None):raise ValueError('Invalid observed value/status')
            if type(returned) not in (int,float) or not usable(returned) or stockout is not None:raise ValueError('Cancellation/unknown stockout contract')
        if item['unit_cost'] is not None:raise ValueError('Do not infer procurement cost from sale price')
    n=len(dates);cut=p['selection']['cutoff'];e=p['replay']['evaluation_weeks'];w=p['replay']['warmup']
    if any(type(x) is not int for x in (cut,e,w)) or cut<64 or e<8 or w<0 or cut+e+w!=n or p['selection']['information_end']!=p['periods'][cut-1]:raise ValueError('Invalid selection/evaluation boundary')
    src=p['source']
    if src.get('license')!='CC-BY-4.0' or not re.fullmatch('[a-f0-9]{64}',src.get('workbook_sha256','')):raise ValueError('Source license/hash required')
    return p


def protection_buffer(history,model,c,protection):
    errors=[]
    for k in range(3,0,-1):
        origin=len(history)-protection*k
        if origin<1:continue
        preds,_=forecast(history[:origin],protection,model,c['season_length'])
        actual=history[origin:origin+protection]
        if preds is not None and len(actual)==protection and all(usable(x) for x in actual):errors.append(sum(actual)-sum(preds))
    return (max(0,quantile(errors,.95)),len(errors)) if errors else (None,0)


def evaluate_public(payload,policy_inputs=None):
    validate(payload);cut=payload['selection']['cutoff'];warm=payload['replay']['warmup']
    c=config_for(dict(weeks=len(payload['periods']),skus=len(payload['series'])))
    if policy_inputs is not None and (not isinstance(policy_inputs,dict) or not set(policy_inputs)<= {r['sku'] for r in payload['series']}):raise ValueError('Unknown SKU policy inputs')
    policy_inputs=policy_inputs or {};assignments=[];predictions=[];details=[];excluded=[]
    scenarios=[dict(id='lead2_history',lead_time=2,initial='history'),dict(id='lead2_zero',lead_time=2,initial='zero'),dict(id='lead4_history',lead_time=4,initial='history')]
    for item in payload['series']:
        sku=item['sku'];history=item['values'][:cut];actual=item['values'][cut:];choice=choose(history,c)
        assignments.append(dict(sku=sku,selection_origin=cut,**choice))
        if choice['selected'] is None:excluded.append(dict(sku=sku,reason='no_validation_model'));continue
        roles={'naive':'naive','seasonal_naive':'seasonal_naive','selected':choice['selected']}
        for t in range(warm,len(actual)):
            past=history+actual[:t];truth=actual[t]
            if not usable(truth):continue
            for role,model in roles.items():
                point,reason=forecast(past,1,model,c['season_length'])
                if point is not None:predictions.append(dict(sku=sku,week=cut+t,period=payload['periods'][cut+t],model=role,assigned=model,actual=truth,predicted=point[0],scale=mase_scale(past,52)))
                else:excluded.append(dict(sku=sku,week=cut+t,role=role,reason=reason))
        custom=policy_inputs.get(sku,{})
        if not isinstance(custom,dict) or set(custom)-{'policy','initial_stock','initial_pipeline'}:raise ValueError('Invalid per-SKU inventory input')
        if not isinstance(custom.get('policy',{}),dict) or 'lead_time' in custom.get('policy',{}):raise ValueError('Scenario grid owns lead_time')
        for scenario in scenarios:
            p=policy_for(dict(lead_time=scenario['lead_time'])|custom.get('policy',{}))
            # Scenario grid owns lead_time so that a scenario ID never mislabels its setting.
            if custom.get('policy',{}).get('lead_time',scenario['lead_time'])!=scenario['lead_time']:raise ValueError('Per-SKU lead_time conflicts with scenario grid')
            initial=0 if scenario['initial']=='zero' else custom.get('initial_stock')
            for role in ['naive','selected']:
                model=roles[role];b,n=protection_buffer(history,model,c,p['lead_time']+p['review_period'])
                for policy in ['no_buffer','validation_buffer']:
                    if policy=='validation_buffer' and b is None:excluded.append(dict(sku=sku,scenario=scenario['id'],role=role,policy=policy,reason='no_prefix_buffer_sample'));continue
                    try:sim=replay(history,actual,model,52,policy=p,buffer=b if policy=='validation_buffer' else 0,initial_stock=initial,initial_pipeline=custom.get('initial_pipeline'),warmup=warm)
                    except ValueError as error:excluded.append(dict(sku=sku,scenario=scenario['id'],role=role,policy=policy,reason=str(error)));continue
                    episode=f"{sku}:{scenario['id']}:{role}:{policy}"
                    for row in sim['rows']:
                        row.update(episode_id=episode,decision_id=episode+':'+str(row['week']),period=payload['periods'][cut+row['week']])
                    details.append(dict(sku=sku,scenario=scenario['id'],role=role,buffer_policy=policy,buffer_sample_n=n,**sim))
    common=set.intersection(*[{(r['sku'],r['week']) for r in predictions if r['model']==role} for role in ['naive','seasonal_naive','selected']])
    metrics=[dict(model=role,**summary([r for r in predictions if r['model']==role and (r['sku'],r['week']) in common])) for role in ['naive','seasonal_naive','selected']]
    summaries=[]
    for scenario in scenarios:
        cells=[(r,b) for r in ['naive','selected'] for b in ['no_buffer','validation_buffer']]
        eligible=set.intersection(*[{d['sku'] for d in details if d['scenario']==scenario['id'] and (d['role'],d['buffer_policy'])==cell} for cell in cells])
        for role,b in cells:
            rs=[d for d in details if d['scenario']==scenario['id'] and d['sku'] in eligible and d['role']==role and d['buffer_policy']==b]
            demand=sum(r['demand'] for r in rs);served=sum(r['served'] for r in rs)
            summaries.append(dict(scenario=scenario['id'],role=role,buffer_policy=b,skus=len(rs),demand=demand,served=served,fill_rate=served/demand if demand else None,
                                  service_met_skus=sum(r['service_met'] is True for r in rs),stockout_weeks=sum(r['stockout_weeks'] for r in rs),
                                  average_on_hand=sum(r['average_on_hand'] for r in rs),average_pipeline=sum(r['average_pipeline'] for r in rs),
                                  worst_sku_fill_rate=min((r['fill_rate'] for r in rs if r['fill_rate'] is not None),default=None)))
    return dict(schema_version='aurora-public-evaluation-v1',synthetic=False,inventory_is_scenario=True,company_performance_claim=False,version=payload['version'],source=payload['source'],data_sha256=digest(payload),
                code_sha256=filehash(__file__),inventory_code_sha256=filehash(Path(__file__).with_name('inventory.py')),forecast_code_sha256=filehash(Path(__file__).with_name('decisions.py')),
                evaluation=dict(selection_cutoff=cut,warmup_weeks=warm,evaluation_weeks=payload['replay']['evaluation_weeks'],forecast_mode='one-step rolling, selected model frozen before warmup',
                scenario_randomness='none; identical observed sales paths, no Monte Carlo confidence interval',scenario_grid=scenarios,policy_inputs_sha256=digest(policy_inputs)),
                paired_metrics=metrics,coverage_metrics=[dict(model=role,**summary([r for r in predictions if r['model']==role])) for role in ['naive','seasonal_naive','selected']],assignments=assignments,predictions=predictions,inventory_summaries=summaries,inventory_details=details,excluded=excluded,
                limitations=payload['assumptions']+['Policy replay is conditional on exogenous recorded sales as scenario demand; no causal evaluation or lost-demand reconstruction','Warmup excluded only from scoring; terminal pipeline remains outstanding; no liquidation value or company savings claim'])


def export_csv(path,rows,columns):
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)


def export_result(result,dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    writejson(dest/'result.json',result)
    export_csv(dest/'forecast.csv',result['predictions'],['sku','period','week','model','assigned','actual','predicted','scale'])
    export_csv(dest/'inventory.csv',result['inventory_summaries'],['scenario','role','buffer_policy','skus','demand','served','fill_rate','service_met_skus','stockout_weeks','average_on_hand','average_pipeline','worst_sku_fill_rate'])
    logs=(dict(sku=d['sku'],scenario=d['scenario'],role=d['role'],buffer_policy=d['buffer_policy'],policy_hash=d['policy_hash'],currency=d['currency'],**row) for d in result['inventory_details'] for row in d['rows'])
    export_csv(dest/'decisions.csv',logs,['decision_id','episode_id','sku','scenario','role','buffer_policy','policy_hash','currency','period','week','information_end_exclusive','phase','opening','received','ordered','target','demand','served','lost','closing','pipeline','capacity_shortfall','holding_cost','shortage_cost','order_cost','total_cost','reward','action_probability'])
    fmt=lambda v:'N/A' if v is None else f'{v:.3f}'
    lines=['# 공개 거래 자료의 수요예측·장기 재고 시나리오 검증','',f"출처: Chen, D. (2012). Online Retail II. UCI. DOI 10.24432/C5CG6D. CC BY 4.0. {PAGE}",'',
           '영국 선물용품 소매업체의 공개 청구 수량입니다. 오로라월드 자료·잠재 수요·회사 재고 실적이 아닙니다. 고객 ID·고객별 정보는 가공 입력/출력에 포함하지 않습니다.','',
           f"선택 절단점: {result['evaluation']['selection_cutoff']}주. 워밍업 {result['evaluation']['warmup_weeks']}주 뒤 {result['evaluation']['evaluation_weeks']}주 평가. 모델 선택·SKU 선정·버퍼는 절단점 이전 자료로 고정합니다.",'',
           '## 같은 SKU·주간 대상의 순차 예측 평가','','| 방식 | n | SKU | MAE | 편향 | MASE |','|---|---:|---:|---:|---:|---:|']
    for m in result['paired_metrics']:lines.append(f"| {m['model']} | {m['n']} | {m['skus']} | {fmt(m['mae'])} | {fmt(m['bias'])} | {fmt(m['mase'])} |")
    lines+=['','## 재고 시나리오 — 수량 기준','','같은 시나리오 내 네 예측×정책 셀은 공통 SKU·동일 판매 경로·초기 조건을 사용합니다. 평균 기말 재고와 미입고를 구분합니다. 조달원가·비용은 미확보이므로 기본 결과에 금액·절감액을 부여하지 않습니다. 서비스 목표 .95·리드타임·초기재고는 예시입니다.','',
            '| 시나리오 | 예측 | 버퍼 | SKU | 충족률 | 목표 충족 SKU | 최악 SKU 충족률 | 평균 보유수량 합 | 평균 미입고수량 합 |','|---|---|---|---:|---:|---:|---:|---:|---:|']
    for s in result['inventory_summaries']:lines.append(f"| {s['scenario']} | {s['role']} | {s['buffer_policy']} | {s['skus']} | {fmt(s['fill_rate'])} | {s['service_met_skus']} | {fmt(s['worst_sku_fill_rate'])} | {fmt(s['average_on_hand'])} | {fmt(s['average_pipeline'])} |")
    lines+=['','## 한계와 재현','']+['- '+v for v in result['limitations']]
    lines+=['',f"- 가공 데이터 SHA-256: `{result['data_sha256']}`",f"- 평가 코드 SHA-256: `{result['code_sha256']}`",'- result.json, forecast.csv, inventory.csv, decisions.csv를 같은 실행의 산출물로 보관합니다. CSV는 동일 결과 객체에서 내보냅니다.','']
    (dest/'report.md').write_text('\n'.join(lines))
    names=['result.json','forecast.csv','inventory.csv','decisions.csv','report.md']
    writejson(dest/'artifacts.json',dict(data_sha256=result['data_sha256'],files=[dict(path=n,sha256=filehash(dest/n),bytes=(dest/n).stat().st_size) for n in names]))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('acquire');a.add_argument('--dest',required=True,type=Path)
    a=sub.add_parser('prepare');a.add_argument('--raw',required=True,type=Path);a.add_argument('--output',required=True,type=Path);a.add_argument('--skus',type=int,default=100)
    a=sub.add_parser('evaluate');a.add_argument('--input',required=True,type=Path);a.add_argument('--output',required=True,type=Path);a.add_argument('--policy-inputs',type=Path)
    args=p.parse_args()
    if args.command=='acquire':
        info=acquire(args.dest);print(json.dumps(dict(downloaded=True,files=info['files']),indent=2));return
    if args.command=='prepare':
        manifest=json.loads((args.raw/'manifest.json').read_text());workbook=args.raw/'online_retail_II.xlsx'
        recorded=next(f['sha256'] for f in manifest['files'] if f['path']==workbook.name)
        if filehash(workbook)!=recorded:raise ValueError('Workbook hash mismatch')
        source=dict(dataset='UCI Online Retail II',landing_page=PAGE,doi='10.24432/C5CG6D',license='CC-BY-4.0',workbook_sha256=recorded,manifest_sha256=filehash(args.raw/'manifest.json'),converter_sha256=filehash(__file__))
        payload=aggregate(excel_rows(workbook),source,sku_limit=args.skus);writejson(args.output,payload)
        print(json.dumps(dict(weeks=len(payload['periods']),skus=len(payload['series']),selection=payload['selection'],audit=payload['audit']),indent=2));return
    payload=json.loads(args.input.read_text());custom=json.loads(args.policy_inputs.read_text()) if args.policy_inputs else None
    result=evaluate_public(payload,custom);export_result(result,args.output)
    print(json.dumps(dict(output=str(args.output),metrics=result['paired_metrics'],inventory_cells=len(result['inventory_summaries']),replays=len(result['inventory_details']),excluded=len(result['excluded'])),indent=2))

if __name__=='__main__':main()
