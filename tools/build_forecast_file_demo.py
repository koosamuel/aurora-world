"""Own synthetic code aliases -> audited weekly input -> same forecasting engine."""
from pathlib import Path
from datetime import date,timedelta
import argparse,copy,json,shutil,tempfile,uuid
from aurora.identity import serialized
from aurora.generation import digest
from aurora.sampling import BriefStore
from aurora.sample_reviews import ReviewStore
from aurora.forecast_files import ForecastFiles
from aurora.identity_weekly import convert

ROOT=Path(__file__).resolve().parents[1]
def example():
 periods=[(date(2024,1,1)+timedelta(weeks=t)).isoformat() for t in range(80)];maps=[];records=[]
 for s in range(6):
  for alias in range(2):
   code=f'{s+1:04d}' if alias==0 else 'A-'+str(s+1);maps.append(dict(mapping_id=f'M-{s}-{alias}',source_system='ERP-SYN',source_scope='SYN-WH',source_code=code,canonical_product_id=f'SIM-SKU-{s+1:03d}',valid_from='2023-01-01',valid_to=None,known_at='2023-01-01',approval_status='approved',approved_by='synthetic-fixture',evidence='자체 합성 별칭 · 기업 승인/매칭 정답 아님'))
   for t,p in enumerate(periods):
    q=(0 if t%7 else 3+s) if s==0 else 5+s+(t%13) if s==1 else 0 if s==2 else 2+(t%4) if s==3 else (t//10)+1 if s==4 else 2+(t%9)
    records.append(dict(row_id=f'ROW-{s}-{alias}-{t}',record_key=f'TX-{code}-{t}',record_type='observed_sales',source_system='ERP-SYN',source_scope='SYN-WH',source_code=code,org_id='SYN-ORG',location_id='SYN-WH',event_date=p,unit='each',quantity=q if alias==0 else t%3))
 identity=dict(schema_version='aurora-product-identity-input-v1',version='alias-shipment-example-v1',data_kind='synthetic',mapping_version='known-before-training-v1',as_of=periods[-1],provenance='자체 합성 거래/승인 메타데이터. 서로 다른 별칭 거래의 합산과 시점/수지 계약 확인용. 실제 기업 거래·매칭 성능 아님.',mappings=maps,records=records)
 return dict(schema_version='aurora-identity-weekly-input-v1',synthetic=True,version='browser-identity-weekly-v1',periods=periods,unit_costs_krw={f'SIM-SKU-{i+1:03d}':1000+100*i for i in range(6)},coverage_assertion='synthetic_complete_weekly_shipments_no_stockouts_or_returns',identity=identity)

def build(root,out):
 if out.exists():raise ValueError('Use a new output directory')
 out.mkdir(parents=True);(out/'artifacts').mkdir();spec=example();weekly,lineage=convert(spec);(out/'identity-input.json').write_bytes(serialized(spec));(out/'weekly-input.json').write_bytes(serialized(weekly))
 with tempfile.TemporaryDirectory() as temp:
  work=Path(temp);reviews=ReviewStore(work,BriefStore(work/'briefs.sqlite'));store=ForecastFiles(work,reviews);token=reviews.session(dict(persona_id='designer'))['token'];raw=serialized(spec);valid=store.validate_file(token,raw);ds=store.register(token,raw,valid['canonical_sha256'],valid['raw_sha256']);job=store.request(token,dict(project_type='forecast',dataset_id=ds['id'],request_key=uuid.uuid4().hex,config=dict(horizon=4,season_length=13,validation_origins=3)));assert store.work_once();row=store.get_dataset_run(ds['id'],job['id']);assert row['status']=='succeeded',row['error']
  result=row['result']
  for meta in result['artifacts']:
   shutil.copy2(store.artifact(job['id'],meta['name']),out/'artifacts'/meta['name']);meta['url']='./demo/forecast-files/artifacts/'+meta['name']
  shutil.copy2(store.artifact(job['id'],'manifest.json'),out/'artifacts/manifest.json');(out/'result.json').write_bytes(serialized(result));(out/'validation.json').write_bytes(serialized(valid))
 metas=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in sorted(out.rglob('*')) if p.is_file()];(out/'manifest.json').write_bytes(serialized(dict(schema_version='aurora-forecast-file-demo-v1',files=metas)))
 print(json.dumps(dict(files=len(metas)+1,source_rows=len(spec['identity']['records']),mappings=len(spec['identity']['mappings']),weekly_rows=len(weekly['series'])*len(weekly['periods']),skus=6,weeks=80,artifacts=5,audit_passed=lineage['audit']['ready_for_downstream'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(ROOT,a.output)
