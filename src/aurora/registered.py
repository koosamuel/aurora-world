"""Worker-only immutable synthetic input provisioning in existing private Storage.

Browser roles retain read-only membership policies; this does not grant uploads.
"""
import argparse,hashlib,json,os,re,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote,urlsplit
from .inputs import encode,decode,load,validate,run_input,MAX_BYTES,require

class RemoteError(RuntimeError):
    def __init__(self,status):self.status=status;super().__init__(f'Supabase 요청 실패 (HTTP {status})')

class Remote:
    def __init__(self):
        self.url=os.environ.get('SUPABASE_URL','').rstrip('/');self.secret=os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')
        u=urlsplit(self.url);require(u.scheme=='https' and u.hostname and u.path=='' and not u.query and not u.fragment and not u.username and not u.password and self.secret,'워커 URL/비밀 설정을 확인하세요.')
    def request(self,path,method='GET',body=None,data=None,raw=False):
        require(path.startswith(('/rest/v1/','/storage/v1/')),'서버 경로를 확인하세요.')
        headers={'apikey':self.secret,'Authorization':'Bearer '+self.secret,'Content-Type':'application/json'}
        if body is not None:data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
        req=Request(self.url+path,data=data,headers=headers,method=method)
        try:
            with urlopen(req,timeout=60) as response:
                data=response.read(MAX_BYTES+1);require(len(data)<=MAX_BYTES,'서버 응답 크기 초과입니다.')
                return data if raw else json.loads(data) if data else None
        except HTTPError as e:raise RemoteError(e.code) from None

def read_registered(remote,config,project_id):
    require(config.get('mode')=='weekly_file_v1','지원하는 파일 입력 모드가 아닙니다.')
    source=config.get('input');require(isinstance(source,dict) and set(source)=={'bucket','path','sha256','bytes'},'파일 메타데이터를 확인하세요.')
    digest=source['sha256'];require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),'파일 해시를 확인하세요.')
    project=str(uuid.UUID(project_id));require(source['bucket']=='aurora-artifacts' and source['path']==f'{project}/inputs/{digest}.json','프로젝트별 파일 경로가 다릅니다.')
    require(type(source['bytes']) is int and 0<source['bytes']<=MAX_BYTES,'등록 파일 크기를 확인하세요.')
    data=remote.request('/storage/v1/object/authenticated/aurora-artifacts/'+source['path'],raw=True)
    require(len(data)==source['bytes'] and hashlib.sha256(data).hexdigest()==digest,'등록된 입력 파일의 크기/해시가 다릅니다.')
    payload=decode(data);q=validate(payload)
    require(q['series']==config.get('skus') and q['weeks']==config.get('weeks'),'등록된 품목/기간 수와 입력이 다릅니다.')
    return payload

def provision(remote,payload,project_id):
    """Validate -> validating metadata -> immutable upload -> read/validate -> ready."""
    project=str(uuid.UUID(project_id));data=encode(payload);q=validate(payload);checksum=hashlib.sha256(data).hexdigest();version=payload['version']
    projects=remote.request('/rest/v1/projects?select=id,project_type&id=eq.'+project)
    require(len(projects)==1 and projects[0]['project_type']=='forecast','수요예측 프로젝트가 필요합니다.')
    config=dict(seed=42,skus=q['series'],weeks=q['weeks'],assumption_version='file-input-A01-A11-v1',mode='weekly_file_v1',input=dict(bucket='aurora-artifacts',path=f'{project}/inputs/{checksum}.json',sha256=checksum,bytes=len(data)))
    query='/rest/v1/datasets?project_id=eq.'+project+'&version=eq.'+quote(version,safe='')
    def existing():
        rows=remote.request(query+'&select=id,status,generator_config');return rows[0] if rows else None
    row=existing()
    if row:
        require(row['generator_config']==config,'같은 버전의 다른 입력을 덮어쓸 수 없습니다.')
        if row['status']=='ready':read_registered(remote,config,project);return dict(dataset_id=row['id'],version=version,status='ready',sha256=checksum,reused=True)
    else:
        ident=str(uuid.uuid4())
        try:remote.request('/rest/v1/datasets','POST',body=dict(id=ident,project_id=project,name=f'연구 참고 합성 입력 · {q["series"]} SKU',version=version,synthetic=True,status='validating',generator_config=config))
        except RemoteError as e:
            if e.status!=409:raise
        row=existing();require(row is not None and row['generator_config']==config,'등록 충돌 또는 버전 불일치입니다.')
    ident=row['id'];row_path='/rest/v1/datasets?id=eq.'+ident
    try:
        remote.request(row_path,'PATCH',body={'status':'validating'})
        try:remote.request('/storage/v1/object/aurora-artifacts/'+config['input']['path'],'POST',data=data)
        except RemoteError as e:
            # Storage may return 400 or 409 for an existing object. Verify, never overwrite.
            if e.status not in (400,409):raise
        read_registered(remote,config,project)
        remote.request(row_path,'PATCH',body={'status':'ready'})
    except Exception:
        remote.request(row_path,'PATCH',body={'status':'rejected'});raise
    return dict(dataset_id=ident,version=version,status='ready',sha256=checksum,reused=False)

def compute_job(remote,job):
    config=job['generator_config']
    if config.get('mode')=='weekly_file_v1':
        rows=remote.request('/rest/v1/runs?select=project_id&id=eq.'+str(uuid.UUID(job['id'])))
        require(len(rows)==1,'작업 프로젝트가 없습니다.')
        payload=read_registered(remote,config,rows[0]['project_id']);return run_input(payload,job['config'])
    require('mode' not in config and 'input' not in config,'알 수 없는 입력 모드입니다.')
    from .forecast import run_baseline
    return run_baseline(config|job['config'])

def env_file(path):
    for line in Path(path).read_text().splitlines():
        if '=' in line:
            key,value=line.split('=',1)
            if key in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'):os.environ[key]=value

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--project',required=True);p.add_argument('--env-file',type=Path,required=True);a=p.parse_args()
    payload=load(a.input);env_file(a.env_file);print(json.dumps(provision(Remote(),payload,a.project),ensure_ascii=False,indent=2))
