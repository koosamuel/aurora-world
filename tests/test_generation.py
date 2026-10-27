import copy,json,struct,tempfile,unittest,concurrent.futures
from pathlib import Path
from aurora.generation import catalog,generate,abo_fit,parse_glb,glb_parts,bounds,procedural,make_glb,GenerationService,decode_request,digest,serialized
from aurora.sampling import BriefStore,seed,Conflict
ROOT=Path(__file__).resolve().parents[1]
class GenerationTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.sources=catalog(ROOT)['sources']
 def tearDown(self):self.temp.cleanup()
 def test_all_families_generate_real_meshes_and_bounded_outputs(self):
  for source in self.sources:
   r=generate(source,42,self.base/source['id'].replace(':','-'))
   self.assertTrue(r['report']['sample_generated']);self.assertFalse(r['report']['learned_model']);self.assertFalse(r['report']['design_approved']);self.assertFalse(r['report']['effect_measured'])
   self.assertLess(r['report']['candidates'][1]['max_dimension_error_mm'],.01)
   self.assertGreater(r['report']['candidates'][1]['triangles'],r['report']['candidates'][0]['triangles'])
   for meta in r['artifacts']:
    p=self.base/source['id'].replace(':','-')/meta['file'];self.assertEqual(p.stat().st_size,meta['bytes']);self.assertEqual(digest(p.read_bytes()),meta['sha256'])
 def test_seed_reproducibility_and_source_revision(self):
  s=self.sources[0];p=procedural(s,42,True);self.assertEqual(make_glb(p),make_glb(procedural(s,42,True)));self.assertNotEqual(make_glb(p),make_glb(procedural(s,43,True)))
  self.assertNotEqual(self.sources[0]['checksum'],self.sources[1]['checksum'])
 def test_no_overwrite_or_bad_seed(self):
  dest=self.base/'out';generate(self.sources[0],1,dest)
  with self.assertRaises(FileExistsError):generate(self.sources[0],1,dest)
  for v in [True,-1,1.2,2147483648]:
   with self.assertRaises(ValueError):generate(self.sources[0],v,self.base/'bad')
 def service(self):
  store=BriefStore(self.base/'brief.sqlite');seed(store,ROOT);return GenerationService(self.base,store),store
 def test_queue_idempotency_conflict_persistence_and_corruption(self):
  service,store=self.service();req=dict(source_id=self.sources[0]['id'],source_checksum=self.sources[0]['checksum'],seed=42,request_key='same-key-123')
  # Service root contains the same source module version but takes registered immutable briefs.
  a,new=service.request(req);self.assertTrue(new);b,new=service.request(req);self.assertFalse(new);self.assertEqual(a['id'],b['id'])
  bad=dict(req,seed=43)
  with self.assertRaises(Conflict):service.request(bad)
  self.assertTrue(service.work(a['id']));self.assertFalse(service.work(a['id']));done=service.get(a['id']);self.assertEqual(done['state'],'succeeded')
  p=service.artifact(a['id'],'candidate.glb');self.assertTrue(p.exists());self.assertIsNone(service.artifact(a['id'],'../input.json'));p.write_bytes(b'bad')
  with self.assertRaises(ValueError):service.artifact(a['id'],'candidate.glb')
  restarted=GenerationService(self.base,store);self.assertEqual(restarted.get(a['id'])['state'],'succeeded')
 def test_same_key_concurrent_requests_only_one(self):
  service,_=self.service();req=dict(source_id=self.sources[0]['id'],source_checksum=self.sources[0]['checksum'],seed=42,request_key='concurrent-key')
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda _:service.request(req),range(4)))
  self.assertEqual(len({r[0]['id'] for r in rows}),1);self.assertEqual(sum(r[1] for r in rows),1)
 def test_unknown_stale_and_restart_failed(self):
  service,store=self.service();req=dict(source_id=self.sources[0]['id'],source_checksum='0'*64,seed=42,request_key='stale-key-123')
  with self.assertRaises(ValueError):service.request(req)
  req['source_id']='http://remote/file'
  with self.assertRaises(ValueError):service.request(req)
  req.update(source_id=self.sources[0]['id'],source_checksum=self.sources[0]['checksum']);row,_=service.request(req);restarted=GenerationService(self.base,store);self.assertEqual(restarted.get(row['id'])['state'],'failed')
  with self.assertRaises(ValueError):service.get('../escape')
 def test_request_fields_duplicates_and_limits(self):
  for raw in [b'{"source_id":"a","source_id":"b"}',b'[]',b'{"seed": NaN}',b'x'*16385]:
   with self.assertRaises(ValueError):decode_request(raw)
 def test_transformed_glb_bounds_and_malformed(self):
  g,b=parse_glb(make_glb(procedural(self.sources[0],42,True)));g['nodes'].append(dict(children=g['scenes'][0]['nodes'],scale=[2,3,4],translation=[1,2,3]));g['scenes'][0]['nodes']=[len(g['nodes'])-1];lo,hi=bounds(glb_parts(g,b));self.assertAlmostEqual(hi[1]-lo[1],self.sources[0]['dimensions_mm']['height']/1000*3,6)
  g['nodes'][-1]['children']=[len(g['nodes'])-1]
  with self.assertRaises(ValueError):glb_parts(g,b)
  for raw in [b'fake',struct.pack('<4sII',b'glTF',1,12)]:
   with self.assertRaises(ValueError):parse_glb(raw)
 def test_saved_demo_assets_hashes_provenance_and_no_external_resources(self):
  c=json.loads((ROOT/'client/demo/generation/catalog.json').read_text());self.assertEqual(len(c['sources']),9)
  for s in c['sources']:
   p=ROOT/'client/demo/generation'/c['demo_runs'][s['id']];r=json.loads((p/'run.json').read_text());self.assertEqual(r['source']['checksum'],s['checksum']);self.assertFalse(r['result']['report']['design_approved'])
   for meta in r['result']['artifacts']:
    raw=(p/meta['file']).read_bytes();self.assertEqual(digest(raw),meta['sha256'])
    if meta['file'].endswith('.glb'):parse_glb(raw)
   if s['data_kind']=='mixed':self.assertEqual(r['result']['report']['source']['license'],'CC BY 4.0');self.assertEqual(r['result']['report']['candidates'][1]['method'],'abo-fit-v1')

 def test_public_adapter_retains_source_and_rejects_corruption(self):
  raw=make_glb(procedural(self.sources[0],1,True));p=self.base/'reference.glb';p.write_bytes(raw);source=dict(dimensions_mm=dict(width=400,height=300,depth=100),source=dict(model_path=p.name,sha256=digest(raw)))
  fitted,parts=abo_fit(source,self.base);self.assertEqual(p.read_bytes(),raw);g,b=parse_glb(fitted);lo,hi=bounds(glb_parts(g,b));self.assertAlmostEqual((hi[1]-lo[1])*1000,300,5);self.assertIn('CC BY 4.0',g['asset']['extras']['attribution'])
  p.write_bytes(raw+b'bad')
  with self.assertRaises(ValueError):abo_fit(source,self.base)
  source['source']['model_path']='../outside.glb'
  with self.assertRaises(ValueError):abo_fit(source,self.base)
