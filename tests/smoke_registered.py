"""Manual synthetic-only registered-input and Storage/RLS live verification."""
import hashlib,json,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from aurora.registered import Remote,env_file,read_registered,provision
from aurora.inputs import load,run_input
from aurora.cloud import SupabaseWorker
root=Path(__file__).resolve().parents[1];env_file(root/'.env.local');remote=Remote()
assert remote.url=='https://unajjkuccpqggulpqhmo.supabase.co'
public='sb_publishable_Am3Fg6z4G2oOWKEfE_xUzA_ZWLRh9rJ';project='10000000-0000-4000-8000-000000000001'
rows=remote.request('/rest/v1/datasets?select=*&project_id=eq.'+project+'&version=eq.research-informed-synthetic-v1-weekly-v1');assert len(rows)==1;dataset=rows[0]
payload=read_registered(remote,dataset['generator_config'],project);assert len(payload['series'])==100
second=provision(remote,payload,project);assert second['reused'] and second['dataset_id']==dataset['id']
credentials=json.loads((root/'results/smoke_auth.json').read_text())
def call(path,method='GET',body=None,token=None,raw=False):
 headers={'apikey':public,'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 req=Request(remote.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
 try:
  with urlopen(req,timeout=60) as res:
   b=res.read();return b if raw else json.loads(b) if b else None
 except HTTPError as e:return {'denied':e.code}
session=call('/auth/v1/token?grant_type=password','POST',{k:credentials[k] for k in ('email','password')});token=session['access_token']
request=dict(p_project_id=project,p_dataset_id=dataset['id'],p_idempotency_key='file-smoke-'+str(uuid.uuid4()),p_config={'horizon':4,'season_length':52,'validation_origins':3})
run=call('/rest/v1/rpc/request_forecast','POST',request,token);assert 'id' in run
assert call('/rest/v1/rpc/request_forecast','POST',request,token)['id']==run['id']
SupabaseWorker().once()
result=call('/rest/v1/runs?id=eq.'+run['id'],token=token)[0];assert result['status']=='succeeded';r=result['result']
assert r['quality']['series']==100 and r['input_manifest']['file_sha256']==dataset['generator_config']['input']['sha256']
assert r==run_input(payload,request['p_config'])
path='/storage/v1/object/authenticated/aurora-artifacts/'+dataset['generator_config']['input']['path']
member_file=call(path,token=token,raw=True);assert isinstance(member_file,bytes) and hashlib.sha256(member_file).hexdigest()==dataset['generator_config']['input']['sha256']
assert call(path).get('denied') in (400,401,403,404)
# Read-only runner cannot upload a new object or rewrite dataset metadata.
assert call('/storage/v1/object/aurora-artifacts/'+project+'/inputs/denied-'+str(uuid.uuid4())+'.json','POST',{'synthetic':True},token).get('denied') in (400,401,403,404)
assert call('/rest/v1/datasets?id=eq.'+dataset['id'],'PATCH',{'status':'rejected'},token).get('denied') in (401,403)
call('/auth/v1/logout','POST',{},token)
report=dict(passed=True,run_id=run['id'],dataset_id=dataset['id'],input_sha256=dataset['generator_config']['input']['sha256'],quality=r['quality'],checks=['private upload/read/validation before ready','same-version idempotency','real Auth request and file worker computation','remote result equals local file computation','member Storage read','anonymous Storage denied','runner upload denied','runner metadata update denied'],paired_metrics=r['decisions']['paired_metrics'])
(root/'results/live_registered_input.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='paired_metrics'},ensure_ascii=False,indent=2))
