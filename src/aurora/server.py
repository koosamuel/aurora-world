"""Loopback-only demo HTTP adapter. Supabase mode uses Auth + RPC instead."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import json
import threading
from .jobs import Store, PROJECTS, work_once


def serve(root, host='127.0.0.1', port=8765):
    root=Path(root); store=Store(root/'results/local-demo.sqlite3')
    pool=ThreadPoolExecutor(max_workers=2)
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
        def do_GET(self):
            if not self.allowed_host():return self.respond(dict(error='로컬 호스트만 허용됩니다.'),403)
            path=urlparse(self.path).path
            try:
                if path=='/api/health':return self.respond(dict(mode='local',synthetic=True,projects=PROJECTS))
                if path=='/api/runs':return self.respond(store.list(self.api_project()))
                if path.startswith('/api/runs/'):
                    r=store.get(unquote(path.split('/')[-1]),self.api_project())
                    return self.respond(r if r else dict(error='실행을 찾을 수 없습니다.'),200 if r else 404)
                if path.startswith('/api/'):return self.respond(dict(error='지원하지 않는 요청입니다.'),404)
                return super().do_GET()
            except ValueError as e:return self.respond(dict(error=str(e)),400)
        def do_POST(self):
            if not self.allowed_host():return self.respond(dict(error='로컬 호스트만 허용됩니다.'),403)
            # A demo server can run jobs, so cross-origin POSTs are refused even on loopback.
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':
                return self.respond(dict(error='다른 출처의 요청입니다.'),403)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:raise ValueError('요청 크기를 확인하세요.')
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):raise ValueError('객체 형식의 요청이 필요합니다.')
                path=urlparse(self.path).path
                if path=='/api/runs':
                    r=store.request(body.get('project_type'),body.get('request_key'),body.get('config'))
                    pool.submit(work_once,store)
                    return self.respond(r,202)
                if path.startswith('/api/runs/') and path.endswith('/cancel'):
                    r=store.cancel(path.split('/')[-2],body.get('project_type'))
                    return self.respond(r if r else dict(error='실행을 찾을 수 없습니다.'),200 if r else 404)
                return self.respond(dict(error='지원하지 않는 요청입니다.'),404)
            except (ValueError,TypeError) as e:return self.respond(dict(error=str(e)),400)
    # A periodic worker also recovers expired leases after startup.
    stopped=threading.Event()
    def worker_loop():
        while not stopped.is_set():
            if not work_once(store):stopped.wait(1)
    worker=threading.Thread(target=worker_loop,daemon=True)
    worker.start()
    server=ThreadingHTTPServer((host,port),Handler)
    print(f'Aurora synthetic demo: http://{host}:{port}',flush=True)
    try:server.serve_forever()
    finally:stopped.set();server.server_close();worker.join(timeout=5);pool.shutdown(wait=True)
