"""Bounded local neural 3D jobs with mandatory foreground review before inference."""
import hashlib,io,json,os,re,subprocess,threading,uuid
from pathlib import Path
from .sketch_fit import decode
from .generation import catalog
from .learned3d_worker import sha

FILES={'condition.png','model.glb','report.json'}
PREVIEW_FILES={'preview.png','mask.png','preflight.json'}
ENGINES={'TripoSR','TripoSG-scribble'}
def confirmation(raw):
    def pairs(items):
        if len(dict(items))!=len(items):raise ValueError('중복 JSON 키')
        return dict(items)
    try:req=json.loads(raw,object_pairs_hook=pairs)
    except (RecursionError,UnicodeDecodeError) as e:raise ValueError('JSON 오류') from e
    if not isinstance(req,dict) or set(req)!={'preparation_sha256','foreground_confirmed'} or req['foreground_confirmed'] is not True or not isinstance(req['preparation_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',req['preparation_sha256']):raise ValueError('미리보기 해시와 명시적 보존 확인 필요')
    return req

class Learned3DService:
    def __init__(self,root,briefs):
        self.root=Path(root);self.briefs=briefs;self.jobs=self.root/'results/learned3d';self.lock=threading.Lock()
        self.jobs.mkdir(parents=True,exist_ok=True)
        for p in self.jobs.glob('*/state.json'):
            row=json.loads(p.read_text())
            if row['status'] in ('preparing','queued','running'):
                row.update(status='failed',error='서버 재시작으로 중단');self.save(p.parent,row)
    def config(self):
        p=self.root/'.learned3d-local.json'
        if not p.is_file():raise ValueError('로컬 모델 설정 필요')
        c=json.loads(p.read_text())
        if not isinstance(c,dict):raise ValueError('모델 설정 객체 필요')
        engine=c.get('engine','TripoSR')
        if engine not in ENGINES:raise ValueError('미지원 엔진')
        keys=('python','source','weights') if engine=='TripoSR' else ('python','triposg_source','triposg_weights')
        for k in keys:
            if not isinstance(c.get(k),str) or not Path(c[k]).is_absolute() or not Path(c[k]).exists():raise ValueError('모델 경로 확인 필요: '+k)
        weight=Path(c['weights'])/'model.ckpt' if engine=='TripoSR' else Path(c['triposg_weights'])/'transformer/diffusion_pytorch_model.safetensors'
        if not weight.is_file():raise ValueError('모델 다운로드 미완료')
        return dict(c,engine=engine)
    def capabilities(self):
        try:
            c=self.config();return dict(available=True,engine=c['engine'],local_only=True,requires_confirmation=True,texture_generated=False if c['engine']=='TripoSG-scribble' else None)
        except (ValueError,KeyError,TypeError):return dict(available=False,reason='로컬 모델 설정/가중치 설치 필요')
    def save(self,d,row):
        p=d/'state.tmp';p.write_text(json.dumps(row,ensure_ascii=False,allow_nan=False));p.replace(d/'state.json')
    def get(self,id):
        if not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('실행 ID 오류')
        p=self.jobs/id/'state.json';return json.loads(p.read_text()) if p.is_file() else None
    def source(self,req):
        s=next((x for x in catalog(self.root,self.briefs)['sources'] if x['id']==req.get('source_id')),None)
        dims=req.get('dimensions_mm',req.get('requested_dimensions_mm'))
        if not s or s['data_kind']!='synthetic' or s['family']!='BUNNY' or s['checksum']!=req.get('source_checksum') or s['dimensions_mm']!=dims:raise ValueError('토끼 명세/해시/치수를 다시 선택하세요.')
        return s
    def file_meta(self,p):return dict(file=p.name,bytes=p.stat().st_size,sha256=sha(p))
    def request(self,raw,pool=None):
        """Prepare only. No GPU inference before a separate confirmation request."""
        c=self.config();req,image=decode(raw,views=('single',));s=self.source(req)
        from PIL import Image,ImageOps,UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(image)) as im:
                if im.format not in ('PNG','JPEG') or getattr(im,'n_frames',1)!=1 or min(im.size)<32 or im.width*im.height>8_000_000:raise ValueError('단일 PNG/JPEG, 32px 이상·8백만 픽셀 이하 필요')
                im.load();im=ImageOps.exif_transpose(im).convert('RGBA');im.thumbnail((1536,1536));safe=im.copy()
        except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as e:raise ValueError('이미지 오류') from e
        if not self.lock.acquire(blocking=False):raise RuntimeError('다른 준비/3D 생성이 진행 중입니다.')
        d=None;row=None
        try:
            if len(list(self.jobs.iterdir()))>=100:raise ValueError('최대100회 저장 한도')
            id=uuid.uuid4().hex;d=self.jobs/id;d.mkdir();safe.save(d/'input.png')
            row=dict(id=id,status='preparing',engine=c['engine'],source_id=s['id'],source_checksum=s['checksum'],requested_dimensions_mm=s['dimensions_mm'],input_sha256=sha(d/'input.png'),dimensions_verified=False,design_approved=False,manufacturing_verified=False)
            self.save(d,row)
            env=dict(os.environ,PYTHONPATH=str(self.root/'src'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
            with (d/'preflight.log').open('w') as log:
                result=subprocess.run([c['python'],'-m','aurora.learned3d_segment','--input',str(d/'input.png'),'--output',str(d/'preview'),'--preflight'],cwd=self.root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=60,check=False)
            if result.returncode:raise ValueError('입력 분리 실패. 밝은 배경/투명 PNG를 확인하세요.')
            files=[self.file_meta(d/'preview'/n) for n in sorted(PREVIEW_FILES)]
            row.update(status='prepared',preparation_artifacts=files,foreground_sha256=sha(d/'preview/foreground.png'),preflight=json.loads((d/'preview/preflight.json').read_text()))
            row['preparation_sha256']=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            self.save(d,row);return row
        except Exception as exc:
            if d is not None and row is not None:
                row.update(status='failed',error='입력 준비 실패');self.save(d,row)
            if isinstance(exc,subprocess.TimeoutExpired):raise ValueError('입력 준비 시간 초과') from exc
            raise
        finally:self.lock.release()
    def confirm(self,id,raw,pool):
        req=confirmation(raw);row=self.get(id)
        if not row or req['preparation_sha256']!=row.get('preparation_sha256'):raise ValueError('준비 입력/해시가 다릅니다.')
        if row['status'] in ('queued','running','succeeded'):return row
        if row['status']!='prepared':raise ValueError('입력을 다시 준비하세요.')
        if not self.lock.acquire(blocking=False):raise RuntimeError('다른 준비/3D 생성이 진행 중입니다.')
        try:
            row=self.get(id)
            if row['status']!='prepared':raise ValueError('준비 상태 변경')
            self.source(row);c=self.config()
            if c['engine']!=row['engine']:raise ValueError('엔진 변경: 입력을 다시 준비하세요.')
            d=self.jobs/id
            if not (d/'input.png').is_file() or not (d/'preview/foreground.png').is_file() or sha(d/'input.png')!=row['input_sha256'] or sha(d/'preview/foreground.png')!=row['foreground_sha256']:raise ValueError('준비 입력 손상')
            for meta in row['preparation_artifacts']:
                p=d/'preview'/meta['file']
                if not p.is_file() or p.stat().st_size!=meta['bytes'] or sha(p)!=meta['sha256']:raise ValueError('미리보기 손상')
            row.update(status='queued',foreground_confirmed=True);self.save(d,row);pool.submit(self.work,d,row,c);return row
        except BaseException:self.lock.release();raise
    def work(self,d,row,c):
        try:
            row=dict(row,status='running');self.save(d,row)
            env=dict(os.environ,PYTHONPATH=str(self.root/'src'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
            module='aurora.triposg_worker' if row['engine']=='TripoSG-scribble' else 'aurora.learned3d_worker'
            command=[c['python'],'-m',module,'--root',str(self.root),'--input',str(d/'preview/foreground.png'),'--output',str(d/'output')]
            if row['engine']=='TripoSR':command+=['--resolution','192']
            with (d/'worker.log').open('w') as log:
                result=subprocess.run(command,cwd=self.root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=1200,check=False)
                if result.returncode:raise RuntimeError('로컬 모델 실패: 관리자 worker.log 확인')
            report=json.loads((d/'output/report.json').read_text());report.update(preparation_sha256=row['preparation_sha256'],original_input_sha256=row['input_sha256'],foreground_confirmed=True,source_id=row['source_id'],source_checksum=row['source_checksum'])
            (d/'output/report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            row.update(status='succeeded',artifacts=[self.file_meta(d/'output'/n) for n in sorted(FILES)],report=report)
        except Exception as e:row.update(status='failed',error=str(e)[:250])
        finally:
            try:self.save(d,row)
            finally:self.lock.release()
    def artifact(self,id,name):
        if name not in FILES|PREVIEW_FILES:raise ValueError('산출물 경로 오류')
        row=self.get(id)
        if not row:return None
        if name in PREVIEW_FILES:folder='preview';meta=next((x for x in row.get('preparation_artifacts',[]) if x['file']==name),None)
        else:
            if row['status']!='succeeded':return None
            folder='output';meta=next((x for x in row['artifacts'] if x['file']==name),None)
        p=self.jobs/id/folder/name
        if not meta:return None
        if not p.is_file() or p.stat().st_size!=meta['bytes'] or sha(p)!=meta['sha256']:raise ValueError('산출물 무결성 오류')
        return p
