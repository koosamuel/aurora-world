"""Bounded loopback-only neural 3D jobs. Uploaded images never leave this machine."""
import io,json,os,re,subprocess,threading,uuid
from pathlib import Path
from .sketch_fit import decode
from .generation import catalog
from .learned3d_worker import sha

FILES={'condition.png','model.glb','report.json'}
class Learned3DService:
    def __init__(self,root,briefs):
        self.root=Path(root);self.briefs=briefs;self.jobs=self.root/'results/learned3d';self.lock=threading.Lock()
        self.jobs.mkdir(parents=True,exist_ok=True)
        for p in self.jobs.glob('*/state.json'):
            row=json.loads(p.read_text())
            if row['status'] in ('queued','running'):row.update(status='failed',error='서버 재시작으로 중단');self.save(p.parent,row)
    def config(self):
        p=self.root/'.learned3d-local.json'
        if not p.is_file():raise ValueError('로컬 TripoSR 설정 및 모델 설치 필요')
        c=json.loads(p.read_text())
        if not isinstance(c,dict) or not {'python','source','weights','revision'}<=set(c):raise ValueError('로컬 모델 설정 필드 누락')
        for k in ('python','source','weights'):
            if not isinstance(c[k],str) or not Path(c[k]).is_absolute() or not Path(c[k]).exists():raise ValueError('모델 경로 확인 필요: '+k)
        if not (Path(c['weights'])/'model.ckpt').is_file():raise ValueError('모델 다운로드 미완료')
        return c
    def capabilities(self):
        try:self.config();return dict(available=True,engine='TripoSR',local_only=True)
        except (ValueError,KeyError):return dict(available=False,reason='로컬 TripoSR 설정/가중치 설치 필요')
    def save(self,d,row):
        p=d/'state.tmp';p.write_text(json.dumps(row,ensure_ascii=False));p.replace(d/'state.json')
    def get(self,id):
        if not re.fullmatch('[0-9a-f]{32}',id):raise ValueError('실행 ID 오류')
        p=self.jobs/id/'state.json';return json.loads(p.read_text()) if p.is_file() else None
    def request(self,raw,pool):
        c=self.config(); req,image=decode(raw,views=('single',))
        if 'source_id' not in req:raise ValueError('기존 U20 명세 연결 필요')
        s=next((x for x in catalog(self.root,self.briefs)['sources'] if x['id']==req['source_id']),None)
        if not s or s['data_kind']!='synthetic' or s['family']!='BUNNY' or s['checksum']!=req['source_checksum'] or s['dimensions_mm']!=req['dimensions_mm']:raise ValueError('토끼 명세/해시/치수를 다시 선택하세요.')
        from PIL import Image,ImageOps,UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(image)) as im:
                if im.format not in ('PNG','JPEG') or getattr(im,'n_frames',1)!=1 or min(im.size)<32 or im.width*im.height>8_000_000:raise ValueError('단일 PNG/JPEG, 32px 이상·8백만 픽셀 이하 필요')
                im.load();im=ImageOps.exif_transpose(im).convert('RGBA');im.thumbnail((1536,1536));safe=im.copy()
        except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as e:raise ValueError('이미지 오류') from e
        if len(list(self.jobs.iterdir()))>=100:raise ValueError('최대 100회 실행 한도')
        if not self.lock.acquire(blocking=False):raise RuntimeError('학습형 3D 생성이 이미 진행 중입니다.')
        try:
            id=uuid.uuid4().hex;d=self.jobs/id;d.mkdir();safe.save(d/'input.png')
            row=dict(id=id,status='queued',engine='TripoSR',source_id=s['id'],source_checksum=s['checksum'],requested_dimensions_mm=s['dimensions_mm'],input_sha256=sha(d/'input.png'),dimensions_verified=False,design_approved=False,manufacturing_verified=False)
            self.save(d,row);pool.submit(self.work,d,row,c);return row
        except BaseException:self.lock.release();raise
    def work(self,d,row,c):
        try:
            row=dict(row,status='running');self.save(d,row)
            env=dict(os.environ,PYTHONPATH=str(self.root/'src'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
            commands=[['-m','aurora.learned3d_segment','--input',str(d/'input.png'),'--output',str(d/'foreground.png')],
                ['-m','aurora.learned3d_worker','--root',str(self.root),'--input',str(d/'foreground.png'),'--output',str(d/'output'),'--resolution','192']]
            with (d/'worker.log').open('w') as log:
                for cmd in commands:
                    result=subprocess.run([c['python'],*cmd],cwd=self.root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=1200,check=False)
                    if result.returncode:raise RuntimeError('로컬 모델 실행 실패: 관리자 worker.log 확인')
            report=json.loads((d/'output/report.json').read_text())
            files=[dict(file=n,bytes=(d/'output'/n).stat().st_size,sha256=sha(d/'output'/n)) for n in sorted(FILES)]
            row.update(status='succeeded',artifacts=files,report=report)
        except Exception as e:row.update(status='failed',error=str(e)[:250])
        finally:
            try:self.save(d,row)
            finally:self.lock.release()
    def artifact(self,id,name):
        if name not in FILES:raise ValueError('산출물 경로 오류')
        row=self.get(id)
        if not row or row['status']!='succeeded':return None
        meta=next((x for x in row['artifacts'] if x['file']==name),None);p=self.jobs/id/'output'/name
        if not meta or not p.is_file() or p.stat().st_size!=meta['bytes'] or sha(p)!=meta['sha256']:raise ValueError('산출물 무결성 오류')
        return p
