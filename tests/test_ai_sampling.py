import copy, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
from aurora.ai_sampling import AIService, SETTINGS, public_catalog
from aurora.ai_worker import condition_plan, make_prompt, verify_models, generate
from aurora.generation import catalog, digest
from aurora.sampling import BriefStore, seed, Conflict

ROOT=Path(__file__).resolve().parents[1]

class AISamplingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  (self.root/'configs/ai').mkdir(parents=True)
  (self.root/'configs/ai/model-manifest.json').write_bytes((ROOT/'configs/ai/model-manifest.json').read_bytes())
  self.briefs=BriefStore(self.root/'briefs.sqlite');seed(self.briefs,ROOT)
  self.service=AIService(self.root,self.briefs)
  s=self.service.catalog()['sources'][0]
  self.req=dict(source_id=s['id'],source_checksum=s['checksum'],seed=42,request_key='ai-test-key-123')
 def tearDown(self):self.tmp.cleanup()
 def configured(self):
  (self.root/'.ai-local.json').write_text(json.dumps(dict(python=sys.executable,sd15=str(self.root),clip=str(self.root))))
 def test_optional_runtime_missing_does_not_break_base_catalog(self):
  self.assertFalse(self.service.catalog()['runtime_available'])
  self.assertTrue(all(s['data_kind']=='synthetic' for s in self.service.catalog()['sources']))
  with self.assertRaises(ValueError):self.service.request(self.req)
 def test_queue_replay_conflict_capacity_and_restart(self):
  self.configured();row,new=self.service.request(self.req);self.assertTrue(new)
  replay,new=self.service.request(self.req);self.assertFalse(new);self.assertEqual(row['id'],replay['id'])
  with self.assertRaises(Conflict):self.service.request(dict(self.req,seed=43))
  with self.assertRaises(ValueError):self.service.request(dict(self.req,request_key='another-ai-key'))
  restart=AIService(self.root,self.briefs);self.assertEqual(restart.get(row['id'])['state'],'failed')
  self.assertIsNone(restart.artifact(row['id'],'input.png'))
 def test_unknown_stale_and_unbounded_requests_rejected(self):
  self.configured()
  for req in [dict(self.req,source_id='abo:test'),dict(self.req,source_checksum='0'*64),dict(self.req,seed=True),dict(self.req,prompt='injected')]:
   with self.assertRaises(ValueError):self.service.request(req)
 def test_worker_timeout_is_failure_no_partial_download(self):
  self.configured();row,_=self.service.request(self.req)
  with patch('aurora.ai_sampling.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',600)) as run:
   self.assertTrue(self.service.work(row['id']));args,kw=run.call_args
   self.assertIsInstance(args[0],list);self.assertNotIn('shell',kw);self.assertEqual(kw['timeout'],600)
   self.assertEqual(kw['env']['HF_HUB_OFFLINE'],'1')
  r=self.service.get(row['id']);self.assertEqual(r['state'],'failed');self.assertNotIn(sys.executable,r['error']);self.assertIsNone(self.service.artifact(row['id'],'report.json'))
 def test_model_corruption_rejected_before_import_or_inference(self):
  p=self.root/'small.safetensors';p.write_bytes(b'fixture')
  m=[dict(key='clip',files=[dict(path=p.name,bytes=7,sha256=digest(b'fixture'))])]
  (self.root/'configs/ai/model-manifest.json').write_text(json.dumps(m))
  verify_models(self.root,dict(clip=str(self.root)))
  p.write_bytes(b'corrupt')
  with self.assertRaises(ValueError):verify_models(self.root,dict(clip=str(self.root)))
 def test_only_supported_condition_hints_and_ambiguous_class_fallback(self):
  b=copy.deepcopy(self.service.catalog()['sources'][0]['brief'])
  b['requirements']['must_have']=['부드러운 둥근 외형','실제 봉제 안전 인증']
  c=condition_plan(b);self.assertEqual(c[1]['prompt_terms'],[]);self.assertTrue(all(x['satisfied'] is None for x in c))
  a=dict(ambiguous=True,hypothesis='rabbit',color=dict(name='cream'))
  p=make_prompt(a,c);self.assertNotIn('rabbit',p);self.assertIn('rounded silhouette',p)
  a['ambiguous']=False;self.assertIn('rabbit plush',make_prompt(a,c))
 def test_worker_rejects_corrupted_or_company_source_without_ai_imports(self):
  s=copy.deepcopy(self.service.catalog()['sources'][0]);s['source']['company_data']=True
  with self.assertRaises(ValueError):generate(self.root,s,42,self.root/'bad')
  self.assertFalse((self.root/'bad').exists())
 def test_saved_real_inference_assets_and_failures_are_explicit(self):
  base=ROOT/'client/demo/ai-sampling';c=json.loads((base/'catalog.json').read_text())
  self.assertEqual(len(c['sources']),6);success=0
  for s in c['sources']:
   p=base/c['demo_runs'][s['id']];r=json.loads((p/'run.json').read_text())
   self.assertEqual(r['source']['checksum'],s['checksum'])
   if r['state']=='failed':
    self.assertIsNone(r['result']);self.assertEqual({f.name for f in p.iterdir()},{'run.json'});continue
   success+=1;report=r['result']['report']
   self.assertTrue(report['learned_model']);self.assertFalse(report['dimensions_verified']);self.assertFalse(report['design_approved'])
   self.assertEqual(report['settings'],SETTINGS);self.assertEqual(len(report['candidates']),2)
   self.assertEqual(len(report['input_analysis']['ranked']),7)
   for a in r['result']['artifacts']:
    raw=(p/a['file']).read_bytes();self.assertEqual(digest(raw),a['sha256']);self.assertEqual(len(raw),a['bytes'])
    if a['file'].endswith('.png'):self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
  self.assertGreaterEqual(success,1)
