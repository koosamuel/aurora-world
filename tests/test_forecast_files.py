import copy,json,csv,io,sqlite3,tempfile,unittest,uuid,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from aurora.forecast_files import ForecastFiles,prepare,decode
from aurora.identity_weekly import convert
from aurora.sample_reviews import ReviewStore,Denied
from aurora.sampling import BriefStore,Conflict
from aurora.inputs import run_input,encode
from aurora.generation import digest
from aurora.identity import serialized
from tools.build_forecast_file_demo import example
ROOT=Path(__file__).resolve().parents[1]
class ForecastFileTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.reviews=ReviewStore(self.root,BriefStore(self.root/'briefs.sqlite'));self.store=ForecastFiles(self.root,self.reviews);self.tokens={r:self.reviews.session(dict(persona_id=r))['token'] for r in ('designer','viewer','reviewer','approver')};self.spec=example();self.raw=serialized(self.spec)
 def tearDown(self):self.temp.cleanup()
 def register(self,raw=None):
  raw=raw or self.raw;v=self.store.validate_file(self.tokens['designer'],raw);return self.store.register(self.tokens['designer'],raw,v['canonical_sha256'],v['raw_sha256'])
 def request(self,ds=None,key=None,options=None):
  ds=ds or self.register();req=dict(project_type='forecast',dataset_id=ds['id'],request_key=key or uuid.uuid4().hex,config=options or dict(horizon=4,season_length=13,validation_origins=3));return self.store.request(self.tokens['designer'],req)
 def test_audit_alias_weekly_balance_and_leading_zero(self):
  p,prov=convert(self.spec);self.assertEqual(prov['audit']['counts']['accepted'],960);self.assertEqual(len(prov['weekly_lineage']),480);self.assertEqual(len(p['series']),6);self.assertEqual(self.spec['identity']['mappings'][0]['source_code'],'0001');self.assertTrue(all(r['preserved'] for r in prov['audit']['quantity_audit']))
  original=sum(r['quantity'] for r in self.spec['identity']['records']);self.assertEqual(sum(sum(x['values']) for x in p['series']),original)
 def test_quarantine_or_unused_overlap_blocks_entire_bridge(self):
  for mutate in [lambda s:s['identity']['records'][0].update(source_code='UNKNOWN'),lambda s:s['identity']['mappings'][0].update(approval_status='candidate'),lambda s:s['identity']['records'].append(dict(s['identity']['records'][0],row_id='DIFFERENT')),lambda s:s['identity']['mappings'].append(dict(s['identity']['mappings'][0],mapping_id='OVERLAP',canonical_product_id='OTHER'))]:
   spec=copy.deepcopy(self.spec);mutate(spec)
   with self.assertRaises(ValueError):convert(spec)
 def test_no_future_mapping_leak_even_if_known_at_asof(self):
  spec=copy.deepcopy(self.spec);spec['identity']['mappings'][0]['known_at']=spec['periods'][10]
  with self.assertRaisesRegex(ValueError,'최초 관측 이후'):convert(spec)
 def test_missing_grid_not_zero_but_observed_zero_retained(self):
  s=copy.deepcopy(self.spec)
  s['identity']['records']=[r for r in s['identity']['records'] if not(r['event_date']==s['periods'][0] and r['source_code'] in ('0001','A-1'))]
  with self.assertRaisesRegex(ValueError,'그리드'):convert(s)
  s=copy.deepcopy(self.spec)
  for r in s['identity']['records']:
   if r['event_date']==s['periods'][0] and r['source_code'] in ('0001','A-1'):r['quantity']=0
  p,_=convert(s);self.assertEqual(p['series'][0]['values'][0],0);self.assertEqual(p['series'][0]['statuses'][0],'observed')
 def test_no_stock_bom_mixed_units_or_company(self):
  cases=[lambda s:s['identity']['records'][0].update(record_type='inventory_snapshot'),lambda s:s['identity']['records'][0].update(unit='kg'),lambda s:s['identity']['records'][0].update(org_id='OTHER'),lambda s:s['identity'].update(data_kind='company'),lambda s:s.update(coverage_assertion='assume_missing_is_zero'),lambda s:s['unit_costs_krw'].update(UNKNOWN=1000)]
  for mutate in cases:
   s=copy.deepcopy(self.spec);mutate(s)
   with self.assertRaises(ValueError):convert(s)
 def test_duplicate_json_unknown_fields_size_and_nonfinite(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'[]',b'x'*(4*1024*1024+1)):
   with self.assertRaises(ValueError):decode(raw)
  s=copy.deepcopy(self.spec);s['extra']=1
  with self.assertRaises(ValueError):prepare(serialized(s))
 def test_validate_has_no_dataset_write_and_roles(self):
  self.store.validate_file(self.tokens['designer'],self.raw);self.assertEqual(self.store.datasets(True),[])
  for role in ('viewer','reviewer','approver'):
   with self.assertRaises(Denied):self.store.validate_file(self.tokens[role],self.raw)
  with self.assertRaises(Denied):self.store.validate_file(None,self.raw)
 def test_registration_roundtrip_same_version_and_raw_reuse(self):
  ds=self.register();payload,meta=self.store.read(ds['id']);self.assertEqual(payload,convert(self.spec)[0]);self.assertEqual(meta['raw_sha256'],digest(self.raw));again=self.register();self.assertTrue(again['reused']);pretty=json.dumps(self.spec,ensure_ascii=False,indent=2).encode();reuse=self.register(pretty);self.assertTrue(reuse['reused']);self.assertEqual(reuse['raw_sha256'],digest(self.raw));self.assertEqual(reuse['uploaded_raw_sha256'],digest(pretty))
 def test_different_bytes_same_version_conflict_and_validation_hash(self):
  ds=self.register();s=copy.deepcopy(self.spec);s['identity']['records'][0]['quantity']+=1
  with self.assertRaises(Conflict):self.register(serialized(s))
  v=self.store.validate_file(self.tokens['designer'],self.raw)
  with self.assertRaises(Conflict):self.store.register(self.tokens['designer'],self.raw,'0'*64,v['raw_sha256'])
  with self.assertRaises(Conflict):self.store.register(self.tokens['designer'],self.raw,v['canonical_sha256'],'0'*64)
 def test_plain_weekly_file_missing_returns_preserved(self):
  payload,_=convert(self.spec);payload['version']='plain-v1';r=payload['series'][0];r['values'][0]=None;r['statuses'][0]='missing';r['returns'][0]=None;r['stockouts'][3]=True;ds=self.register(encode(payload));p,m=self.store.read(ds['id']);self.assertEqual(m['provenance']['quality']['missing'],1);self.assertEqual(m['provenance']['quality']['stockouts'],1);self.assertIsNone(p['series'][0]['values'][0])
 def test_registration_failure_rejected_never_executable(self):
  v=self.store.validate_file(self.tokens['designer'],self.raw);base=self.store.inputs/v['canonical_sha256'];base.mkdir();(base/'weekly.json').write_bytes(b'corrupt')
  with self.assertRaises(ValueError):self.store.register(self.tokens['designer'],self.raw,v['canonical_sha256'],v['raw_sha256'])
  self.assertEqual(self.store.datasets(),[]);self.assertEqual(self.store.datasets(True)[0]['status'],'rejected')
 def test_concurrent_registration_is_single_immutable_dataset(self):
  with ThreadPoolExecutor(2) as pool:rs=list(pool.map(lambda _:self.register(),range(2)))
  self.assertEqual(sorted(r['reused'] for r in rs),[False,True]);self.assertEqual(len(self.store.datasets()),1)
 def test_registration_metadata_immutable_and_tampered_input(self):
  ds=self.register()
  with self.store.connect() as db:
   for sql in ('UPDATE file_datasets SET metadata=metadata','DELETE FROM file_datasets'):
    with self.assertRaises(sqlite3.IntegrityError):db.execute(sql)
  (self.store.inputs/ds['sha256']/'source.json').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.store.read(ds['id'])
  with self.assertRaises(ValueError):self.store.read('../outside')
 def test_actual_run_matches_existing_engine_and_file_lineage(self):
  ds=self.register();job=self.request(ds);self.assertTrue(self.store.work_once());row=self.store.get_dataset_run(ds['id'],job['id']);self.assertEqual(row['status'],'succeeded');base=run_input(convert(self.spec)[0],dict(horizon=4,season_length=13,validation_origins=3));r=row['result'];self.assertEqual(r['dataset_checksum'],base['dataset_checksum']);self.assertEqual(r['paired_metrics'],base['paired_metrics']);self.assertEqual(r['decisions'],base['decisions']);self.assertEqual(r['file_registration']['mapping_version'],self.spec['identity']['mapping_version'])
 def test_run_idempotency_cross_dataset_and_project_guard(self):
  ds=self.register();key=uuid.uuid4().hex;a=self.request(ds,key);b=self.request(ds,key);self.assertEqual(a['id'],b['id'])
  with self.assertRaises(Conflict):self.request(ds,key,dict(horizon=3))
  s=copy.deepcopy(self.spec);s['version']='second-v1';other=self.register(serialized(s));self.assertEqual(self.store.list_dataset(other['id']),[]);self.assertIsNone(self.store.get_dataset_run(other['id'],a['id']))
  req=dict(project_type='labeling',dataset_id=ds['id'],request_key=uuid.uuid4().hex,config={})
  with self.assertRaises(ValueError):self.store.request(self.tokens['designer'],req)
  req['project_type']='forecast'
  with self.assertRaises(Denied):self.store.request(self.tokens['viewer'],req)
 def test_cancel_queued_and_running_files_never_exposed(self):
  ds=self.register();job=self.request(ds);r=self.store.cancel_run(self.tokens['designer'],ds['id'],job['id']);self.assertEqual(r['status'],'cancelled');self.assertFalse(self.store.work_once());self.assertIsNone(self.store.artifact(job['id'],'result.json'))
  job=self.request(ds);claimed=self.store.claim();self.store.cancel_run(self.tokens['designer'],ds['id'],job['id']);self.assertFalse(self.store.finish(claimed,{}));self.assertIsNone(self.store.artifact(job['id'],'result.json'))
 def test_attempt_fencing_recovery_and_current_file_hash(self):
  ds=self.register();job=self.request(ds);first=self.store.claim(lease_seconds=-1);second=self.store.claim();self.assertFalse(self.store.finish(first,{}));self.assertTrue(self.store.finish(second,dict(artifacts=[])));self.assertEqual(self.store.get(job['id'],'forecast')['attempt'],2)
 def test_artifact_hashes_csv_balance_tamper_and_traversal(self):
  ds=self.register();job=self.request(ds);self.store.work_once();r=self.store.get(job['id'],'forecast')['result']
  for meta in r['artifacts']:
   raw=self.store.artifact(job['id'],meta['name']).read_bytes();self.assertEqual(digest(raw),meta['sha256']);self.assertEqual(len(raw),meta['bytes'])
  meta=next(m for m in r['artifacts'] if m['name']=='predictions.csv');rows=list(csv.DictReader(io.StringIO(self.store.artifact(job['id'],'predictions.csv').read_text(encoding='utf-8-sig'))));self.assertEqual(len(rows),len(r['predictions']))
  self.store.artifact(job['id'],'manifest.json');self.store.artifact(job['id'],'predictions.csv').write_bytes(b'bad')
  with self.assertRaises(ValueError):self.store.artifact(job['id'],'predictions.csv')
  with self.assertRaises(ValueError):self.store.artifact(job['id'],'../input.json')
 def test_corrupt_input_worker_failure_preserves_dataset(self):
  ds=self.register();job=self.request(ds);(self.store.inputs/ds['sha256']/'weekly.json').write_bytes(b'corrupt');self.store.work_once();self.assertEqual(self.store.get(job['id'],'forecast')['status'],'failed');self.assertIsNone(self.store.artifact(job['id'],'result.json'))
 def test_unsupported_file_config_and_restart(self):
  ds=self.register()
  for config in ({'weeks':30},{'horizon':True},{'season_length':1000}):
   with self.assertRaises(ValueError):self.request(ds,options=config)
  other=ForecastFiles(self.root,self.reviews);self.assertEqual(other.read(ds['id'])[0],convert(self.spec)[0])
 def test_saved_manifest_matches_and_no_company_claims(self):
  root=ROOT/'client/demo/forecast-files'
  for meta in json.loads((root/'manifest.json').read_text())['files']:
   raw=(root/meta['path']).read_bytes();self.assertEqual(digest(raw),meta['sha256']);self.assertEqual(len(raw),meta['bytes'])
  r=json.loads((root/'result.json').read_text());self.assertEqual(r['file_registration']['identity_counts']['accepted'],960);self.assertFalse(r['decisions']['interval_summary']['calibrated'])
if __name__=='__main__':unittest.main()
