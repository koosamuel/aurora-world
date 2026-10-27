"""Replay frozen U22 synthetic fixtures (never production import) and execute U23."""
import argparse,copy,json,shutil,tempfile,uuid
from pathlib import Path
from aurora.pattern_links import PatternLinks,audit
from aurora.sample_reviews import ReviewStore
from aurora.sampling import BriefStore,seed
from aurora.identity import serialized,require
from aurora.generation import digest

def import_review_fixtures(root,work,briefs):
 s=ReviewStore(work,briefs);base=root/'client/demo/reviews'
 # Local build/test tool only. No HTTP path accepts imported approvals.
 with s.db() as db:
  for f in sorted((base/'products').glob('*.json')):
   r=json.loads(f.read_text());pid=r['product_id']
   db.execute('INSERT INTO review_tracks VALUES(?,?,?)',(pid,r['head_version'],r['seq']))
   for rev in r['revisions']:
    snap={k:v for k,v in rev.items() if k not in ('sha256','state','review','approval','stale_brief','active_approval')}
    require(digest(serialized(snap))==rev['sha256'],'U22 fixture snapshot hash')
    db.execute('INSERT INTO review_revisions VALUES(?,?,?,?)',(pid,rev['version'],serialized(snap).decode(),rev['sha256']))
    for a in rev['assets']:
     raw=(base/'assets'/a['asset']).read_bytes();require(len(raw)==a['bytes'] and digest(raw)==a['sha256'],'U22 fixture asset hash');(s.assets/a['asset']).write_bytes(raw)
   for event in r['events']:
    snap={k:v for k,v in event.items() if k!='sha256'};require(digest(serialized(snap))==event['sha256'],'U22 event hash')
    db.execute('INSERT INTO review_events VALUES(?,?,?,?)',(pid,event['seq'],serialized(snap).decode(),event['sha256']))
 for f in (base/'products').glob('*.json'):s.export(f.stem)
 return s

def request(store,pid):
 r=store.get(pid);a=r['current_approval'];v=r['latest_bundle_version'];b=store.bundle(pid,v)
 return dict(product_id=pid,bundle_version=v,bundle_sha256=b['sha256'],sample_revision_sha256=a['revision_sha256'],approval_event_sha256=a['approval_event_sha256'],expected_review_seq=a['review_seq'],parent_version=r['head_version'],reason='합성 수동 패턴/BOM 대응 · 제작 적합성 미검증',request_key=uuid.uuid4().hex)

def build(root,out):
 root=Path(root);out=Path(out)
 if out.exists():raise ValueError('Use new output directory')
 shutil.copytree(root/'client/demo/pattern-links',out,ignore=shutil.ignore_patterns('catalog.json','manifest.json','products','counterexamples.json'))
 (out/'products').mkdir();rejected=[]
 with tempfile.TemporaryDirectory() as temp:
  work=Path(temp);(work/'client').symlink_to(root/'client',target_is_directory=True);briefs=BriefStore(work/'briefs.sqlite');seed(briefs,root);reviews=import_review_fixtures(root,work,briefs)
  lib=work/'library';shutil.copytree(out,lib);full=json.loads((lib/'library.json').read_text());first=copy.deepcopy(full);first['bundles']=[m for m in full['bundles'] if m['version']==1];(lib/'library.json').write_bytes(serialized(first))
  store=PatternLinks(work,reviews,lib);token=reviews.session(dict(persona_id='designer'))['token']
  for pid in ('SYN-BUNNY','SYN-COW'):store.link(token,request(store,pid))
  (lib/'library.json').write_bytes(serialized(full))
  for pid in ('SYN-BUNNY','SYN-COW'):
   assert not store.get(pid)['links'][-1]['current_valid'];store.link(token,request(store,pid))
  for pid in sorted({m['product_id'] for m in full['bundles']}):
   r=store.export(pid);(out/'products'/(pid+'.json')).write_bytes(serialized(r))
  shutil.copytree(store.assets,out/'assets',dirs_exist_ok=True)
  cat=store.catalog();cat['mode']='saved_synthetic';(out/'catalog.json').write_bytes(serialized(cat))
  valid=store.bundle('SYN-BUNNY',2)['bundle']
  for case,mutate in [
   ('missing_bom',lambda b:b['bom'].pop()),('duplicate_piece',lambda b:b['pieces'].append(b['pieces'][0])),
   ('quantity_unit',lambda b:b['bom'][0].update(quantity_unit='kg')),('area_unit',lambda b:b['bom'][0].update(consumption_unit='m')),
   ('material_missing',lambda b:b['pieces'][0].update(material_id='UNKNOWN')),('pattern_version',lambda b:b['bom'][0].update(pattern_version='old')),
   ('quantity_balance',lambda b:b['bom'][0].update(quantity=99)),('area_balance',lambda b:b['bom'][0].update(consumption=99)),
  ]:
   b=copy.deepcopy(valid);mutate(b);report=audit(b);assert not report['passed'];rejected.append(dict(case=case,audit=report))
 (out/'counterexamples.json').write_bytes(serialized(rejected))
 metas=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json']
 (out/'manifest.json').write_bytes(serialized(dict(schema_version='aurora-pattern-link-demo-v1',files=metas)))
 print(json.dumps(dict(products=len(cat['products']),bundle_versions=len(full['bundles']),piece_rows=144,unique_assets=len(list((out/'assets').glob('*.svg'))),links=4,current_links=2,counterexamples=len(rejected),files=len(metas)+1)))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(Path(__file__).resolve().parents[1],a.output)
