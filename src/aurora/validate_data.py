"""Integrity checks for the exported synthetic dataset; standard library only."""
import argparse,collections,hashlib,json,math,struct,xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

def read(path):return [json.loads(s) for s in path.read_text().splitlines()]
def validate(root):
    manifest=json.loads((root/'manifest.json').read_text());checks=[]
    def check(label,condition):
        if not condition:raise AssertionError(label)
        checks.append(label)
    for f in manifest['files']:
        p=root/f['path'];check('hash:'+f['path'],p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256'])
    products=read(root/'products.jsonl');pids={p['sku_id'] for p in products}
    pieces=read(root/'patterns/pieces.jsonl');labels=read(root/'patterns/labels.jsonl');arts=read(root/'artworks/index.jsonl')
    sales=read(root/'forecast/sales_observations.jsonl');ledger=read(root/'forecast/inventory_ledger.jsonl');orders=read(root/'forecast/purchase_orders.jsonl')
    check('unique sku',len(pids)==100==len(products))
    check('unique piece',len({p['piece_id'] for p in pieces})==1200==len(pieces))
    check('label coverage',set(x['piece_id'] for x in labels)==set(x['piece_id'] for x in pieces))
    check('balanced 12 part classes',len(collections.Counter(x['standard_part_id'] for x in labels))==12 and set(collections.Counter(x['standard_part_id'] for x in labels).values())=={100})
    groups=collections.defaultdict(set);source_keys=collections.defaultdict(set)
    for p in products:groups[p['split']].add(p['family_id'])
    for art in arts:source_keys[art['split']].add(art['source_key_id'])
    for a in groups:
        for b in groups:
            if a!=b:
                check('group split disjoint '+a+b,not groups[a]&groups[b]);check('source sketch split disjoint '+a+b,not source_keys[a]&source_keys[b])
    check('known SKUs',all(x['sku_id'] in pids for x in pieces+sales+ledger+orders))
    check('SKU/week unique',len({(s['sku_id'],s['period']) for s in sales})==len(sales)==15600)
    check('missing is null',all(s['quantity'] is None for s in sales if s['status'] in ('missing','not_started')))
    check('observed nonnegative',all(s['quantity'] is not None and s['quantity']>=0 for s in sales if s['status']=='observed'))
    check('real zeros exist',any(s['status']=='observed' and s['quantity']==0 for s in sales))
    check('returns exist',any(s['return_qty'] and s['return_qty']>0 for s in sales))
    check('stockouts exist',any(s['stockout'] for s in sales))
    check('stock balance',all(x['opening_stock']+x['receipts']+x['resalable_returns']-x['shipments']==x['closing_stock']>=0 for x in ledger))
    check('inventory value',all(x['closing_stock']*x['unit_cost_krw']==x['inventory_value_krw'] for x in ledger))
    receipts=collections.Counter()
    for order in orders:
        check('leadtime:'+order['order_id'],(date.fromisoformat(order['expected_receipt_period'])-date.fromisoformat(order['order_period'])).days==14)
        receipts[order['sku_id'],order['expected_receipt_period']]+=order['qty']
    check('PO receipts reconcile',all(receipts[x['sku_id'],x['period']]==x['receipts'] for x in ledger))
    previous={}
    for x in ledger:
        if x['sku_id'] in previous:check('carry:'+x['sku_id']+x['period'],previous[x['sku_id']]==x['opening_stock'])
        previous[x['sku_id']]=x['closing_stock']
    for part in pieces:
        check('area:'+part['piece_id'],part['area_mm2']>0 and 0<part['relative_area']<1)
        png=(root/part['png_path']).read_bytes();check('PNG dimensions:'+part['piece_id'],png[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',png[16:24])==(256,256))
        svg=ET.parse(root/part['svg_path']).getroot();vb=[float(n) for n in svg.attrib['viewBox'].split()]
        polygon=svg.find('{http://www.w3.org/2000/svg}polygon');pts=[tuple(map(float,v.split(','))) for v in polygon.attrib['points'].split()]
        check('SVG bounds:'+part['piece_id'],len(pts)>=3 and all(0<=x<=vb[2] and 0<=y<=vb[3] for x,y in pts))
    check('no M4 competition test calibration',manifest['M4_test_used_for_generation'] is False and all(r['uses_M4_test'] is False for r in read(root/'forecast/calibration.jsonl')))
    report={'passed':True,'checks':len(checks),'counts':manifest['counts'],'split_counts':manifest['split_product_counts'],'zero_observations':sum(x['quantity']==0 for x in sales),'missing_observations':sum(x['quantity'] is None for x in sales),'stockout_observations':sum(x['stockout'] for x in sales),'claims':'Synthetic software fixtures; not sufficient evidence of enterprise model accuracy.'}
    (root/'validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);validate(p.parse_args().root)
