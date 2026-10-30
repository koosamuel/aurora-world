"""Immutable local projection derivatives of confirmed TripoSG runs, not approvals."""
import hashlib,json,os,re,subprocess,threading,uuid
from pathlib import Path
from .learned3d_worker import sha
from .sketch_projection import settings
FILES={'projected.glb','projection-report.json'}
def decode(raw):
    if not 0<len(raw)<=65536:raise ValueError('투영 요청 크기 오류')
    def pairs(items):
        if len(dict(items))!=len(items):raise ValueError('중복 JSON 키')
        return dict(items)
    try:req=json.loads(raw,object_pairs_hook=pairs)
    except (RecursionError,UnicodeDecodeError) as e:raise ValueError('투영 JSON 오류') from e
    if not isinstance(req,dict) or set(req)!={'parent_model_sha256','source_image_sha256','settings','projection_confirmed'} or req['projection_confirmed'] is not True:raise ValueError('투영 해시·설정·명시적 확인 필요')
    for k in ('parent_model_sha256','source_image_sha256'):
        if not isinstance(req[k],str) or not re.fullmatch('[0-9a-f]{64}',req[k]):raise ValueError('투영 해시 형식 오류')
    settings(req['settings']);req['settings']={k:float(v) for k,v in req['settings'].items()};return req
class ProjectionService:
    def __init__(self,root,learned):
        self.root=Path(root);self.learned=learned;self.folder=self.root/'results/sketch-projections';self.folder.mkdir(parents=True,exist_ok=True);self.lock=threading.Lock()
        for p in self.folder.glob('*/state.json'):
            row=json.loads(p.read_text())
            if row['status']=='running':row.update(status='failed',error='서버 재시작으로 투영 중단');self.save(p.parent,row)
    def save(self,d,row):
        p=d/'state.tmp';p.write_text(json.dumps(row,ensure_ascii=False,allow_nan=False));p.replace(d/'state.json')
    def get(self,id):
        if not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('투영 ID 오류')
        p=self.folder/id/'state.json';return json.loads(p.read_text()) if p.is_file() else None
    def create(self,run_id,raw):
        req=decode(raw);parent=self.learned.get(run_id)
        if not parent or parent['status']!='succeeded' or parent['engine']!='TripoSG-scribble' or parent.get('foreground_confirmed') is not True:raise ValueError('확인 후 생성된 TripoSG 완료 결과만 투영 가능')
        self.learned.source(parent)
        model=self.learned.artifact(run_id,'model.glb');image=self.learned.jobs/run_id/'preview/foreground.png'
        if model is None or not image.is_file() or sha(model)!=req['parent_model_sha256'] or sha(image)!=req['source_image_sha256'] or sha(image)!=parent['foreground_sha256']:raise ValueError('부모 형상/전경 해시 불일치')
        identity=dict(parent_run_id=run_id,**req);key=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if not self.lock.acquire(blocking=False):raise RuntimeError('다른 투영 사본 처리 중')
        d=None;row=None
        try:
            previous=[json.loads(p.read_text()) for p in self.folder.glob('*/state.json')]
            for row in previous:
                if row.get('spec_sha256')==key and row['status']=='succeeded':
                    for n in FILES:self.artifact(row['id'],n)
                    return row
            if len(previous)>=200 or sum(x['parent_run_id']==run_id for x in previous)>=20:raise ValueError('투영 사본 한도: 전체200·원본당20')
            id=uuid.uuid4().hex;d=self.folder/id;d.mkdir();row=dict(id=id,status='running',parent_run_id=run_id,spec_sha256=key,source_id=parent['source_id'],source_checksum=parent['source_checksum'],**req,design_approved=False,manufacturing_verified=False);self.save(d,row)
            c=self.learned.config();env=dict(os.environ,PYTHONPATH=str(self.root/'src'))
            with (d/'worker.log').open('w') as log:
                result=subprocess.run([c['python'],'-m','aurora.sketch_projection','--model',str(model),'--image',str(image),'--output',str(d/'output'),'--settings',json.dumps(req['settings'],allow_nan=False)],cwd=self.root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=60,check=False)
            if result.returncode:raise ValueError('투영 실패: 관리자 로그 확인')
            report=json.loads((d/'output/projection-report.json').read_text())
            if report.get('parent_model_sha256')!=req['parent_model_sha256'] or report.get('source_image_sha256')!=req['source_image_sha256'] or report.get('geometry_preserved') is not True:raise ValueError('투영 결과 출처/형상 검증 실패')
            files=[dict(file=n,bytes=(d/'output'/n).stat().st_size,sha256=sha(d/'output'/n)) for n in sorted(FILES)]
            row.update(status='succeeded',artifacts=files,report=report);self.save(d,row);return row
        except Exception as e:
            if d is not None and row is not None:row.update(status='failed',error='투영 처리 실패');self.save(d,row)
            if isinstance(e,subprocess.TimeoutExpired):raise ValueError('투영 처리 시간 초과') from e
            raise
        finally:self.lock.release()
    def artifact(self,id,name):
        if name not in FILES:raise ValueError('투영 파일명 오류')
        row=self.get(id)
        if not row or row['status']!='succeeded':return None
        meta=next((x for x in row['artifacts'] if x['file']==name),None);p=self.folder/id/'output'/name
        if not meta or not p.is_file() or p.stat().st_size!=meta['bytes'] or sha(p)!=meta['sha256']:raise ValueError('투영 산출물 무결성 오류')
        return p
