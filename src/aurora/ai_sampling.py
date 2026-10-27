"""Optional U21 learned 2D preview adapter. No model imports in the base server.

Only registered, validated U20 synthetic artwork enters the offline worker.
The generic queue's durable read/artifact logic is shared; its geometry engine
and model-free reports remain independent.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, os, subprocess, uuid
from .generation import GenerationService, catalog as source_catalog, digest, ident, decode_request
from .identity import require, serialized
from .sampling import Conflict

SETTINGS = dict(size=512, steps=20, strengths=[0.45, 0.70], guidance_scale=7.5,
                scheduler='DDIM', safety_checker=True)
FILES = {'input.json', 'input.png', 'preserve.png', 'reinterpret.png',
         'analysis.json', 'report.json', 'models.json', 'artifacts.json'}

def engine_hash():
    return digest(b''.join(Path(__file__).with_name(n).read_bytes()
                         for n in ('ai_sampling.py', 'ai_worker.py', 'sampling.py', 'identity.py')))

def runtime(root):
    """Developer-only paths; never accepted from HTTP. Return sanitized status."""
    p = Path(root)/'.ai-local.json'
    require(p.is_file(), 'AI 실행 환경이 없습니다. docs/AI_SAMPLING.md의 로컬 설정을 먼저 준비하세요.')
    c = json.loads(p.read_text())
    require(set(c) == {'python', 'sd15', 'clip'}, '로컬 AI 설정 필드를 확인하세요.')
    require(all(isinstance(v, str) and Path(v).is_absolute() and Path(v).exists() for v in c.values()), '로컬 AI 경로가 없습니다.')
    require(Path(c['python']).is_file() and Path(c['sd15']).is_dir() and Path(c['clip']).is_dir(), 'AI 실행/모델 경로 형식을 확인하세요.')
    return c

def public_catalog(root, store=None):
    data = source_catalog(root, store)
    data.update(schema_version='aurora-ai-sampling-catalog-v1', learned_model=True,
                settings=SETTINGS, runtime_available=False, runtime_message='')
    try:
        runtime(root); data['runtime_available'] = True
        data['runtime_message'] = '오프라인 모델 설정 있음 · 추론 시작 시 가중치/런타임 검증'
    except (ValueError, OSError, TypeError):
        data['runtime_message'] = '로컬 AI 환경 미설정 · 저장 결과는 게시 데모에서 확인하세요.'
    data['methods'] = {'interpretation': 'CLIP 픽셀 분류 후보', 'generation': 'SD 1.5 image-to-image · 2D PNG'}
    return data

class AIService(GenerationService):
    def __init__(self, root, brief_store):
        self.root=Path(root); self.briefs=brief_store
        self.output=self.root/'results/ai-samples'; self.output.mkdir(parents=True, exist_ok=True)
        self.dbpath=self.root/'results/ai-sampling.sqlite3'
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS generation_runs(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,body TEXT NOT NULL,result TEXT,error TEXT,created_at TEXT NOT NULL)')
            db.execute("UPDATE generation_runs SET state='failed',error='AI 작업이 서버 재시작으로 중단됐습니다. 새 요청으로 재실행하세요.' WHERE state IN ('queued','running')")

    def catalog(self): return public_catalog(self.root, self.briefs)

    def request(self, req):
        req=decode_request(serialized(req)); c=runtime(self.root)
        sources={s['id']:s for s in self.catalog()['sources']}
        require(req['source_id'] in sources, 'AI 입력은 등록된 자체 합성 U20 원화만 지원합니다.')
        source=sources[req['source_id']]
        require(source['checksum']==req['source_checksum'], '명세 해시가 바뀌었습니다. 다시 선택하세요.')
        body=dict(source=source, seed=req['seed'], settings=SETTINGS, engine_sha256=engine_hash(),
                  manifest_sha256=digest((self.root/'configs/ai/model-manifest.json').read_bytes()),
                  runtime_config_sha256=digest(serialized(c)))
        fingerprint=digest(serialized(body)); new=False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute('SELECT id,fingerprint FROM generation_runs WHERE request_key=?',(req['request_key'],)).fetchone()
            if r:
                if r['fingerprint']!=fingerprint: raise Conflict('동일 요청 키의 AI 입력/설정을 변경할 수 없습니다.')
                id=r['id']
            else:
                require(db.execute("SELECT count(*) FROM generation_runs WHERE state IN ('queued','running')").fetchone()[0]==0,
                        'AI 작업은 한 번에 하나입니다. 현재 작업 완료 후 다시 시도하세요.')
                id=uuid.uuid4().hex
                db.execute('INSERT INTO generation_runs VALUES(?,?,?,?,?,?,?,?)',
                           (id,req['request_key'],fingerprint,'queued',serialized(body).decode(),None,None,datetime.now(timezone.utc).isoformat()))
                new=True
        return self.get(id),new

    def work(self, id):
        ident(id)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute("SELECT body FROM generation_runs WHERE id=? AND state='queued'",(id,)).fetchone()
            if not r:return False
            db.execute("UPDATE generation_runs SET state='running' WHERE id=?",(id,))
        try:
            body=json.loads(r['body']); c=runtime(self.root)
            require(body['engine_sha256']==engine_hash() and body['settings']==SETTINGS, 'AI 코드/설정이 변경됐습니다.')
            require(body['manifest_sha256']==digest((self.root/'configs/ai/model-manifest.json').read_bytes()) and
                    body['runtime_config_sha256']==digest(serialized(c)), 'AI 런타임/모델 명세가 변경됐습니다.')
            job=self.output/(id+'.json');job.write_bytes(serialized(body))
            env=dict(os.environ, PYTHONPATH=str(self.root/'src'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
            with (self.output/(id+'.log')).open('wb') as log:
                subprocess.run([c['python'],'-m','aurora.ai_worker','--root',str(self.root),'--job',str(job),'--output',str(self.output/id)],
                               env=env,stdout=log,stderr=log,check=True,timeout=600)
            result=json.loads((self.output/id/'result.json').read_text())
            require(result['report']['schema_version']=='aurora-ai-sample-v1' and
                    result['report']['source_checksum']==body['source']['checksum'], 'AI 보고서 입력 해시가 다릅니다.')
            require({a['file'] for a in result['artifacts']}==FILES, 'AI 산출물 목록이 다릅니다.')
            for a in result['artifacts']:
                p=self.output/id/a['file']
                require(p.stat().st_size==a['bytes'] and digest(p.read_bytes())==a['sha256'], 'AI 산출물 해시가 다릅니다.')
            with self.db() as db:db.execute("UPDATE generation_runs SET state='succeeded',result=? WHERE id=?",(serialized(result).decode(),id))
        except Exception as e:
            # Do not expose local environment paths or subprocess internals via HTTP.
            error='AI 추론 실패 · 로컬 results/ai-samples 실행 로그를 확인하세요.' if isinstance(e,subprocess.SubprocessError) else str(e)[:300]
            with self.db() as db:db.execute("UPDATE generation_runs SET state='failed',error=? WHERE id=?",(error,id))
        return True
