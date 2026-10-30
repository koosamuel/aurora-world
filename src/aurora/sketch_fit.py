"""Local-only, deterministic front-silhouette fitting. Not Sketch2Mesh reproduction."""
import base64
import binascii
import hashlib
import io
import json
import math
import re
import threading
import uuid
from pathlib import Path
from .generation import procedural, fit, bounds, make_glb

MAX_BODY = 3 * 1024 * 1024
SIZE = 128
SCOPE = '정면 토끼 규칙 기하 보정. 深度 미추정·학습모형 아님·봉제/패턴/BOM 미검증.'.replace('深度', '깊이')
PARAMS = {'body_width': (.7, 1.3), 'head_width': (.7, 1.3), 'head_height': (.75, 1.25), 'ear_length': (.65, 1.35), 'ear_spacing': (.7, 1.3)}

def decode(raw):
    if not 0 < len(raw) <= MAX_BODY: raise ValueError('요청 크기 초과')
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out: raise ValueError('중복 JSON 키')
            out[k] = v
        return out
    def bad(_): raise ValueError('비유한 수치')
    try: req = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    except RecursionError as exc: raise ValueError('JSON 중첩이 너무 깊습니다.') from exc
    if not isinstance(req, dict) or set(req) != {'image_base64', 'dimensions_mm', 'view'}: raise ValueError('이미지·dimensions_mm·view만 허용')
    if req['view'] != 'front': raise ValueError('정면만 지원')
    dims = req['dimensions_mm']
    if not isinstance(dims, dict) or set(dims) != {'width', 'height', 'depth'}: raise ValueError('세 치수 필요')
    for v in dims.values():
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not 10 <= v <= 2000: raise ValueError('목표 치수는 10~2000mm')
    if not isinstance(req['image_base64'], str): raise ValueError('base64 이미지 필요')
    try: image = base64.b64decode(req['image_base64'], validate=True)
    except (ValueError, binascii.Error) as exc: raise ValueError('잘못된 base64') from exc
    if not 0 < len(image) <= 2 * 1024 * 1024: raise ValueError('이미지는 최대 2MiB')
    return req, image

def normalize(mask):
    from PIL import Image
    bbox = mask.getbbox()
    if not bbox: raise ValueError('윤곽이 비어 있습니다.')
    cut = mask.crop(bbox)
    w, h = cut.size
    ratio = min((SIZE - 16) / w, (SIZE - 16) / h)
    cut = cut.resize((max(1, round(w * ratio)), max(1, round(h * ratio))), Image.Resampling.NEAREST)
    out = Image.new('L', (SIZE, SIZE), 0)
    out.paste(cut, ((SIZE - cut.width) // 2, (SIZE - cut.height) // 2))
    return out

def input_mask(raw):
    from PIL import Image, ImageOps, ImageFilter, ImageDraw, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(raw)) as src:
            if src.format not in ('PNG', 'JPEG') or getattr(src, 'n_frames', 1) != 1: raise ValueError('단일 PNG/JPEG만 지원')
            if src.width * src.height > 8_000_000 or min(src.size) < 32: raise ValueError('32px 이상·8백만 픽셀 이하 필요')
            src.load()
            src = ImageOps.exif_transpose(src).convert('RGBA')
            bg = Image.new('RGBA', src.size, 'white'); bg.alpha_composite(src)
            gray = bg.convert('L'); gray.thumbnail((256, 256))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc: raise ValueError('이미지를 읽을 수 없습니다.') from exc
    ink = gray.point(lambda x: 255 if x < 180 else 0)
    # Close tiny raster gaps, then fill enclosed regions. This is NOT semantic segmentation.
    ink = ink.filter(ImageFilter.MaxFilter(3))
    canvas = Image.new('L', (ink.width + 4, ink.height + 4), 0); canvas.paste(ink, (2, 2))
    flood = canvas.copy(); ImageDraw.floodfill(flood, (0, 0), 128)
    filled = flood.point(lambda x: 0 if x == 128 else 255)
    # Keep the largest connected component, rejecting dust and detached annotations.
    pixels = filled.load(); seen = set(); largest = []
    for y in range(filled.height):
        for x in range(filled.width):
            if not pixels[x, y] or (x, y) in seen: continue
            todo = [(x, y)]; seen.add((x, y)); component = []
            while todo:
                a, b = todo.pop(); component.append((a, b))
                for u, v in ((a-1,b),(a+1,b),(a,b-1),(a,b+1)):
                    if 0 <= u < filled.width and 0 <= v < filled.height and (u,v) not in seen and pixels[u,v]:
                        seen.add((u,v)); todo.append((u,v))
            if len(component) > len(largest): largest = component
    if not .04 <= len(largest) / (ink.width * ink.height) <= .85: raise ValueError('분리 가능한 닫힌 외곽선이 필요합니다. 밝은 배경·어두운 정면 토끼 윤곽을 사용하세요.')
    result = Image.new('L', filled.size, 0)
    for x, y in largest: result.putpixel((x,y),255)
    return normalize(result)

def model(params, dims):
    parts = procedural({'family':'BUNNY','dimensions_mm':dims}, 42, True)
    for p in parts:
        vs = p['vertices']; lo, hi = bounds([p]); c = [(a+b)/2 for a,b in zip(lo,hi)]
        name = p['name']
        sx = params['body_width'] if name == 'body' else params['head_width'] if name in ('head','eye') else 1
        sy = params['head_height'] if name == 'head' else params['ear_length'] if name in ('ear','inner-ear') else 1
        for v in vs:
            v[0] = c[0] + (v[0]-c[0])*sx
            v[1] = c[1] + (v[1]-c[1])*sy
            if name in ('ear','inner-ear'): v[0] *= params['ear_spacing']
    return fit(parts, dims)

def silhouette(parts):
    from PIL import Image, ImageDraw
    lo, hi = bounds(parts); scale = (SIZE-16) / max(hi[0]-lo[0], hi[1]-lo[1])
    mid = [(lo[k]+hi[k])/2 for k in range(3)]
    im = Image.new('L', (SIZE,SIZE), 0); draw = ImageDraw.Draw(im)
    for p in parts:
        pts = [((v[0]-mid[0])*scale+SIZE/2, SIZE/2-(v[1]-mid[1])*scale) for v in p['vertices']]
        for i in range(0,len(p['indices']),3): draw.polygon([pts[j] for j in p['indices'][i:i+3]], fill=255)
    return normalize(im)

def iou(a,b):
    from PIL import ImageChops
    intersection = sum(ImageChops.darker(a,b).histogram()[1:])
    union = sum(ImageChops.lighter(a,b).histogram()[1:])
    return intersection / union if union else 0.

def optimize(target, dims):
    params = {k:1. for k in PARAMS}; before = model(params,dims); score = iou(target,silhouette(before)); initial = score
    history = [score]; evaluations = 1
    for step in (.18,.09,.045):
        for key,(low,high) in PARAMS.items():
            winner = params; best = score
            for direction in (-1,1):
                trial = dict(params); trial[key] = max(low,min(high,params[key]+direction*step))
                value = iou(target,silhouette(model(trial,dims))); evaluations += 1
                if value > best: winner,best = trial,value
            params,score = winner,best; history.append(score)
    return before,model(params,dims),dict(before_iou=initial,after_iou=score,history=history,evaluations=evaluations,parameters=params)

class SketchFitService:
    def __init__(self,root):
        self.root = Path(root)/'results/sketch-fit'; self.lock = threading.Lock()
    def run(self,raw):
        req,image = decode(raw)
        if not self.lock.acquire(blocking=False): raise RuntimeError('다른 윤곽 보정이 실행 중입니다. 잠시 후 다시 시도하세요.')
        try:
            target = input_mask(image)
            before,after,metrics = optimize(target, req['dimensions_mm'])
            self.root.mkdir(parents=True,exist_ok=True)
            if len(list(self.root.iterdir())) >= 100: raise ValueError('로컬 보정 결과 100건 한도입니다. 결과를 정리한 후 다시 실행하세요.')
            run_id = uuid.uuid4().hex; dest = self.root/run_id; dest.mkdir()
            files = {'before.glb':make_glb(before),'after.glb':make_glb(after),'input.bin':image}
            for name,im in [('target.png',target),('before.png',silhouette(before)),('after.png',silhouette(after))]:
                buf = io.BytesIO(); im.save(buf,format='PNG'); files[name] = buf.getvalue()
            report = dict(id=run_id,method='bunny-front-silhouette-fit-v1',scope=SCOPE,dimensions_mm=req['dimensions_mm'],depth_source='user_assumption_not_reconstructed',input_sha256=hashlib.sha256(image).hexdigest(),engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),metrics=metrics,manufacturing_verified=False,design_approved=False,warnings=['단일 정면·직교 투영 및 밝은 배경의 닫힌 외곽선 가정','목표 마스크를 먼저 확인하세요. 사진 배경·글씨·열린 선은 오분할될 수 있습니다.','IoU는 정규화된 2D 실루엣 겹침이지 실제 치수 정확도·3D 정답·봉제 적합성이 아닙니다.','깊이는 사용자 가정값이며 원화에서 복원하지 않습니다.'])
            files['report.json'] = json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2).encode()
            for name,data in files.items(): (dest/name).write_bytes(data)
            report['artifacts'] = [dict(file=k,bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for k,v in files.items() if k!='input.bin']
            (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False))
            return report
        finally: self.lock.release()
    def artifact(self,run_id,name):
        if not re.fullmatch('[0-9a-f]{32}',run_id) or name not in {'before.glb','after.glb','target.png','before.png','after.png','report.json'}: raise ValueError('파일 경로 거부')
        dest = self.root/run_id
        if not (dest/'manifest.json').is_file(): return None
        meta = next((a for a in json.loads((dest/'manifest.json').read_text())['artifacts'] if a['file']==name),None)
        p = dest/name
        if not meta or not p.is_file(): return None
        data = p.read_bytes()
        if len(data)!=meta['bytes'] or hashlib.sha256(data).hexdigest()!=meta['sha256']: raise ValueError('산출물 무결성 오류')
        return p
