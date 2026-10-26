"""Create attributed research-informed synthetic fixtures; never read M4 test data."""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, math, random, statistics
from datetime import date, timedelta
from pathlib import Path
from PIL import Image, ImageDraw

PARTS=[('HEAD_FRONT','머리 앞',62,46),('HEAD_BACK','머리 뒤',62,46),('BODY_FRONT','몸통 앞',65,80),('BODY_BACK','몸통 뒤',65,80),('EAR_LEFT','왼쪽 귀',22,36),('EAR_RIGHT','오른쪽 귀',22,36),('ARM_LEFT','왼팔',21,48),('ARM_RIGHT','오른팔',21,48),('LEG_LEFT','왼다리',28,43),('LEG_RIGHT','오른다리',28,43),('TAIL','꼬리',17,56),('BELLY_PATCH','배 패치',40,48)]
SOURCE_URLS=['https://auroraworld.com/ko/business/overview','https://auroraworld.com/ko/business/global-design','https://palmpals.co.kr/']

def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False))
def write_lines(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in rows))
def read_lines(path):return [json.loads(line) for line in path.read_text().splitlines()]
def split_family(n):return 'train' if n<14 else 'validation' if n<17 else 'test'
def qsplit(key):
    n=int(hashlib.sha256(key.encode()).hexdigest()[:8],16)%10
    return 'train' if n<7 else 'validation' if n<9 else 'test'
def source_series(raw):
    # Source competition test file is deliberately not opened here.
    series=[]
    with (raw/'M4/Weekly-train.csv').open(newline='') as f:
        for row in csv.reader(f):
            if row[0]=='V1':continue
            try:values=[float(x) for x in row[1:] if x.strip() and x!='NA']
            except ValueError:continue
            if len(values)>=80 and all(math.isfinite(v) and v>=0 for v in values):
                prefix=values[:-13] # Reserve source tail too; fit only a past prefix.
                mean=statistics.mean(prefix)
                if mean>0:series.append((row[0],prefix,[max(-.8,min(1.5,v/mean-1)) for v in prefix]))
    if len(series)<100:raise ValueError('Too few usable source training series')
    return series

def make(out,raw,seed=42):
    if out.exists():raise ValueError('Output already exists; choose a new version directory.')
    out.mkdir(parents=True);rng=random.Random(seed);sources=source_series(raw)
    sketches=collections.defaultdict(list)
    for word in ['bear','cat','rabbit']:
        for item in read_lines(raw/'QuickDraw'/f'{word}.first300.ndjson'):
            if item.get('recognized') and item.get('drawing'):sketches[word,qsplit(str(item['key_id']))].append(item)
    skus=[];obs=[];inventory=[];truth=[];orders=[];calibration=[];parts=[];labels=[];bom=[];mapping=[];artworks=[]
    for i in range(100):
        family=i//5;split=split_family(family);species=['bear','cat','rabbit'][family%3]
        sku=f'SIM-{i+1:03}';design=f'DESIGN-{i+1:03}';group=f'FAMILY-{family+1:02}'
        base=10+(i%9)*4;cost=800+(i%9)*200;style=['steady','seasonal','intermittent','trend','zero','short','missing','returns','promotion','supply_gap'][i%10]
        source_id,source_prefix,residuals=sources[i];cv=statistics.pstdev(source_prefix)/statistics.mean(source_prefix)
        calibration.append(dict(sku_id=sku,source='M4/Weekly-train.csv',source_series_id=source_id,prefix_length=len(source_prefix),source_tail_reserved=13,cv=cv,method='clipped-relative-residual block bootstrap + explicit synthetic scenarios',uses_M4_test=False))
        skus.append(dict(sku_id=sku,design_id=design,family_id=group,split=split,name=f'가상 봉제 {species} {i+1:03}',brand='VIRTUAL_PLUSH',species=species,currency='KRW',unit='each',unit_cost_krw=cost,lead_time_weeks=2,reference_urls=SOURCE_URLS,synthetic=True))
        stock=base*4;pipeline=[];past=[];cumulative_sales=0;cumulative_returns=0;block=[]
        for t in range(156):
            period=(date(2023,1,2)+timedelta(weeks=t)).isoformat()
            if t%8==0:
                start=rng.randrange(max(1,len(residuals)-8));block=residuals[start:start+8]
            noise=block[t%8] if t%8<len(block) else 0
            seasonal=1+.28*math.sin(2*math.pi*t/52+(family%4)) if style=='seasonal' else 1
            trend=1+t/220 if style=='trend' else 1
            demand=max(0,round(base*seasonal*trend*(1+.3*noise)+rng.gauss(0,1)))
            if style=='intermittent' and rng.random()<.65:demand=0
            if style=='zero' or style=='short' and t<144:demand=0
            promotion=style=='promotion' and t%26 in (11,12)
            if promotion:demand*=3
            received=sum(q for due,q,_ in pipeline if due==t)
            pipeline=[p for p in pipeline if p[0]!=t]
            returned=min(rng.randint(1,8),max(0,cumulative_sales-cumulative_returns)) if style=='returns' and t%17==9 else 0
            opening=stock;available=opening+received+returned;shipped=min(available,demand);stock=available-shipped
            cumulative_sales+=shipped;cumulative_returns+=returned
            not_started=style=='short' and t<144;missing=style=='missing' and t%29==7
            status='not_started' if not_started else 'missing' if missing else 'observed'
            obs.append(dict(sku_id=sku,period=period,org_id='SIM-ORG',warehouse_id='SIM-WH',quantity=None if missing or not_started else shipped,gross_shipped= None if missing or not_started else shipped,return_qty=None if missing else returned,net_invoice_qty=None if missing or not_started else shipped-returned,status=status,stockout=demand>shipped,unit='each',promotion_announced_at=(date(2023,1,2)+timedelta(weeks=max(0,t-2))).isoformat() if promotion else None,synthetic=True))
            inventory.append(dict(sku_id=sku,period=period,opening_stock=opening,receipts=received,resalable_returns=returned,shipments=shipped,closing_stock=stock,pipeline_qty=sum(q for _,q,_ in pipeline),unit_cost_krw=cost,currency='KRW',inventory_value_krw=stock*cost,synthetic=True))
            truth.append(dict(sku_id=sku,period=period,latent_demand=demand,lost_sales=demand-shipped,true_gross_shipped=shipped,scenario=style,synthetic=True,evaluation_only=True))
            past.append(shipped)
            forecast=sum(past[-4:])/len(past[-4:]);target=math.ceil(3*forecast+base)
            qty=max(0,target-stock-sum(q for _,q,_ in pipeline))
            if style=='supply_gap' and 75<=t<=82:qty=0
            if qty:
                oid=f'PO-{i+1:03}-{t:03}';pipeline.append((t+2,qty,oid))
                orders.append(dict(order_id=oid,sku_id=sku,order_period=period,expected_receipt_period=(date(2023,1,2)+timedelta(weeks=t+2)).isoformat(),qty=qty,lead_time_weeks=2,unit='each',synthetic=True))
        # Source drawings are split before augmentation and stay in one product family split.
        available=sketches[species,split]
        source_sketch=available[(family*5+i)%len(available)]
        strokes=source_sketch['drawing'];lines=[]
        angle=rng.uniform(-.12,.12);scale=rng.uniform(.8,.95)
        for xs,ys in strokes:
            points=[]
            for x,y in zip(xs,ys):
                x,y=x-127.5,y-127.5;points.append((128+scale*(x*math.cos(angle)-y*math.sin(angle)),128+scale*(x*math.sin(angle)+y*math.cos(angle))))
            if len(points)>1:lines.append(points)
        artpath=f'artworks/{design}.svg';body=''.join('<polyline points="'+ ' '.join(f'{x:.2f},{y:.2f}' for x,y in pts)+'"/>' for pts in lines)
        (out/'artworks').mkdir(exist_ok=True)
        (out/artpath).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><title>Quick Draw derivative: synthetic artwork, not an Aurora product</title><rect width="256" height="256" fill="white"/><g fill="none" stroke="#193f3d" stroke-width="3" stroke-linecap="round">{body}</g></svg>')
        art=Image.new('RGB',(256,256),'white');draw=ImageDraw.Draw(art)
        for pts in lines:draw.line(pts,fill='#193f3d',width=3)
        art.save(out/artpath.replace('.svg','.png'))
        artworks.append(dict(design_id=design,sku_id=sku,family_id=group,split=split,svg_path=artpath,png_path=artpath.replace('.svg','.png'),source_word=species,source_key_id=str(source_sketch['key_id']),license='CC-BY-4.0',attribution='Google, Inc. and Quick, Draw! contributors',modifications='rotation/scaling; synthetic artwork; no actual Aurora image',synthetic=True))
        # Front/back and left/right share geometry intentionally; metadata/review is needed.
        shape_scale=.82+(family%7)*.05+(i%5)*.015
        sheets=[]
        for j,(code,korean,width,height) in enumerate(PARTS):
            w=width*shape_scale;h=height*shape_scale
            if code.startswith('EAR') and species=='rabbit':h*=1.6
            if code=='TAIL' and species=='bear':h*=.48;w*=1.8
            kind=code.split('_')[0];phase=(family%5)*.4
            pts=[]
            for k in range(80):
                a=2*math.pi*k/80;r=1+.055*math.sin(3*a+phase)
                x=w/2*(1+r*math.cos(a));y=h/2*(1+r*math.sin(a))
                pts.append((x,y))
            pid=f'PIECE-{i*12+j+1:05}';svg_path=f'patterns/svg/{pid}.svg';png_path=f'patterns/png/{pid}.png'
            poly=' '.join(f'{x+5:.3f},{y+5:.3f}' for x,y in pts)
            (out/'patterns/svg').mkdir(parents=True,exist_ok=True);(out/'patterns/png').mkdir(parents=True,exist_ok=True)
            (out/svg_path).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w+10:.3f}mm" height="{h+10:.3f}mm" viewBox="0 0 {w+10:.3f} {h+10:.3f}"><title>Synthetic closed pattern contour</title><polygon points="{poly}" fill="white" stroke="black" stroke-width=".5"/></svg>')
            # Same silhouette without textual labels; preserve aspect ratio and rotate.
            im=Image.new('L',(256,256),255);dr=ImageDraw.Draw(im);factor=210/max(w,h);theta=rng.uniform(-.14,.14)
            pp=[]
            for x,y in pts:
                x,y=(x-w/2)*factor,(y-h/2)*factor;pp.append((128+x*math.cos(theta)-y*math.sin(theta),128+x*math.sin(theta)+y*math.cos(theta)))
            dr.polygon(pp,fill=0);im.save(out/png_path)
            x0=(j%4)*105+(105-w-10)/2;y0=(j//4)*99+(99-h-10)/2
            # Clamp oversized rabbit ear layout by uniform A3-only scaling; record scale.
            layout_scale=min(1,88/(h+10),94/(w+10));x0=(j%4)*105+(105-(w+10)*layout_scale)/2;y0=(j//4)*99+(99-(h+10)*layout_scale)/2
            sheets.append(f'<g transform="translate({x0:.3f} {y0:.3f}) scale({layout_scale:.6f})"><polygon points="{poly}" fill="#eff5f2" stroke="#24534d" stroke-width=".4"/></g>')
            material=f'FABRIC-{family%4+1:02}'
            area=abs(sum(pts[k][0]*pts[(k+1)%len(pts)][1]-pts[(k+1)%len(pts)][0]*pts[k][1] for k in range(len(pts))))/2
            parts.append(dict(area_mm2=round(area,3),piece_id=pid,sku_id=sku,design_id=design,family_id=group,pattern_version='synthetic-v1',split=split,svg_path=svg_path,png_path=png_path,width_mm=round(max(x for x,y in pts)-min(x for x,y in pts),3),height_mm=round(max(y for x,y in pts)-min(y for x,y in pts),3),material_id=material,cut_qty=1,a3_x_mm=round(x0,3),a3_y_mm=round(y0,3),a3_layout_scale=round(layout_scale,6),synthetic=True))
            review=code not in ('TAIL','BELLY_PATCH')
            labels.append(dict(piece_id=pid,standard_part_id=code,standard_part_name=korean,side='left' if code.endswith('LEFT') else 'right' if code.endswith('RIGHT') else 'front' if code.endswith('FRONT') else 'back' if code.endswith('BACK') else 'none',requires_review_from_geometry_alone=review,ground_truth_origin='synthetic_template_not_company_approved'))
            aliases=[korean,code.lower(),korean.replace(' ','')+'조각',code.replace('_','-').lower()]
            alias='귀' if j in (4,5) and i%5==0 else aliases[i%4]
            mapping.append(dict(piece_id=pid,raw_name=alias,standard_part_id=code,ambiguous=alias=='귀',synthetic=True))
            bom.append(dict(sku_id=sku,design_id=design,piece_id=pid,pattern_version='synthetic-v1',raw_part_name=alias,material_id=material,cut_qty=1,estimated_area_mm2=round(math.pi*w*h/4,3),area_estimate_method='ellipse_approximation_not_actual_cutting_yield',synthetic=True))
        (out/'patterns/a3').mkdir(parents=True,exist_ok=True)
        (out/f'patterns/a3/{design}.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 420 297"><title>Synthetic A3 layout; not a production pattern</title>'+''.join(sheets)+'</svg>')
    totals=collections.Counter()
    for part in parts:totals[part['design_id']]+=part['area_mm2']
    for part in parts:part['relative_area']=part['area_mm2']/totals[part['design_id']]
    tables={'products.jsonl':skus,'forecast/sales_observations.jsonl':obs,'forecast/inventory_ledger.jsonl':inventory,'forecast/purchase_orders.jsonl':orders,'forecast/calibration.jsonl':calibration,'evaluation_only/latent_demand.jsonl':truth,'patterns/pieces.jsonl':parts,'patterns/labels.jsonl':labels,'patterns/name_mapping.jsonl':mapping,'patterns/bom.jsonl':bom,'artworks/index.jsonl':artworks}
    for name,rows in tables.items():write_lines(out/name,rows)
    write_json(out/'standard_parts.json',[dict(standard_part_id=c,name=n,company_approved=False,synthetic=True) for c,n,_,_ in PARTS])
    files=[]
    for path in sorted(out.rglob('*')):
        if path.is_file():files.append(dict(path=str(path.relative_to(out)),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    write_json(out/'manifest.json',dict(version='research-informed-synthetic-v1',seed=seed,synthetic=True,source_manifest_sha256=hashlib.sha256((raw/'download_manifest.json').read_bytes()).hexdigest(),pillow_version=__import__('PIL').__version__,generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),counts={k:len(v) for k,v in tables.items()},split_product_counts=dict(collections.Counter(x['split'] for x in skus)),split_group_counts={'train':14,'validation':3,'test':3},M4_test_used_for_generation=False,official_sources=SOURCE_URLS,files=files))
    print(json.dumps({'output':str(out),'counts':{k:len(v) for k,v in tables.items()},'files':len(files)},ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=42);a=p.parse_args();make(a.output,a.raw,a.seed)
