"""U24 synthetic, paired descriptive measurement. Never real/causal business effects."""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import copy,csv,io,json,re,shutil,sqlite3,uuid
from .identity import require,serialized,text,iso
from .sampling import fields,integer,product,timestamp,Conflict
from .sample_reviews import Denied,KEY
from .generation import digest

STUDY=re.compile(r'SYN-EFFECT-[A-Z0-9_-]{1,50}\Z');HEX=re.compile(r'[0-9a-f]{64}\Z')
DEFINITION='calendar_brief_to_final_review_v1'
BASELINE_TIME='합성 기준: 명세 접수부터 기존 샘플 최종 검토 완료까지의 달력 경과시간'
METRICS={'sample_units':('실물 제작 수량','개'),'make_events':('실물 제작 사건','회'),'elapsed_hours':('개발 달력 경과시간','시간'),'bom_errors':('BOM 오류 수정 사건','건')}
SCOPE='합성 짝 비교의 기술통계입니다. 실제 기업 효과·인과 효과·BOM 정확도/오류율·비용 절감은 미측정입니다.'
FILES=('report.json','report.md','products.csv','events.csv','lineage.json')

def engine():return digest(Path(__file__).read_bytes())
def study(value):require(isinstance(value,str) and STUDY.fullmatch(value),'합성 study_id 형식 오류')
def sha(value):require(isinstance(value,str) and HEX.fullmatch(value),'SHA-256 형식 오류')
def decode(raw):
 require(len(raw)<=128*1024,'효과 입력은128 KiB 이하입니다.')
 def pairs(items):
  r={}
  for k,v in items:require(k not in r,'중복 JSON 키');r[k]=v
  return r
 def bad(v):raise ValueError('비유한 JSON 값')
 try:r=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
 except (UnicodeError,RecursionError) as e:raise ValueError('효과 JSON 형식 오류') from e
 require(isinstance(r,dict),'JSON 객체 필요');return r

def validate(spec):
 fields(spec,{'schema_version','data_kind','study_id','version','previous_sha256','reason','assumptions','pairs'},'effect input')
 require(spec['schema_version']=='aurora-sampling-effect-input-v1' and spec['data_kind']=='synthetic','자체 합성 효과 입력만 허용합니다.')
 study(spec['study_id']);integer(spec['version'],'version',1,1000);text(spec['reason'],'reason',2000);text(spec['assumptions'],'assumptions',3000)
 require((spec['version']==1)==(spec['previous_sha256'] is None),'최초 버전만 부모 해시가 없습니다.')
 if spec['previous_sha256'] is not None:sha(spec['previous_sha256'])
 require(isinstance(spec['pairs'],list) and 1<=len(spec['pairs'])<=40,'제품 짝은1~40개');seen=set()
 for row in spec['pairs']:
  fields(row,{'product_id','baseline_version','baseline_checksum','definition_id','scope_id','baseline_coverage','pilot','anchor'},'product pair')
  pid=row['product_id'];product(pid);require(pid not in seen,'제품 짝 중복');seen.add(pid);integer(row['baseline_version'],'baseline_version');sha(row['baseline_checksum'])
  for k in ('definition_id','scope_id'):text(row[k],k,100)
  fields(row['baseline_coverage'],{'physical_complete','bom_complete'},'baseline coverage')
  require(all(type(v) is bool for v in row['baseline_coverage'].values()),'현행 관측 완결성은 boolean')
  if row['anchor'] is not None:
   fields(row['anchor'],{'link_version','link_sha256'},'workflow anchor');integer(row['anchor']['link_version'],'link version');sha(row['anchor']['link_sha256'])
  p=row['pilot'];fields(p,{'status','window_start','window_end','started_at','ended_at','definition_id','scope_id','physical_complete','bom_complete','physical_samples','bom_changes'},'pilot')
  require(p['status'] in ('complete','in_progress','unmeasured'),'관측 상태 오류')
  for k in ('window_start','window_end'):iso(p[k],k)
  require(p['window_start']<=p['window_end'],'관측창 순서 오류')
  for k in ('definition_id','scope_id'):text(p[k],k,100)
  require(type(p['physical_complete']) is bool and type(p['bom_complete']) is bool,'시범 관측 완결성은 boolean')
  for k in ('physical_samples','bom_changes'):require(isinstance(p[k],list) and len(p[k])<=100,'사건 배열/개수 오류')
  if p['status']=='unmeasured':
   require(p['started_at'] is None and p['ended_at'] is None and not p['physical_samples'] and not p['bom_changes'] and not p['physical_complete'] and not p['bom_complete'],'미측정에는 값/완결성을 넣지 않습니다.');continue
  start=timestamp(p['started_at'],'started_at');require(p['window_start']<=start.date().isoformat()<=p['window_end'],'시작 시각이 관측창 밖')
  if p['status']=='complete':
   end=timestamp(p['ended_at'],'ended_at');require(start<=end and end.date().isoformat()<=p['window_end'],'종료 시각/관측창 오류')
  else:require(p['ended_at'] is None,'진행 중은 종료 시각 미확정');end=timestamp(p['window_end']+'T23:59:59Z','cutoff')
  ids=set()
  for kind in ('physical_samples','bom_changes'):
   for e in p[kind]:
    fields(e,{'event_id','occurred_at','quantity'} if kind=='physical_samples' else {'event_id','occurred_at','reason','description'},kind)
    text(e['event_id'],'event_id',80);require(e['event_id'] not in ids,'제품/시범 내 사건 ID 중복');ids.add(e['event_id'])
    require(start<=timestamp(e['occurred_at'],'occurred_at')<=end,'사건이 개발기간/관측창 밖')
    if kind=='physical_samples':integer(e['quantity'],'physical quantity',1,1000)
    else:require(e['reason'] in ('error_correction','design_change','unknown'),'BOM 변경 분류 오류');text(e['description'],'BOM description',300)
 require(len(serialized(spec))<=128*1024,'효과 입력 크기 초과');return spec

def values(arm):
 measured=arm['status']!='unmeasured';complete=arm['status']=='complete'
 return dict(sample_units=sum(e['quantity'] for e in arm['physical_samples']) if measured else None,
             make_events=len(arm['physical_samples']) if measured else None,
             elapsed_hours=(timestamp(arm['ended_at'],'end')-timestamp(arm['started_at'],'start')).total_seconds()/3600 if complete else None,
             bom_errors=sum(e['reason']=='error_correction' for e in arm['bom_changes']) if measured else None,
             design_changes=sum(e['reason']=='design_change' for e in arm['bom_changes']) if measured else None,
             unclassified_changes=sum(e['reason']=='unknown' for e in arm['bom_changes']) if measured else None)

def calculate(spec,sources):
 require(len(spec['pairs'])==len(sources),'출처 수 불일치');rows=[]
 for pair,source in zip(spec['pairs'],sources):
  require(pair['product_id']==source['product_id'],'제품/출처 순서 불일치')
  b=source['baseline'];baseline=dict(status='complete' if b['status']=='synthetic_recorded' else 'unmeasured',**{k:b[k] for k in ('window_start','window_end','started_at','ended_at','physical_samples','bom_changes')},**pair['baseline_coverage'])
  pilot=pair['pilot'];before,after=values(baseline),values(pilot);common=list(source['issues'])
  if baseline['status']!='complete':common.append('baseline_unmeasured')
  if pilot['status']!='complete':common.append('pilot_'+pilot['status'])
  if pair['definition_id']!=DEFINITION or pilot['definition_id']!=DEFINITION or b['time_definition']!=BASELINE_TIME:common.append('definition_mismatch')
  if pair['scope_id']!=pilot['scope_id']:common.append('scope_mismatch')
  metrics={}
  for key in METRICS:
   reasons=list(common)
   if key in ('sample_units','make_events') and not (baseline['physical_complete'] and pilot['physical_complete']):reasons.append('physical_coverage_incomplete')
   if key=='bom_errors':
    if not (baseline['bom_complete'] and pilot['bom_complete']):reasons.append('bom_coverage_incomplete')
    if before['unclassified_changes'] or after['unclassified_changes']:reasons.append('bom_reason_unknown')
   eligible=not reasons;a,z=before[key],after[key];reduction=a-z if eligible else None
   metrics[key]=dict(eligible=eligible,reasons=reasons,before=a,after=z,reduction=reduction,reduction_pct=100*reduction/a if eligible and a else None,
                     percent_status='available' if eligible and a else 'baseline_zero' if eligible else 'not_comparable')
  rows.append(dict(product_id=pair['product_id'],baseline=baseline,pilot=pilot,before=before,after=after,metrics=metrics,anchor=source['anchor']))
 summaries={}
 for key,(label,unit) in METRICS.items():
  included=[r for r in rows if r['metrics'][key]['eligible']];n=len(included)
  a=sum(r['before'][key] for r in included) if n else None;z=sum(r['after'][key] for r in included) if n else None;reduction=a-z if n else None
  summaries[key]=dict(label=label,unit=unit,paired_products=n,total_products=len(rows),included=[r['product_id'] for r in included],
                      excluded=[dict(product_id=r['product_id'],reasons=r['metrics'][key]['reasons']) for r in rows if not r['metrics'][key]['eligible']],
                      before_total=a,after_total=z,before_mean=a/n if n else None,after_mean=z/n if n else None,reduction=reduction,reduction_pct=100*reduction/a if n and a else None,
                      percent_status='available' if n and a else 'baseline_zero' if n else 'unmeasured',direction=('improved' if reduction>0 else 'worsened' if reduction<0 else 'unchanged') if n else 'unmeasured')
 return dict(schema_version='aurora-sampling-effect-report-v1',data_kind='synthetic',effect_measured=False,synthetic_comparison_available=any(s['paired_products'] for s in summaries.values()),
             scope=SCOPE,definition=dict(id=DEFINITION,start='명세 접수',end='샘플 최종 검토 완료',clock='calendar_elapsed_hours_including_wait',sample_units='제작 개수 합계',make_events='제작 사건 건수; 한 사건에 여러 개 가능',bom_errors='오류 수정 사건 건수; 정확도/오류율 분모 미확보',aggregation='각 지표의 동일 제품 짝만 합산; 비율은 합계의 비율'),assumptions=spec['assumptions'],summary=summaries,products=rows)

def csv_bytes(rows):
 out=io.StringIO(newline='');w=csv.writer(out)
 for row in rows:w.writerow([("'"+v if v and v.lstrip().startswith(('=','+','-','@')) else v) if isinstance(v,str) else v for v in row])
 return out.getvalue().encode('utf-8-sig')

def artifacts(snapshot):
 result=snapshot['result'];lineage=dict(study_id=snapshot['study_id'],version=snapshot['version'],input_sha256=snapshot['input_sha256'],source_sha256=snapshot['source_sha256'],engine_sha256=snapshot['engine_sha256'],sources=snapshot['sources'],scope=SCOPE)
 rows=[['product_id','metric','before','after','eligible','reduction','reduction_pct','percent_status','excluded_reasons']];events=[['product_id','arm','event_type','event_id','occurred_at','quantity','bom_reason','description']]
 for p in result['products']:
  for key,m in p['metrics'].items():rows.append([p['product_id'],key,m['before'],m['after'],m['eligible'],m['reduction'],m['reduction_pct'],m['percent_status'],'|'.join(m['reasons'])])
  for arm in ('baseline','pilot'):
   for kind in ('physical_samples','bom_changes'):
    for e in p[arm][kind]:events.append([p['product_id'],arm,kind,e['event_id'],e['occurred_at'],e.get('quantity'),e.get('reason'),e.get('description')])
 md=['# 디지털 샘플링 효과 측정 · 합성 보고', '',SCOPE,'','이 보고서는 저장 시점의 불변 스냅샷이다. 현재 승인/연결의 유효성은 앱에서 다시 조회한다.','',f"연구 {snapshot['study_id']} / 버전 {snapshot['version']} / 기록 {snapshot['created_at']}",'', '## 측정 정의','', '명세 접수→샘플 최종 검토 완료의 달력 경과시간(대기 포함). 제작 개수와 사건 횟수를 분리한다. BOM 정상 설계 변경·미분류는 오류 수정과 분리한다.','', '## 지표별 동일 짝 비교','', '| 지표 | 비교 제품 수 / 전체 | 현행 합계 | 시범 합계 | 감소량 | 감소율 |','|---|---|---|---|---|---|']
 fmt=lambda x:'미측정/비교 불가' if x is None else f'{x:.3f}' if isinstance(x,float) else str(x)
 for key,s in result['summary'].items():md.append('| '+ ' | '.join([s['label']+' ('+s['unit']+')',str(s['paired_products'])+' / '+str(s['total_products']),fmt(s['before_total']),fmt(s['after_total']),fmt(s['reduction']),fmt(s['reduction_pct'])+'%' if s['reduction_pct'] is not None else s['percent_status']])+' |')
 md+=['','감소량=현행−시범. 음수는 악화다. 현행 합계0이면 비율은 계산하지 않는다. 관측 없는 값은0으로 채우지 않는다. 지표마다 제외된 제품이 달라질 수 있으며 개별 감소율의 단순 평균을 쓰지 않는다.','','## 제품별 관측·제외 근거','']
 for p in result['products']:
  md += ['### '+p['product_id'],'',f"현행 {p['baseline']['window_start']}~{p['baseline']['window_end']} / 시범 {p['pilot']['window_start']}~{p['pilot']['window_end']}; 시범 상태 {p['pilot']['status']}.",f"BOM 정상 변경 현행 {fmt(p['before']['design_changes'])} / 시범 {fmt(p['after']['design_changes'])}; 미분류 현행 {fmt(p['before']['unclassified_changes'])} / 시범 {fmt(p['after']['unclassified_changes'])}.",'']
  for key,m in p['metrics'].items():md.append('- '+METRICS[key][0]+': '+('비교 가능' if m['eligible'] else '제외 · '+', '.join(m['reasons'])))
 md+=['','## 가정·한계·운영','',result['assumptions'],'','제품 난이도·업무량·관측창·완결성·동일 정의의 현업 확인이 필요하다. 통계적 유의성·인과 개선·기업 목표 달성은 판정하지 않는다. 실제 작업/대기시간 분리·BOM 전체 오류 기회·비용은 미확보다. U22/U23의 디지털 승인은 실물 제작의 검증이 아니다.','','입력 수정 시 새 버전과 부모 SHA·사유를 등록한다. 승인 철회/명세/패턴 변경 후 현재 재계산을 확인하고 필요하면 새 보고서를 저장한다. 원본 입력·products.csv·events.csv·lineage.json·manifest의 해시로 추적한다. 실제 사용자 인증·기업 입력·Supabase DS 저장은 후속이다.','','## 재현·제출 연결','', '기본 Python 서버의 동일 검증/계산부를 사용한다. `tools/build_effect_demo.py`로 자체 합성 저장 예제를 새 출력 경로에 재현한다. DS-05 지표/분모/제외 근거와 DS-06 효과/운영 보고 초안이다. 실제 기업 중간/최종 인수 보고서로 간주하지 않는다.','','입력 SHA: '+snapshot['input_sha256'],'출처 SHA: '+snapshot['source_sha256'],'엔진 SHA: '+snapshot['engine_sha256']]
 return {'report.json':serialized(snapshot),'report.md':'\n'.join(md).encode(),'products.csv':csv_bytes(rows),'events.csv':csv_bytes(events),'lineage.json':serialized(lineage)}

class EffectStore:
 def __init__(self,root,patterns):
  self.root=Path(root);self.patterns=patterns;self.path=self.root/'results/sampling-effects.sqlite3';self.output=self.root/'results/sampling-effect-artifacts';self.output.mkdir(parents=True,exist_ok=True)
  with self.db() as db:db.executescript('''CREATE TABLE IF NOT EXISTS effect_reports(study_id TEXT,version INTEGER,snapshot TEXT NOT NULL,sha256 TEXT NOT NULL,artifact_key TEXT NOT NULL,manifest TEXT NOT NULL,PRIMARY KEY(study_id,version));
  CREATE TABLE IF NOT EXISTS effect_requests(actor TEXT,request_key TEXT,fingerprint TEXT NOT NULL,study_id TEXT,version INTEGER,PRIMARY KEY(actor,request_key));
  CREATE TRIGGER IF NOT EXISTS effects_no_update BEFORE UPDATE ON effect_reports BEGIN SELECT RAISE(ABORT,'immutable effect report'); END;
  CREATE TRIGGER IF NOT EXISTS effects_no_delete BEFORE DELETE ON effect_reports BEGIN SELECT RAISE(ABORT,'immutable effect report'); END;''')
 @contextmanager
 def db(self):
  db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
  try:
   with db:yield db
  finally:db.close()
 @contextmanager
 def sources(self,spec):
  # Preserve the established U20 -> U22 -> U23 -> U24 lock order.
  with self.patterns.reviews.write() as review_db:
   library=self.patterns.bundles()
   with self.patterns.db() as pattern_db:
    pattern_db.execute('BEGIN IMMEDIATE');sources=[]
    for pair in spec['pairs']:
     pid=pair['product_id'];base=self.patterns.reviews.briefs.get(pid,pair['baseline_version'])
     if not base or base['checksum']!=pair['baseline_checksum']:raise Conflict('현행 U20 버전/체크섬 불일치')
     link_state=self.patterns._read(pattern_db,pid,self.patterns.reviews._read(review_db,pid),library);anchor=None;issues=[]
     if pair['anchor'] is None:issues.append('workflow_anchor_missing')
     else:
      anchor=next((x for x in link_state['links'] if x['version']==pair['anchor']['link_version']),None)
      if not anchor or anchor['sha256']!=pair['anchor']['link_sha256']:raise Conflict('U23 연결 버전/해시 불일치')
      if not anchor['current_valid']:issues.append('workflow_anchor_inactive')
      if anchor['brief_checksum']!=base['checksum']:issues.append('baseline_brief_differs_from_sample')
      anchor={k:anchor[k] for k in ('product_id','version','sha256','brief_checksum','sample_version','sample_revision_sha256','approval_event_sha256','bundle_sha256','current_valid','invalid_reasons')}
     sources.append(dict(product_id=pid,brief_version=base['brief']['brief_version'],brief_checksum=base['checksum'],baseline=base['brief']['baseline'],anchor=anchor,issues=issues))
    yield sources
 def _history(self,db,sid):
  rows=[];prev=None
  for r in db.execute('SELECT * FROM effect_reports WHERE study_id=? ORDER BY version',(sid,)):
   snap=json.loads(r['snapshot']);require(digest(serialized(snap))==r['sha256'] and snap['previous_sha256']==prev and snap['version']==len(rows)+1,'효과 보고서 해시/부모 연결 오류');prev=r['sha256'];rows.append(r)
  return rows
 def _result(self,row,history,sources):
  snap=json.loads(row['snapshot']);return dict(snapshot=snap,sha256=row['sha256'],history=[dict(version=r['version'],sha256=r['sha256']) for r in history],
                 source_changed=digest(serialized(sources))!=snap['source_sha256'],current_report=calculate(snap['input'],sources),recalculation_engine_sha256=engine(),artifact_manifest=json.loads(row['manifest']))
 def get(self,sid,version=None):
  study(sid)
  if version is not None:integer(version,'report version',1,1000)
  with self.db() as db:history=self._history(db,sid)
  if not history:return None
  row=next((r for r in history if r['version']==version),None) if version is not None else history[-1]
  if row is None:return None
  spec=json.loads(row['snapshot'])['input']
  with self.sources(spec) as sources:return self._result(row,history,sources)
 def catalog(self):
  with self.db() as db:rows=db.execute('SELECT study_id,MAX(version) version FROM effect_reports GROUP BY study_id ORDER BY study_id').fetchall()
  return dict(schema_version='aurora-effect-catalog-v1',mode='local_synthetic',reports=[dict(study_id=r['study_id'],version=r['version']) for r in rows],examples=['six-products'],scope=SCOPE)
 def example(self):
  spec=json.loads((self.root/'client/demo/effects/input-example.json').read_text())
  # Adapt references to this PC without importing saved approvals or making up observations.
  for pair in spec['pairs']:
   record=self.patterns.get(pair['product_id']);links=record['links'];active=next((l for l in reversed(links) if l['current_valid']),None)
   pair['anchor']=dict(link_version=active['version'],link_sha256=active['sha256']) if active else None
  return spec
 def register(self,token,req):
  fields(req,{'input','request_key'},'effect request');spec=validate(req['input']);actor=self.patterns.reviews.actor(token)
  if actor['role']!='designer':raise Denied('효과 보고서 등록은 가상 작성자만 가능합니다.')
  require(isinstance(req['request_key'],str) and KEY.fullmatch(req['request_key']),'요청 키 형식 오류')
  with self.sources(spec) as sources:
   with self.db() as db:
    db.execute('BEGIN IMMEDIATE');replay=db.execute('SELECT * FROM effect_requests WHERE actor=? AND request_key=?',(actor['id'],req['request_key'])).fetchone()
    history=self._history(db,spec['study_id'])
    if replay:
     if replay['fingerprint']!=digest(serialized(req)):raise Conflict('같은 요청 키의 내용 변경')
     return dict(**self._result(history[replay['version']-1],history,sources),replayed=True,original_receipt_version=replay['version'])
    if spec['version']!=len(history)+1 or spec['previous_sha256']!=(history[-1]['sha256'] if history else None):raise Conflict('최신 보고서 버전/부모 SHA가 바뀌었습니다.')
    snap=dict(study_id=spec['study_id'],version=spec['version'],previous_sha256=spec['previous_sha256'],data_kind='synthetic',input=copy.deepcopy(spec),input_sha256=digest(serialized(spec)),sources=copy.deepcopy(sources),source_sha256=digest(serialized(sources)),engine_sha256=engine(),result=calculate(spec,sources),created_by=actor,created_at=datetime.now(timezone.utc).isoformat())
    raw=serialized(snap);key=uuid.uuid4().hex;dest=self.output/key;dest.mkdir()
    try:
     payloads=artifacts(snap);metas=[]
     for name,data in payloads.items():(dest/name).write_bytes(data);metas.append(dict(file=name,bytes=len(data),sha256=digest(data)))
     manifest=dict(schema_version='aurora-effect-artifacts-v1',study_id=spec['study_id'],version=spec['version'],snapshot_sha256=digest(raw),files=metas)
     (dest/'manifest.json').write_bytes(serialized(manifest))
     db.execute('INSERT INTO effect_reports VALUES(?,?,?,?,?,?)',(spec['study_id'],spec['version'],raw.decode(),digest(raw),key,serialized(manifest).decode()))
     db.execute('INSERT INTO effect_requests VALUES(?,?,?,?,?)',(actor['id'],req['request_key'],digest(serialized(req)),spec['study_id'],spec['version']))
    except Exception:shutil.rmtree(dest);raise
    history=self._history(db,spec['study_id']);return dict(**self._result(history[-1],history,sources),replayed=False)
 def artifact(self,sid,version,name):
  study(sid);integer(version,'report version',1,1000);require(name in (*FILES,'manifest.json'),'보고 파일명 오류')
  with self.db() as db:
   history=self._history(db,sid);row=next((r for r in history if r['version']==version),None)
  if not row:return None
  require(re.fullmatch(r'[0-9a-f]{32}',row['artifact_key']),'산출물 경로 오류');p=self.output/row['artifact_key']/name;raw=p.read_bytes();manifest=json.loads(row['manifest'])
  if name=='manifest.json':require(raw==serialized(manifest),'산출물 명세 손상')
  else:
   meta=next(m for m in manifest['files'] if m['file']==name);require(len(raw)==meta['bytes'] and digest(raw)==meta['sha256'],'보고 파일 크기/해시 오류')
  return p
