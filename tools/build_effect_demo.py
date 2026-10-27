"""Build reproducible U24 input and reports using only own frozen U20/U22/U23 fixtures."""
from pathlib import Path
import argparse,copy,json,shutil,tempfile,uuid
from aurora.identity import serialized,require
from aurora.generation import digest
from aurora.sampling import BriefStore,seed
from aurora.pattern_links import PatternLinks
from aurora.sampling_effects import EffectStore,DEFINITION
try:from tools.build_pattern_demo import import_review_fixtures
except ModuleNotFoundError:from build_pattern_demo import import_review_fixtures

ROOT=Path(__file__).resolve().parents[1]
def fixture_store(root,work):
 (work/'client').symlink_to(root/'client',target_is_directory=True);briefs=BriefStore(work/'briefs.sqlite');seed(briefs,root);reviews=import_review_fixtures(root,work,briefs);patterns=PatternLinks(work,reviews)
 base=root/'client/demo/pattern-links'
 with patterns.db() as db:
  for f in (base/'products').glob('*.json'):
   r=json.loads(f.read_text())
   for link in r['links']:
    snap={k:v for k,v in link.items() if k not in ('sha256','current_valid','invalid_reasons')};require(digest(serialized(snap))==link['sha256'],'U23 fixture hash')
    db.execute('INSERT INTO pattern_links VALUES(?,?,?,?)',(r['product_id'],link['version'],serialized(snap).decode(),link['sha256']))
    for p in link['bundle']['pieces']:
     raw=(base/'assets'/p['asset']).read_bytes();require(len(raw)==p['asset_bytes'] and digest(raw)==p['asset'][:-4],'U23 fixture asset hash');(patterns.assets/p['asset']).write_bytes(raw)
 for f in (base/'products').glob('*.json'):patterns.export(f.stem)
 return EffectStore(work,patterns)

def input_example(root):
 rows=[]
 for f in sorted((root/'configs/examples/sampling').glob('*v2.json')):
  brief=json.loads(f.read_text());pid=brief['product_id'];ref=json.loads((root/'client/demo/pattern-links/products'/f'{pid}.json').read_text());link=next((x for x in reversed(ref['links']) if x['current_valid']),None);scope=pid+'-SPEC-V2'
  p=dict(status='complete',window_start='2026-10-01',window_end='2026-10-25',started_at='2026-10-01T09:00:00Z',ended_at='2026-10-10T09:00:00Z',definition_id=DEFINITION,scope_id=scope,physical_complete=True,bom_complete=True,physical_samples=[dict(event_id='PILOT-MAKE-1',occurred_at='2026-10-03T09:00:00Z',quantity=1)],bom_changes=[dict(event_id='PILOT-DESIGN-1',occurred_at='2026-10-07T09:00:00Z',reason='design_change',description='합성 정상 디자인 변경 · 오류 수정과 구분')])
  if pid=='SYN-COW':
   p.update(ended_at='2026-10-18T09:00:00Z',physical_samples=[dict(event_id='PILOT-MAKE-1',occurred_at='2026-10-03T09:00:00Z',quantity=2),dict(event_id='PILOT-MAKE-2',occurred_at='2026-10-14T09:00:00Z',quantity=2)])
   p['bom_changes']+=[dict(event_id='PILOT-ERROR-'+str(i),occurred_at='2026-10-0'+str(i+4)+'T09:00:00Z',reason='error_correction',description='합성 수량 기입 오류 수정') for i in (1,2)]
  elif pid=='SYN-CAT':p.update(bom_complete=False);p['bom_changes'][0]['reason']='unknown'
  elif pid=='SYN-DOG':p.update(physical_samples=[],bom_changes=[])
  elif pid=='SYN-FRUIT':p.update(status='unmeasured',started_at=None,ended_at=None,physical_complete=False,bom_complete=False,physical_samples=[],bom_changes=[])
  elif pid=='SYN-CACTUS':p.update(status='in_progress',ended_at=None,definition_id='business_hours_unverified',physical_complete=False,bom_complete=False)
  rows.append(dict(product_id=pid,baseline_version=2,baseline_checksum=digest(serialized(brief)),definition_id=DEFINITION,scope_id=scope,baseline_coverage=dict(physical_complete=brief['baseline']['status']=='synthetic_recorded',bom_complete=brief['baseline']['status']=='synthetic_recorded'),pilot=p,anchor=dict(link_version=link['version'],link_sha256=link['sha256']) if link else None))
 return dict(schema_version='aurora-sampling-effect-input-v1',data_kind='synthetic',study_id='SYN-EFFECT-SIX-PRODUCTS',version=1,previous_sha256=None,reason='자체 합성 현행/시범의 측정·제외 규칙 확인',assumptions='U20의 가상 현행을 재사용하고 시범 제작/BOM 사건을 새로 합성했다. 같은 제품 범위/난이도·정의라는 가정이며 실제 현장 비교군이 아니다. U22/U23 해시는 디지털 이력 참조이고 합성 제작 사건이 실제로 일어났다는 증거가 아니다. 기업 실측·인과 개선·실제 비용/정확도는 미측정이다.',pairs=rows)

def build(root,out):
 if out.exists():raise ValueError('Use a new output directory')
 out.mkdir(parents=True);(out/'reports').mkdir();(out/'artifacts').mkdir();spec=input_example(root);(out/'input-example.json').write_bytes(serialized(spec))
 with tempfile.TemporaryDirectory() as temp:
  store=fixture_store(root,Path(temp));token=store.patterns.reviews.session(dict(persona_id='designer'))['token']
  first=copy.deepcopy(spec);cow=next(p for p in first['pairs'] if p['product_id']=='SYN-COW')['pilot'];cow.update(status='in_progress',ended_at=None,physical_complete=False,bom_complete=False)
  r=store.register(token,dict(input=first,request_key=uuid.uuid4().hex));spec.update(version=2,previous_sha256=r['sha256'],reason='젖소형 시범 관측 완료 · 악화 사례도 포함해 비교 분모 갱신');store.register(token,dict(input=spec,request_key=uuid.uuid4().hex))
  for v in (1,2):
   r=store.get(spec['study_id'],v);(out/'reports'/f'{spec["study_id"]}-v{v}.json').write_bytes(serialized(r));d=out/'artifacts'/f'{spec["study_id"]}-v{v}';d.mkdir()
   for name in (*[m['file'] for m in r['artifact_manifest']['files']],'manifest.json'):shutil.copy2(store.artifact(spec['study_id'],v,name),d/name)
  cat=store.catalog();cat['mode']='saved_synthetic';(out/'catalog.json').write_bytes(serialized(cat))
 metas=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in sorted(out.rglob('*')) if p.is_file()]
 (out/'manifest.json').write_bytes(serialized(dict(schema_version='aurora-effect-demo-manifest-v1',files=metas)))
 print(json.dumps(dict(products=6,report_versions=2,artifact_files=12,files=len(metas)+1,latest_summary={k:dict(pairs=v['paired_products'],before=v['before_total'],after=v['after_total']) for k,v in r['current_report']['summary'].items()})))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(ROOT,a.output)
