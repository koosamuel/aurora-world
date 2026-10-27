"""U21 deterministic geometric candidates. No learned image model or manufacturing claim."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
from .identity import require, serialized
from .sampling import validate, summary, checksum, fields, integer, Conflict
import copy, html, json, math, random, re, sqlite3, struct, time, uuid
from contextlib import contextmanager

SCHEMA='aurora-digital-sample-v1'
FAMILIES=('BUNNY','COW','DOG','CAT','CACTUS','FRUIT')
ARTIFACT_NAMES={f'{m}.{ext}' for m in ('baseline','candidate') for ext in ('glb','front.svg','side.svg')}|{'report.json','input.json','comparison.md'}
IDS=re.compile(r'[0-9a-f]{32}\Z')

def digest(data):return sha256(data).hexdigest()
def engine_hash():return digest(Path(__file__).read_bytes())
def ident(value):require(isinstance(value,str) and IDS.fullmatch(value),'잘못된 생성 실행 ID입니다.')
def dimensions(b):return {k:float(v) for k,v in summary(b)['dimensions_mm'].items()}

def decode_request(raw):
    def pairs(items):
        d={}
        for k,v in items:require(k not in d,'중복 JSON 키입니다.');d[k]=v
        return d
    def bad(x):raise ValueError('비유한 JSON 수치입니다.')
    require(len(raw)<=16384,'생성 요청은16 KiB 이하입니다.')
    try:d=json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except (UnicodeError,RecursionError,TypeError) as e:raise ValueError('잘못된 생성 JSON입니다.') from e
    fields(d,{'source_id','source_checksum','seed','request_key'},'generation request');integer(d['seed'],'seed',0,2147483647)
    require(isinstance(d['request_key'],str) and re.fullmatch(r'[A-Za-z0-9_-]{8,80}',d['request_key']),'request_key 형식을 확인하세요.')
    require(isinstance(d['source_id'],str) and len(d['source_id'])<=100 and isinstance(d['source_checksum'],str) and re.fullmatch(r'[0-9a-f]{64}',d['source_checksum']),'입력/해시를 확인하세요.')
    return d

def catalog(root,store=None,reference_root=None):
    root=Path(root);items=[]
    if store:
        briefs=[store.get(x['summary']['product_id'],x['summary']['brief_version'])['brief'] for x in store.list()]
    else:briefs=[json.loads(p.read_text()) for p in sorted((root/'configs/examples/sampling').glob('*.json'))]
    for b in briefs:
        validate(b);family=b['product_id'].removeprefix('SYN-')
        if family not in FAMILIES:continue
        entry=dict(id=f"u20:{b['product_id']}:{b['brief_version']}",name=f"{b['product_name']} · 명세 v{b['brief_version']}",data_kind='synthetic',family=family,dimensions_mm=dimensions(b),brief=b,brief_checksum=checksum(b),source=dict(kind='self_generated_synthetic',company_data=False,provenance=b['rights']['provenance']))
        entry['checksum']=digest(serialized(entry));items.append(entry)
    if reference_root:
        reference_root=Path(reference_root);registry=json.loads((root/'configs/sampling-references.json').read_text())
        for item in registry['objects']:
            entry=copy.deepcopy(item);entry['id']='abo:'+item['reference_id'];entry['family']='CUSHION';entry['data_kind']='mixed';entry['name']='공개 쿠션 '+item['reference_id']+' · 가상 치수';entry['brief_checksum']=None
            entry['checksum']=digest(serialized(entry));items.append(entry)
    return dict(schema_version='aurora-generation-catalog-v1',sources=items,methods={'baseline':'규칙 기하 기준선','synthetic_candidate':'부위별 파라미터 기하 생성','mixed_candidate':'공개 ABO 형상의 가상 치수 변환'},learned_model=False)

def ellipsoid(name,center,radii,color,rings=10,segments=20):
    vertices=[];indices=[]
    for j in range(rings+1):
        lat=math.pi*j/rings
        for i in range(segments+1):
            a=2*math.pi*i/segments
            vertices.append([center[0]+radii[0]*math.sin(lat)*math.cos(a),center[1]+radii[1]*math.cos(lat),center[2]+radii[2]*math.sin(lat)*math.sin(a)])
    for j in range(rings):
        for i in range(segments):
            a=j*(segments+1)+i;b=a+segments+1
            if j>0:indices.extend([a,a+1,b])
            if j<rings-1:indices.extend([a+1,b+1,b])
    return dict(name=name,vertices=vertices,indices=indices,color=color)

def bounds(parts):
    vertices=[v for p in parts for v in p['vertices']];require(bool(vertices),'빈 형상입니다.')
    require(all(math.isfinite(x) for v in vertices for x in v),'잘못된 형상 수치입니다.')
    lo=[min(v[k] for v in vertices) for k in range(3)];hi=[max(v[k] for v in vertices) for k in range(3)]
    require(all(hi[k]-lo[k]>1e-9 for k in range(3)),'퇴화한 형상입니다.')
    return lo,hi

def fit(parts,dim):
    lo,hi=bounds(parts);target=[dim['width']/1000,dim['height']/1000,dim['depth']/1000]
    for p in parts:
        p['vertices']=[[(v[k]-(lo[k]+hi[k])/2)*target[k]/(hi[k]-lo[k])+(target[1]/2 if k==1 else 0) for k in range(3)] for v in p['vertices']]
    return parts

def procedural(source,seed,detail):
    rng=random.Random(seed);family=source['family'];colors=[x['hex'] for x in source.get('brief',{}).get('requirements',{}).get('colors',[])];body=colors[0] if colors else '#d8b779';accent=colors[1] if len(colors)>1 else '#f1e0b9'
    parts=[]
    def add(name,c,r,col=body):parts.append(ellipsoid(name,c,r,col))
    add('body',(0,.38,0),(.38,.38,.30))
    if detail and family!='CUSHION':
        add('head',(0,.83,.05),(.31,.30,.26))
        if family=='BUNNY':
            for s in (-1,1):add('ear',(s*.17,1.25,.03),(.09,.34,.08));add('inner-ear',(s*.17,1.26,.10),(.045,.23,.03),accent)
        elif family in ('CAT','COW','DOG'):
            for s in (-1,1):add('ear',(s*.28,1.03,.02),(.12,.19 if family!='DOG' else .30,.09),accent)
            if family=='COW':add('muzzle',(0,.75,.27),(.21,.12,.06),accent)
        elif family=='CACTUS':
            for s in (-1,1):add('arm',(s*.43,.53,0),(.16,.27,.14))
        elif family=='FRUIT':
            add('leaf',(0,1.18,0),(.24,.18,.08),'#488753')
        for s in (-1,1):
            add('foot',(s*.23,.08,.13),(.18,.10,.21),accent);add('eye',(s*.115,.87,.295),(.035,.045,.035),'#24292c')
        # Reproducible design variation, not a probability model or random physical measurement.
        factor=.94+rng.random()*.12
        for p in parts:
            if p['name']=='body':p['vertices']=[[x*factor,y,z] for x,y,z in p['vertices']]
    return fit(parts,source['dimensions_mm'])

def pack_glb(g,bin_data):
    j=serialized(g);j+=b' '*((-len(j))%4);bin_data+=b'\0'*((-len(bin_data))%4)
    return struct.pack('<4sII',b'glTF',2,12+8+len(j)+8+len(bin_data))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(bin_data),0x004e4942)+bin_data

def make_glb(parts):
    g=dict(asset=dict(version='2.0',generator='Aurora U21 procedural geometry v1'),scene=0,scenes=[dict(nodes=[])],nodes=[],meshes=[],materials=[],buffers=[],bufferViews=[],accessors=[]);binary=bytearray()
    def access(data,fmt,component,typ,count,limits=None):
        binary.extend(b'\0'*((-len(binary))%4));offset=len(binary);raw=struct.pack('<'+fmt*len(data),*data);binary.extend(raw)
        view=len(g['bufferViews']);g['bufferViews'].append(dict(buffer=0,byteOffset=offset,byteLength=len(raw)))
        a=dict(bufferView=view,componentType=component,count=count,type=typ)
        if limits:a.update(min=limits[0],max=limits[1])
        g['accessors'].append(a);return len(g['accessors'])-1
    for p in parts:
        lo,hi=bounds([p]);pos=access([x for v in p['vertices'] for x in v],'f',5126,'VEC3',len(p['vertices']),(lo,hi));idx=access(p['indices'],'I',5125,'SCALAR',len(p['indices']))
        rgb=[int(p['color'][i:i+2],16)/255 for i in (1,3,5)];mat=len(g['materials']);g['materials'].append(dict(name=p['name'],pbrMetallicRoughness=dict(baseColorFactor=rgb+[1],metallicFactor=0,roughnessFactor=.92),doubleSided=True))
        center=[(lo[k]+hi[k])/2 for k in range(3)];radii=[(hi[k]-lo[k])/2 for k in range(3)];normals=[]
        for v in p['vertices']:
            direction=[(v[k]-center[k])/(radii[k]**2) for k in range(3)];length=math.sqrt(sum(x*x for x in direction));normals.extend(x/length for x in direction)
        normal=access(normals,'f',5126,'VEC3',len(p['vertices']))
        n=len(g['meshes']);g['meshes'].append(dict(name=p['name'],primitives=[dict(attributes=dict(POSITION=pos,NORMAL=normal),indices=idx,material=mat)]));g['nodes'].append(dict(mesh=n));g['scenes'][0]['nodes'].append(n)
    g['buffers']=[dict(byteLength=len(binary))];return pack_glb(g,bytes(binary))

def parse_glb(raw):
    require(len(raw)>=20 and len(raw)<=16*1024*1024,'GLB 크기를 확인하세요.')
    magic,v,n=struct.unpack_from('<4sII',raw);require(magic==b'glTF' and v==2 and n==len(raw),'GLB2.0 헤더 오류')
    chunks=[];offset=12
    while offset<n:
        require(offset+8<=n,'GLB 청크 헤더 오류');size,kind=struct.unpack_from('<II',raw,offset);require(offset+8+size<=n,'GLB 청크 길이 오류');chunks.append((kind,raw[offset+8:offset+8+size]));offset+=8+size
    require(len(chunks)==2 and chunks[0][0]==0x4e4f534a and chunks[1][0]==0x004e4942,'GLB 청크 형식 오류')
    g=json.loads(chunks[0][1]);require(g.get('asset',{}).get('version')=='2.0' and len(g.get('buffers',[]))==1 and not g.get('extensionsRequired'),'지원하지 않는 GLB 형식')
    require(not any(x.get('uri') for x in g.get('buffers',[])+g.get('images',[])),'외부 GLB 자원은 허용하지 않습니다.')
    return g,chunks[1][1]

def mul(a,b):return [sum(a[r+k*4]*b[k+c*4] for k in range(4)) for c in range(4) for r in range(4)]
IDENTITY=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
def matrix(node):
    if 'matrix' in node:return node['matrix']
    x,y,z,w=node.get('rotation',[0,0,0,1]);sx,sy,sz=node.get('scale',[1,1,1]);tx,ty,tz=node.get('translation',[0,0,0])
    return [(1-2*y*y-2*z*z)*sx,(2*x*y+2*z*w)*sx,(2*x*z-2*y*w)*sx,0,(2*x*y-2*z*w)*sy,(1-2*x*x-2*z*z)*sy,(2*y*z+2*x*w)*sy,0,(2*x*z+2*y*w)*sz,(2*y*z-2*x*w)*sz,(1-2*x*x-2*y*y)*sz,0,tx,ty,tz,1]

def glb_parts(g,binary):
    def accessor(i):
        a=g['accessors'][i];require('sparse' not in a and not a.get('normalized'),'지원하지 않는 accessor');v=g['bufferViews'][a['bufferView']];fmt,n={5126:('f',4),5125:('I',4),5123:('H',2),5121:('B',1)}[a['componentType']];size={'VEC3':3,'SCALAR':1}[a['type']];stride=v.get('byteStride',size*n);start=v.get('byteOffset',0)+a.get('byteOffset',0);require(a['count']<=200000 and stride>=size*n,'accessor 범위 오류');out=[]
        for j in range(a['count']):
            off=start+j*stride;require(off+size*n<=min(len(binary),v.get('byteOffset',0)+v['byteLength']),'accessor 버퍼 범위 오류');vals=list(struct.unpack_from('<'+fmt*size,binary,off));out.append(vals if size>1 else vals[0])
        return out
    out=[];seen=set()
    def visit(index,parent,depth=0):
        require(depth<32 and index not in seen,'GLB 노드 순환/중복');seen.add(index);node=g['nodes'][index];m=mul(parent,matrix(node));require(all(math.isfinite(x) for x in m),'GLB transform 오류')
        if 'mesh' in node:
            for primitive in g['meshes'][node['mesh']]['primitives']:
                require(primitive.get('mode',4)==4,'삼각형 mesh만 지원합니다.');vertices=accessor(primitive['attributes']['POSITION']);require(bool(vertices),'빈 mesh')
                vertices=[[sum(m[k+c*4]*v[c] for c in range(3))+m[k+12] for k in range(3)] for v in vertices];indices=accessor(primitive['indices']) if 'indices' in primitive else list(range(len(vertices)));require(len(indices)%3==0 and all(type(i) is int and 0<=i<len(vertices) for i in indices),'삼각형 인덱스 오류')
                out.append(dict(name='public-cushion',vertices=vertices,indices=indices,color='#b7a88c'))
        for child in node.get('children',[]):visit(child,m,depth+1)
    for i in g['scenes'][g.get('scene',0)]['nodes']:visit(i,IDENTITY)
    bounds(out);return out

def abo_fit(source,reference_root):
    require(reference_root is not None,'ABO 원본 경로가 필요합니다.');p=Path(reference_root)/source['source']['model_path'];require(p.resolve().is_relative_to(Path(reference_root).resolve()),'참조 경로 오류')
    raw=p.read_bytes();require(digest(raw)==source['source']['sha256'],'ABO 원본 해시가 다릅니다.');g,b=parse_glb(raw);parts=glb_parts(g,b);lo,hi=bounds(parts);dims=source['dimensions_mm'];target=[dims['width']/1000,dims['height']/1000,dims['depth']/1000];sc=[target[k]/(hi[k]-lo[k]) for k in range(3)];translation=[-(lo[k]+hi[k])/2*sc[k]+(target[1]/2 if k==1 else 0) for k in range(3)]
    roots=g['scenes'][g.get('scene',0)]['nodes'];g['nodes'].append(dict(name='Aurora synthetic target transform',children=roots,scale=sc,translation=translation));g['scenes'][g.get('scene',0)]['nodes']=[len(g['nodes'])-1];g['asset']['extras']=dict(attribution='Amazon.com and ABO dataset creators; CC BY 4.0',modified='Added nonuniform synthetic target transform; original materials/textures retained',source_sha256=source['source']['sha256']);return pack_glb(g,b),fit(parts,dims)

def projection(parts,dim,side=False):
    axis=2 if side else 0;width=dim['depth'] if side else dim['width'];height=dim['height'];scale=340/max(width,height);ox=210-width*scale/2;oy=390;polygons=[]
    for part in parts:
        v=part['vertices'];color=part['color']
        # Coarse geometric projection uses every fourth face for dense public meshes; clearly labelled below.
        triangles=[part['indices'][i:i+3] for i in range(0,len(part['indices']),3)];stride=max(1,math.ceil(len(triangles)/5000))
        for ids in triangles[::stride]:
            points=[v[i] for i in ids];depth=sum(p[0 if side else 2] for p in points)/3;coords=' '.join(f'{ox+(p[axis]*1000+width/2)*scale:.2f},{oy-p[1]*1000*scale:.2f}' for p in points);polygons.append((depth,f'<polygon points="{coords}" fill="{color}" stroke="{color}" stroke-width="0.25"/>'))
    title='SIDE' if side else 'FRONT';body=''.join(x[1] for x in sorted(polygons,key=lambda x:x[0]));label=html.escape(f'{title} / {width:g} x {height:g} mm / geometry projection')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="440" viewBox="0 0 420 440"><rect width="420" height="440" fill="#f5f7f4"/>{body}<text x="16" y="424" font-size="12" fill="#34464a">{label}</text></svg>'.encode()

def generate(source,seed,output,reference_root=None):
    integer(seed,'seed',0,2147483647);out=Path(output);out.mkdir(parents=True,exist_ok=False);started=time.perf_counter();records=[];artifact=[]
    def write(name,raw):
        (out/name).write_bytes(raw);artifact.append(dict(file=name,bytes=len(raw),sha256=digest(raw)))
    write('input.json',serialized(source));dims=source['dimensions_mm']
    for name,detail in [('baseline',False),('candidate',True)]:
        tick=time.perf_counter()
        if detail and source['data_kind']=='mixed':glb,parts=abo_fit(source,reference_root);method='abo-fit-v1';kind='mixed'
        else:parts=procedural(source,seed,detail);glb=make_glb(parts);method='part-geometry-v1' if detail else 'ellipsoid-baseline-v1';kind='synthetic'
        write(name+'.glb',glb);write(name+'.front.svg',projection(parts,dims));write(name+'.side.svg',projection(parts,dims,True));lo,hi=bounds(glb_parts(*parse_glb(glb)));actual={k:(hi[i]-lo[i])*1000 for i,k in enumerate(('width','height','depth'))};errors={k:abs(actual[k]-dims[k]) for k in dims};require(max(errors.values())<.01,'생성 치수 허용 오차를 벗어났습니다.')
        records.append(dict(id=name,method=method,data_kind=kind,output_format='glTF 2.0 GLB',dimensions_mm=actual,max_dimension_error_mm=max(errors.values()),mesh_parts=len(parts),triangles=sum(len(p['indices'])//3 for p in parts),generation_seconds=time.perf_counter()-tick,colors='public textures retained; SVG is geometry-only' if kind=='mixed' else 'first two brief colors plus fixed eye/leaf palette',fabric_physics_verified=False,must_have_review=[dict(condition=c,status='human_review_required') for c in source.get('brief',{}).get('requirements',{}).get('must_have',[])],design_approved=False,manufacturing_verified=False))
    report=dict(schema_version=SCHEMA,source_id=source['id'],source_checksum=source['checksum'],brief_checksum=source.get('brief_checksum'),data_kind=source['data_kind'],seed=seed,engine_sha256=engine_hash(),learned_model=False,model_weights=None,prompt=None,sampler=None,inference_steps=None,requested_dimensions_mm=dims,source=source['source'],candidates=records,elapsed_seconds=time.perf_counter()-started,sample_generated=True,design_approved=False,effect_measured=False,comparison_scope='Same target dimensions; synthetic geometric concepts / public cushion derivative. No accuracy, manufacturability, style approval or business-effect claim.',unsupported=['unrestricted artwork interpretation','text condition satisfaction','fabric stretch and seams','watertight union','sewing patterns and BOM','business effect measurement'])
    write('report.json',serialized(report));md='# U21 기하 생성 방식 비교\n\n학습 모델: 없음. 같은 목표 치수의 규칙 기준선/후보를 비교한다.\n\n|방식|형상 부위|삼각형|최대 치수 오차 mm|생성 초|\n|---|---:|---:|---:|---:|\n'+''.join(f"|{c['method']}|{c['mesh_parts']}|{c['triangles']}|{c['max_dimension_error_mm']:.6f}|{c['generation_seconds']:.4f}|\n" for c in records)+'\n출처: '+source['source'].get('provenance','ABO public object + synthetic target dimensions')+'\n\n원단 물성·필수 조건·현업 승인·제작/효과는 미검증이다. 겹치는 부위의 외피 결합/시접·패턴/BOM 생성은 제공하지 않는다.\n';write('comparison.md',md.encode())
    manifest=dict(schema_version='aurora-generation-artifacts-v1',source_checksum=source['checksum'],engine_sha256=engine_hash(),files=artifact);manifest_bytes=serialized(manifest);(out/'artifacts.json').write_bytes(manifest_bytes);return dict(report=report,artifacts=manifest['files']+[dict(file='artifacts.json',bytes=len(manifest_bytes),sha256=digest(manifest_bytes))])

class GenerationService:
    def __init__(self,root,brief_store,reference_root=None):
        self.root=Path(root);self.briefs=brief_store;self.reference_root=Path(reference_root) if reference_root else None;self.output=self.root/'results/digital-samples';self.output.mkdir(parents=True,exist_ok=True);self.dbpath=self.root/'results/generation.sqlite3'
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS generation_runs(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,body TEXT NOT NULL,result TEXT,error TEXT,created_at TEXT NOT NULL)')
            db.execute("UPDATE generation_runs SET state='failed',error='서버 재시작으로 중단됐습니다. 새 요청 키로 재실행하세요.' WHERE state IN ('queued','running')")
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.dbpath,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def catalog(self):return catalog(self.root,self.briefs,self.reference_root)
    def get(self,id):
        ident(id)
        with self.db() as db:r=db.execute('SELECT * FROM generation_runs WHERE id=?',(id,)).fetchone()
        if not r:return None
        return dict(id=r['id'],state=r['state'],source=json.loads(r['body'])['source'],seed=json.loads(r['body'])['seed'],result=json.loads(r['result']) if r['result'] else None,error=r['error'],created_at=r['created_at'])
    def request(self,req):
        req=decode_request(serialized(req));sources={x['id']:x for x in self.catalog()['sources']};require(req['source_id'] in sources,'지원하지 않는 입력입니다.');source=sources[req['source_id']]
        require(source['checksum']==req['source_checksum'],'명세/출처 해시가 바뀌었습니다. 다시 선택하세요.');body=dict(source=source,seed=req['seed'],engine_sha256=engine_hash());fingerprint=digest(serialized(body));new=False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');r=db.execute('SELECT id,fingerprint FROM generation_runs WHERE request_key=?',(req['request_key'],)).fetchone()
            if r:
                if r['fingerprint']!=fingerprint:raise Conflict('같은 요청 키의 입력/설정을 바꿀 수 없습니다.')
                id=r['id']
            else:
                require(db.execute("SELECT count(*) FROM generation_runs WHERE state IN ('queued','running')").fetchone()[0]<4,'생성 작업이 많습니다. 완료 후 다시 시도하세요.');id=uuid.uuid4().hex;db.execute('INSERT INTO generation_runs VALUES(?,?,?,?,?,?,?,?)',(id,req['request_key'],fingerprint,'queued',serialized(body).decode(),None,None,datetime.now(timezone.utc).isoformat()));new=True
        return self.get(id),new
    def work(self,id):
        ident(id)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');r=db.execute("SELECT body FROM generation_runs WHERE id=? AND state='queued'",(id,)).fetchone()
            if not r:return False
            db.execute("UPDATE generation_runs SET state='running' WHERE id=?",(id,))
        try:
            body=json.loads(r['body']);require(body['engine_sha256']==engine_hash(),'생성 코드 버전이 바뀌었습니다.');result=generate(body['source'],body['seed'],self.output/id,self.reference_root)
            with self.db() as db:db.execute("UPDATE generation_runs SET state='succeeded',result=? WHERE id=?",(serialized(result).decode(),id))
        except Exception as e:
            with self.db() as db:db.execute("UPDATE generation_runs SET state='failed',error=? WHERE id=?",(str(e)[:500],id))
        return True
    def artifact(self,id,name):
        row=self.get(id)
        if not row or row['state']!='succeeded':return None
        allowed={x['file']:x for x in row['result']['artifacts']}
        if name not in allowed:return None
        p=self.output/id/name
        if not p.resolve().is_relative_to((self.output/id).resolve()):return None
        meta=allowed[name];require(p.stat().st_size==meta['bytes'] and digest(p.read_bytes())==meta['sha256'],'산출물 해시가 다릅니다.');return p
