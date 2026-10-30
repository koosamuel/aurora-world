"""Loopback-only demo HTTP adapter. Supabase mode uses Auth + RPC instead."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import json
import threading
from .jobs import Store, PROJECTS, work_once


def serve(root, host='127.0.0.1', port=8765, public_input=None, reference_root=None):
    root=Path(root); store=Store(root/'results/local-demo.sqlite3')
    from .sampling import BriefStore, Conflict, MAX_BYTES as SAMPLING_BYTES, decode as sampling_decode, envelope as sampling_envelope, seed as sampling_seed
    sampling=BriefStore(root/'results/sampling-briefs.sqlite3');sampling_seed(sampling,root)
    from .generation import GenerationService, decode_request as generation_decode
    if reference_root is None:
        candidate=root.parent/'04_데이터/원본/공개연구데이터/ABO_디지털샘플링_선정'
        if candidate.is_dir():reference_root=candidate
    generation=GenerationService(root,sampling,reference_root)
    from .ai_sampling import AIService
    ai=AIService(root,sampling)
    from .sample_reviews import ReviewStore, Denied as ReviewDenied, decode as review_decode
    reviews=ReviewStore(root,sampling,generation,ai)
    from .pattern_links import PatternLinks
    pattern_links=PatternLinks(root,reviews)
    from .sampling_effects import EffectStore, decode as effect_decode
    effects=EffectStore(root,pattern_links)
    from .forecast_files import ForecastFiles, decode as file_decode
    from .inputs import MAX_BYTES as FILE_BYTES
    weekly=ForecastFiles(root,reviews)
    from .sketch_fit import SketchFitService, MAX_BODY as SKETCH_BYTES
    sketch_fit=SketchFitService(root,sampling)
    from .learned3d import Learned3DService
    learned3d=Learned3DService(root,sampling)
    pool=ThreadPoolExecutor(max_workers=2)
    gpu_pool=ThreadPoolExecutor(max_workers=1)
    if public_input is None:public_input=root.parent/'04_데이터/가공/2026-10-26_UCI_Online_Retail_II/weekly.json'
    from .public_jobs import PublicStore
    public=PublicStore(root/'results/public-jobs.sqlite3',public_input) if Path(public_input).exists() else None
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root/'client'),**kwargs)
        def respond(self,payload,status=200):
            data=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
            self.end_headers();self.wfile.write(data)
        def api_project(self):return parse_qs(urlparse(self.path).query).get('project_type',['forecast'])[0]
        def allowed_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
        def review_token(self):
            auth=self.headers.get('Authorization','')
            return auth[7:] if auth.startswith('Bearer ') else None
        def do_GET(self):
            if not self.allowed_host():return self.respond(dict(error='로컬 호스트만 허용됩니다.'),403)
            path=urlparse(self.path).path
            try:
                if path.startswith('/api/learned3d/'):
                    if urlparse(self.path).query:raise ValueError('쿼리 거부')
                    if path=='/api/learned3d/capabilities':return self.respond(learned3d.capabilities())
                    bits=path.split('/')
                    if len(bits)==5 and bits[3]=='runs':
                        row=learned3d.get(bits[4]);return self.respond(row or dict(error='실행 없음'),200 if row else 404)
                    if len(bits)==6 and bits[3]=='artifacts':
                        p=learned3d.artifact(bits[4],bits[5])
                        if not p:return self.respond(dict(error='파일 없음'),404)
                        raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type', 'model/gltf-binary' if p.suffix=='.glb' else 'image/png' if p.suffix=='.png' else 'application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw);return
                    raise ValueError('경로 오류')
                if path=='/api/sketch-fit/capabilities':
                    try: import PIL
                    except ImportError: return self.respond(dict(available=False,reason='Pillow 설치 필요: pip install -e ".[data]"'))
                    return self.respond(dict(available=True,mode='local',view='front',family='BUNNY'))
                if path.startswith('/api/sketch-fit/artifacts/'):
                    if urlparse(self.path).query: raise ValueError('쿼리 거부')
                    bits=path.split('/')
                    if len(bits)!=6: raise ValueError('파일 경로 거부')
                    p=sketch_fit.artifact(bits[4],bits[5])
                    if not p: return self.respond(dict(error='보정 파일 없음'),404)
                    raw=p.read_bytes();self.send_response(200)
                    self.send_header('Content-Type','image/png' if p.suffix=='.png' else 'model/gltf-binary' if p.suffix=='.glb' else 'application/json')
                    self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw);return
                if path.startswith('/api/forecast-files/'):
                    bits=path.split('/');query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                    if path=='/api/forecast-files/datasets':
                        if query:raise ValueError('파일 목록 쿼리 거부')
                        return self.respond(weekly.datasets(include_rejected=True))
                    if path=='/api/forecast-files/runs':
                        if set(query)!={'dataset_id'} or len(query['dataset_id'])!=1:raise ValueError('단일 dataset_id 필요')
                        return self.respond(weekly.list_dataset(query['dataset_id'][0]))
                    if len(bits)==5 and bits[3]=='runs':
                        if set(query)!={'dataset_id'} or len(query['dataset_id'])!=1:raise ValueError('단일 dataset_id 필요')
                        row=weekly.get_dataset_run(query['dataset_id'][0],bits[4]);return self.respond(row if row else dict(error='이 데이터셋의 실행 없음'),200 if row else 404)
                    if query:raise ValueError('파일 API 쿼리 거부')
                    if len(bits)==6 and bits[3]=='artifacts':
                        p=weekly.artifact(bits[4],bits[5])
                        if not p:return self.respond(dict(error='완료한 현재 시도의 파일 없음'),404)
                        raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type','application/json' if p.suffix=='.json' else 'text/csv; charset=utf-8' if p.suffix=='.csv' else 'text/markdown; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Disposition','attachment; filename='+p.name);self.end_headers();self.wfile.write(raw);return
                    return self.respond(dict(error='지원하지 않는 파일 입력 경로'),404)
                if path.startswith('/api/sampling-effects/'):
                    if urlparse(self.path).query:raise ValueError('효과 API 쿼리 거부')
                    if path=='/api/sampling-effects/catalog':return self.respond(effects.catalog())
                    if path=='/api/sampling-effects/examples/six-products':return self.respond(effects.example())
                    bits=path.split('/')
                    if len(bits) in (5,6) and bits[3]=='reports':
                        row=effects.get(unquote(bits[4]),int(bits[5]) if len(bits)==6 else None)
                        return self.respond(row if row else dict(error='효과 보고서 없음'),200 if row else 404)
                    if len(bits)==7 and bits[3]=='artifacts':
                        p=effects.artifact(unquote(bits[4]),int(bits[5]),bits[6])
                        if not p:return self.respond(dict(error='보고 파일 없음'),404)
                        raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type','application/json' if p.suffix=='.json' else 'text/csv; charset=utf-8' if p.suffix=='.csv' else 'text/markdown; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Disposition','attachment; filename='+p.name);self.end_headers();self.wfile.write(raw);return
                    return self.respond(dict(error='지원하지 않는 효과 경로'),404)
                if path.startswith('/api/pattern-links/'):
                    if urlparse(self.path).query:raise ValueError('패턴 연결 API 쿼리 거부')
                    if path=='/api/pattern-links/catalog':return self.respond(pattern_links.catalog())
                    bits=path.split('/')
                    if len(bits)==5 and bits[3] in ('products','export'):
                        return self.respond(pattern_links.export(unquote(bits[4])) if bits[3]=='export' else pattern_links.get(unquote(bits[4])))
                    if len(bits)==6 and bits[3]=='bundles':return self.respond(pattern_links.bundle(unquote(bits[4]),int(bits[5])))
                    if len(bits)==5 and bits[3]=='assets':
                        p=pattern_links.asset(bits[4])
                        if not p:return self.respond(dict(error='등록된 연결 조각 없음'),404)
                        raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw);return
                    return self.respond(dict(error='지원하지 않는 패턴 연결 경로'),404)
                if path.startswith('/api/sample-reviews/'):

                    if urlparse(self.path).query:raise ValueError('검토 API 쿼리는 허용하지 않습니다.')
                    if path=='/api/sample-reviews/catalog':return self.respond(reviews.catalog())
                    if path=='/api/sample-reviews/session':return self.respond(dict(actor=reviews.actor(self.review_token()),authentication='local_demo_persona_only'))
                    bits=path.split('/')
                    if len(bits)==5 and bits[3] in ('products','export'):
                        row=reviews.export(unquote(bits[4])) if bits[3]=='export' else reviews.get(unquote(bits[4]))
                        return self.respond(row if row else dict(error='등록된 검토 없음'),200 if row else 404)
                    if len(bits)==5 and bits[3]=='assets':
                        p=reviews.asset(bits[4])
                        if not p:return self.respond(dict(error='등록된 검토 자산 없음'),404)
                        raw=p.read_bytes();self.send_response(200);self.send_header('Content-Type',{'.png':'image/png','.svg':'image/svg+xml','.glb':'model/gltf-binary'}[p.suffix]);self.send_header('Content-Length',str(len(raw)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw);return
                    return self.respond(dict(error='지원하지 않는 검토 경로'),404)
                if path.startswith('/api/ai-sampling/'):
                    if urlparse(self.path).query:raise ValueError('AI API 쿼리는 허용하지 않습니다.')
                    if path=='/api/ai-sampling/catalog':return self.respond(ai.catalog())
                    bits=path.split('/')
                    if len(bits)==5 and bits[3]=='runs':
                        row=ai.get(bits[-1]);return self.respond(row if row else dict(error='AI 실행 없음'),200 if row else 404)
                    if len(bits)==6 and bits[3]=='artifacts':
                        file=ai.artifact(bits[-2],bits[-1])
                        if not file:return self.respond(dict(error='완료한 AI 파일 없음'),404)
                        data=file.read_bytes();self.send_response(200)
                        self.send_header('Content-Type','image/png' if file.suffix=='.png' else 'application/json')
                        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
                        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
                    return self.respond(dict(error='지원하지 않는 AI 경로'),404)
                if path.startswith('/api/generation/'):
                    if urlparse(self.path).query:raise ValueError('생성 API 쿼리는 허용하지 않습니다.')
                    if path=='/api/generation/catalog':return self.respond(generation.catalog())
                    if path.startswith('/api/generation/runs/'):
                        bits=path.split('/')
                        if len(bits)!=5:raise ValueError('생성 조회 경로를 확인하세요.')
                        row=generation.get(bits[-1]);return self.respond(row if row else dict(error='생성 실행 없음'),200 if row else 404)
                    if path.startswith('/api/generation/artifacts/'):
                        bits=path.split('/')
                        if len(bits)!=6:raise ValueError('생성 파일 경로를 확인하세요.')
                        file=generation.artifact(bits[-2],bits[-1])
                        if not file:return self.respond(dict(error='완료한 생성 파일 없음'),404)
                        mime='model/gltf-binary' if file.suffix=='.glb' else 'image/svg+xml' if file.suffix=='.svg' else 'application/json' if file.suffix=='.json' else 'text/markdown; charset=utf-8'
                        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(file.stat().st_size));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Disposition','attachment; filename='+file.name);self.end_headers()
                        with file.open('rb') as stream:self.copyfile(stream,self.wfile)
                        return
                    return self.respond(dict(error='지원하지 않는 생성 경로입니다.'),404)
                if path=='/api/sampling/briefs':return self.respond(sampling.list())
                if path.startswith('/api/sampling/briefs/'):
                    bits=path.split('/')
                    if len(bits)!=6:raise ValueError('명세 조회 경로를 확인하세요.')
                    version=int(bits[-1]);row=sampling.get(unquote(bits[-2]),version)
                    return self.respond(row if row else dict(error='등록된 명세 없음'),200 if row else 404)
                if path=='/api/datasets':return self.respond([dict(id='local-generated',name='로컬 합성 · 새 계산',dataset_kind='synthetic',generator_config=dict(skus=50,weeks=156))]+([public.dataset] if public else [])+weekly.datasets())
                if path.startswith('/api/public/artifacts/'):
                    bits=path.split('/')
                    file=public.artifact(bits[-2],bits[-1]) if public and len(bits)==6 else None
                    if not file:return self.respond(dict(error='완료한 산출물이 없습니다.'),404)
                    mime='application/json' if file.suffix=='.json' else 'text/markdown' if file.suffix=='.md' else 'text/csv'
                    self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(file.stat().st_size));self.send_header('Cache-Control','no-store');self.send_header('Content-Disposition','attachment; filename='+file.name);self.end_headers()
                    with file.open('rb') as stream:self.copyfile(stream,self.wfile)
                    return
                if path.startswith('/api/public/runs'):
                    if not public:return self.respond(dict(error='공개 입력 미등록'),404)
                    if path=='/api/public/runs':return self.respond(public.list('forecast'))
                    row=public.get(unquote(path.split('/')[-1]),'forecast')
                    return self.respond(row if row else dict(error='실행 없음'),200 if row else 404)
                if path=='/api/identity-demo':
                    from .identity import demo
                    query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
                    if set(query)-{'case'} or len(query.get('case',['valid']))!=1:raise ValueError('invalid identity query')
                    return self.respond(demo(root,query.get('case',['valid'])[0]))
                if path=='/api/health':return self.respond(dict(mode='local',synthetic=True,projects=PROJECTS))
                if path=='/api/runs':return self.respond(store.list(self.api_project()))
                if path.startswith('/api/runs/'):
                    r=store.get(unquote(path.split('/')[-1]),self.api_project())
                    return self.respond(r if r else dict(error='실행을 찾을 수 없습니다.'),200 if r else 404)
                if path.startswith('/api/'):return self.respond(dict(error='지원하지 않는 요청입니다.'),404)
                return super().do_GET()
            except ReviewDenied as e:return self.respond(dict(error=str(e)),403)
            except (ValueError,TypeError) as e:return self.respond(dict(error=str(e)),400)
        def do_POST(self):
            if not self.allowed_host():return self.respond(dict(error='로컬 호스트만 허용됩니다.'),403)
            # A demo server can run jobs, so cross-origin POSTs are refused even on loopback.
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':
                return self.respond(dict(error='다른 출처의 요청입니다.'),403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                path=urlparse(self.path).path
                limit=SKETCH_BYTES if path in ('/api/sketch-fit/runs','/api/learned3d/runs') else FILE_BYTES if path in ('/api/forecast-files/validate','/api/forecast-files/datasets') else SAMPLING_BYTES if path in ('/api/sampling/validate','/api/sampling/briefs') else 128*1024 if path=='/api/sampling-effects/reports' else 65536
                if not 0<size<=limit:raise ValueError('요청 크기를 확인하세요.')
                if path=='/api/learned3d/runs':
                    if urlparse(self.path).query:raise ValueError('쿼리 거부')
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('application/json 필요')
                    try:return self.respond(learned3d.request(self.rfile.read(size),gpu_pool),202)
                    except RuntimeError as e:return self.respond(dict(error=str(e)),409)
                if path=='/api/sketch-fit/runs':
                    if urlparse(self.path).query: raise ValueError('쿼리 거부')
                    if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('application/json 필요')
                    try: return self.respond(sketch_fit.run(self.rfile.read(size)),201)
                    except ImportError: return self.respond(dict(error='Pillow 설치 필요: pip install -e ".[data]"'),503)
                    except RuntimeError as exc: return self.respond(dict(error=str(exc)),409)

                if path.startswith('/api/forecast-files/'):
                    if urlparse(self.path).query:raise ValueError('파일 API 쿼리 거부')
                    raw=self.rfile.read(size)
                    if path=='/api/forecast-files/validate':return self.respond(weekly.validate_file(self.review_token(),raw))
                    if path=='/api/forecast-files/datasets':return self.respond(weekly.register(self.review_token(),raw,self.headers.get('X-Weekly-SHA256'),self.headers.get('X-Upload-SHA256')),201)
                    if path=='/api/forecast-files/runs':
                        row=weekly.request(self.review_token(),file_decode(raw));pool.submit(weekly.work_once);return self.respond(row,202)
                    bits=path.split('/')
                    if len(bits)==6 and bits[3]=='runs' and bits[5]=='cancel':
                        req=file_decode(raw)
                        if set(req)!={'dataset_id'}:raise ValueError('취소 데이터셋 필요')
                        row=weekly.cancel_run(self.review_token(),req['dataset_id'],bits[4]);return self.respond(row if row else dict(error='이 데이터셋의 실행 없음'),200 if row else 404)
                    return self.respond(dict(error='지원하지 않는 파일 경로'),404)
                if path=='/api/sampling-effects/reports':
                    if urlparse(self.path).query:raise ValueError('효과 API 쿼리 거부')
                    return self.respond(effects.register(self.review_token(),effect_decode(self.rfile.read(size))),201)
                if path.startswith('/api/pattern-links/'):
                    if urlparse(self.path).query:raise ValueError('패턴 연결 API 쿼리 거부')
                    body=review_decode(self.rfile.read(size))
                    if path=='/api/pattern-links/links':return self.respond(pattern_links.link(self.review_token(),body),201)
                    return self.respond(dict(error='지원하지 않는 패턴 연결 경로'),404)
                if path.startswith('/api/sample-reviews/'):
                    if urlparse(self.path).query:raise ValueError('검토 API 쿼리는 허용하지 않습니다.')
                    body=review_decode(self.rfile.read(size))
                    if path=='/api/sample-reviews/session':return self.respond(reviews.session(body))
                    if path=='/api/sample-reviews/revisions':return self.respond(reviews.revision(self.review_token(),body),201)
                    if path=='/api/sample-reviews/events':return self.respond(reviews.event(self.review_token(),body))
                    return self.respond(dict(error='지원하지 않는 검토 경로'),404)
                if path in ('/api/sampling/validate','/api/sampling/briefs'):
                    brief=sampling_decode(self.rfile.read(size))
                    return self.respond(sampling_envelope(brief) if path.endswith('/validate') else sampling.register(brief),200 if path.endswith('/validate') else 201)
                if path=='/api/generation/runs':
                    if urlparse(self.path).query:raise ValueError('생성 API 쿼리는 허용하지 않습니다.')
                    req=generation_decode(self.rfile.read(size));row,new=generation.request(req)
                    if new:pool.submit(generation.work,row['id'])
                    return self.respond(row,202)
                if path=='/api/ai-sampling/runs':
                    if urlparse(self.path).query:raise ValueError('AI API 쿼리는 허용하지 않습니다.')
                    req=generation_decode(self.rfile.read(size));row,new=ai.request(req)
                    if new:gpu_pool.submit(ai.work,row['id'])
                    return self.respond(row,202)
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('객체 형식의 요청이 필요합니다.')
                path=urlparse(self.path).path
                if path=='/api/public/runs':
                    if not public:raise ValueError('공개 입력 미등록')
                    r=public.request('forecast',body.get('request_key'),body.get('config',{}));pool.submit(public.work_once);return self.respond(r,202)
                if path=='/api/runs':
                    r=store.request(body.get('project_type'),body.get('request_key'),body.get('config'))
                    pool.submit(work_once,store)
                    return self.respond(r,202)
                if path.startswith('/api/runs/') and path.endswith('/cancel'):
                    r=store.cancel(path.split('/')[-2],body.get('project_type'))
                    return self.respond(r if r else dict(error='실행을 찾을 수 없습니다.'),200 if r else 404)
                return self.respond(dict(error='지원하지 않는 요청입니다.'),404)
            except Conflict as e:return self.respond(dict(error=str(e)),409)
            except ReviewDenied as e:return self.respond(dict(error=str(e)),403)
            except (ValueError,TypeError) as e:return self.respond(dict(error=str(e)),400)
    # A periodic worker also recovers expired leases after startup.
    stopped=threading.Event()
    def worker_loop():
        while not stopped.is_set():
            progressed=work_once(store)
            progressed=weekly.work_once() or progressed
            if not progressed:stopped.wait(1)
    worker=threading.Thread(target=worker_loop,daemon=True)
    worker.start()
    server=ThreadingHTTPServer((host,port),Handler)
    print(f'Aurora synthetic demo: http://{host}:{port}',flush=True)
    try:server.serve_forever()
    finally:stopped.set();server.server_close();worker.join(timeout=5);pool.shutdown(wait=True);gpu_pool.shutdown(wait=True)
