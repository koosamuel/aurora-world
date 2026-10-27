"""Run REAL offline inference for saved Pages examples; never fabricate outputs."""
from pathlib import Path
import argparse
from aurora.ai_sampling import public_catalog
from aurora.ai_worker import generate
from aurora.identity import serialized

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args()
root=Path(__file__).resolve().parents[1];out=a.output
if out.exists() and not a.resume:raise SystemExit('Use a new output directory or explicit --resume.')
out.mkdir(parents=True,exist_ok=a.resume);c=public_catalog(root)
sources=[s for s in c['sources'] if s['brief']['brief_version']==2];mapping={}
for source in sources:
    id='ai-'+source['checksum'][:16]
    if a.resume and (out/id/'run.json').exists():
        import json
        row=json.loads((out/id/'run.json').read_text())
        if row['source']['checksum']!=source['checksum']:raise SystemExit('Resume source checksum changed')
    else:
        # Partial/blocked attempts stay in local results, never in published artifacts.
        if (out/id).exists():
            import shutil,uuid
            quarantine=root/'results/ai-sampling-build-failures'/uuid.uuid4().hex
            quarantine.parent.mkdir(parents=True,exist_ok=True);shutil.move(out/id,quarantine)
            # A previously blocked attempt is recorded rather than retried.
            row=dict(id=id,state='failed',source=source,seed=42,result=None,error='이전 실행의 부분 출력은 게시하지 않았습니다. 로컬 추론 로그를 확인하세요.',created_at=None)
            (out/id).mkdir()
        else:
            try:
                result=generate(root,source,42,out/id)
                row=dict(id=id,state='succeeded',source=source,seed=42,result=result,error=None,created_at=None)
            except ValueError as e:
                import shutil,uuid
                if (out/id).exists():
                    quarantine=root/'results/ai-sampling-build-failures'/uuid.uuid4().hex
                    quarantine.parent.mkdir(parents=True,exist_ok=True);shutil.move(out/id,quarantine)
                (out/id).mkdir()
                row=dict(id=id,state='failed',source=source,seed=42,result=None,error=str(e),created_at=None)
    (out/id/'run.json').write_bytes(serialized(row));mapping[source['id']]=id
    print(source['id'],row['state'],row['result']['report']['input_analysis']['hypothesis'] if row['result'] else row['error'],flush=True)
c.update(sources=sources,demo_runs=mapping,runtime_available=False,runtime_message='실제로 추론한 저장 이미지 · 게시 화면은 새 추론을 실행하지 않습니다.')
(out/'catalog.json').write_bytes(serialized(c))
