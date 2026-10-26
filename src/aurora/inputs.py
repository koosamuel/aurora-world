"""Strict synthetic weekly-file contract. Does not import latent demand or images."""
import argparse,hashlib,json,math,re
from datetime import date,timedelta
from pathlib import Path
from .forecast import DEFAULT,config_for,run_series

SCHEMA='aurora-weekly-input-v1'
MAX_BYTES=4*1024*1024
ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')

def require(condition,message):
    if not condition:raise ValueError(message)

def number(value):return type(value) in (int,float) and math.isfinite(value) and value>=0

def validate(payload):
    require(isinstance(payload,dict),'입력 객체가 필요합니다.')
    fields={'schema_version','synthetic','version','target','unit','currency','org_id','warehouse_id','periods','series','source'}
    require(set(payload)==fields,'입력 필드가 계약과 다릅니다.')
    require(payload['schema_version']==SCHEMA and payload['synthetic'] is True,'합성 주간 입력 v1만 허용합니다.')
    require(isinstance(payload['version'],str) and ID.fullmatch(payload['version']),'버전을 확인하세요.')
    require(payload['target']=='observed_gross_shipments','관측 총출하량만 지원합니다.')
    require(payload['unit']=='each' and payload['currency']=='KRW','단위 each·통화 KRW만 지원합니다.')
    for k in ('org_id','warehouse_id'):require(isinstance(payload[k],str) and ID.fullmatch(payload[k]),'단일 법인/창고 ID를 확인하세요.')
    periods=payload['periods'];require(isinstance(periods,list) and 20<=len(periods)<=520,'주간 기간은 20~520개여야 합니다.')
    try:
        dates=[date.fromisoformat(p) for p in periods]
        require(all(d.isoformat()==p and d.weekday()==0 for d,p in zip(dates,periods)),'ISO 월요일 기준이 필요합니다.')
        require(all(b-a==timedelta(days=7) for a,b in zip(dates,dates[1:])),'기간 중복·누락·역순을 허용하지 않습니다. 누락 주는 null 행으로 보존하세요.')
    except (TypeError,ValueError):raise ValueError('연속 ISO 월요일 주간 기간을 확인하세요.') from None
    rows=payload['series'];require(isinstance(rows,list) and 1<=len(rows)<=100,'1~100개 SKU를 지원합니다.')
    seen=set()
    for item in rows:
        require(isinstance(item,dict) and set(item)=={'sku','pattern','values','statuses','stockouts','returns','unit_cost_krw'},'SKU 필드가 계약과 다릅니다.')
        sku=item['sku'];require(isinstance(sku,str) and ID.fullmatch(sku) and sku not in seen,'SKU ID 중복/형식을 확인하세요.');seen.add(sku)
        require(isinstance(item['pattern'],str) and 1<=len(item['pattern'])<=80,'합성 패턴 설명이 필요합니다.')
        require(number(item['unit_cost_krw']) and item['unit_cost_krw']>0,'가상 단가를 확인하세요.')
        require(all(isinstance(item[k],list) and len(item[k])==len(periods) for k in ('values','statuses','stockouts','returns')),'모든 SKU는 전체 주간 그리드가 필요합니다.')
        for value,status,stockout,returned in zip(item['values'],item['statuses'],item['stockouts'],item['returns']):
            require(status in ('observed','missing','not_started'),'관측 상태를 확인하세요.')
            require(number(value) if status=='observed' else value is None,'누락/미개시는 null, 관측은 0 이상 유한 수량이어야 합니다.')
            require(type(stockout) is bool and (status=='observed' or not stockout),'품절 플래그를 확인하세요.')
            require(number(returned) or (returned is None and status=='missing'),'반품은 수요와 분리한 0 이상 수량이어야 합니다.')
    source=payload['source'];require(isinstance(source,dict) and set(source)=={'manifest_sha256','generator_sha256'},'출처 해시가 필요합니다.')
    require(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in source.values()),'출처 SHA-256을 확인하세요.')
    return dict(series=len(rows),observations=len(rows)*len(periods),weeks=len(periods),
                missing=sum(s=='missing' for r in rows for s in r['statuses']),
                not_started=sum(s=='not_started' for r in rows for s in r['statuses']),
                returns=sum(v is not None and v>0 for r in rows for v in r['returns']),
                stockouts=sum(v for r in rows for v in r['stockouts']))

def encode(payload):
    validate(payload);data=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    require(len(data)<=MAX_BYTES,'입력 파일은 최대 4 MiB입니다.');return data

def decode(data):
    require(isinstance(data,bytes) and 0<len(data)<=MAX_BYTES,'입력 파일 크기를 확인하세요.')
    def object_pairs(pairs):
        result={}
        for k,v in pairs:
            require(k not in result,'JSON 객체 키 중복을 허용하지 않습니다.');result[k]=v
        return result
    try:payload=json.loads(data,object_pairs_hook=object_pairs)
    except (UnicodeError,json.JSONDecodeError):raise ValueError('UTF-8 JSON을 확인하세요.') from None
    validate(payload);return payload

def load(path):
    with Path(path).open('rb') as f:return decode(f.read(MAX_BYTES+1))

def export_research(root):
    root=Path(root);manifest_bytes=(root/'manifest.json').read_bytes();manifest=json.loads(manifest_bytes)
    require(manifest.get('synthetic') is True,'합성 자료만 변환합니다.')
    def read_verified(name):
        expected=[f for f in manifest['files'] if f['path']==name];require(len(expected)==1,'명세에 고유 파일 해시가 필요합니다.')
        data=(root/name).read_bytes();require(hashlib.sha256(data).hexdigest()==expected[0]['sha256'],'원본 명세와 파일 해시가 다릅니다.')
        return [json.loads(x) for x in data.decode().splitlines()]
    products=read_verified('products.jsonl');sales=read_verified('forecast/sales_observations.jsonl')
    require(1<=len(products)<=100,'품목 수를 확인하세요.');by_sku={}
    for p in products:
        require(p.get('synthetic') is True and p['unit']=='each' and p['currency']=='KRW','품목의 합성/단위/통화를 확인하세요.')
        require(p['sku_id'] not in by_sku,'품목 키 중복입니다.');by_sku[p['sku_id']]={}
    require(sales,'관측 자료가 필요합니다.');orgs=set();warehouses=set();periods=set()
    for row in sales:
        require(row.get('synthetic') is True and row['unit']=='each','거래의 합성/단위를 확인하세요.')
        require(row['sku_id'] in by_sku,'알 수 없는 SKU입니다.');group=by_sku[row['sku_id']]
        require(row['period'] not in group,'SKU/주 중복입니다.');group[row['period']]=row
        require(row['quantity']==row['gross_shipped'],'관측 총출하량과 수량이 다릅니다.')
        orgs.add(row['org_id']);warehouses.add(row['warehouse_id']);periods.add(row['period'])
    require(len(orgs)==len(warehouses)==1,'단일 법인/창고만 지원합니다.')
    periods=sorted(periods);series=[]
    for p in sorted(products,key=lambda x:x['sku_id']):
        group=by_sku[p['sku_id']];require(set(group)==set(periods),'SKU별 주간 그리드가 다릅니다.')
        rows=[group[t] for t in periods]
        series.append(dict(sku=p['sku_id'],pattern='research-derived synthetic shipments',unit_cost_krw=p['unit_cost_krw'],values=[r['quantity'] for r in rows],statuses=[r['status'] for r in rows],stockouts=[r['stockout'] for r in rows],returns=[r['return_qty'] for r in rows]))
    payload=dict(schema_version=SCHEMA,synthetic=True,version=manifest['version']+'-weekly-v1',target='observed_gross_shipments',unit='each',currency='KRW',org_id=next(iter(orgs)),warehouse_id=next(iter(warehouses)),periods=periods,series=series,source=dict(manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),generator_sha256=manifest['generator_sha256']))
    validate(payload);return payload

def run_input(payload,options=None):
    quality=validate(payload);options=options or {}
    require(isinstance(options,dict) and not set(options)-{'horizon','season_length','validation_origins'},'파일 입력의 실행 설정을 확인하세요.')
    c=config_for({'skus':quality['series'],'weeks':quality['weeks'],'assumption_version':'file-input-A01-A11-v1'}|options)
    meta={k:payload[k] for k in ('schema_version','version','target','unit','currency','org_id','warehouse_id','source')}
    meta.update(file_sha256=hashlib.sha256(encode(payload)).hexdigest(),stockout_censoring=True,inventory_cost_policy='fixed synthetic 1000 KRW; product cost metadata not applied',input_validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return run_series(payload['series'],c,payload['periods'],payload['version'],meta,quality)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--research-root',type=Path);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--result',type=Path);a=p.parse_args()
    require(bool(a.research_root)!=bool(a.input),'--research-root 또는 --input 하나를 선택하세요.')
    payload=export_research(a.research_root) if a.research_root else load(a.input)
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(encode(payload))
    if a.result:a.result.parent.mkdir(parents=True,exist_ok=True);a.result.write_text(json.dumps(run_input(payload),ensure_ascii=False,allow_nan=False))
    print(json.dumps(dict(valid=True,version=payload['version'],quality=validate(payload),sha256=hashlib.sha256(encode(payload)).hexdigest()),ensure_ascii=False,indent=2))
