"""Explicit manual live smoke test for a synthetic-only Aurora development project."""
import json,os,secrets,time,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from aurora.cloud import SupabaseWorker
root=Path(__file__).resolve().parents[1]
for line in (root/'.env.local').read_text().splitlines():
 if '=' in line:
  key,value=line.split('=',1)
  if key in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'):os.environ[key]=value
url=os.environ['SUPABASE_URL'];service=os.environ['SUPABASE_SERVICE_ROLE_KEY']
public='sb_publishable_Am3Fg6z4G2oOWKEfE_xUzA_ZWLRh9rJ'
def call(path,method='GET',body=None,token=None,key=None):
 headers={'apikey':key or service,'Content-Type':'application/json'}
 if token:headers['Authorization']='Bearer '+token
 elif key is None:headers['Authorization']='Bearer '+service
 request=Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
 try:
  with urlopen(request,timeout=60) as response:
   data=response.read();return json.loads(data) if data else None
 except HTTPError as e:raise RuntimeError(f'{method} {path.split("?")[0]}: HTTP {e.code}') from None
assert url=='https://unajjkuccpqggulpqhmo.supabase.co','Wrong development project'
project='10000000-0000-4000-8000-000000000001';label='10000000-0000-4000-8000-000000000002';dataset='20000000-0000-4000-8000-000000000001'
statefile=root/'results/smoke_auth.json';statefile.parent.mkdir(exist_ok=True)
if statefile.exists():credentials=json.loads(statefile.read_text())
else:
 credentials={'email':'aurora-smoke-test@example.invalid','password':secrets.token_urlsafe(30)}
 user=call('/auth/v1/admin/users','POST',credentials|{'email_confirm':True})
 credentials['user_id']=user['id'];statefile.write_text(json.dumps(credentials));statefile.chmod(0o600)
# Only synthetic projects; no invitation/email is sent to a real recipient.
for pid,role in [(project,'runner'),(label,'viewer')]:
 try:
  call('/rest/v1/project_members','POST',{'project_id':pid,'user_id':credentials['user_id'],'role':role})
 except RuntimeError as e:
  if 'HTTP 409' not in str(e):raise
session=call('/auth/v1/token?grant_type=password','POST',{k:credentials[k] for k in ('email','password')},key=public)
token=session['access_token']
projects=call('/rest/v1/projects?select=id,project_type',token=token,key=public);assert {p['id'] for p in projects}=={project,label}
request={'p_project_id':project,'p_dataset_id':dataset,'p_idempotency_key':'smoke-'+str(uuid.uuid4()),'p_config':{'horizon':4,'season_length':52,'validation_origins':3}}
run=call('/rest/v1/rpc/request_forecast','POST',request,token=token,key=public)
assert call('/rest/v1/rpc/request_forecast','POST',request,token=token,key=public)['id']==run['id']
worker=SupabaseWorker();worker.once()
rows=call('/rest/v1/runs?id=eq.'+run['id']+'&project_id=eq.'+project,token=token,key=public)
assert rows[0]['status']=='succeeded',rows[0]['status']
result=rows[0]['result'];assert result['synthetic'] and result['quality']['series']==50
assert result['decisions']['schema_version']=='aurora-decisions-v1'
assert len(result['decisions']['paired_metrics'])==8
assert len(result['decisions']['inventory']['scenarios'])==4
try:call('/rest/v1/rpc/claim_run','POST',{},token=token,key=public);raise AssertionError('Browser could claim worker job')
except RuntimeError as e:assert 'HTTP 40' in str(e)
try:anonymous=call('/rest/v1/runs?select=id',key=public);assert anonymous==[]
except RuntimeError as e:assert 'HTTP 40' in str(e)
call('/auth/v1/logout','POST',{},token=token,key=public)
report={'passed':True,'project_ref':'unajjkuccpqggulpqhmo','region':'ap-northeast-2','run_id':run['id'],'status':'succeeded','checks':['real Auth login/logout','RLS member projects','idempotent RPC request','service worker claim/compute/complete','completed baseline + segments + model selection + inventory result fetch','browser worker-RPC denied','anonymous results denied'],'paired_metrics':result['paired_metrics'],'test_user':'synthetic test identity only; credentials in ignored local results, not repository'}
(root/'results/live_supabase_smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='paired_metrics'},ensure_ascii=False,indent=2))
