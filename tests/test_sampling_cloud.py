import copy,json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from aurora.sampling_cloud import SamplingWorker,source_for,provision,mime
from aurora.sampling import decode,envelope
from aurora.identity import serialized
from aurora.generation import digest,parse_glb
ROOT=Path(__file__).resolve().parents[1]
class FakeRemote:
 def __init__(self):self.objects={};self.calls=[];self.job=None;self.completed=None;self.rows=[]
 def request(self,path,method='GET',body=None,data=None,raw=False,**kwargs):
  self.calls.append((path,method,body))
  if path.endswith('/sampling_worker_beat'):return True
  if path.endswith('/claim_sampling'):return self.job
  if path.endswith('/complete_sampling'):self.completed=body;return True
  if '/sampling_briefs?' in path:return self.rows
  if path=='/rest/v1/sampling_briefs':return None
  if '/storage/v1/object/' in path:
   name=path.replace('/storage/v1/object/authenticated/','').replace('/storage/v1/object/','')
   if method=='POST':self.objects[name]=data;return None
   return self.objects[name]
  raise AssertionError(path)
class SamplingCloudTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'configs').symlink_to(ROOT/'configs',target_is_directory=True);self.remote=FakeRemote();self.worker=SamplingWorker(self.root,self.remote);self.brief=decode(next((ROOT/'configs/examples/sampling').glob('*v1.json')).read_bytes());self.source=source_for(self.root,self.brief)
 def tearDown(self):self.tmp.cleanup()
 def job(self,kind='geometry'):
  return dict(id=str(uuid.uuid4()),project_id='10000000-0000-4000-8000-000000000002',kind=kind,attempt=1,claim_token=str(uuid.uuid4()),payload=dict(source=self.source,seed=74))
 def test_source_uses_original_validators_and_checksum(self):
  self.assertEqual(self.source['brief_checksum'],envelope(self.brief)['checksum']);bad=copy.deepcopy(self.brief);bad['data_kind']='company'
  with self.assertRaises(ValueError):source_for(self.root,bad)
 def test_validation_duplicate_json_unknown_fields_and_script(self):
  job=self.job('validate_brief');job['payload']={'raw_brief':serialized(self.brief).decode()};r,files=self.worker.compute(job);self.assertEqual(r['envelope']['brief'],self.brief);self.assertEqual(files,[])
  for raw in ['{"a":1,"a":2}',serialized(dict(self.brief,unknown=True)).decode(),'{"x":NaN}']:
   job['payload']['raw_brief']=raw
   with self.assertRaises(ValueError):self.worker.compute(job)
 def test_geometry_new_seed_files_and_private_roundtrip(self):
  job=self.job();r,files=self.worker.compute(job);self.assertEqual(r['report']['seed'],74);self.assertEqual(len(files),10);self.assertFalse(r['report']['design_approved']);self.assertFalse(r['report']['learned_model'])
  for f in files:
   self.assertTrue(f['path'].startswith(job['project_id']+'/sampling/'+job['id']+'/attempt-1/'));raw=self.remote.objects[f['bucket']+'/'+f['path']];self.assertEqual(len(raw),f['bytes']);self.assertEqual(digest(raw),f['sha256'])
   if f['name'].endswith('.glb'):parse_glb(raw)
 def test_wrong_source_hash_company_and_kind_rejected(self):
  for mutate in [lambda j:j['payload']['source'].update(checksum='0'*64),lambda j:j['payload']['source']['brief'].update(data_kind='company'),lambda j:j.update(kind='forecast')]:
   job=copy.deepcopy(self.job());mutate(job)
   with self.assertRaises(ValueError):self.worker.compute(job)
 def test_post_upload_corruption_never_completes(self):
  original=self.remote.request
  def corrupt(path,*args,**kwargs):return b'corrupt' if '/authenticated/' in path else original(path,*args,**kwargs)
  self.remote.request=corrupt;self.remote.job=self.job();self.assertTrue(self.worker.once());self.assertIsNotNone(self.remote.completed['p_error']);self.assertIsNone(self.remote.completed['p_result'])
 def test_validation_failure_becomes_failed_job(self):
  self.remote.job=self.job('validate_brief');self.remote.job['payload']={'raw_brief':'{}'};self.worker.once();self.assertIsNotNone(self.remote.completed['p_error'])
 def test_worker_no_job_beat_and_success_publish(self):
  self.assertFalse(self.worker.once());self.assertTrue(any(c[0].endswith('sampling_worker_beat') for c in self.remote.calls));self.remote.job=self.job();self.worker.once();self.assertIsNone(self.remote.completed['p_error']);self.assertEqual(len(self.remote.completed['p_artifacts']),10)
 def test_retry_attempt_path_immutable_and_invalid_attempt(self):
  job=self.job();self.worker.compute(job);job['attempt']=2;_,files=self.worker.compute(job);self.assertTrue(all('/attempt-2/' in f['path'] for f in files));job['attempt']=0
  with self.assertRaises(ValueError):self.worker.compute(job)
 def test_provision_12_originals_no_wrong_project(self):
  rows=provision(self.remote,ROOT);self.assertEqual(len(rows),12)
  with self.assertRaises(ValueError):provision(self.remote,ROOT,'10000000-0000-4000-8000-000000000001')
 def test_ai_absent_and_mime_contract(self):
  self.assertFalse(self.worker.ai_available());self.assertEqual(mime('candidate.glb'),'model/gltf-binary');self.assertEqual(mime('input.png'),'image/png')
if __name__=='__main__':unittest.main()
