import copy,json,tempfile,unittest,uuid
from pathlib import Path
from aurora.public_service import canonical,decode,read_public,provision_public,compute_public_job,public_summary
from aurora.public_jobs import PublicStore
from aurora.registered import RemoteError
from test_public_retail import fixture

PROJECT='10000000-0000-4000-8000-000000000001';RUN='40000000-0000-4000-8000-000000000001'
class RemoteDouble:
 def __init__(self):self.dataset=None;self.objects={};self.corrupt=False
 def request(self,path,method='GET',body=None,data=None,raw=False,**kw):
  if path.startswith('/rest/v1/projects'):return [dict(id=PROJECT,project_type='forecast')]
  if path.startswith('/rest/v1/runs'):return [dict(project_id=PROJECT)]
  if path.startswith('/rest/v1/datasets'):
   if method=='GET':return [self.dataset] if self.dataset else []
   if method=='POST':self.dataset=body.copy();return None
   if method=='PATCH':self.dataset.update(body);return None
  if path.startswith('/storage/v1/object/'):
   p=path.split('/storage/v1/object/')[1].removeprefix('authenticated/')
   if method=='POST':
    if p in self.objects:raise RemoteError(409)
    self.objects[p]=data;return {}
   return self.objects[p]+(b'x' if self.corrupt else b'')
  raise AssertionError(path)

class PublicServiceTests(unittest.TestCase):
 def test_registration_private_read_idempotency_and_hash_guard(self):
  remote=RemoteDouble();p=fixture();a=provision_public(remote,p,PROJECT);b=provision_public(remote,p,PROJECT)
  self.assertEqual(a['dataset_id'],b['dataset_id']);self.assertTrue(b['reused']);self.assertFalse(remote.dataset['synthetic'])
  c=remote.dataset['generator_config'];self.assertEqual(read_public(remote,c,PROJECT),p)
  with self.assertRaises(ValueError):read_public(remote,c,'10000000-0000-4000-8000-000000000002')
  remote.corrupt=True
  with self.assertRaises(ValueError):read_public(remote,c,PROJECT)
 def test_same_version_different_input_cannot_overwrite(self):
  remote=RemoteDouble();p=fixture();provision_public(remote,p,PROJECT);q=copy.deepcopy(p);q['series'][0]['values'][10]=999
  with self.assertRaises(ValueError):provision_public(remote,q,PROJECT)
  self.assertEqual(remote.dataset['status'],'ready')
 def test_cloud_calculates_and_uploads_five_attempt_scoped_artifacts(self):
  remote=RemoteDouble();p=fixture();provision_public(remote,p,PROJECT)
  job=dict(id=RUN,attempt=2,config={'policy_inputs':{}},generator_config=remote.dataset['generator_config'])
  r=compute_public_job(remote,job);self.assertEqual(len(r['artifacts']),5)
  self.assertNotIn('inventory_details',r['summary']);self.assertNotIn('predictions',r['summary']);self.assertFalse(r['summary']['synthetic'])
  for a in r['artifacts']:
   self.assertIn(f'{PROJECT}/runs/{RUN}/attempt-2/',a['path'])
   self.assertEqual(a['bytes'],len(remote.objects['aurora-artifacts/'+a['path']]))
  self.assertEqual(r,compute_public_job(remote,job)) # immutable retry objects verified
 def test_local_request_and_report_download_share_result_and_no_path_traversal(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'input.json').write_bytes(canonical(fixture()));store=PublicStore(root/'jobs.sqlite3',root/'input.json')
   a=store.request('forecast','same',{});self.assertEqual(a['id'],store.request('forecast','same',{})['id'])
   with self.assertRaises(ValueError):store.request('forecast','same',{'policy_inputs':{'UCI-12345':{'initial_stock':3}}})
   self.assertIsNone(store.artifact(a['id'],'report.md'));self.assertTrue(store.work_once())
   run=store.get(a['id'],'forecast');self.assertEqual(run['status'],'succeeded');self.assertEqual(len(run['result']['artifacts']),5)
   self.assertTrue(store.artifact(a['id'],'report.md').is_file());self.assertIsNone(store.artifact(a['id'],'../../jobs.sqlite3'))
   self.assertLess(len(json.dumps(run['result'])),1048576)
 def test_malformed_public_input_rejected(self):
  with self.assertRaises(ValueError):decode(b'{"x":1,"x":2}')
  p=fixture();p['synthetic']=True
  with self.assertRaises(ValueError):canonical(p)
