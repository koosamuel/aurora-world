"""SQLite-backed synthetic demo queue with idempotency and attempt fencing."""
import json
import sqlite3
import time
import uuid
from pathlib import Path
from .forecast import config_for, digest, run_baseline

PROJECTS = (dict(id="demo-forecast", project_type="forecast", name="수요예측·운전자본"),
            dict(id="demo-labeling", project_type="labeling", name="패턴 부위명 자동 라벨링"))


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, project_type TEXT NOT NULL, request_key TEXT NOT NULL,
                config TEXT NOT NULL, config_hash TEXT NOT NULL, status TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0, token TEXT, lease REAL,
                created REAL NOT NULL, updated REAL NOT NULL, result TEXT, error TEXT,
                UNIQUE(project_type,request_key))''')
    def connect(self):
        db=sqlite3.connect(self.path, timeout=15)
        db.row_factory=sqlite3.Row
        return db
    @staticmethod
    def decode(row, detail=False):
        if row is None: return None
        r=dict(row)
        r.pop('token',None); r.pop('lease',None)
        r['config']=json.loads(r['config'])
        if detail: r['result']=json.loads(r['result']) if r['result'] else None
        else:r.pop('result',None)
        return r
    def request(self, project_type, request_key, options=None):
        if project_type!='forecast':raise ValueError('라벨링 실행기는 구현 예정입니다.')
        if not isinstance(request_key,str) or not 1<=len(request_key)<=120:raise ValueError('요청 키를 확인하세요.')
        c=config_for(options); h=digest(c); now=time.time(); run_id=str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO runs(id,project_type,request_key,config,config_hash,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (run_id,project_type,request_key,json.dumps(c),h,'queued',now,now))
            row=db.execute('SELECT * FROM runs WHERE project_type=? AND request_key=?',(project_type,request_key)).fetchone()
            if row['config_hash']!=h:raise ValueError('같은 요청 키로 다른 설정을 보낼 수 없습니다.')
        return self.decode(row)
    def list(self, project_type):
        if project_type not in ('forecast','labeling'):raise ValueError('프로젝트를 확인하세요.')
        with self.connect() as db:
            rows=db.execute('SELECT * FROM runs WHERE project_type=? ORDER BY created DESC LIMIT 30',(project_type,)).fetchall()
        return [self.decode(r) for r in rows]
    def get(self, run_id, project_type):
        with self.connect() as db:
            row=db.execute('SELECT * FROM runs WHERE id=? AND project_type=?',(run_id,project_type)).fetchone()
        return self.decode(row,True)
    def claim(self, lease_seconds=120):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now=time.time()
            db.execute("UPDATE runs SET status='failed',error='작업 재시도 한도를 초과했습니다.',updated=? WHERE status='running' AND lease<? AND attempt>=3",(now,now))
            row=db.execute("SELECT * FROM runs WHERE (status='queued' OR (status='running' AND lease<?)) AND attempt<3 ORDER BY created LIMIT 1",(now,)).fetchone()
            if row is None:return None
            token=str(uuid.uuid4())
            db.execute("UPDATE runs SET status='running',attempt=attempt+1,token=?,lease=?,updated=? WHERE id=?",(token,now+lease_seconds,now,row['id']))
            return dict(id=row['id'],config=json.loads(row['config']),token=token,attempt=row['attempt']+1)
    def finish(self, job, result=None, error=None):
        with self.connect() as db:
            cur=db.execute("UPDATE runs SET status=?,result=?,error=?,updated=? WHERE id=? AND token=? AND status='running' AND lease>=?",
                ('failed' if error else 'succeeded',json.dumps(result,allow_nan=False) if result is not None else None,
                 error,time.time(),job['id'],job['token'],time.time()))
        return cur.rowcount==1
    def cancel(self, run_id, project_type):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='cancelled',updated=? WHERE id=? AND project_type=? AND status IN ('queued','running')",(time.time(),run_id,project_type))
        return self.get(run_id,project_type)


def work_once(store):
    job=store.claim()
    if not job:return False
    try:store.finish(job,run_baseline(job['config']))
    except Exception:store.finish(job,error='합성 기준선 실행에 실패했습니다. 입력과 워커 기록을 확인하세요.')
    return True
