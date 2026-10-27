"""U22 local synthetic sample review with immutable revisions and audit events.

Demo personas simulate duties, NOT real authentication or company approval.
An approval attaches to one frozen file/brief/review; it never certifies sewing.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import copy, json, re, secrets, sqlite3, time, uuid
from .identity import require, serialized, text
from .sampling import Conflict, fields, integer, product, validate, checksum
from .generation import digest

ACTORS={
    'designer':dict(id='designer',name='가상 작성자',role='designer'),
    'reviewer':dict(id='reviewer',name='가상 검토자',role='reviewer'),
    'approver':dict(id='approver',name='가상 승인자',role='approver'),
    'viewer':dict(id='viewer',name='가상 열람자',role='viewer'),
}
ASSET=re.compile(r'[0-9a-f]{64}\.(?:png|svg|glb)\Z')
KEY=re.compile(r'[A-Za-z0-9_-]{8,80}\Z')

class Denied(ValueError):pass

def decode(raw):
    require(len(raw)<=32768,'검토 요청은32 KiB 이하입니다.')
    def pairs(items):
        d={}
        for k,v in items:
            require(k not in d,'중복 JSON 키입니다.');d[k]=v
        return d
    def bad(v):raise ValueError('비유한 JSON 값입니다.')
    try:d=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except (UnicodeError,RecursionError) as e:raise ValueError('검토 JSON 형식 오류') from e
    require(isinstance(d,dict),'검토 JSON 객체가 필요합니다.');return d

def checklist(brief):
    return [dict(id=k,label=v) for k,v in [
        ('appearance','외형·원화와의 차이를 검토함'),('color','색상·표현 차이를 검토함'),
        ('dimensions','목표 치수를 확인함 · 이미지의 실측 검증은 아님'),
        ('fabric','원단 표현의 한계를 확인함 · 물성/봉제 검증은 아님'),
    ]]+[dict(id='condition-'+str(i),label=v) for i,v in enumerate(brief['requirements']['must_have'])]

class ReviewStore:
    def __init__(self,root,briefs,generation=None,ai=None):
        self.root=Path(root);self.briefs=briefs;self.generation=generation;self.ai=ai
        self.assets=self.root/'results/sample-review-assets';self.assets.mkdir(parents=True,exist_ok=True)
        self.dbpath=self.root/'results/sample-reviews.sqlite3'
        with self.db() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS review_tracks(product_id TEXT PRIMARY KEY,head INTEGER NOT NULL,seq INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS review_revisions(product_id TEXT,version INTEGER,snapshot TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(product_id,version));
              CREATE TABLE IF NOT EXISTS review_events(product_id TEXT,seq INTEGER,event TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(product_id,seq));
              CREATE TABLE IF NOT EXISTS review_requests(actor TEXT,request_key TEXT,fingerprint TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(actor,request_key));
              CREATE TABLE IF NOT EXISTS review_sessions(token_hash TEXT PRIMARY KEY,actor TEXT NOT NULL,expires REAL NOT NULL);
              CREATE TRIGGER IF NOT EXISTS revision_no_update BEFORE UPDATE ON review_revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
              CREATE TRIGGER IF NOT EXISTS revision_no_delete BEFORE DELETE ON review_revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
              CREATE TRIGGER IF NOT EXISTS event_no_update BEFORE UPDATE ON review_events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
              CREATE TRIGGER IF NOT EXISTS event_no_delete BEFORE DELETE ON review_events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
            ''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.dbpath,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    @contextmanager
    def write(self):
        # Lock the U20 source first: a new brief cannot race an approval commit.
        with self.briefs.connect() as briefs_db:
            briefs_db.execute('BEGIN IMMEDIATE')
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');yield db

    def session(self,req):
        fields(req,{'persona_id'},'demo session');require(req['persona_id'] in ACTORS,'알 수 없는 합성 역할입니다.')
        token=secrets.token_urlsafe(32);expiry=time.time()+8*3600
        with self.db() as db:
            db.execute('DELETE FROM review_sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO review_sessions VALUES(?,?,?)',(digest(token.encode()),req['persona_id'],expiry))
        return dict(token=token,actor=ACTORS[req['persona_id']],expires_at=expiry,authentication='local_demo_persona_only')

    def actor(self,token):
        if not isinstance(token,str) or len(token)>100:raise Denied('합성 역할 세션을 선택하세요.')
        with self.db() as db:r=db.execute('SELECT actor,expires FROM review_sessions WHERE token_hash=?',(digest(token.encode()),)).fetchone()
        if not r or r['expires']<=time.time():raise Denied('합성 역할 세션이 없거나 만료됐습니다.')
        return ACTORS[r['actor']]

    def _candidate_rows(self):
        for kind,service in [('geometry',self.generation),('ai',self.ai)]:
            base=self.root/'client/demo'/('generation' if kind=='geometry' else 'ai-sampling')
            if (base/'catalog.json').exists():
                cat=json.loads((base/'catalog.json').read_text())
                for rid in cat['demo_runs'].values():
                    require(re.fullmatch(r'(?:demo|ai)-[0-9a-f]{16}',rid),'저장 실행 ID 오류')
                    yield kind,'saved',rid,json.loads((base/rid/'run.json').read_text()),base/rid
            if service:
                with service.db() as db:ids=[r[0] for r in db.execute("SELECT id FROM generation_runs WHERE state='succeeded' ORDER BY created_at DESC LIMIT 100")]
                for rid in ids:yield kind,'local',rid,service.get(rid),service.output/rid

    def _candidates(self):
        result={}
        for kind,location,rid,row,base in self._candidate_rows():
            if row['state']!='succeeded' or row['source']['data_kind']!='synthetic':continue
            source=row['source'];b=source['brief'];validate(b)
            require(checksum(b)==source['brief_checksum'],'생성 명세 체크섬 오류')
            require(digest(serialized({k:v for k,v in source.items() if k!='checksum'}))==source['checksum'],'생성 입력 해시 오류')
            require(row['result']['report']['source_checksum']==source['checksum'],'생성 보고서의 입력 불일치')
            metas={a['file']:a for a in row['result']['artifacts']}
            for c in row['result']['report']['candidates']:
                cid=c['id'];require(cid in ('baseline','candidate','preserve','reinterpret'),'생성 후보 이름 오류')
                names=[cid+'.png'] if kind=='ai' else [cid+'.front.svg',cid+'.side.svg',cid+'.glb']
                candidate=dict(id=f'{location}:{kind}:{rid}:{cid}',name=f"{b['product_name']} · 명세v{b['brief_version']} · {kind}/{cid} · {rid[:12]}",
                               product_id=b['product_id'],source=source,kind=kind,run_id=rid,candidate_id=cid,
                               engine_sha256=row['result']['report']['engine_sha256'],files=[metas[n] for n in names])
                candidate['checksum']=digest(serialized(candidate));result[candidate['id']]=(candidate,base)
        return result

    def latest_brief(self,pid):
        rows=[r['summary']['brief_version'] for r in self.briefs.list() if r['summary']['product_id']==pid]
        return self.briefs.get(pid,max(rows)) if rows else None

    def catalog(self):
        with self.db() as db:ids=[r[0] for r in db.execute('SELECT product_id FROM review_tracks ORDER BY product_id')]
        candidates=[]
        for c,_ in self._candidates().values():
            latest=self.latest_brief(c['product_id']);c=copy.deepcopy(c)
            c['latest_brief']=bool(latest and latest['checksum']==c['source']['brief_checksum']);candidates.append(c)
        products=[]
        for pid in ids:
            r=self.get(pid);rev=r['revisions'][-1]
            products.append(dict(product_id=pid,head_version=r['head_version'],seq=r['seq'],state=rev['state'],active_approval=rev['active_approval'],stale_brief=rev['stale_brief']))
        return dict(schema_version='aurora-review-catalog-v1',mode='local_synthetic',actors=list(ACTORS.values()),
                    candidates=candidates,products=products,authentication='local_demo_persona_only')

    def _read(self,db,pid):
        track=db.execute('SELECT * FROM review_tracks WHERE product_id=?',(pid,)).fetchone()
        if not track:return None
        revisions=[]
        for r in db.execute('SELECT * FROM review_revisions WHERE product_id=? ORDER BY version',(pid,)):
            snap=json.loads(r['snapshot']);require(digest(serialized(snap))==r['sha256'],'수정본 스냅샷 해시 오류')
            require(snap['version']==len(revisions)+1 and snap['parent_sha256']==(revisions[-1]['sha256'] if revisions else None),'수정본 부모 연결 오류')
            revisions.append(dict(**snap,sha256=r['sha256']))
        events=[];previous=None
        for r in db.execute('SELECT * FROM review_events WHERE product_id=? ORDER BY seq',(pid,)):
            e=json.loads(r['event']);require(digest(serialized(e))==r['sha256'] and e['previous_event_sha256']==previous and e['seq']==len(events)+1,'검토 이력 해시 연결 오류')
            previous=r['sha256'];events.append(dict(**e,sha256=r['sha256']))
        require(track['seq']==len(events) and track['head']==len(revisions),'검토 이력 포인터 오류')
        latest=self.latest_brief(pid)
        for rev in revisions:
            state='draft';review=None;approval=None
            for e in [x for x in events if x['version']==rev['version']]:
                action=e['action']
                if action=='submit':state='in_review';review=None;approval=None
                elif action=='review':review=e
                elif action=='request_changes':state='changes_requested';approval=None
                elif action=='hold':state='on_hold';approval=None
                elif action=='approve':state='approved';approval=e
                elif action=='superseded':state='superseded'
            stale=not latest or latest['checksum']!=rev['sample']['source']['brief_checksum']
            rev.update(state=state,review=review,approval=approval,stale_brief=stale,
                       active_approval=bool(approval and state=='approved' and rev['version']==track['head'] and not stale))
        return dict(schema_version='aurora-sample-review-v1',data_kind='synthetic',product_id=pid,head_version=track['head'],seq=track['seq'],
                    revisions=revisions,events=events,audit_head_sha256=previous,history_hash_verified=True,
                    latest_brief_checksum=latest['checksum'] if latest else None,manufacturing_verified=False,effect_measured=False,
                    approval_scope='local synthetic digital design review only; not company acceptance or sewing certification')

    def get(self,pid):
        product(pid)
        with self.db() as db:return self._read(db,pid)

    def _append(self,db,pid,version,action,actor,payload):
        track=db.execute('SELECT seq FROM review_tracks WHERE product_id=?',(pid,)).fetchone()
        prev=db.execute('SELECT sha256 FROM review_events WHERE product_id=? ORDER BY seq DESC LIMIT 1',(pid,)).fetchone()
        e=dict(id=uuid.uuid4().hex,product_id=pid,version=version,seq=track['seq']+1,action=action,actor=actor,
               recorded_at=datetime.now(timezone.utc).isoformat(),payload=payload,previous_event_sha256=prev[0] if prev else None)
        sha=digest(serialized(e));db.execute('INSERT INTO review_events VALUES(?,?,?,?)',(pid,e['seq'],serialized(e).decode(),sha))
        db.execute('UPDATE review_tracks SET seq=? WHERE product_id=?',(e['seq'],pid))
        return dict(**e,sha256=sha)

    def _replay(self,db,actor,req):
        require(isinstance(req['request_key'],str) and KEY.fullmatch(req['request_key']),'요청 키 형식 오류')
        r=db.execute('SELECT fingerprint,response FROM review_requests WHERE actor=? AND request_key=?',(actor['id'],req['request_key'])).fetchone()
        if r:
            if r['fingerprint']!=digest(serialized(req)):raise Conflict('같은 요청 키의 내용이 달라졌습니다.')
            receipt=json.loads(r['response'])
            # Replay never resurrects the validity of an old approval snapshot.
            return dict(**self._read(db,receipt['product_id']),replayed=True,original_receipt_seq=receipt['seq'])

    def _finish(self,db,actor,req,pid):
        result=self._read(db,pid)
        db.execute('INSERT INTO review_requests VALUES(?,?,?,?)',(actor['id'],req['request_key'],digest(serialized(req)),serialized(result).decode()))
        return dict(**result,replayed=False)

    def revision(self,token,req):
        fields(req,{'candidate_id','candidate_checksum','parent_version','expected_seq','change_reason','request_key'},'sample revision')
        actor=self.actor(token)
        if actor['role']!='designer':raise Denied('수정본 등록은 가상 작성자 역할만 가능합니다.')
        integer(req['expected_seq'],'expected_seq',0)
        if req['parent_version'] is not None:integer(req['parent_version'],'parent_version')
        text(req['change_reason'],'change_reason',2000)
        require(isinstance(req['candidate_id'],str) and isinstance(req['candidate_checksum'],str),'후보 ID/해시 오류')
        with self.write() as db:
            replay=self._replay(db,actor,req)
            if replay:return replay
            available=self._candidates();require(req['candidate_id'] in available,'완료한 자체 합성 후보만 등록할 수 있습니다.')
            candidate,base=available[req['candidate_id']]
            require(req['candidate_checksum']==candidate['checksum'],'생성 후보 해시가 다릅니다.')
            pid=candidate['product_id'];old=self._read(db,pid);latest=self.latest_brief(pid)
            if not latest or latest['checksum']!=candidate['source']['brief_checksum']:raise Conflict('최신 U20 명세로 생성한 후보가 필요합니다.')
            if req['expected_seq']!=(old['seq'] if old else 0) or req['parent_version']!=(old['head_version'] if old else None):raise Conflict('수정본/이력이 바뀌었습니다. 다시 조회하세요.')
            visual_changed=True;brief_changed=False
            if old:
                before=old['revisions'][-1]['sample']
                visual_changed=before['files'][0]['sha256']!=candidate['files'][0]['sha256']
                brief_changed=before['source']['brief_checksum']!=candidate['source']['brief_checksum']
                require(visual_changed or brief_changed,'수정본은 다른 미리보기 또는 새 명세가 필요합니다. U21에서 새 후보를 생성/선택하세요.')
            assets=[]
            for meta in candidate['files']:
                require(re.fullmatch(r'[a-z]+\.(?:png|front\.svg|side\.svg|glb)',meta['file']),'후보 파일 경로 오류')
                p=base/meta['file'];raw=p.read_bytes()
                require(len(raw)==meta['bytes'] and digest(raw)==meta['sha256'],'생성 파일 손상/해시 불일치')
                name=meta['sha256']+p.suffix;target=self.assets/name
                if target.exists():require(target.read_bytes()==raw,'고정 자산 내용 불일치')
                else:
                    with target.open('xb') as f:f.write(raw)
                assets.append(dict(**meta,asset=name))
            version=old['head_version']+1 if old else 1
            snap=dict(product_id=pid,version=version,parent_sha256=old['revisions'][-1]['sha256'] if old else None,
                      sample=candidate,assets=assets,checklist=checklist(candidate['source']['brief']),
                      change_reason=req['change_reason'],visual_changed=visual_changed,brief_changed=brief_changed,
                      created_by=actor,created_at=datetime.now(timezone.utc).isoformat())
            if not old:db.execute('INSERT INTO review_tracks VALUES(?,?,?)',(pid,version,0))
            else:
                self._append(db,pid,old['head_version'],'superseded',actor,dict(new_version=version,approval_invalidated=old['revisions'][-1]['active_approval']))
                db.execute('UPDATE review_tracks SET head=? WHERE product_id=?',(version,pid))
            db.execute('INSERT INTO review_revisions VALUES(?,?,?,?)',(pid,version,serialized(snap).decode(),digest(serialized(snap))))
            self._append(db,pid,version,'revision_created',actor,dict(change_reason=req['change_reason'],sample_checksum=candidate['checksum']))
            return self._finish(db,actor,req,pid)

    def event(self,token,req):
        fields(req,{'product_id','version','expected_seq','action','comment','checks','request_key'},'review event')
        actor=self.actor(token);pid=req['product_id'];product(pid);integer(req['version'],'version');integer(req['expected_seq'],'expected_seq',0)
        require(isinstance(req['action'],str) and req['action'] in ('submit','review','request_changes','hold','approve','comment'),'검토 동작을 확인하세요.')
        text(req['comment'],'comment',2000)
        action=req['action'];roles={'submit':{'designer'},'review':{'reviewer'},'request_changes':{'reviewer','approver'},'hold':{'reviewer','approver'},'approve':{'approver'},'comment':{'designer','reviewer','approver'}}
        if actor['role'] not in roles[action]:raise Denied('현재 합성 역할에 이 동작 권한이 없습니다.')
        require(isinstance(req['checks'],list),'검토 항목 배열이 필요합니다.')
        with self.write() as db:
            replay=self._replay(db,actor,req)
            if replay:return replay
            record=self._read(db,pid);require(record is not None,'등록된 샘플이 없습니다.')
            if req['expected_seq']!=record['seq'] or req['version']!=record['head_version']:raise Conflict('낡은 버전/검토 이력입니다. 최신 상태를 조회하세요.')
            rev=record['revisions'][-1]
            if rev['stale_brief'] and action!='comment':raise Conflict('U20 명세가 변경됐습니다. 새 명세의 샘플 수정본을 등록하세요.')
            if action=='review':
                require(rev['state']=='in_review','검토 요청 중인 샘플만 검토할 수 있습니다.')
                expected={c['id'] for c in rev['checklist']};actual=[]
                for c in req['checks']:
                    fields(c,{'id','status','note'},'check');require(isinstance(c['id'],str) and c['status'] in ('pass','fail','unreviewed'),'검토 상태 오류')
                    require(isinstance(c['note'],str) and len(c['note'])<=500,'검토 메모 길이 오류')
                    if c['status']=='fail':require(c['note'].strip(),'미충족 항목은 사유가 필요합니다.')
                    actual.append(c['id'])
                require(len(actual)==len(set(actual)) and set(actual)==expected,'모든 필수 검토 항목을 중복 없이 제출하세요.')
            else:require(req['checks']==[],'이 동작에는 조건 판정을 제출하지 않습니다.')
            if action=='submit':require(rev['state'] in ('draft','on_hold'),'초안/보류만 검토 요청할 수 있습니다. 수정요청에는 새 수정본이 필요합니다.')
            elif action=='hold':require(rev['state']=='in_review' or rev['state']=='approved' and actor['role']=='approver','검토 중인 샘플의 보류 또는 승인자의 승인 철회만 가능합니다.')
            elif action=='request_changes':require(rev['state']=='in_review','검토 중인 샘플에서만 수정을 요청할 수 있습니다.')
            elif action=='approve':
                require(rev['state']=='in_review' and rev['review'] is not None,'최신 제출본의 검토 결과가 필요합니다.')
                require(all(c['status']=='pass' for c in rev['review']['payload']['checks']),'미충족/미검토 조건이 있어 승인할 수 없습니다.')
                require(actor['id'] not in (rev['created_by']['id'],rev['review']['actor']['id']),'작성·검토와 승인 역할을 구분하세요.')
            payload=dict(comment=req['comment'],checks=req['checks'])
            if action=='hold' and rev['approval']:payload['revoked_approval_sha256']=rev['approval']['sha256']
            if action=='approve':payload.update(revision_sha256=rev['sha256'],review_event_sha256=rev['review']['sha256'],brief_checksum=rev['sample']['source']['brief_checksum'],scope='synthetic_digital_review_only')
            self._append(db,pid,req['version'],action,actor,payload)
            return self._finish(db,actor,req,pid)

    def asset(self,name):
        require(isinstance(name,str) and ASSET.fullmatch(name),'검토 파일 경로 오류')
        with self.db() as db:
            referenced=any(any(a['asset']==name for a in json.loads(r[0])['assets']) for r in db.execute('SELECT snapshot FROM review_revisions'))
        if not referenced:return None
        p=self.assets/name;require(p.is_file() and digest(p.read_bytes())==name.split('.')[0],'검토 자산 해시 오류');return p

    def export(self,pid):
        record=self.get(pid);require(record is not None,'등록된 검토 이력이 없습니다.')
        for r in record['revisions']:
            for a in r['assets']:
                p=self.asset(a['asset']);require(p.stat().st_size==a['bytes'],'검토 자산 크기 오류')
        return dict(**record,asset_hashes_verified=True,export_sha256=digest(serialized(record)))
