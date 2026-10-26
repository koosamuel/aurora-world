"""Loopback public-data queue, with the same summary/artifact boundary as Supabase."""
import json,time,uuid,hashlib
from pathlib import Path
from .jobs import Store
from .forecast import digest
from .public_service import decode,public_summary,NAMES
from .public_retail import evaluate_public,export_result

class PublicStore(Store):
    def __init__(self,path,input_path):
        super().__init__(path);self.payload=decode(Path(input_path).read_bytes());self.checksum=digest(self.payload)
        self.output=Path(path).parent/'public-artifacts'
        self.dataset=dict(id='local-public-'+self.checksum[:16],name='UCI 공개 거래 · 100 SKU / 104주',dataset_kind='public_retail',synthetic=False,generator_config=dict(skus=len(self.payload['series']),weeks=len(self.payload['periods'])))
    def request(self,project_type,request_key,options=None):
        if project_type!='forecast' or not isinstance(request_key,str) or not 1<=len(request_key)<=120:raise ValueError('실행 요청을 확인하세요.')
        if not isinstance(options,dict) or set(options)-{'policy_inputs'}:raise ValueError('공개 거래 정책 입력만 허용합니다.')
        c=dict(policy_inputs=options.get('policy_inputs',{}),dataset_sha256=self.checksum)
        if not isinstance(c['policy_inputs'],dict):raise ValueError('정책 JSON 객체가 필요합니다.')
        h=digest(c);now=time.time()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO runs(id,project_type,request_key,config,config_hash,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),project_type,request_key,json.dumps(c),h,'queued',now,now))
            row=db.execute('SELECT * FROM runs WHERE project_type=? AND request_key=?',(project_type,request_key)).fetchone()
            if row['config_hash']!=h:raise ValueError('같은 요청 키의 데이터/설정이 다릅니다.')
        return self.decode(row)
    def work_once(self):
        job=self.claim()
        if not job:return False
        try:
            if job['config']['dataset_sha256']!=self.checksum:raise ValueError('Dataset version changed')
            result=evaluate_public(self.payload,job['config']['policy_inputs']);path=self.output/job['id']/f"attempt-{job['attempt']}"
            export_result(result,path);summary=public_summary(result);summary['artifacts']=[]
            for name in NAMES:
                data=(path/name).read_bytes();summary['artifacts'].append(dict(id=name,name=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),url=f"./api/public/artifacts/{job['id']}/{name}"))
            self.finish(job,summary)
        except Exception:self.finish(job,error='공개 거래 계산 실패: 정책의 품목 ID·단위·범위를 확인하세요.')
        return True
    def artifact(self,run_id,name):
        if name not in NAMES:return None
        row=self.get(run_id,'forecast')
        if not row or row['status']!='succeeded':return None
        path=self.output/str(uuid.UUID(run_id))/f"attempt-{row['attempt']}"/name
        info=next((a for a in row['result'].get('artifacts',[]) if a['name']==name),None)
        if not info or not path.exists() or path.stat().st_size!=info['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:return None
        return path
