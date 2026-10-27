import copy,json,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from aurora.sample_reviews import ReviewStore,Denied,decode
from aurora.sampling import BriefStore,seed,checksum,Conflict
from aurora.generation import GenerationService,digest
from aurora.identity import serialized

ROOT=Path(__file__).resolve().parents[1]
class SampleReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'client').symlink_to(ROOT/'client',target_is_directory=True)
  self.briefs=BriefStore(self.root/'briefs.sqlite');seed(self.briefs,ROOT);self.gen=GenerationService(self.root,self.briefs)
  self.store=ReviewStore(self.root,self.briefs,self.gen);self.tokens={k:self.store.session(dict(persona_id=k))['token'] for k in ('designer','reviewer','approver','viewer')}
  self.candidates=[c for c in self.store.catalog()['candidates'] if c['product_id']=='SYN-BUNNY' and c['kind']=='ai']
 def tearDown(self):self.tmp.cleanup()
 def revision(self,index=0):
  old=self.store.get('SYN-BUNNY');c=self.candidates[index]
  return self.store.revision(self.tokens['designer'],dict(candidate_id=c['id'],candidate_checksum=c['checksum'],parent_version=old['head_version'] if old else None,expected_seq=old['seq'] if old else 0,change_reason='합성 후보 교체',request_key=uuid.uuid4().hex))
 def request(self,action,status='pass',role=None):
  r=self.store.get('SYN-BUNNY');rev=r['revisions'][-1]
  req=dict(product_id='SYN-BUNNY',version=r['head_version'],expected_seq=r['seq'],action=action,comment='합성 검토 의견',checks=[dict(id=c['id'],status=status,note='합성 검토 사유') for c in rev['checklist']] if action=='review' else [],request_key=uuid.uuid4().hex)
  return self.tokens[role or {'submit':'designer','review':'reviewer','approve':'approver','request_changes':'reviewer','hold':'reviewer','comment':'designer'}[action]],req
 def act(self,action,status='pass',role=None):
  token,req=self.request(action,status,role);return self.store.event(token,req)
 def approved(self):
  self.revision();self.act('submit');self.act('review');return self.act('approve')
 def test_full_revision_review_changes_and_bound_approval(self):
  self.revision();self.act('submit');self.act('review','fail')
  with self.assertRaises(ValueError):self.act('approve')
  self.act('request_changes')
  with self.assertRaises(ValueError):self.act('submit')
  r=self.revision(1);self.assertIsNone(r['revisions'][-1]['review']);self.assertFalse(r['revisions'][-1]['active_approval'])
  self.act('submit');self.act('review');r=self.act('approve');v=r['revisions'][-1]
  self.assertTrue(v['active_approval']);self.assertEqual(v['approval']['payload']['revision_sha256'],v['sha256']);self.assertEqual(v['approval']['payload']['review_event_sha256'],v['review']['sha256']);self.assertFalse(r['manufacturing_verified'])
  exported=self.store.export('SYN-BUNNY');self.assertTrue(exported['asset_hashes_verified']);self.assertEqual(exported['export_sha256'],digest(serialized({k:v for k,v in exported.items() if k not in ('asset_hashes_verified','export_sha256')})))
 def test_no_approval_inheritance_and_old_revision_rejected(self):
  first=self.approved();old=copy.deepcopy(first['revisions'][0]);r=self.revision(1)
  self.assertEqual(r['revisions'][0]['state'],'superseded');self.assertIsNotNone(r['revisions'][0]['approval']);self.assertFalse(r['revisions'][0]['active_approval']);self.assertFalse(r['revisions'][1]['active_approval'])
  self.assertEqual(r['revisions'][1]['parent_sha256'],old['sha256'])
  token,req=self.request('approve');req['version']=1
  with self.assertRaises(Conflict):self.store.event(token,req)
 def test_role_session_expiry_and_no_client_role_override(self):
  self.revision();self.act('submit')
  for action,role in [('approve','reviewer'),('review','designer'),('comment','viewer')]:
   token,req=self.request(action,role=role)
   with self.assertRaises(Denied):self.store.event(token,req)
  token,req=self.request('approve')
  with self.assertRaises(Denied):self.store.event('forged',req)
  with self.assertRaises(ValueError):self.store.event(token,dict(req,role='approver'))
  with self.store.db() as db:db.execute('UPDATE review_sessions SET expires=0')
  with self.assertRaises(Denied):self.store.actor(token)
 def test_incomplete_checklist_unreviewed_and_missing_reason(self):
  self.revision();self.act('submit');token,req=self.request('review')
  for checks in [[],req['checks']+req['checks'][:1],[dict(c,status='fail',note='') for c in req['checks']]]:
   with self.assertRaises(ValueError):self.store.event(token,dict(req,checks=checks))
  self.act('review','unreviewed')
  with self.assertRaises(ValueError):self.act('approve')
 def test_event_replay_and_content_conflict(self):
  self.revision();token,req=self.request('submit');a=self.store.event(token,req);b=self.store.event(token,req)
  self.assertTrue(b['replayed']);self.assertEqual(a['seq'],b['seq']);self.assertEqual(self.store.get('SYN-BUNNY')['seq'],a['seq'])
  with self.assertRaises(Conflict):self.store.event(token,dict(req,comment='다른 내용'))
 def test_old_approval_replay_returns_current_validity_without_new_event(self):
  self.revision();self.act('submit');self.act('review');token,req=self.request('approve');receipt=self.store.event(token,req)
  latest=self.revision(1);replayed=self.store.event(token,req)
  self.assertTrue(replayed['replayed']);self.assertEqual(replayed['original_receipt_seq'],receipt['seq']);self.assertEqual(replayed['seq'],latest['seq']);self.assertFalse(replayed['revisions'][0]['active_approval']);self.assertFalse(replayed['revisions'][1]['active_approval'])
 def test_concurrent_mutations_one_wins_and_duplicate_is_single_event(self):
  self.revision();token,req=self.request('comment');req2=dict(req,comment='경쟁 수정',request_key=uuid.uuid4().hex)
  def run(body):
   try:return self.store.event(token,body)
   except Conflict:return None
  with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,[req,req2]))
  self.assertEqual(sum(r is not None for r in rows),1)
  token,req=self.request('comment')
  with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(run,[req,req]))
  self.assertEqual(len({r['seq'] for r in rows}),1)
 def test_stale_parent_and_identical_sample_cannot_fake_revision(self):
  r=self.revision();c=self.candidates[1]
  with self.assertRaises(Conflict):self.store.revision(self.tokens['designer'],dict(candidate_id=c['id'],candidate_checksum=c['checksum'],parent_version=None,expected_seq=0,change_reason='stale',request_key=uuid.uuid4().hex))
  with self.assertRaises(ValueError):self.revision()
 def test_brief_change_invalidates_approval_without_erasing_history(self):
  self.approved();b=copy.deepcopy(self.briefs.get('SYN-BUNNY',2)['brief']);b.update(brief_version=3,previous_checksum=checksum(b));b['requirements']['dimensions']['height']+=10;self.briefs.register(b)
  r=self.store.get('SYN-BUNNY');self.assertEqual(r['revisions'][-1]['state'],'approved');self.assertTrue(r['revisions'][-1]['stale_brief']);self.assertFalse(r['revisions'][-1]['active_approval'])
  with self.assertRaises(Conflict):self.act('hold',role='approver')
  with self.assertRaises(Conflict):self.revision(1)
  # Generate a real local geometry candidate from the new brief and re-review it.
  c=next(c for c in self.gen.catalog()['sources'] if c['id']=='u20:SYN-BUNNY:3');row,new=self.gen.request(dict(source_id=c['id'],source_checksum=c['checksum'],seed=42,request_key=uuid.uuid4().hex));self.gen.work(row['id'])
  self.candidates=[c for c in self.store.catalog()['candidates'] if c['run_id']==row['id']]
  r=self.revision();self.assertTrue(r['revisions'][-1]['brief_changed']);self.assertFalse(r['revisions'][-1]['active_approval'])
 def test_approval_withdrawal_and_resubmit_requires_new_review(self):
  self.approved();r=self.act('hold',role='approver');self.assertFalse(r['revisions'][-1]['active_approval']);self.assertIn('revoked_approval_sha256',r['events'][-1]['payload'])
  self.act('submit')
  with self.assertRaises(ValueError):self.act('approve')
  self.act('review');self.assertTrue(self.act('approve')['revisions'][-1]['active_approval'])
 def test_assets_persist_export_and_reject_damage_or_path_escape(self):
  r=self.approved();a=r['revisions'][0]['assets'][0];p=self.store.asset(a['asset']);self.assertTrue(p.exists())
  restarted=ReviewStore(self.root,self.briefs,self.gen);self.assertEqual(restarted.get('SYN-BUNNY')['seq'],r['seq']);self.assertEqual(restarted.actor(self.tokens['designer'])['role'],'designer')
  with self.assertRaises(ValueError):self.store.asset('../input.json')
  p.write_bytes(b'broken')
  with self.assertRaises(ValueError):self.store.export('SYN-BUNNY')
 def test_database_immutability_and_audit_corruption_detection(self):
  self.revision()
  with self.assertRaises(sqlite3.IntegrityError),self.store.db() as db:db.execute('DELETE FROM review_events')
  with self.assertRaises(sqlite3.IntegrityError),self.store.db() as db:db.execute("UPDATE review_revisions SET snapshot='{}'")
  with self.store.db() as db:
   db.execute('DROP TRIGGER event_no_update');db.execute("UPDATE review_events SET event=replace(event,'revision_created','revision_altered')")
  with self.assertRaises(ValueError):self.store.get('SYN-BUNNY')
 def test_decoding_and_non_synthetic_candidates_rejected(self):
  for raw in [b'{"a":1,"a":2}',b'{"x":NaN}',b'[]',b'\xff',b'x'*32769]:
   with self.assertRaises(ValueError):decode(raw)
  candidates=self.store.catalog()['candidates'];self.assertEqual(len(candidates),18);self.assertTrue(all(c['source']['data_kind']=='synthetic' for c in candidates));self.assertTrue(all('abo:' not in c['id'] for c in candidates))
 def test_saved_review_snapshot_hashes_and_states(self):
  p=ROOT/'client/demo/reviews';cat=json.loads((p/'catalog.json').read_text());self.assertEqual(len(cat['products']),6)
  for row in cat['products']:
   e=json.loads((p/'products'/f"{row['product_id']}.json").read_text());self.assertTrue(e['history_hash_verified']);self.assertTrue(e['asset_hashes_verified']);prev=None
   for event in e['events']:
    self.assertEqual(event['previous_event_sha256'],prev);prev=event['sha256'];self.assertEqual(prev,digest(serialized({k:v for k,v in event.items() if k!='sha256'})))
   for rev in e['revisions']:
    for a in rev['assets']:
     raw=(p/'assets'/a['asset']).read_bytes();self.assertEqual(digest(raw),a['sha256']);self.assertEqual(len(raw),a['bytes'])
