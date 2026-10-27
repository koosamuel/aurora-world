"""Product-code crosswalk audit. No fuzzy matching, ERP writes or model input mutation."""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
from pathlib import Path
import json
import math
import re

MAX_BYTES = 4 * 1024 * 1024
TOP = {'schema_version','version','data_kind','mapping_version','as_of','provenance','mappings','records'}
MAP = {'mapping_id','source_system','source_scope','source_code','canonical_product_id','valid_from','valid_to','known_at','approval_status','approved_by','evidence'}
ROW = {'row_id','record_key','record_type','source_system','source_scope','source_code','org_id','location_id','event_date','unit','quantity'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def serialized(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',',':')).encode('utf-8')


def digest(value):
    return sha256(serialized(value)).hexdigest()


def text(value, field, limit=300):
    require(isinstance(value,str) and 0 < len(value) <= limit and value == value.strip()
            and not any(ord(c)<32 or 127<=ord(c)<=159 for c in value), f'{field}: bounded nonblank string required')


def iso(value, field):
    require(isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',value), f'{field}: ISO date required')
    try:
        date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f'{field}: invalid date') from e


def validate(payload):
    require(isinstance(payload,dict) and set(payload)==TOP, 'unexpected/missing input fields')
    require(payload['schema_version']=='aurora-product-identity-input-v1','unsupported schema')
    require(payload['data_kind'] in ('synthetic','public','mixed','company'),'unsupported data_kind')
    for k in ('version','mapping_version','provenance'):
        text(payload[k],k,2000 if k=='provenance' else 100)
    iso(payload['as_of'],'as_of')
    maps,rows=payload['mappings'],payload['records']
    require(isinstance(maps,list) and len(maps)<=2000,'mappings: max 2000')
    require(isinstance(rows,list) and 0<len(rows)<=10000,'records: 1..10000 required')
    ids=set()
    for m in maps:
        require(isinstance(m,dict) and set(m)==MAP,'unexpected/missing mapping fields')
        for k in ('mapping_id','source_system','source_scope','source_code','canonical_product_id','evidence'):
            text(m[k],k,2000 if k=='evidence' else 300)
        require(m['mapping_id'] not in ids,'duplicate mapping_id');ids.add(m['mapping_id'])
        for k in ('valid_from','known_at'):iso(m[k],k)
        if m['valid_to'] is not None:
            iso(m['valid_to'],'valid_to');require(m['valid_from']<m['valid_to'],'empty/reversed validity interval')
        require(m['approval_status'] in ('approved','candidate','rejected'),'invalid approval_status')
        if m['approved_by'] is not None:text(m['approved_by'],'approved_by')
        require(m['approval_status']!='approved' or m['approved_by'] is not None,'approved mapping needs approver')
    ids=set()
    for r in rows:
        require(isinstance(r,dict) and set(r)==ROW,'unexpected/missing record fields')
        for k in ROW-{'quantity','event_date'}:text(r[k],k)
        require(r['row_id'] not in ids,'duplicate row_id');ids.add(r['row_id'])
        require(r['record_type'] in ('observed_sales','inventory_snapshot','bom_piece'),'invalid record_type')
        iso(r['event_date'],'event_date')
        q=r['quantity']
        require(type(q) in (int,float) and 0<=q<=1e12 and math.isfinite(q),'quantity: finite nonnegative number <= 1e12 required')
    return payload


def decode(raw):
    require(len(raw)<=MAX_BYTES,'input too large')
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,'duplicate JSON key');result[k]=v
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON number')
    try:
        return validate(json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid))
    except (UnicodeError,RecursionError,TypeError) as e:
        raise ValueError('invalid JSON input') from e


def load(path):
    with Path(path).open('rb') as f:
        return decode(f.read(MAX_BYTES+1))


def key(row):
    return tuple(row[k] for k in ('source_system','source_scope','source_code'))


def active(m, day):
    return m['valid_from']<=day and (m['valid_to'] is None or day<m['valid_to'])


def audit(payload):
    validate(payload)
    groups=defaultdict(list)
    for m in payload['mappings']:groups[key(m)].append(m)
    issues=[]
    for scope, mappings in sorted(groups.items()):
        known=sorted((m for m in mappings if m['approval_status']=='approved' and m['known_at']<=payload['as_of']),key=lambda m:(m['valid_from'],m['mapping_id']))
        previous=None
        for m in known:
            if previous and (previous['valid_to'] is None or m['valid_from']<previous['valid_to']):
                issues.append(dict(reason='overlapping_approved_intervals',source_key=list(scope),mapping_ids=[previous['mapping_id'],m['mapping_id']]))
            if previous is None or (previous['valid_to'] is not None and (m['valid_to'] is None or m['valid_to']>previous['valid_to'])):
                previous=m
    business_counts=Counter((r['source_system'],r['source_scope'],r['record_type'],r['record_key']) for r in payload['records'])
    accepted=[];quarantine=[]
    for r in payload['records']:
        reason=None
        if business_counts[(r['source_system'],r['source_scope'],r['record_type'],r['record_key'])]>1:reason='duplicate_source_record'
        elif r['event_date']>payload['as_of']:reason='future_record'
        options=groups.get(key(r),[])
        effective=[m for m in options if active(m,r['event_date'])]
        eligible=[m for m in effective if m['approval_status']=='approved' and m['known_at']<=payload['as_of']]
        if reason is None:
            if len(eligible)>1:reason='ambiguous_approved_mapping'
            elif not eligible:
                reason=('mapping_not_yet_known' if any(m['approval_status']=='approved' and m['known_at']>payload['as_of'] for m in effective)
                        else 'mapping_not_approved' if effective else 'no_effective_mapping' if options else 'unmapped_code')
        if reason:
            quarantine.append(dict(record=dict(r),reason=reason,candidate_mapping_ids=[m['mapping_id'] for m in effective]))
        else:
            m=eligible[0]
            accepted.append(dict(**r,canonical_product_id=m['canonical_product_id'],mapping_id=m['mapping_id'],mapping_version=payload['mapping_version']))
    # Inventory is a snapshot, not a flow. Alias rows at the same declared grain cannot be summed.
    stock_key=lambda r:tuple(r[k] for k in ('canonical_product_id','org_id','location_id','event_date','unit'))
    stock_counts=Counter(stock_key(r) for r in accepted if r['record_type']=='inventory_snapshot')
    safe=[]
    original={r['row_id']:r for r in payload['records']}
    for r in accepted:
        if r['record_type']=='inventory_snapshot' and stock_counts[stock_key(r)]>1:
            quarantine.append(dict(record=dict(original[r['row_id']]),reason='duplicate_canonical_snapshot',candidate_mapping_ids=[r['mapping_id']]))
        else:safe.append(r)
    accepted=safe
    # Decimals are serialized as strings. Do not pool units, dates, organisations, locations or record kinds.
    dimensions=('record_type','org_id','location_id','event_date','unit')
    totals=defaultdict(lambda:dict(source_count=0,accepted_count=0,quarantine_count=0,source_quantity=Decimal(0),accepted_quantity=Decimal(0),quarantine_quantity=Decimal(0)))
    accepted_ids={r['row_id'] for r in accepted}
    with localcontext() as context:
        context.prec=400
        for r in payload['records']:
            t=totals[tuple(r[k] for k in dimensions)];which='accepted' if r['row_id'] in accepted_ids else 'quarantine';q=Decimal(str(r['quantity']))
            t['source_count']+=1;t[which+'_count']+=1;t['source_quantity']+=q;t[which+'_quantity']+=q
        balance=[]
        for scope,t in sorted(totals.items()):
            preserved=t['source_count']==t['accepted_count']+t['quarantine_count'] and t['source_quantity']==t['accepted_quantity']+t['quarantine_quantity']
            balance.append(dict(**dict(zip(dimensions,scope)),**{k:format(v,'f') if isinstance(v,Decimal) else v for k,v in t.items()},preserved=preserved))
    reasons=Counter(r['reason'] for r in quarantine)
    return dict(schema_version='aurora-product-identity-audit-v1',version=payload['version'],data_kind=payload['data_kind'],as_of=payload['as_of'],mapping_version=payload['mapping_version'],provenance=payload['provenance'],input_sha256=digest(payload),mapping_sha256=digest(payload['mappings']),engine_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),ready_for_downstream=not quarantine and not issues,counts=dict(source=len(payload['records']),accepted=len(accepted),quarantined=len(quarantine),mapping_issues=len(issues)),quarantine_reasons=dict(sorted(reasons.items())),mapping_issues=issues,quantity_audit=balance,accepted=accepted,quarantine=quarantine)


def report(result):
    c=result['counts']
    return '\n'.join(['# Product identity audit','',f"Data: {result['data_kind']} · version: {result['version']}",f"As of: {result['as_of']} · mapping: {result['mapping_version']}",'',f"Source {c['source']} = accepted {c['accepted']} + quarantine {c['quarantined']}",f"Ready for downstream: {result['ready_for_downstream']}",'','This is a mapping-contract audit, not matcher accuracy or company ERP acceptance.','Quantities are decimal strings, balanced separately by kind, organisation, location, date and unit.','Quarantined rows are retained; they are never replaced by zero.','',json.dumps(result['quarantine_reasons'],ensure_ascii=False,sort_keys=True),'',f"Input SHA-256: {result['input_sha256']}",f"Mapping SHA-256: {result['mapping_sha256']}",f"Engine SHA-256: {result['engine_sha256']}",''])


def export(payload, output):
    result=audit(payload)
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    files={'mapped.json':serialized(result['accepted']),'quarantine.json':serialized(result['quarantine']),'audit.json':serialized(result),'report.md':report(result).encode()}
    manifest=dict(schema_version='aurora-identity-artifacts-v1',input_sha256=result['input_sha256'],files=[])
    for name,data in files.items():
        (out/name).write_bytes(data);manifest['files'].append(dict(file=name,bytes=len(data),sha256=sha256(data).hexdigest()))
    (out/'artifacts.json').write_bytes(serialized(manifest))
    return result


def demo(root, case):
    require(case in ('valid','conflicts'),'unsupported identity demo case')
    return audit(load(Path(root)/'configs/examples'/f'identity-{case}.json'))
