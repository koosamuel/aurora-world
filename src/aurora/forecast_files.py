"""U05/U19 local synthetic browser registration, immutable input and fenced jobs.
Uses existing U22 demo personas, NOT Supabase authentication/membership.
"""
from pathlib import Path
from datetime import datetime,timezone
import csv,io,json,re,time,uuid
from . import inputs
from .identity import require,serialized
from .generation import digest
from .sampling import Conflict,fields
from .sample_reviews import Denied,KEY
from .jobs import Store

DATASET=re.compile(r'weekly-[0-9a-f]{64}\Z')
NAMES=('result.json','predictions.csv','inventory.csv','report.md','input-lineage.json')

def decode(raw):
 require(isinstance(raw,bytes) and 0<len(raw)<=inputs.MAX_BYTES,'파일은 UTF-8 JSON 4 MiB 이하입니다.')
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'중복 JSON 키');d[k]=v
  return d
 def bad(v):raise ValueError('비유한 JSON 수치')
 try:r=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
 except (UnicodeError,RecursionError) as e:raise ValueError('JSON 형식 오류') from e
 require(isinstance(r,dict),'JSON 객체 필요');return r

def prepare(raw):
 payload=decode(raw)
 if payload.get('schema_version')=='aurora-weekly-input-v1':inputs.validate(payload);provenance=dict(kind='weekly_file_v1',quality=inputs.validate(payload))
 elif payload.get('schema_version')=='aurora-identity-weekly-input-v1':
  from .identity_weekly import convert
  payload,provenance=convert(payload)
 else:raise ValueError('합성 weekly-input-v1 또는 identity-weekly-input-v1만 허용합니다.')
 data=inputs.encode(payload);sha=digest(data);provenance.update(raw_sha256=digest(raw),canonical_weekly_sha256=sha,registration_engine_sha256=digest(Path(__file__).read_bytes()))
 return payload,data,provenance

def csv_data(rows):
 stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
 for row in rows:writer.writerow([("'"+v if v and v.lstrip().startswith(('=','+','-','@')) else v) if isinstance(v,str) else v for v in row])
 return stream.getvalue().encode('utf-8-sig')

class ForecastFiles(Store):
 def __init__(self,root,reviews):
  self.root=Path(root);self.reviews=reviews;super().__init__(self.root/'results/forecast-files.sqlite3');self.inputs=self.root/'results/forecast-file-inputs';self.inputs.mkdir(parents=True,exist_ok=True);self.output=self.root/'results/forecast-file-artifacts'
  with self.connect() as db:db.executescript('''CREATE TABLE IF NOT EXISTS file_datasets(id TEXT PRIMARY KEY,version TEXT UNIQUE NOT NULL,status TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,error TEXT);
  CREATE TRIGGER IF NOT EXISTS dataset_body_no_update BEFORE UPDATE OF id,version,metadata,created_at ON file_datasets BEGIN SELECT RAISE(ABORT,'immutable input metadata'); END;
  CREATE TRIGGER IF NOT EXISTS dataset_no_delete BEFORE DELETE ON file_datasets BEGIN SELECT RAISE(ABORT,'immutable input metadata'); END;''')
 def authorize(self,token):
  actor=self.reviews.actor(token)
  if actor['role']!='designer':raise Denied('합성 입력 등록/실행은 가상 작성자 역할만 가능합니다.')
  return actor
 def validate_file(self,token,raw):
  self.authorize(token);payload,data,p=prepare(raw)
  return dict(valid=True,version=payload['version'],canonical_sha256=digest(data),raw_sha256=digest(raw),raw_bytes=len(raw),canonical_bytes=len(data),quality=p['quality'],source_kind=p['kind'],identity_counts=p.get('audit',{}).get('counts'),mapping_version=p.get('mapping_version'),mapping_known_before_first_period=p.get('mapping_known_before_first_period'),scope='self-declared synthetic only; no company authorization or matching accuracy')
 def register(self,token,raw,expected_weekly,expected_raw):
  actor=self.authorize(token);payload,data,provenance=prepare(raw);sha=digest(data)
  if sha!=expected_weekly or digest(raw)!=expected_raw:raise Conflict('검증한 파일과 등록 파일의 해시가 다릅니다.')
  ident='weekly-'+sha;quality=inputs.validate(payload)
  meta=dict(id=ident,name='합성 파일 · '+payload['version'],version=payload['version'],dataset_kind='weekly_file',synthetic=True,generator_config=dict(skus=quality['series'],weeks=quality['weeks'],mode='weekly_file_v1'),sha256=sha,bytes=len(data),raw_sha256=digest(raw),raw_bytes=len(raw),provenance=provenance,registered_by=actor)
  error=None
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM file_datasets WHERE version=?',(payload['version'],)).fetchone()
   if row:
    if row['id']!=ident:raise Conflict('같은 데이터 버전의 다른 파일은 덮어쓸 수 없습니다.')
    if row['status']=='ready':self.read(ident);return dict(**json.loads(row['metadata']),status='ready',reused=True,uploaded_raw_sha256=digest(raw))
    meta=json.loads(row['metadata'])
    require(meta['raw_sha256']==digest(raw),'실패 등록 재시도는 처음과 같은 원문 파일이 필요합니다.')
   else:db.execute('INSERT INTO file_datasets VALUES(?,?,?,?,?,NULL)',(ident,payload['version'],'validating',serialized(meta).decode(),datetime.now(timezone.utc).isoformat()))
   try:
    directory=self.inputs/sha;directory.mkdir(exist_ok=True)
    for name,content in [('source.json',raw),('weekly.json',data)]:
     p=directory/name
     if p.exists():require(p.read_bytes()==content,'기존 입력 파일 손상/충돌')
     else:
      with p.open('xb') as f:f.write(content)
    require((directory/'source.json').stat().st_size==meta['raw_bytes'] and digest((directory/'source.json').read_bytes())==meta['raw_sha256'],'원문 입력 해시 오류')
    require(digest((directory/'weekly.json').read_bytes())==sha,'등록 입력 해시 오류');inputs.decode((directory/'weekly.json').read_bytes())
    db.execute("UPDATE file_datasets SET status='ready',error=NULL WHERE id=?",(ident,))
   except (ValueError,OSError):db.execute("UPDATE file_datasets SET status='rejected',error='입력 보관/검증 실패' WHERE id=?",(ident,));error=ValueError('입력 보관/검증 실패. ready로 등록하지 않았습니다.')
  if error:raise error
  return dict(**meta,status='ready',reused=False)
 def datasets(self,include_rejected=False):
  with self.connect() as db:rows=db.execute('SELECT * FROM file_datasets ORDER BY created_at DESC').fetchall()
  return [dict(**json.loads(r['metadata']),status=r['status'],error=r['error']) for r in rows if include_rejected or r['status']=='ready']
 def read(self,ident):
  require(isinstance(ident,str) and DATASET.fullmatch(ident),'파일 데이터셋 ID 오류')
  with self.connect() as db:row=db.execute('SELECT * FROM file_datasets WHERE id=?',(ident,)).fetchone()
  require(row is not None and row['status']=='ready','준비된 파일 데이터셋이 필요합니다.');meta=json.loads(row['metadata']);base=self.inputs/ident[7:]
  try:raw=(base/'source.json').read_bytes();data=(base/'weekly.json').read_bytes()
  except OSError as e:raise ValueError('등록 입력 파일을 찾을 수 없습니다.') from e
  require(len(raw)==meta['raw_bytes'] and digest(raw)==meta['raw_sha256'] and len(data)==meta['bytes'] and digest(data)==meta['sha256'],'등록 입력 크기/해시 오류')
  payload=inputs.decode(data);require(payload['version']==meta['version'],'파일 버전 불일치');return payload,meta
 def request(self,token,req):
  self.authorize(token);fields(req,{'project_type','dataset_id','request_key','config'},'file run');require(req['project_type']=='forecast','수요예측 파일만 실행합니다.')
  require(isinstance(req['request_key'],str) and KEY.fullmatch(req['request_key']),'요청 키 오류');payload,meta=self.read(req['dataset_id']);options=req['config']
  require(isinstance(options,dict) and not set(options)-{'horizon','season_length','validation_origins'},'파일 실행 설정 오류')
  from .forecast import config_for
  config_for(dict(skus=meta['generator_config']['skus'],weeks=meta['generator_config']['weeks'])|options)
  c=dict(dataset_id=req['dataset_id'],dataset_sha256=meta['sha256'],options=options);h=digest(serialized(c));now=time.time()
  with self.connect() as db:
   db.execute('INSERT OR IGNORE INTO runs(id,project_type,request_key,config,config_hash,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),'forecast',req['request_key'],serialized(c).decode(),h,'queued',now,now));row=db.execute('SELECT * FROM runs WHERE project_type=? AND request_key=?',('forecast',req['request_key'])).fetchone()
   if row['config_hash']!=h:raise Conflict('같은 요청 키의 파일/실행 설정이 다릅니다.')
  return self.decode(row)
 def list_dataset(self,ident):
  self.read(ident)
  with self.connect() as db:rows=db.execute("SELECT * FROM runs WHERE project_type='forecast' ORDER BY created DESC").fetchall()
  return [self.decode(r) for r in rows if json.loads(r['config'])['dataset_id']==ident][:30]
 def get_dataset_run(self,ident,rid):
  require(isinstance(ident,str) and DATASET.fullmatch(ident),'파일 데이터셋 ID 오류');rid=str(uuid.UUID(rid));row=self.get(rid,'forecast')
  return row if row and row['config']['dataset_id']==ident else None
 def cancel_run(self,token,ident,rid):
  self.authorize(token)
  if not self.get_dataset_run(ident,rid):return None
  return self.cancel(rid,'forecast')
 def work_once(self):
  job=self.claim()
  if not job:return False
  try:
   payload,meta=self.read(job['config']['dataset_id']);require(meta['sha256']==job['config']['dataset_sha256'],'작업 입력 버전 변경')
   result=inputs.run_input(payload,job['config']['options']);result['file_registration']=dict(dataset_id=meta['id'],raw_sha256=meta['raw_sha256'],canonical_sha256=meta['sha256'],source_kind=meta['provenance']['kind'],mapping_version=meta['provenance'].get('mapping_version'),mapping_sha256=meta['provenance'].get('mapping_sha256'),identity_counts=meta['provenance'].get('audit',{}).get('counts'),worker_engine_sha256=digest(Path(__file__).read_bytes()))
   from .reports import decision_report
   predictions=[['sku','split','origin','horizon','model','actual','predicted','mase_scale']]+[[r[k] for k in ('sku','split','origin','horizon','model','actual','predicted','mase_scale')] for r in result['predictions']]
   inventory=[['sku','role','policy','fill_rate','average_on_hand','average_pipeline','invested_krw']]+[[r.get(k) for k in ('sku','role','policy','fill_rate','average_on_hand','average_pipeline','invested_krw')] for r in result['decisions']['inventory']['details']]
   report=decision_report(result)+'\n\n## 브라우저 입력·ID 감사 연결\n\n이 실행은 등록한 관측 출하 파일을 읽었으며 생성기를 다시 실행하지 않았다. 누락/품절은 실제 수요가 아니고 금액은 공통 가상 정책이다. ID 연결 입력은 전부 감사 통과·최초 관측 전 known_at·완결 그리드 선언을 요구한다. 기업 대응 승인·매칭 성능/ERP 연동·실제 비용·독립 구간 보정은 미검증이다.\n\n'+json.dumps(result['file_registration'],ensure_ascii=False,indent=2)
   files={'result.json':serialized(result),'predictions.csv':csv_data(predictions),'inventory.csv':csv_data(inventory),'report.md':report.encode(),'input-lineage.json':serialized(dict(dataset=meta,config=job['config'],run_id=job['id'],attempt=job['attempt']))}
   directory=self.output/job['id']/('attempt-'+str(job['attempt']));directory.mkdir(parents=True,exist_ok=False);artifacts=[]
   for name,raw in files.items():
    (directory/name).write_bytes(raw);artifacts.append(dict(name=name,bytes=len(raw),sha256=digest(raw),mime='application/json' if name.endswith('.json') else 'text/csv' if name.endswith('.csv') else 'text/markdown',url='./api/forecast-files/artifacts/'+job['id']+'/'+name))
   (directory/'manifest.json').write_bytes(serialized(dict(input_sha256=meta['sha256'],run_id=job['id'],attempt=job['attempt'],files=artifacts)));result['artifacts']=artifacts;self.finish(job,result)
  except Exception:self.finish(job,error='합성 파일 실행 실패: 입력/설정·보관 파일 해시를 확인하세요.')
  return True
 def artifact(self,rid,name):
  require(name in (*NAMES,'manifest.json'),'파일 산출물 이름 오류');rid=str(uuid.UUID(rid));row=self.get(rid,'forecast')
  if not row or row['status']!='succeeded':return None
  p=self.output/rid/('attempt-'+str(row['attempt']))/name
  if name=='manifest.json':
   expected=serialized(dict(input_sha256=row['config']['dataset_sha256'],run_id=rid,attempt=row['attempt'],files=row['result']['artifacts']));require(p.is_file() and p.read_bytes()==expected,'실행 명세 손상')
  else:
   meta=next(a for a in row['result']['artifacts'] if a['name']==name);require(p.is_file() and p.stat().st_size==meta['bytes'] and digest(p.read_bytes())==meta['sha256'],'실행 산출물 크기/해시 오류')
  return p
