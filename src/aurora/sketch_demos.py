"""Four local project sketches. Separate synthetic demo sources, never U20 registrations."""
import base64,hashlib,json,unicodedata
from pathlib import Path
from .learned3d_worker import sha
PROMPTS={
 'BUNNY':'a single plush rabbit toy, full body, round head, two long ears, one upright ear and one floppy bent ear, two short arms, two long legs with round feet',
 'BEAR':'a single seated teddy bear plush toy, round head, two small round ears, short rounded muzzle, two arms, rounded belly, two large round feet facing forward',
 'ELEPHANT':'a single elephant-like plush toy as drawn, standing upright, round head, two large round ears, a short rounded snout, two arms and two long legs with round feet',
 'DUCK':'a single lying duck plush toy, low round head with a broad flat bill, long rounded horizontal body, small wings and webbed feet, full body'
}
ITEMS=[('rabbit','토끼','BUNNY','01_토끼_스케치.jpg'),('bear','곰','BEAR','02_곰_스케치.jpg'),('elephant','코끼리','ELEPHANT','03_코끼리_스케치.jpg'),('duck','오리','DUCK','04_오리_스케치.jpg')]
FOLDER='04_데이터/가공/2026-10-29_봉제완구_스케치4종'
def image_path(root,id):
    entry=next((x for x in ITEMS if x[0]==id),None)
    if not entry:raise ValueError('미지원 데모 ID')
    folder=Path(root).parent/FOLDER
    if not folder.is_dir():raise ValueError('로컬 데모 그림 폴더 없음')
    p=next((p for p in folder.iterdir() if unicodedata.normalize('NFC',p.name)==entry[3]),None)
    if not p or not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=2*1024*1024:raise ValueError('로컬 데모 그림 없음/크기 오류')
    return p

def catalog(root):
    rows=[]
    for id,label,family,name in ITEMS:
        try:p=image_path(root,id)
        except ValueError:continue
        row=dict(id='local-demo:'+id,demo_id=id,label=label,family=family,data_kind='synthetic',source_kind='local_sketch_demo',dimensions_mm=dict(width=180,height=300,depth=120),dimensions_origin='illustrative only; no scale applied',image_sha256=sha(p),image_bytes=p.stat().st_size,prompt=PROMPTS[family],prompt_origin='fixed demo caption; not automatically extracted',image_url='./api/learned3d/demo-images/'+id)
        row['checksum']=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest();rows.append(row)
    return rows

def prepare(service,raw):
    if not 0<len(raw)<=65536:raise ValueError('데모 요청 크기 오류')
    def pairs(items):
        if len(dict(items))!=len(items):raise ValueError('중복 JSON 키')
        return dict(items)
    try:req=json.loads(raw,object_pairs_hook=pairs)
    except (RecursionError,UnicodeDecodeError) as e:raise ValueError('데모 JSON 오류') from e
    if not isinstance(req,dict) or set(req)!={'demo_id','source_checksum','storage_consent'} or req['storage_consent'] is not True:raise ValueError('데모 ID·현재 해시·저장 동의 필요')
    if service.config()['engine']!='TripoSG-scribble':raise ValueError('4종 데모는 TripoSG-scribble 필요')
    source=next((s for s in catalog(service.root) if s['demo_id']==req['demo_id'] and s['checksum']==req['source_checksum']),None)
    if not source:raise ValueError('데모 입력/현재 해시 확인 필요')
    image=image_path(service.root,source['demo_id']).read_bytes()
    if hashlib.sha256(image).hexdigest()!=source['image_sha256']:raise ValueError('데모 파일 변경')
    return service.request(json.dumps(dict(image_base64=base64.b64encode(image).decode(),dimensions_mm=source['dimensions_mm'],view='single',source_id=source['id'],source_checksum=source['checksum'])).encode())
