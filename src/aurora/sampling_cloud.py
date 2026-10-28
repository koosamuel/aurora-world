"""Authenticated U20/U21 worker: existing validators/geometry/offline AI, private outputs."""
import argparse,json,shutil,threading,time,uuid
from pathlib import Path
from .registered import Remote,RemoteError,env_file
from .sampling import decode,envelope,checksum
from .generation import catalog,generate,digest
from .identity import require,serialized

PROJECT='10000000-0000-4000-8000-000000000002'
MAX=16*1024*1024
class OneBrief:
 def __init__(self,brief):self.brief=brief
 def list(self):return [envelope(self.brief)]
 def get(self,pid,version):return envelope(self.brief) if pid==self.brief['product_id'] and version==self.brief['brief_version'] else None

def source_for(root,brief):
 sources=catalog(root,OneBrief(brief))['sources'];require(len(sources)==1,'원격 생성은 지원하는6개 자체 합성 제품군만 가능합니다.');return sources[0]

def mime(name):return 'model/gltf-binary' if name.endswith('.glb') else 'image/svg+xml' if name.endswith('.svg') else 'image/png' if name.endswith('.png') else 'text/markdown' if name.endswith('.md') else 'application/json'

def provision(remote,root,project=PROJECT):
 require(str(uuid.UUID(project))==PROJECT,'오로라 합성 개발 프로젝트만 등록합니다.');result=[]
 for path in sorted((Path(root)/'configs/examples/sampling').glob('*.json')):
  brief=decode(path.read_bytes());env=envelope(brief);source=source_for(root,brief)
  rows=remote.request('/rest/v1/sampling_briefs?select=id,checksum&project_id=eq.'+project+'&product_id=eq.'+brief['product_id']+'&version=eq.'+str(brief['brief_version']))
  if rows:require(rows[0]['checksum']==env['checksum'],'원격 같은 버전의 다른 명세는 덮어쓰지 않습니다.')
  else:remote.request('/rest/v1/sampling_briefs','POST',body=dict(project_id=project,product_id=brief['product_id'],version=brief['brief_version'],checksum=env['checksum'],envelope=env,source=source))
  result.append(dict(product_id=brief['product_id'],version=brief['brief_version'],checksum=env['checksum'],reused=bool(rows)))
 return result

class SamplingWorker:
 def __init__(self,root,remote=None,worker_id='aurora-development-sampling'):
  self.root=Path(root);self.remote=remote or Remote();self.worker_id=worker_id
 def rpc(self,name,body):return self.remote.request('/rest/v1/rpc/'+name,'POST',body=body,max_bytes=2*1024*1024)
 def ai_available(self):
  from .ai_sampling import runtime
  try:runtime(self.root);return True
  except (ValueError,OSError):return False
 def beat(self):return self.rpc('sampling_worker_beat',dict(p_worker_id=self.worker_id,p_ai_available=self.ai_available()))
 def compute(self,job):
  kind=job['kind'];payload=job['payload']
  if kind=='validate_brief':
   brief=decode(payload['raw_brief'].encode());return dict(envelope=envelope(brief),source=source_for(self.root,brief),validator_sha256=digest(Path(__file__).with_name('sampling.py').read_bytes())),[]
  require(kind in ('geometry','ai'),'원격 작업 종류 오류');source=payload['source'];brief=decode(serialized(source['brief']));require(source==source_for(self.root,brief),'등록 명세/원화/출처 해시 오류')
  ident=str(uuid.UUID(job['id']));project=str(uuid.UUID(job['project_id']));attempt=job['attempt'];require(type(attempt) is int and 1<=attempt<=3,'시도 번호 오류')
  base=self.root/'results/cloud-sampling'/ident/('attempt-'+str(attempt));base.mkdir(parents=True,exist_ok=False)
  if kind=='geometry':result=generate(source,payload['seed'],base/'output');output=base/'output'
  else:
   from .ai_sampling import AIService
   for name in ('src','configs'):(base/name).symlink_to(self.root/name,target_is_directory=True)
   shutil.copy2(self.root/'.ai-local.json',base/'.ai-local.json');service=AIService(base,OneBrief(brief));row,_=service.request(dict(source_id=source['id'],source_checksum=source['checksum'],seed=payload['seed'],request_key=uuid.uuid4().hex));service.work(row['id']);row=service.get(row['id']);require(row['state']=='succeeded','AI 추론 실패: 워커의 실행 로그를 확인하세요.');result=row['result'];output=service.output/row['id']
  artifacts=[]
  for a in result['artifacts']:
   require(a['file'] and '/' not in a['file'] and '\\' not in a['file'],'산출물 이름 오류');raw=(output/a['file']).read_bytes();require(0<len(raw)<=MAX and len(raw)==a['bytes'] and digest(raw)==a['sha256'],'생성 산출물 크기/SHA 오류');path=f"{project}/sampling/{ident}/attempt-{attempt}/{a['sha256']}/{a['file']}";content_type=mime(a['file'])
   try:self.remote.request('/storage/v1/object/aurora-sampling/'+path,'POST',data=raw,content_type=content_type)
   except RemoteError as e:
    if e.status not in (400,409):raise
   stored=self.remote.request('/storage/v1/object/authenticated/aurora-sampling/'+path,raw=True,max_bytes=MAX);require(len(stored)==len(raw) and digest(stored)==a['sha256'],'비공개 업로드 재읽기/SHA 오류')
   artifacts.append(dict(name=a['file'],bucket='aurora-sampling',path=path,sha256=a['sha256'],bytes=len(raw),mime=content_type))
  return result,artifacts
 def once(self):
  self.beat();job=self.rpc('claim_sampling',{})
  if not job:return False
  stop=threading.Event();lost=threading.Event()
  def heartbeat():
   while not stop.wait(20):
    try:
     self.beat()
     if not self.rpc('heartbeat_sampling',dict(p_run_id=job['id'],p_token=job['claim_token'])):lost.set();return
    except Exception:lost.set();return
  thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
  try:
   result,files=self.compute(job)
   require(not lost.is_set(),'작업 선점 만료')
   ok=self.rpc('complete_sampling',dict(p_run_id=job['id'],p_token=job['claim_token'],p_result=result,p_artifacts=files,p_error=None));require(ok,'취소/만료된 시도의 결과는 게시하지 않았습니다.')
   print('Completed sampling:',job['kind'],job['id'],flush=True)
  except Exception as error:
   message=str(error)[:250] if isinstance(error,ValueError) else '샘플 워커 실패: 입력·모델·연결을 확인하세요.'
   self.rpc('complete_sampling',dict(p_run_id=job['id'],p_token=job['claim_token'],p_result=None,p_artifacts=[],p_error=message));print('Sampling job failed:',job['id'],flush=True)
  finally:stop.set();thread.join(timeout=2)
  return True
 def run(self,once=False):
  while True:
   try:found=self.once()
   except Exception:print('Sampling worker connection failed; retrying.',flush=True);found=False
   if once:return
   if not found:time.sleep(10)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--env-file',type=Path,required=True);p.add_argument('--once',action='store_true');p.add_argument('--provision',action='store_true');a=p.parse_args();env_file(a.env_file)
 if a.provision:print(json.dumps(provision(Remote(),a.root),ensure_ascii=False,indent=2))
 else:SamplingWorker(a.root).run(a.once)
