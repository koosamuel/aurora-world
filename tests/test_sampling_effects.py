import copy,csv,io,json,sqlite3,tempfile,unittest,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from aurora.sampling_effects import EffectStore,calculate,validate,decode,engine
from aurora.sampling import Conflict,checksum
from aurora.sample_reviews import Denied
from aurora.generation import digest
from aurora.identity import serialized
from tools.build_effect_demo import fixture_store,input_example

ROOT=Path(__file__).resolve().parents[1]
class EffectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=fixture_store(ROOT,self.root);self.spec=input_example(ROOT)
  self.tokens={k:self.store.patterns.reviews.session(dict(persona_id=k))['token'] for k in ('designer','reviewer','approver','viewer')}
 def tearDown(self):self.temp.cleanup()
 def req(self,spec=None):return dict(input=spec or copy.deepcopy(self.spec),request_key=uuid.uuid4().hex)
 def save(self,req=None,role='designer'):return self.store.register(self.tokens[role],req or self.req())
 def sources(self,spec=None):
  with self.store.sources(spec or self.spec) as src:return copy.deepcopy(src)
 def revoke(self,pid='SYN-BUNNY'):
  s=self.store.patterns.reviews;r=s.get(pid)
  return s.event(self.tokens['approver'],dict(product_id=pid,version=r['head_version'],expected_seq=r['seq'],action='hold',comment='합성 승인 철회',checks=[],request_key=uuid.uuid4().hex))
 def test_hand_calculated_pairs_and_negative_cases(self):
  r=self.save()['current_report'];s=r['summary'];self.assertEqual((s['sample_units']['before_total'],s['sample_units']['after_total']),(6,5));self.assertEqual(s['sample_units']['paired_products'],2);self.assertAlmostEqual(s['sample_units']['reduction_pct'],100/6)
  self.assertEqual((s['make_events']['before_total'],s['make_events']['after_total']),(4,3));self.assertEqual((s['elapsed_hours']['before_total'],s['elapsed_hours']['after_total']),(672,624));self.assertEqual(s['bom_errors']['direction'],'unchanged')
  cow=next(p for p in r['products'] if p['product_id']=='SYN-COW');self.assertEqual(cow['metrics']['sample_units']['reduction'],-1);self.assertEqual(cow['metrics']['bom_errors']['reduction'],-1);self.assertFalse(r['effect_measured'])
 def test_unmeasured_not_zero_and_observed_zero(self):
  r=self.save()['current_report'];fruit=next(p for p in r['products'] if p['product_id']=='SYN-FRUIT');dog=next(p for p in r['products'] if p['product_id']=='SYN-DOG');self.assertIsNone(fruit['after']['sample_units']);self.assertEqual(dog['after']['sample_units'],0);self.assertIsNone(dog['before']['sample_units']);self.assertFalse(dog['metrics']['sample_units']['eligible'])
 def test_per_metric_denominators_unknown_bom_not_error(self):
  spec=copy.deepcopy(self.spec);b=next(p for p in spec['pairs'] if p['product_id']=='SYN-BUNNY');b['pilot']['bom_changes'][0]['reason']='unknown';r=self.save(self.req(spec))['current_report'];self.assertEqual(r['summary']['sample_units']['paired_products'],2);self.assertEqual(r['summary']['bom_errors']['paired_products'],1);b=next(p for p in r['products'] if p['product_id']=='SYN-BUNNY');self.assertEqual(b['after']['unclassified_changes'],1);self.assertIn('bom_reason_unknown',b['metrics']['bom_errors']['reasons'])
 def test_design_change_is_not_error(self):
  p=self.save()['current_report']['products'];b=next(p for p in p if p['product_id']=='SYN-BUNNY');self.assertEqual(b['after']['bom_errors'],0);self.assertEqual(b['after']['design_changes'],1)
 def test_scope_definition_and_partial_exclusions(self):
  for change,reason in [(dict(scope_id='OTHER'),'scope_mismatch'),(dict(definition_id='working_hours'),'definition_mismatch'),(dict(status='in_progress',ended_at=None),'pilot_in_progress'),(dict(physical_complete=False),'physical_coverage_incomplete')]:
   spec=copy.deepcopy(self.spec);b=next(p for p in spec['pairs'] if p['product_id']=='SYN-BUNNY');b['pilot'].update(change);r=calculate(validate(spec),self.sources(spec));b=next(p for p in r['products'] if p['product_id']=='SYN-BUNNY');self.assertIn(reason,b['metrics']['sample_units']['reasons'])
 def test_zero_baseline_denominator_absolute_change_only(self):
  src=self.sources();b=next(s for s in src if s['product_id']=='SYN-BUNNY');b['baseline']['physical_samples']=[];b['baseline']['bom_changes']=[];b['baseline']['ended_at']=b['baseline']['started_at'];r=calculate(self.spec,src);p=next(p for p in r['products'] if p['product_id']=='SYN-BUNNY');self.assertTrue(p['metrics']['sample_units']['eligible']);self.assertEqual(p['metrics']['sample_units']['percent_status'],'baseline_zero');self.assertIsNone(p['metrics']['sample_units']['reduction_pct']);self.assertEqual(p['metrics']['sample_units']['reduction'],-1)
 def test_all_excluded_summary_is_none(self):
  spec=copy.deepcopy(self.spec)
  for p in spec['pairs']:p['anchor']=None
  r=self.save(self.req(spec))['current_report'];self.assertFalse(r['synthetic_comparison_available'])
  for s in r['summary'].values():self.assertEqual(s['paired_products'],0);self.assertIsNone(s['before_total']);self.assertIsNone(s['reduction_pct'])
 def test_duplicate_ids_quantities_dates_windows_rejected(self):
  def pair(s):return next(p for p in s['pairs'] if p['product_id']=='SYN-BUNNY')['pilot']
  mutations=[lambda s:s['pairs'].append(s['pairs'][0]),lambda s:pair(s)['physical_samples'].append(pair(s)['physical_samples'][0]),lambda s:pair(s)['physical_samples'][0].update(quantity=True),lambda s:pair(s)['physical_samples'][0].update(quantity=-1),lambda s:pair(s)['physical_samples'][0].update(occurred_at='2026-09-01T09:00:00Z'),lambda s:pair(s).update(ended_at='2026-09-01T09:00:00Z'),lambda s:pair(s).update(window_end='2026-10-02'),lambda s:pair(s).update(status='unmeasured'),lambda s:pair(s)['bom_changes'][0].update(reason='all_changes_are_errors')]
  for mutate in mutations:
   spec=copy.deepcopy(self.spec);mutate(spec)
   with self.assertRaises(ValueError):validate(spec)
 def test_source_and_anchor_checksums_fail_closed(self):
  for key in ('baseline_checksum','anchor'):
   spec=copy.deepcopy(self.spec);p=next(p for p in spec['pairs'] if p['product_id']=='SYN-BUNNY')
   if key=='anchor':p['anchor']['link_sha256']='0'*64
   else:p[key]='0'*64
   with self.assertRaises(Conflict):self.save(self.req(spec))
 def test_no_anchor_not_inferred_from_shape_or_approval(self):
  spec=copy.deepcopy(self.spec);p=next(p for p in spec['pairs'] if p['product_id']=='SYN-BUNNY');p['anchor']=None;r=self.save(self.req(spec))['current_report'];self.assertEqual(r['summary']['sample_units']['included'],['SYN-COW'])
 def test_revocation_recomputes_current_and_preserves_frozen(self):
  r=self.save();self.revoke();new=self.store.get(self.spec['study_id']);self.assertTrue(new['source_changed']);self.assertEqual(new['snapshot'],r['snapshot']);self.assertEqual(new['sha256'],r['sha256']);self.assertEqual(new['current_report']['summary']['sample_units']['paired_products'],1);self.assertEqual(r['snapshot']['result']['summary']['sample_units']['paired_products'],2)
 def test_new_brief_invalidates_current_workflow(self):
  self.save();review=self.store.patterns.reviews;b=copy.deepcopy(review.latest_brief('SYN-BUNNY')['brief']);b.update(brief_version=3,previous_checksum=checksum(b));b['product_name']+=' 변경';review.briefs.register(b);r=self.store.get(self.spec['study_id']);self.assertTrue(r['source_changed']);self.assertEqual(r['current_report']['summary']['sample_units']['paired_products'],1)
 def test_roles_require_designer_and_no_session(self):
  for role in ('viewer','reviewer','approver'):
   with self.assertRaises(Denied):self.save(role=role)
  with self.assertRaises(Denied):self.store.register(None,self.req())
 def test_version_and_idempotency_same_key_changed_key(self):
  req=self.req();r=self.save(req);self.assertTrue(self.save(req)['replayed']);self.revoke();replay=self.save(req);self.assertTrue(replay['source_changed']);self.assertEqual(replay['current_report']['summary']['sample_units']['paired_products'],1)
  req['input']['reason']='changed'
  with self.assertRaises(Conflict):self.save(req)
  with self.assertRaises(Conflict):self.save()
  s=copy.deepcopy(self.spec);s.update(version=2,previous_sha256=r['sha256']);r2=self.save(self.req(s));self.assertEqual(len(r2['history']),2)
 def test_replay_pinned_version_after_later_pair_change(self):
  req=self.req();r=self.save(req);s=copy.deepcopy(self.spec);s.update(version=2,previous_sha256=r['sha256']);s['pairs']=s['pairs'][:1];self.save(self.req(s));again=self.save(req);self.assertEqual(again['snapshot']['version'],1);self.assertEqual(len(again['current_report']['products']),6)
 def test_concurrent_same_key_and_different_keys(self):
  req=self.req()
  with ThreadPoolExecutor(2) as pool:rs=list(pool.map(lambda _:self.save(req),range(2)))
  self.assertEqual(sorted(r['replayed'] for r in rs),[False,True])
  r=rs[0];spec=copy.deepcopy(self.spec);spec.update(version=2,previous_sha256=r['sha256'])
  def run(req):
   try:self.save(req);return 'ok'
   except Conflict:return 'conflict'
  with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(run,[self.req(spec),self.req(copy.deepcopy(spec))])),['conflict','ok'])
 def test_immutable_and_history_hash(self):
  self.save()
  with self.store.db() as db:
   for sql in ('UPDATE effect_reports SET sha256=sha256','DELETE FROM effect_reports'):
    with self.assertRaises(sqlite3.IntegrityError):db.execute(sql)
   db.execute('DROP TRIGGER effects_no_update');db.execute('UPDATE effect_reports SET sha256=?',('0'*64,))
  with self.assertRaises(ValueError):self.store.get(self.spec['study_id'])
 def test_artifacts_hash_csv_reconcile_frozen_after_change(self):
  r=self.save();sid=self.spec['study_id'];before={m['file']:self.store.artifact(sid,1,m['file']).read_bytes() for m in r['artifact_manifest']['files']}
  for m in r['artifact_manifest']['files']:self.assertEqual(digest(before[m['file']]),m['sha256']);self.assertEqual(len(before[m['file']]),m['bytes'])
  rows=list(csv.DictReader(io.StringIO(before['products.csv'].decode('utf-8-sig'))));eligible=[x for x in rows if x['metric']=='sample_units' and x['eligible']=='True'];self.assertEqual(sum(float(x['before']) for x in eligible),6);self.assertEqual(sum(float(x['after']) for x in eligible),5)
  self.revoke();self.assertEqual(self.store.artifact(sid,1,'report.json').read_bytes(),before['report.json']);self.assertIn('실제 기업 효과'.encode(),before['report.md'])
 def test_artifact_damage_and_traversal(self):
  r=self.save();p=self.store.artifact(self.spec['study_id'],1,'products.csv');p.write_bytes(b'bad')
  with self.assertRaises(ValueError):self.store.artifact(self.spec['study_id'],1,'products.csv')
  with self.assertRaises(ValueError):self.store.artifact(self.spec['study_id'],1,'../manifest.json')
 def test_decode_and_unknown_fields(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'[]',b'x'*131073):
   with self.assertRaises(ValueError):decode(raw)
  s=copy.deepcopy(self.spec);s['actual_company_effect']=True
  with self.assertRaises(ValueError):validate(s)
 def test_zero_total_and_metric_specific_coverage(self):
  spec=copy.deepcopy(self.spec);spec['pairs']=[p for p in spec['pairs'] if p['product_id']=='SYN-BUNNY'];src=self.sources(spec);src[0]['baseline']['physical_samples']=[];r=calculate(spec,src);self.assertEqual(r['summary']['sample_units']['percent_status'],'baseline_zero');self.assertIsNone(r['summary']['sample_units']['reduction_pct'])
  spec['pairs'][0]['baseline_coverage']['physical_complete']=False;r=calculate(spec,src);self.assertEqual(r['summary']['sample_units']['paired_products'],0);self.assertEqual(r['summary']['elapsed_hours']['paired_products'],1)
 def test_report_save_and_revocation_serialize(self):
  with ThreadPoolExecutor(2) as pool:
   a=pool.submit(self.save);b=pool.submit(self.revoke);a.result();b.result()
  r=self.store.get(self.spec['study_id']);self.assertEqual(r['current_report']['summary']['sample_units']['paired_products'],1)
 def test_restart_and_saved_fixture_consistency(self):
  self.save();s=EffectStore(self.root,self.store.patterns);self.assertEqual(s.get(self.spec['study_id'])['current_report']['summary']['sample_units']['paired_products'],2)
  base=ROOT/'client/demo/effects'
  for m in json.loads((base/'manifest.json').read_text())['files']:
   raw=(base/m['path']).read_bytes();self.assertEqual(digest(raw),m['sha256']);self.assertEqual(len(raw),m['bytes'])
  a=json.loads((base/'reports/SYN-EFFECT-SIX-PRODUCTS-v1.json').read_text());b=json.loads((base/'reports/SYN-EFFECT-SIX-PRODUCTS-v2.json').read_text());self.assertEqual(a['current_report']['summary']['sample_units']['paired_products'],1);self.assertEqual(b['current_report']['summary']['sample_units']['paired_products'],2);self.assertEqual(b['snapshot']['previous_sha256'],a['sha256'])
if __name__=='__main__':unittest.main()
