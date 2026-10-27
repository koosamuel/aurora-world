"""U23: audited, version-pinned synthetic sample -> pattern/piece/material BOM links.
No pattern generation, sewing certification or real authentication is implied.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import copy, json, math, re, sqlite3
from .identity import require, serialized, text
from .generation import digest
from .sampling import Conflict, fields, integer, product
from .sample_reviews import Denied, KEY

SHA=re.compile(r'[0-9a-f]{64}\Z')
ASSET=re.compile(r'[0-9a-f]{64}\.svg\Z')
ID=re.compile(r'[A-Z][A-Z0-9_-]{0,79}\Z')
SCOPE='synthetic manual crosswalk; not generated sewing patterns, manufacturing approval or actual fabric yield'

def number(v):return type(v) in (int,float) and math.isfinite(v) and 0<v<=1e9

def audit(bundle):
    """Return blocking domain errors; shape, units and FK checks never silently coerce."""
    fields(bundle,{'schema_version','data_kind','product_id','version','pattern_id','pattern_version','bom_version','mapping_method','provenance','materials','pieces','bom'},'pattern bundle')
    require(bundle['schema_version']=='aurora-pattern-bundle-v1' and bundle['data_kind']=='synthetic','합성 패턴 묶음 v1만 허용합니다.')
    product(bundle['product_id']);integer(bundle['version'],'bundle version',1,1000)
    require(bundle['mapping_method']=='manual_synthetic_crosswalk','수동 합성 대응 출처가 필요합니다.')
    for k in ('pattern_id','pattern_version','bom_version'):text(bundle[k],k,80)
    require(isinstance(bundle['provenance'],dict) and bundle['provenance'].get('manufacturing_verified') is False,'제작 미검증 출처가 필요합니다.')
    for k in ('materials','pieces','bom'):require(isinstance(bundle[k],list) and 0<len(bundle[k])<=500,'빈/과대 '+k)
    errors=[]
    def error(code,key):errors.append(dict(code=code,key=str(key)))
    def unique(rows,key):
        seen={}
        for r in rows:
            require(isinstance(r,dict) and isinstance(r.get(key),str) and ID.fullmatch(r[key]),'키 형식 오류: '+key)
            if r[key] in seen:error('duplicate_'+key,r[key])
            seen[r[key]]=r
        return seen
    materials=unique(bundle['materials'],'material_id');pieces=unique(bundle['pieces'],'piece_id');lines=unique(bundle['bom'],'piece_id')
    for m in materials.values():
        fields(m,{'material_id','name','unit'},'material');text(m['name'],'material name',100)
        if m['unit'] not in ('mm2','cm2'):error('material_unit',m['material_id'])
    for p in pieces.values():
        fields(p,{'piece_id','standard_part_id','width_mm','height_mm','area_mm2','cut_qty','material_id','asset','asset_bytes'},'piece')
        text(p['standard_part_id'],'standard part',80)
        if not all(number(p[k]) for k in ('width_mm','height_mm','area_mm2')):error('piece_geometry',p['piece_id'])
        elif p['area_mm2']>p['width_mm']*p['height_mm']+0.01:error('area_exceeds_bounds',p['piece_id'])
        if type(p['cut_qty']) is not int or not 1<=p['cut_qty']<=1000:error('cut_quantity',p['piece_id'])
        require(isinstance(p['asset'],str) and ASSET.fullmatch(p['asset']) and type(p['asset_bytes']) is int and 0<p['asset_bytes']<=131072,'조각 자산 메타데이터 오류')
        if p['material_id'] not in materials:error('missing_material',p['piece_id'])
        if p['piece_id'] not in lines:error('missing_bom',p['piece_id'])
    used=set();total=0
    for b in lines.values():
        fields(b,{'piece_id','pattern_version','material_id','quantity','quantity_unit','consumption','consumption_unit'},'bom line')
        key=b['piece_id'];p=pieces.get(key);m=materials.get(b['material_id'])
        if not p:error('orphan_bom',key)
        if b['pattern_version']!=bundle['pattern_version']:error('pattern_version',key)
        if not m:error('missing_bom_material',key)
        if b['quantity_unit']!='pcs' or type(b['quantity']) is not int or not 1<=b['quantity']<=1000:error('quantity_unit_or_value',key)
        if not number(b['consumption']):error('consumption',key)
        if b['consumption_unit'] not in ('mm2','cm2') or (m and b['consumption_unit']!=m['unit']):error('consumption_unit',key)
        if p:
            if b['material_id']!=p['material_id']:error('material_mismatch',key)
            if b['quantity']!=p['cut_qty']:error('quantity_mismatch',key)
            if number(b['consumption']) and b['consumption_unit'] in ('mm2','cm2') and number(p['area_mm2']) and type(p['cut_qty']) is int:
                mm2=b['consumption']*(100 if b['consumption_unit']=='cm2' else 1)
                if not math.isclose(mm2,p['area_mm2']*p['cut_qty'],rel_tol=1e-8,abs_tol=.01):error('area_balance',key)
                total+=mm2
        used.add(b['material_id'])
    for mid in materials.keys()-used:error('unused_material',mid)
    return dict(passed=not errors,errors=errors,piece_count=len(bundle['pieces']),bom_count=len(bundle['bom']),
                cut_quantity=sum(p['cut_qty'] for p in pieces.values() if type(p['cut_qty']) is int),estimated_area_mm2=round(total,3),
                area_basis='synthetic polygon area * cut quantity; excludes waste, seams, nesting, fabric width, stuffing and labour',scope=SCOPE)

def impact(before,after):
    if not before:return dict(initial=True,added=[p['piece_id'] for p in after['pieces']],removed=[],changed=[],material_totals=[])
    a={p['piece_id']:p for p in before['pieces']};b={p['piece_id']:p for p in after['pieces']}
    ba={p['piece_id']:p for p in before['bom']};bb={p['piece_id']:p for p in after['bom']}
    changed=[]
    for key in sorted(a.keys()&b.keys()):
        cols=[k for k in a[key] if a[key][k]!=b[key][k]]
        bomcols=[k for k in ba[key] if ba[key][k]!=bb[key][k]]
        if cols or bomcols:changed.append(dict(piece_id=key,piece_fields=cols,bom_fields=bomcols))
    def totals(bundle):
        result={}
        for row in bundle['bom']:result[row['material_id']]=result.get(row['material_id'],0)+row['consumption']*(100 if row['consumption_unit']=='cm2' else 1)
        return result
    ta,tb=totals(before),totals(after)
    return dict(initial=False,added=sorted(b.keys()-a.keys()),removed=sorted(a.keys()-b.keys()),changed=changed,
                material_totals=[dict(material_id=k,before_mm2=round(ta.get(k,0),3),after_mm2=round(tb.get(k,0),3),delta_mm2=round(tb.get(k,0)-ta.get(k,0),3)) for k in sorted(ta.keys()|tb.keys())])

class PatternLinks:
    def __init__(self,root,reviews,library=None):
        self.root=Path(root);self.reviews=reviews;self.library=Path(library) if library else self.root/'client/demo/pattern-links'
        self.assets=self.root/'results/pattern-link-assets';self.assets.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'results/pattern-links.sqlite3'
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS pattern_links(product_id TEXT,version INTEGER,snapshot TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(product_id,version));
            CREATE TABLE IF NOT EXISTS pattern_link_requests(actor TEXT,request_key TEXT,fingerprint TEXT NOT NULL,product_id TEXT,version INTEGER,PRIMARY KEY(actor,request_key));
            CREATE TRIGGER IF NOT EXISTS link_no_update BEFORE UPDATE ON pattern_links BEGIN SELECT RAISE(ABORT,'immutable pattern link'); END;
            CREATE TRIGGER IF NOT EXISTS link_no_delete BEFORE DELETE ON pattern_links BEGIN SELECT RAISE(ABORT,'immutable pattern link'); END;''')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def bundles(self):
        cat=json.loads((self.library/'library.json').read_text());rows={}
        require(cat['schema_version']=='aurora-pattern-library-v1' and len(cat['bundles'])<=1000,'패턴 목록 오류')
        for meta in cat['bundles']:
            pid=meta['product_id'];product(pid);integer(meta['version'],'bundle version',1,1000)
            key=(pid,meta['version']);require(key not in rows,'중복 묶음 버전')
            raw=(self.library/'bundles'/f'{pid}-v{meta["version"]}.json').read_bytes()
            require(digest(raw)==meta['sha256'] and len(raw)==meta['bytes'],'패턴 묶음 파일 해시 오류')
            bundle=json.loads(raw);require(bundle['product_id']==pid and bundle['version']==meta['version'],'묶음 제품/버전 불일치')
            report=audit(bundle);rows[key]=dict(bundle=bundle,sha256=meta['sha256'],audit=report)
        return rows
    def catalog(self):
        rows=self.bundles();products=[]
        for pid in sorted({k[0] for k in rows}):
            r=self.get(pid);products.append(dict(product_id=pid,head_version=r['head_version'],active_approval=bool(r['current_approval']),current_link_valid=bool(r['links'] and r['links'][-1]['current_valid'])))
        return dict(schema_version='aurora-pattern-link-catalog-v1',mode='local_synthetic',products=products,
                    bundles=[dict(product_id=p,version=v,sha256=x['sha256'],audit=x['audit']) for (p,v),x in sorted(rows.items())],scope=SCOPE)
    def _read(self,db,pid,review,rows):
        latest=max((k[1] for k in rows if k[0]==pid),default=None)
        rev=review['revisions'][-1] if review else None
        active=rev if rev and rev['active_approval'] else None
        links=[];previous=None
        for row in db.execute('SELECT * FROM pattern_links WHERE product_id=? ORDER BY version',(pid,)):
            snap=json.loads(row['snapshot']);require(digest(serialized(snap))==row['sha256'] and snap['previous_sha256']==previous and snap['version']==len(links)+1,'연결 이력 해시 오류')
            require(audit(snap['bundle'])['passed'],'저장된 연결 감사 오류')
            reasons=[];key=(pid,snap['bundle']['version']);existing=rows.get(key)
            if not active or active['sha256']!=snap['sample_revision_sha256'] or active['approval']['sha256']!=snap['approval_event_sha256']:reasons.append('approval_changed_or_inactive')
            if latest!=snap['bundle']['version']:reasons.append('new_pattern_bom_version')
            if not existing or existing['sha256']!=snap['bundle_sha256']:reasons.append('bundle_removed_or_changed')
            links.append(dict(**snap,sha256=row['sha256'],current_valid=not reasons,invalid_reasons=reasons));previous=row['sha256']
        for link in links[:-1]:link['current_valid']=False;link['invalid_reasons'].append('superseded_link')
        return dict(schema_version='aurora-pattern-links-v1',data_kind='synthetic',product_id=pid,head_version=len(links),
                    current_approval=dict(sample_version=active['version'],revision_sha256=active['sha256'],approval_event_sha256=active['approval']['sha256'],brief_checksum=active['sample']['source']['brief_checksum'],review_seq=review['seq']) if active else None,
                    latest_bundle_version=latest,links=links,history_hash_verified=True,manufacturing_verified=False,effect_measured=False,scope=SCOPE)
    def get(self,pid):
        product(pid)
        # Same lock order as writes/U22. This yields one coherent U20/U22/U23 view.
        with self.reviews.write() as review_db:
            review=self.reviews._read(review_db,pid);rows=self.bundles()
            with self.db() as db:return self._read(db,pid,review,rows)
    def bundle(self,pid,version):
        product(pid);integer(version,'bundle version',1,1000)
        row=self.bundles().get((pid,version));require(row is not None,'패턴 묶음 없음');return row
    def _freeze(self,bundle):
        for p in bundle['pieces']:
            raw=(self.library/'assets'/p['asset']).read_bytes()
            require(len(raw)==p['asset_bytes'] and digest(raw)==p['asset'][:-4],'조각 SVG 크기/해시 오류')
            # Only the existing own closed polygon SVG contract, no uploads/external resources.
            import xml.etree.ElementTree as ET
            source=raw.decode();require('<!' not in source and '<?' not in source,'SVG 선언/엔티티 거부')
            try:tree=ET.fromstring(source)
            except ET.ParseError as e:raise ValueError('조각 SVG XML 오류') from e
            ns='{http://www.w3.org/2000/svg}'
            require(tree.tag==ns+'svg' and set(tree.attrib)=={'width','height','viewBox'},'조각 SVG 루트 오류')
            nodes=list(tree);require(len(nodes)==2 and nodes[0].tag==ns+'title' and nodes[1].tag==ns+'polygon' and not list(nodes[0]) and not list(nodes[1]),'제한된 조각 SVG만 허용')
            require(not nodes[0].attrib and set(nodes[1].attrib)=={'points','fill','stroke','stroke-width'},'조각 SVG 속성 오류')
            require(nodes[1].attrib['fill']=='white' and nodes[1].attrib['stroke']=='black' and nodes[1].attrib['stroke-width']=='.5','조각 SVG 스타일 오류')
            points=nodes[1].attrib['points'];require(len(points)<20000 and re.fullmatch(r'[0-9., ]+',points),'조각 좌표 오류')
            try:xy=[tuple(map(float,t.split(','))) for t in points.split()]
            except ValueError as e:raise ValueError('조각 좌표 오류') from e
            require(3<=len(xy)<=500 and all(len(v)==2 and all(math.isfinite(x) and 0<=x<=2000 for x in v) for v in xy),'조각 좌표 범위 오류')
            area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(xy,xy[1:]+xy[:1])))/2
            require(math.isclose(area,p['area_mm2'],abs_tol=.1,rel_tol=1e-5),'SVG 면적과 조각 면적 불일치')
            require(abs(max(x for x,y in xy)-min(x for x,y in xy)-p['width_mm'])<.01 and abs(max(y for x,y in xy)-min(y for x,y in xy)-p['height_mm'])<.01,'SVG 윤곽 치수 불일치')
            dest=self.assets/p['asset']
            if dest.exists():require(dest.read_bytes()==raw,'고정 조각 파일 손상')
            else:
                with dest.open('xb') as f:f.write(raw)
    def link(self,token,req):
        fields(req,{'product_id','bundle_version','bundle_sha256','sample_revision_sha256','approval_event_sha256','expected_review_seq','parent_version','reason','request_key'},'pattern link')
        actor=self.reviews.actor(token)
        if actor['role']!='designer':raise Denied('패턴/BOM 연결은 가상 작성자 역할만 가능합니다.')
        pid=req['product_id'];product(pid);integer(req['bundle_version'],'bundle_version',1,1000);integer(req['parent_version'],'parent_version',0);integer(req['expected_review_seq'],'expected_review_seq',0);text(req['reason'],'reason',2000)
        for k in ('bundle_sha256','sample_revision_sha256','approval_event_sha256'):require(isinstance(req[k],str) and SHA.fullmatch(req[k]),'연결 해시 형식 오류')
        require(isinstance(req['request_key'],str) and KEY.fullmatch(req['request_key']),'요청 키 형식 오류')
        # U20 -> U22 -> U23: approval revocation and brief edits cannot race commit.
        with self.reviews.write() as review_db:
            review=self.reviews._read(review_db,pid);rows=self.bundles()
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');current=self._read(db,pid,review,rows)
                old=db.execute('SELECT * FROM pattern_link_requests WHERE actor=? AND request_key=?',(actor['id'],req['request_key'])).fetchone()
                if old:
                    if old['fingerprint']!=digest(serialized(req)):raise Conflict('같은 요청 키의 내용이 달라졌습니다.')
                    return dict(**self._read(db,old['product_id'],self.reviews._read(review_db,old['product_id']),rows),replayed=True,original_receipt_version=old['version'])
                approval=current['current_approval']
                if not approval:raise Conflict('현재 유효한 U22 합성 디지털 승인이 필요합니다.')
                if (req['sample_revision_sha256'],req['approval_event_sha256'],req['expected_review_seq'])!=(approval['revision_sha256'],approval['approval_event_sha256'],approval['review_seq']):raise Conflict('샘플/승인 이력이 바뀌었습니다. 다시 조회하세요.')
                if req['parent_version']!=current['head_version']:raise Conflict('연결 이력 부모가 바뀌었습니다.')
                row=rows.get((pid,req['bundle_version']));require(row is not None,'등록된 패턴 묶음이 아닙니다.')
                if req['bundle_version']!=current['latest_bundle_version'] or req['bundle_sha256']!=row['sha256']:raise Conflict('최신 패턴/BOM 버전·해시를 선택하세요.')
                require(row['audit']['passed'],'패턴/BOM 감사 실패: '+', '.join(e['code'] for e in row['audit']['errors']))
                for prior in current['links']:
                    if prior['bundle']['version']==req['bundle_version'] and prior['bundle_sha256']!=row['sha256']:raise Conflict('이미 연결한 묶음 버전의 내용이 바뀌었습니다. 새 버전이 필요합니다.')
                before=current['links'][-1] if current['links'] else None
                if before and before['current_valid']:raise Conflict('이미 같은 승인·최신 패턴/BOM에 유효하게 연결되어 있습니다.')
                self._freeze(row['bundle'])
                rev=review['revisions'][-1]
                # Verify pinned review assets too; do not link a damaged approved sample.
                for asset in rev['assets']:require(self.reviews.asset(asset['asset']) is not None,'승인 샘플 파일 없음')
                snap=dict(product_id=pid,version=current['head_version']+1,previous_sha256=before['sha256'] if before else None,
                          sample_version=approval['sample_version'],sample_revision_sha256=approval['revision_sha256'],approval_event_sha256=approval['approval_event_sha256'],brief_checksum=approval['brief_checksum'],
                          bundle=copy.deepcopy(row['bundle']),bundle_sha256=row['sha256'],audit=row['audit'],
                          impact=impact(before['bundle'] if before else None,row['bundle']),reason=req['reason'],created_by=actor,created_at=datetime.now(timezone.utc).isoformat())
                db.execute('INSERT INTO pattern_links VALUES(?,?,?,?)',(pid,snap['version'],serialized(snap).decode(),digest(serialized(snap))))
                db.execute('INSERT INTO pattern_link_requests VALUES(?,?,?,?,?)',(actor['id'],req['request_key'],digest(serialized(req)),pid,snap['version']))
                return dict(**self._read(db,pid,review,rows),replayed=False)
    def asset(self,name):
        require(isinstance(name,str) and ASSET.fullmatch(name),'조각 파일명 오류')
        with self.db() as db:snaps=[json.loads(r[0]) for r in db.execute('SELECT snapshot FROM pattern_links')]
        refs=[p for s in snaps for p in s['bundle']['pieces'] if p['asset']==name]
        if not refs:return None
        p=self.assets/name;raw=p.read_bytes();require(digest(raw)==name[:-4] and all(len(raw)==r['asset_bytes'] for r in refs),'고정 조각 파일 해시 오류');return p
    def export(self,pid):
        r=self.get(pid)
        for link in r['links']:
            for p in link['bundle']['pieces']:require(self.asset(p['asset']) is not None,'고정 조각 파일 없음')
        return dict(**r,asset_hashes_verified=True,export_sha256=digest(serialized(r)))
