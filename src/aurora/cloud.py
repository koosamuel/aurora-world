"""Supabase REST worker. Credentials come only from process environment."""
import json
import os
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .registered import Remote,compute_job


class SupabaseWorker:
    def __init__(self):
        self.url=os.environ.get('SUPABASE_URL','').rstrip('/')
        self.secret=os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')
        if not self.url.startswith('https://') or not self.secret:
            raise ValueError('SUPABASE_URL과 워커 전용 SUPABASE_SERVICE_ROLE_KEY를 설정하세요.')
    def rpc(self,name,body):
        req=Request(self.url+'/rest/v1/rpc/'+name,data=json.dumps(body,allow_nan=False).encode(),
            headers={'apikey':self.secret,'Authorization':'Bearer '+self.secret,'Content-Type':'application/json'},method='POST')
        try:
            with urlopen(req,timeout=45) as res:return json.load(res)
        except HTTPError as e:
            # Do not echo tokens, signed URLs or request headers into logs.
            raise RuntimeError(f'Supabase {name} 요청 실패 (HTTP {e.code})') from None
    def once(self):
        job=self.rpc('claim_run',{})
        if not job:return False
        stop=threading.Event();lease_lost=threading.Event()
        def heartbeat():
            while not stop.wait(30):
                try:
                    if not self.rpc('heartbeat_run',{'p_run_id':job['id'],'p_token':job['token']}):lease_lost.set();return
                except Exception:lease_lost.set();return
        thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
        try:
            if job['task_type']!='forecast':raise ValueError('현재 워커는 수요예측 기준선만 지원합니다.')
            result=compute_job(Remote(),job)
            if lease_lost.is_set():raise RuntimeError('작업 선점이 만료됐습니다.')
            if job['generator_config'].get('mode')=='public_file_v1':
                ok=self.rpc('complete_public_run',{'p_run_id':job['id'],'p_token':job['token'],'p_result':result['summary'],'p_artifacts':result['artifacts']})
            else:
                ok=self.rpc('complete_run',{'p_run_id':job['id'],'p_token':job['token'],'p_result':result,'p_error':None})
            if not ok:raise RuntimeError('만료되거나 취소된 실행 결과를 저장하지 않았습니다.')
            print('Completed forecast run:',job['id'],flush=True)
        except Exception:
            self.rpc('complete_run',{'p_run_id':job['id'],'p_token':job['token'],'p_result':None,
                                    'p_error':'워커 실행 실패: 설정·호환 버전·연결을 확인하세요.'})
            raise
        finally:stop.set();thread.join(timeout=2)
        return True
    def run(self,once=False):
        while True:
            found=self.once()
            if once:return
            if not found:time.sleep(3)
