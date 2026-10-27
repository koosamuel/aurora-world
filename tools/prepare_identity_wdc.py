"""Inspect official WDC Products archives; derive a MIXED crosswalk contract fixture.

Does not train a matcher. Source labels are reference lookups, not company approvals.
Use: PYTHONPATH=src python tools/prepare_identity_wdc.py --raw RAW_DIR --output NEW_DIR
"""
import argparse
from collections import Counter, defaultdict
import copy
import gzip
import hashlib
import json
from pathlib import Path
import zipfile
from aurora.identity import export, serialized

ARCHIVES={'80multi.zip':'5385e2491e82c7f6c208d8eac7ec777a4a44180769f3a339c99803ff2b068981','80pair.zip':'b2044939cee5ea6f12148a2f3551508de3cb77660dfc91767c44daaf9d8a9c4a'}
SOURCE='https://webdatacommons.org/largescaleproductcorpus/wdc-products/index.html'


def read_archive(path, expected_hash):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:raise ValueError(f'{path.name}: source hash mismatch')
    result={};inventory=[]
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or '/' in info.filename or not info.filename.endswith('.json.gz') or info.file_size>64*1024*1024:raise ValueError('unexpected ZIP member')
            compressed=archive.read(info)
            import io
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                raw=stream.read(64*1024*1024+1)
            if len(raw)>64*1024*1024:raise ValueError('gzip content too large')
            rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
            if not rows:raise ValueError('empty split')
            result[info.filename]=rows
            inventory.append(dict(member=info.filename,rows=len(rows),sha256=hashlib.sha256(compressed).hexdigest(),positive=sum(r['label']==1 for r in rows) if 'id_left' in rows[0] else None))
    if len(result)!=9:raise ValueError('expected nine benchmark splits per archive')
    return result,inventory


def prepare(raw_dir, output):
    raw_dir=Path(raw_dir);out=Path(output)
    if out.exists():raise FileExistsError(out)
    multi,mi=read_archive(raw_dir/'80multi.zip',ARCHIVES['80multi.zip'])
    pair,pi=read_archive(raw_dir/'80pair.zip',ARCHIVES['80pair.zip'])
    prefix='wdcproductsmulti80cc20rnd000un_';checks=[]
    for size in ('small','medium','large'):
        subsets=[multi[prefix+f'train_{size}.json.gz'],multi[prefix+f'valid_{size}.json.gz'],multi[prefix+'gs.json.gz']]
        ids=[{r['id'] for r in rows} for rows in subsets]
        overlaps=[len(ids[a]&ids[b]) for a,b in ((0,1),(0,2),(1,2))]
        checks.append(dict(size=size,train_valid_overlap=overlaps[0],train_test_overlap=overlaps[1],valid_test_overlap=overlaps[2]))
    # Only train_small is consumed for this fixture; validation/test are never used to construct mappings.
    member=prefix+'train_small.json.gz';rows=sorted(multi[member],key=lambda r:r['id'])
    if len(rows)!=1000 or len({r['id'] for r in rows})!=len(rows):raise ValueError('unexpected source offer IDs')
    maps=[];records=[]
    for index,r in enumerate(rows):
        code=str(r['id']);canonical='WDC-'+str(r['cluster_id'])
        if r['label']!=r['cluster_id']:raise ValueError('multi-class label mismatch')
        maps.append(dict(mapping_id=f'wdc-map-{index}',source_system='WDC2020',source_scope='BENCHMARK-OFFERS',source_code=code,canonical_product_id=canonical,valid_from='2026-01-01',valid_to=None,known_at='2026-01-01',approval_status='approved',approved_by='benchmark-reference-only',evidence=f'80multi.zip::{member} offer id={code}; benchmark label, NOT company approval'))
        records.append(dict(row_id=f'synthetic-sale-{index}',record_key=f'synthetic-transaction-{index}',record_type='observed_sales',source_system='WDC2020',source_scope='BENCHMARK-OFFERS',source_code=code,org_id='SYNTHETIC-ORG',location_id='SYNTHETIC-WH',event_date='2026-09-07',unit='each',quantity=index%17+1))
    payload=dict(schema_version='aurora-product-identity-input-v1',version='wdc80-train-small-mixed-v1',data_kind='mixed',mapping_version='wdc80-reference-v1',as_of='2026-09-30',provenance=f'{SOURCE} | Public offer IDs/cluster labels from 80multi.zip train_small only. ALL transaction rows, quantities, organisation/location, effective dates, known_at and approval metadata are SYNTHETIC test assumptions. Reference labels are supplied to exercise joins, NOT learned or scored as matcher predictions.',mappings=maps,records=records)
    conflict=copy.deepcopy(payload);conflict['version']='wdc80-train-small-injected-errors-v1'
    conflict['mappings'].pop(0)
    collision=copy.deepcopy(conflict['mappings'][0]);collision.update(mapping_id='injected-collision',canonical_product_id='INJECTED-WRONG-ID');conflict['mappings'].append(collision)
    conflict['mappings'][1].update(approval_status='candidate',approved_by=None)
    conflict['mappings'][2]['known_at']='2026-10-01'
    by_product=defaultdict(list)
    for m in maps[4:]:by_product[m['canonical_product_id']].append(m)
    aliases=next(ms[:2] for ms in by_product.values() if len(ms)>1)
    for index,m in enumerate(aliases):
        row=copy.deepcopy(records[4]);row.update(row_id=f'injected-stock-{index}',record_key=f'injected-stock-{index}',record_type='inventory_snapshot',source_code=m['source_code'],quantity=42);conflict['records'].append(row)
    for index in range(2):
        row=copy.deepcopy(records[4]);row.update(row_id=f'injected-duplicate-{index}',record_key='injected-duplicate-business-key');conflict['records'].append(row)
    out.mkdir(parents=True)
    (out/'identity-input.json').write_bytes(serialized(payload))
    (out/'identity-injected-errors.json').write_bytes(serialized(conflict))
    valid=export(payload,out/'valid-audit');bad=export(conflict,out/'injected-errors-audit')
    summary=dict(source=SOURCE,data_kind='mixed',archive_sha256=ARCHIVES,inventory=dict(multi=mi,pair=pi),split_checks=checks,benchmark_evaluation_ready=not any(c[k] for c in checks for k in ('train_valid_overlap','train_test_overlap','valid_test_overlap')),selected_member=member,selected_offers=len(rows),selected_products=len({r['cluster_id'] for r in rows}),valid_counts=valid['counts'],injected_counts=bad['counts'],injected_reasons=bad['quarantine_reasons'],all_quantities_preserved=all(g['preserved'] for a in (valid,bad) for g in a['quantity_audit']),matcher_trained=False,matcher_score=None,license_status='Official free public download; data-specific redistribution license not explicitly established. Raw records and derived IDs remain local, not included in the public code repository.')
    (out/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--raw',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=prepare(args.raw,args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('inventory',)},ensure_ascii=False,indent=2))
