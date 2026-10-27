"""U20 synthetic design-brief validation and immutable local registration.

This module does not generate samples, approve designs or calculate business effects.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import copy
import json
import math
import re
import sqlite3
import xml.etree.ElementTree as ET
from .identity import require, serialized, text, iso

MAX_BYTES=512*1024
SCHEMA='aurora-sampling-brief-v1'
TOP={'schema_version','data_kind','product_id','product_name','brief_version','previous_checksum','artwork_version','artwork','requirements','rights','baseline'}
HEX=re.compile(r'[0-9a-f]{64}\Z')
PRODUCT=re.compile(r'SYN-[A-Z0-9][A-Z0-9_-]{0,59}\Z')


class Conflict(ValueError):
    """An immutable version or its parent conflicts with the current stored version."""


def fields(value, expected, label):
    require(isinstance(value,dict) and set(value)==expected,f'{label}: 필수/허용 필드를 확인하세요.')


def numeric(v, field, minimum=0, maximum=10000):
    require(type(v) in (int,float) and minimum<=v<=maximum and math.isfinite(v),f'{field}: {minimum}~{maximum}의 유한 수가 필요합니다.')


def integer(v,field,minimum=1,maximum=1000000):
    require(type(v) is int and minimum<=v<=maximum,f'{field}: 정수가 필요합니다.')


def timestamp(value,field):
    require(isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',value),f'{field}: UTC YYYY-MM-DDTHH:MM:SSZ 형식이 필요합니다.')
    try:return datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as e:raise ValueError(field+': 잘못된 일시입니다.') from e


def product(value):
    require(isinstance(value,str) and PRODUCT.fullmatch(value),'SYN-으로 시작하는 합성 product_id가 필요합니다.')


def svg(artwork):
    fields(artwork,{'file_name','media_type','sha256','width_mm','height_mm','svg'},'artwork')
    require(isinstance(artwork['file_name'],str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.svg',artwork['file_name']),'SVG 파일명을 확인하세요.')
    require(artwork['media_type']=='image/svg+xml','v1은 제한된 SVG 형식만 허용합니다.')
    raw=artwork['svg'];require(isinstance(raw,str) and len(raw.encode('utf-8'))<=128*1024,'SVG는 UTF-8 128 KiB 이하입니다.')
    require(isinstance(artwork['sha256'],str) and HEX.fullmatch(artwork['sha256']) and sha256(raw.encode()).hexdigest()==artwork['sha256'],'아트워크 SHA-256이 일치하지 않습니다.')
    require('<!' not in raw and '<?' not in raw,'SVG 선언·DTD·엔티티는 허용하지 않습니다.')
    for k in ('width_mm','height_mm'):numeric(artwork[k],k,1,2000)
    try:root=ET.fromstring(raw)
    except ET.ParseError as e:raise ValueError('SVG XML을 읽을 수 없습니다.') from e
    ns='{http://www.w3.org/2000/svg}'
    require(root.tag==ns+'svg','SVG 루트/이름공간을 확인하세요.')
    require(root.attrib.get('width')==str(artwork['width_mm'])+'mm' and root.attrib.get('height')==str(artwork['height_mm'])+'mm','SVG 캔버스 단위/치수가 명세와 다릅니다.')
    expected='0 0 '+str(artwork['width_mm'])+' '+str(artwork['height_mm'])
    require(root.attrib.get('viewBox')==expected,'SVG viewBox를 캔버스와 일치시키세요.')
    allowed={'svg':{'width','height','viewBox'},'g':{'fill','stroke','stroke-width'},'ellipse':{'cx','cy','rx','ry','fill','stroke','stroke-width'},'circle':{'cx','cy','r','fill','stroke','stroke-width'},'rect':{'x','y','width','height','rx','fill','stroke','stroke-width'},'path':{'d','fill','stroke','stroke-width'}}
    nodes=list(root.iter());require(len(nodes)<=200,'SVG 요소는 200개 이하입니다.')
    for node in nodes:
        tag=node.tag.removeprefix(ns)
        require(node.tag.startswith(ns) and tag in allowed,'SVG 요소를 허용하지 않습니다: '+str(tag))
        require(node is root or tag!='svg','중첩 SVG는 허용하지 않습니다.')
        require(set(node.attrib)<=allowed[tag] and not (node.text or '').strip() and not (node.tail or '').strip(),'SVG 속성/문자열은 허용 목록만 사용하세요.')
        for key,value in node.attrib.items():
            if key in ('fill','stroke'):
                require(value=='none' or re.fullmatch(r'#[0-9a-fA-F]{6}',value),'SVG 색상은 hex 또는 none만 허용합니다.')
            elif key=='d':
                require(0<len(value)<=12000 and re.fullmatch(r'[MmLlHhVvCcSsQqTtAaZz0-9eE+.,\s-]+',value),'SVG path 형식을 확인하세요.')
                token_pattern=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?|[A-Za-z]'
                tokens=re.findall(token_pattern,value)
                require(not re.sub(r'[,\s]+','',re.sub(token_pattern,'',value)),'SVG path 문자를 확인하세요.')
                require(len(tokens)<=2200 and tokens[0] in ('M','m'),'SVG path 시작/길이를 확인하세요.')
                arity={'M':2,'L':2,'H':1,'V':1,'C':6,'S':4,'Q':4,'T':2,'A':7,'Z':0};index=0
                while index<len(tokens):
                    command=tokens[index].upper();require(command in arity,'SVG path 명령을 확인하세요.');index+=1;values=[]
                    while index<len(tokens) and not tokens[index].isalpha():
                        number=float(tokens[index]);numeric(number,'SVG path',-10000,10000);values.append(number);index+=1
                    n=arity[command]
                    require(not values if n==0 else len(values)>0 and len(values)%n==0,'SVG path 인수 수를 확인하세요.')
                    if command=='A':
                        for offset in range(0,len(values),7):require(values[offset]>=0 and values[offset+1]>=0 and values[offset+3] in (0,1) and values[offset+4] in (0,1),'SVG arc 반지름/플래그를 확인하세요.')
            elif tag=='svg':continue
            else:
                try:n=float(value)
                except ValueError as e:raise ValueError('잘못된 SVG 수치') from e
                numeric(n,'SVG '+key,0,10000)


def validate(payload):
    fields(payload,TOP,'brief')
    require(payload['schema_version']==SCHEMA and payload['data_kind']=='synthetic','U20 v1은 합성 명세만 허용합니다.')
    product(payload['product_id']);text(payload['product_name'],'product_name',100)
    for key in ('brief_version','artwork_version'):integer(payload[key],key)
    previous=payload['previous_checksum'];require(previous is None or isinstance(previous,str) and HEX.fullmatch(previous),'previous_checksum 형식을 확인하세요.')
    require((payload['brief_version']==1)==(previous is None),'최초 버전만 부모 해시가 없어야 합니다.')
    svg(payload['artwork'])
    req=payload['requirements'];fields(req,{'dimensions','fabric','colors','must_have'},'requirements')
    dim=req['dimensions'];fields(dim,{'height','width','depth','unit'},'dimensions');require(dim['unit'] in ('mm','cm'),'치수 단위는 mm 또는 cm입니다.')
    for k in ('height','width','depth'):numeric(dim[k],k,0.1,1000 if dim['unit']=='cm' else 10000)
    fields(req['fabric'],{'code','description'},'fabric')
    for k in req['fabric']:text(req['fabric'][k],'fabric.'+k,300)
    require(isinstance(req['colors'],list) and 1<=len(req['colors'])<=12,'색상 명세는 1~12개입니다.')
    parts=set()
    for c in req['colors']:
        fields(c,{'part','name','hex'},'color');text(c['part'],'color.part',60);text(c['name'],'color.name',60)
        require(isinstance(c['hex'],str) and re.fullmatch(r'#[0-9A-Fa-f]{6}',c['hex']),'색상 hex를 확인하세요.')
        require(c['part'] not in parts,'부위별 색상 명세가 중복됩니다.');parts.add(c['part'])
    must=req['must_have'];require(isinstance(must,list) and 1<=len(must)<=20,'필수 조건은 1~20개입니다.')
    for condition in must:text(condition,'must_have',300)
    require(len(set(must))==len(must),'필수 조건이 중복됩니다.')
    rights=payload['rights'];fields(rights,{'source_type','company_data','allowed_use','provenance'},'rights')
    require(rights['source_type']=='self_generated_synthetic' and rights['company_data'] is False and rights['allowed_use']=='public_synthetic_demo','회사 자료·사용 범위가 불명확한 입력은 이 합성 데모에 등록하지 않습니다.')
    text(rights['provenance'],'provenance',2000)
    b=payload['baseline'];fields(b,{'status','window_start','window_end','time_definition','started_at','ended_at','physical_samples','bom_changes'},'baseline')
    require(b['status'] in ('unmeasured','synthetic_recorded'),'현행 측정 상태를 확인하세요.')
    for k in ('window_start','window_end'):iso(b[k],k)
    require(b['window_start']<=b['window_end'],'측정기간 종료가 시작보다 빠릅니다.');text(b['time_definition'],'time_definition',500)
    for k in ('physical_samples','bom_changes'):require(isinstance(b[k],list) and len(b[k])<=100,'현행 사건은 종류별 최대100개입니다.')
    if b['status']=='unmeasured':
        require(b['started_at'] is None and b['ended_at'] is None and not b['physical_samples'] and not b['bom_changes'],'미측정 상태에 측정값을 넣을 수 없습니다.')
    else:
        start=timestamp(b['started_at'],'started_at');end=timestamp(b['ended_at'],'ended_at')
        require(start<=end and b['window_start']<=start.date().isoformat()<=end.date().isoformat()<=b['window_end'],'시작·종료/측정기간을 확인하세요.')
        ids=set()
        for kind in ('physical_samples','bom_changes'):
            for event in b[kind]:
                expected={'event_id','occurred_at','quantity'} if kind=='physical_samples' else {'event_id','occurred_at','reason','description'}
                fields(event,expected,kind);text(event['event_id'],'event_id',80)
                require(event['event_id'] not in ids,'현행 사건 ID가 중복됩니다.');ids.add(event['event_id'])
                when=timestamp(event['occurred_at'],'occurred_at');require(start<=when<=end,'현행 사건이 개발기간 밖에 있습니다.')
                if kind=='physical_samples':integer(event['quantity'],'physical quantity',1,1000)
                else:
                    require(event['reason'] in ('design_change','error_correction'),'BOM 변경 사유를 구분하세요.');text(event['description'],'BOM description',300)
    return payload


def decode(raw):
    require(len(raw)<=MAX_BYTES,'명세 JSON은 512 KiB 이하입니다.')
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'중복 JSON 키입니다.');out[k]=v
        return out
    def invalid(value):raise ValueError('비유한 JSON 수치입니다.')
    try:return validate(json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid))
    except (UnicodeError,RecursionError,TypeError) as e:raise ValueError('JSON 명세 형식을 확인하세요.') from e


def load(path):
    with Path(path).open('rb') as stream:return decode(stream.read(MAX_BYTES+1))


def checksum(payload):return sha256(serialized(payload)).hexdigest()


def summary(payload):
    validate(payload);dim=payload['requirements']['dimensions'];factor=Decimal(10 if dim['unit']=='cm' else 1);b=payload['baseline'];measured=b['status']=='synthetic_recorded'
    return dict(product_id=payload['product_id'],product_name=payload['product_name'],brief_version=payload['brief_version'],artwork_version=payload['artwork_version'],data_kind='synthetic',dimensions_mm={k:format(Decimal(str(dim[k]))*factor,'f') for k in ('height','width','depth')},baseline_status=b['status'],physical_sample_count=sum(e['quantity'] for e in b['physical_samples']) if measured else None,physical_event_count=len(b['physical_samples']) if measured else None,elapsed_hours=(timestamp(b['ended_at'],'end')-timestamp(b['started_at'],'start')).total_seconds()/3600 if measured else None,bom_error_corrections=sum(e['reason']=='error_correction' for e in b['bom_changes']) if measured else None,bom_design_changes=sum(e['reason']=='design_change' for e in b['bom_changes']) if measured else None,effect_measured=False,sample_generated=False,design_approved=False)


def envelope(payload,registered_at=None,reused=False):
    return dict(brief=copy.deepcopy(payload),checksum=checksum(payload),summary=summary(payload),registered_at=registered_at,reused=reused)


class BriefStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS sampling_briefs (product_id TEXT NOT NULL,version INTEGER NOT NULL,checksum TEXT NOT NULL,body TEXT NOT NULL,registered_at TEXT NOT NULL,PRIMARY KEY(product_id,version))')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def get(self,product_id,version):
        product(product_id);integer(version,'version')
        with self.connect() as db:row=db.execute('SELECT * FROM sampling_briefs WHERE product_id=? AND version=?',(product_id,version)).fetchone()
        return envelope(json.loads(row['body']),row['registered_at']) if row else None
    def list(self):
        with self.connect() as db:rows=db.execute('SELECT * FROM sampling_briefs ORDER BY product_id,version DESC').fetchall()
        return [dict(checksum=r['checksum'],registered_at=r['registered_at'],summary=summary(json.loads(r['body']))) for r in rows]
    def register(self,payload):
        validate(payload);require(len(serialized(payload))<=MAX_BYTES,'명세 JSON이 너무 큽니다.');pid=payload['product_id'];version=payload['brief_version'];digest=checksum(payload)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT * FROM sampling_briefs WHERE product_id=? AND version=?',(pid,version)).fetchone()
            if existing:
                if existing['checksum']!=digest:raise Conflict('같은 제품·버전을 다른 내용으로 덮어쓸 수 없습니다.')
                return envelope(json.loads(existing['body']),existing['registered_at'],True)
            latest=db.execute('SELECT * FROM sampling_briefs WHERE product_id=? ORDER BY version DESC LIMIT 1',(pid,)).fetchone()
            if latest:
                if version!=latest['version']+1 or payload['previous_checksum']!=latest['checksum']:raise Conflict('최신 버전·부모 해시가 바뀌었습니다. 최신 명세에서 수정본을 만드세요.')
                previous=json.loads(latest['body']);changed=previous['artwork']!=payload['artwork'];expected=previous['artwork_version']+(1 if changed else 0)
                if payload['artwork_version']!=expected:raise Conflict('원화 변경 여부와 artwork_version이 일치하지 않습니다.')
            elif version!=1 or payload['artwork_version']!=1:raise Conflict('새 제품은 명세·원화 버전1부터 등록하세요.')
            now=datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO sampling_briefs VALUES(?,?,?,?,?)',(pid,version,digest,serialized(payload).decode(),now))
            return envelope(payload,now)


def seed(store,root):
    for path in sorted((Path(root)/'configs/examples/sampling').glob('*.json')):store.register(load(path))


def export(payload,output):
    result=envelope(payload);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    files={'brief.json':serialized(payload),'validation.json':serialized(result),'artwork.svg':payload['artwork']['svg'].encode('utf-8')}
    manifest=dict(schema_version='aurora-sampling-artifacts-v1',input_sha256=result['checksum'],engine_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),files=[])
    for name,raw in files.items():
        (out/name).write_bytes(raw);manifest['files'].append(dict(file=name,bytes=len(raw),sha256=sha256(raw).hexdigest()))
    (out/'artifacts.json').write_bytes(serialized(manifest));return result
