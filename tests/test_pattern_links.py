import copy,json,shutil,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from aurora.pattern_links import PatternLinks,audit,impact
from aurora.sample_reviews import ReviewStore,Denied
from aurora.sampling import BriefStore,seed,checksum,Conflict
from aurora.generation import digest
from aurora.identity import serialized

ROOT=Path(__file__).resolve().parents[1]
class PatternLinkTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'client').symlink_to(ROOT/'client',target_is_directory=True)
  self.briefs=BriefStore(self.root/'briefs.sqlite');seed(self.briefs,ROOT);self.reviews=ReviewStore(self.root,self.briefs)
  self.tokens={k:self.reviews.session(dict(persona_id=k))['token'] for k in ('designer','reviewer','approver','viewer')}
  self.library=self.root/'library';shutil.copytree(ROOT/'client/demo/pattern-links',self.library);self.store=PatternLinks(self.root,self.reviews,self.library)
  self.candidates=[c for c in self.reviews.catalog()['candidates'] if c['product_id']=='SYN-BUNNY' and c['kind']=='ai'];self.revision();self.act('submit');self.act('review');self.act('approve')
 def tearDown(self):self.temp.cleanup()
 def revision(self,index=0):
  c=self.candidates[index];r=self.reviews.get('SYN-BUNNY')
  return self.reviews.revision(self.tokens['designer'],dict(candidate_id=c['id'],candidate_checksum=c['checksum'],parent_version=r['head_version'] if r else None,expected_seq=r['seq'] if r else 0,change_reason='합성 수정본',request_key=uuid.uuid4().hex))
 def act(self,action,role=None):
  r=self.reviews.get('SYN-BUNNY');rev=r['revisions'][-1]
  return self.reviews.event(self.tokens[role or {'submit':'designer','review':'reviewer','approve':'approver','hold':'approver','comment':'reviewer'}[action]],dict(product_id='SYN-BUNNY',version=r['head_version'],expected_seq=r['seq'],action=action,comment='합성 검토',checks=[dict(id=c['id'],status='pass',note='합성') for c in rev['checklist']] if action=='review' else [],request_key=uuid.uuid4().hex))
 def req(self):
  r=self.store.get('SYN-BUNNY');a=r['current_approval'];b=self.store.bundle('SYN-BUNNY',r['latest_bundle_version'])
  return dict(product_id='SYN-BUNNY',bundle_version=r['latest_bundle_version'],bundle_sha256=b['sha256'],sample_revision_sha256=a['revision_sha256'],approval_event_sha256=a['approval_event_sha256'],expected_review_seq=a['review_seq'],parent_version=r['head_version'],reason='합성 수동 연결',request_key=uuid.uuid4().hex)
 def link(self,req=None):return self.store.link(self.tokens['designer'],req or self.req())
 def save_bundle(self,b):
  raw=serialized(b);(self.library/'bundles'/f'SYN-BUNNY-v{b["version"]}.json').write_bytes(raw)
  cat=json.loads((self.library/'library.json').read_text())
  for m in cat['bundles']:
   if m['product_id']=='SYN-BUNNY' and m['version']==b['version']:m.update(sha256=digest(raw),bytes=len(raw))
  (self.library/'library.json').write_bytes(serialized(cat))
 def test_bound_link_export_and_restart(self):
  r=self.link();l=r['links'][0];self.assertTrue(l['current_valid']);self.assertEqual(l['sample_revision_sha256'],r['current_approval']['revision_sha256']);self.assertEqual(l['approval_event_sha256'],r['current_approval']['approval_event_sha256']);self.assertEqual(l['audit']['piece_count'],12)
  self.assertTrue(self.store.export('SYN-BUNNY')['asset_hashes_verified'])
  self.assertEqual(PatternLinks(self.root,self.reviews,self.library).get('SYN-BUNNY')['links'],r['links'])
 def test_roles_and_missing_session(self):
  for token in (None,*[self.tokens[r] for r in ('viewer','reviewer','approver')]):
   with self.assertRaises(Denied):self.store.link(token,self.req())
 def test_pending_product_cannot_link(self):
  req=self.req();req['product_id']='SYN-CAT'
  with self.assertRaises(Conflict):self.link(req)
 def test_revision_invalidates_link_and_no_inherited_approval(self):
  self.link();self.revision(1);r=self.store.get('SYN-BUNNY');self.assertIsNone(r['current_approval']);self.assertFalse(r['links'][0]['current_valid'])
  self.assertIn('approval_changed_or_inactive',r['links'][0]['invalid_reasons'])
 def test_revocation_replay_never_resurrects_link(self):
  req=self.req();self.link(req);self.act('hold');r=self.link(req);self.assertTrue(r['replayed']);self.assertFalse(r['links'][0]['current_valid'])
 def test_reapproval_requires_new_link_to_new_approval(self):
  self.link();self.act('hold');self.act('submit');self.act('review');self.act('approve');r=self.link();self.assertEqual(r['head_version'],2);self.assertFalse(r['links'][0]['current_valid']);self.assertTrue(r['links'][1]['current_valid']);self.assertNotEqual(r['links'][0]['approval_event_sha256'],r['links'][1]['approval_event_sha256'])
 def test_brief_change_invalidates_link(self):
  self.link();b=copy.deepcopy(self.reviews.latest_brief('SYN-BUNNY')['brief']);b.update(brief_version=b['brief_version']+1,previous_checksum=checksum(b));b['product_name']+=' 수정';self.briefs.register(b);self.assertFalse(self.store.get('SYN-BUNNY')['links'][0]['current_valid'])
 def test_review_seq_compare_and_swap(self):
  req=self.req();self.act('comment')
  with self.assertRaises(Conflict):self.link(req)
 def test_stale_parent_wrong_hash_and_old_bundle(self):
  for change in (dict(parent_version=3),dict(bundle_sha256='0'*64),dict(sample_revision_sha256='0'*64),dict(approval_event_sha256='0'*64),dict(bundle_version=1)):
   req=self.req();req.update(change)
   with self.assertRaises(Conflict):self.link(req)
 def test_idempotency_duplicate_and_changed_key(self):
  req=self.req();self.link(req);self.assertTrue(self.link(req)['replayed'])
  with self.assertRaises(Conflict):self.link()
  req['reason']='changed'
  with self.assertRaises(Conflict):self.link(req)
 def test_concurrent_same_key(self):
  req=self.req()
  with ThreadPoolExecutor(2) as pool:rows=list(pool.map(lambda _:self.link(req),range(2)))
  self.assertEqual(sorted(r['replayed'] for r in rows),[False,True]);self.assertEqual(self.store.get('SYN-BUNNY')['head_version'],1)
 def test_concurrent_different_keys(self):
  a,b=self.req(),self.req()
  def run(req):
   try:self.link(req);return 'ok'
   except Conflict:return 'conflict'
  with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(run,[a,b])),['conflict','ok'])
 def test_immutable_sql_and_chain_corruption(self):
  self.link()
  with self.store.db() as db:
   for sql in ('UPDATE pattern_links SET sha256=sha256','DELETE FROM pattern_links'):
    with self.assertRaises(sqlite3.IntegrityError):db.execute(sql)
   db.execute('DROP TRIGGER link_no_update');db.execute("UPDATE pattern_links SET sha256=?",('0'*64,))
  with self.assertRaises(ValueError):self.store.get('SYN-BUNNY')
 def test_asset_tamper_and_traversal(self):
  r=self.link();p=r['links'][0]['bundle']['pieces'][0];(self.store.assets/p['asset']).write_bytes(b'bad')
  with self.assertRaises(ValueError):self.store.export('SYN-BUNNY')
  with self.assertRaises(ValueError):self.store.asset('../library.json')
 def test_library_tamper_blocks_new_link(self):
  p=self.library/'bundles/SYN-BUNNY-v2.json';p.write_text(p.read_text()+' ')
  with self.assertRaises(ValueError):self.store.catalog()
 def test_missing_duplicate_units_versions_and_balances(self):
  original=self.store.bundle('SYN-BUNNY',2)['bundle']
  cases=[lambda b:b['bom'].pop(),lambda b:b['pieces'].append(b['pieces'][0]),lambda b:b['bom'].append(b['bom'][0]),lambda b:b['bom'][0].update(consumption_unit='m'),lambda b:b['bom'][0].update(quantity_unit='kg'),lambda b:b['pieces'][0].update(material_id='UNKNOWN'),lambda b:b['bom'][0].update(pattern_version='old'),lambda b:b['bom'][0].update(quantity=3),lambda b:b['bom'][0].update(consumption=999),lambda b:b['pieces'][0].update(cut_qty=True),lambda b:b['pieces'][0].update(area_mm2=float('nan'))]
  for mutate in cases:
   b=copy.deepcopy(original);mutate(b);self.assertFalse(audit(b)['passed'])
 def test_bad_bundle_audit_fails_closed_before_insert(self):
  b=self.store.bundle('SYN-BUNNY',2)['bundle'];b['bom'].pop();self.save_bundle(b)
  with self.assertRaises(ValueError):self.link()
  self.assertEqual(self.store.get('SYN-BUNNY')['head_version'],0)
 def test_pattern_version_change_and_change_impact(self):
  full=(self.library/'library.json').read_bytes();cat=json.loads(full);cat['bundles']=[m for m in cat['bundles'] if m['version']==1];(self.library/'library.json').write_bytes(serialized(cat));self.link();(self.library/'library.json').write_bytes(full)
  old=self.store.get('SYN-BUNNY');self.assertFalse(old['links'][0]['current_valid']);self.assertIn('new_pattern_bom_version',old['links'][0]['invalid_reasons']);r=self.link();i=r['links'][1]['impact'];self.assertEqual(len(i['changed']),12);self.assertEqual(i['added'],[]);self.assertEqual(len(i['material_totals']),2);self.assertTrue(r['links'][1]['current_valid']);self.assertEqual(r['links'][1]['previous_sha256'],r['links'][0]['sha256'])
 def test_same_version_replacement_requires_new_version(self):
  self.link();b=self.store.bundle('SYN-BUNNY',2)['bundle'];b['provenance']['mapping_basis']='changed';self.save_bundle(b)
  self.assertFalse(self.store.get('SYN-BUNNY')['links'][0]['current_valid'])
  with self.assertRaises(Conflict):self.link()
 def test_source_svg_damage_blocks_link(self):
  b=self.store.bundle('SYN-BUNNY',2)['bundle'];(self.library/'assets'/b['pieces'][0]['asset']).write_bytes(b'bad')
  with self.assertRaises(ValueError):self.link()
  self.assertEqual(self.store.get('SYN-BUNNY')['head_version'],0)
 def test_link_and_revocation_serialize(self):
  req=self.req()
  def link():
   try:self.link(req);return 'linked'
   except Conflict:return 'conflict'
  with ThreadPoolExecutor(2) as pool:
   a=pool.submit(link);b=pool.submit(self.act,'hold');a.result();b.result()
  r=self.store.get('SYN-BUNNY');self.assertIsNone(r['current_approval']);self.assertTrue(all(not l['current_valid'] for l in r['links']))
 def test_unit_conversion_matches_geometry(self):
  b=self.store.bundle('SYN-BUNNY',2)['bundle'];r=audit(b);self.assertTrue(r['passed']);self.assertEqual(r['cut_quantity'],13);self.assertAlmostEqual(r['estimated_area_mm2'],sum(p['area_mm2']*p['cut_qty'] for p in b['pieces']),places=2)
 def test_saved_demo_consistency_and_no_secrets(self):
  base=ROOT/'client/demo/pattern-links';manifest=json.loads((base/'manifest.json').read_text())
  for meta in manifest['files']:
   raw=(base/meta['path']).read_bytes();self.assertEqual(len(raw),meta['bytes']);self.assertEqual(digest(raw),meta['sha256'])
  for f in (base/'products').glob('*.json'):
   r=json.loads(f.read_text());u22=json.loads((ROOT/'client/demo/reviews/products'/f.name).read_text());current=u22['revisions'][-1];self.assertEqual(bool(r['current_approval']),current['active_approval'])
   for l in r['links']:
    self.assertEqual(l['approval_event_sha256'],current['approval']['sha256']);self.assertFalse(r['manufacturing_verified'])
  raw=''.join((base/m['path']).read_text() for m in manifest['files'] if m['path'].endswith('.json'));self.assertNotIn('token_hash',raw);self.assertNotIn('service_role',raw)
if __name__=='__main__':unittest.main()
