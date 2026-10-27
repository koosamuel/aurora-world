"""U19 conservative synthetic-only audited code crosswalk -> weekly forecast input."""
from collections import defaultdict
from decimal import Decimal,localcontext
from pathlib import Path
from . import identity,inputs
from .identity import require,serialized,text
from .generation import digest

SCHEMA='aurora-identity-weekly-input-v1'

def convert(spec):
 require(isinstance(spec,dict) and set(spec)=={'schema_version','synthetic','version','periods','unit_costs_krw','coverage_assertion','identity'},'ID 주간 연결 필드 오류')
 require(spec['schema_version']==SCHEMA and spec['synthetic'] is True,'ID 연결은 자체 합성 전용입니다.')
 require(spec['coverage_assertion']=='synthetic_complete_weekly_shipments_no_stockouts_or_returns','완결 주간 출하·품절/반품 없음의 합성 선언이 필요합니다.')
 text(spec['version'],'version',80);periods=spec['periods'];require(isinstance(periods,list) and 20<=len(periods)<=520 and all(isinstance(p,str) for p in periods),'주간 기간 오류')
 require(isinstance(spec['unit_costs_krw'],dict) and spec['unit_costs_krw'],'합성 SKU별 단가 필요')
 source=spec['identity'];identity.validate(source);require(source['data_kind']=='synthetic','공개/혼합/기업 ID 입력을 합성 출하량으로 바꾸지 않습니다.')
 # Audit may look through the last record date, but every mapping must have been
 # available before the FIRST observation. This conservative bridge cannot leak
 # mappings learned in a calibration or holdout period into earlier forecasts.
 require(all(m['known_at']<=periods[0] for m in source['mappings']),'최초 관측 이후에 알려진 대응표는 시계열 실행에 사용할 수 없습니다.')
 audit=identity.audit(source);require(audit['ready_for_downstream'],'ID 감사 미통과: '+', '.join([*audit['quarantine_reasons'],*{x['reason'] for x in audit['mapping_issues']}]))
 require(all(x['preserved'] for x in audit['quantity_audit']),'ID 수량 수지 불일치')
 rows=audit['accepted'];require(all(r['record_type']=='observed_sales' and r['unit']=='each' for r in rows),'each 단위의 관측 출하 흐름만 연결합니다. 재고/BOM은 합산하지 않습니다.')
 orgs={r['org_id'] for r in rows};warehouses={r['location_id'] for r in rows};require(len(orgs)==len(warehouses)==1,'단일 법인/창고가 필요합니다.')
 require(all(r['event_date'] in periods for r in rows),'원천 사건은 선언한 주간 월요일 그리드에 있어야 합니다.')
 groups=defaultdict(list)
 for r in rows:groups[(r['canonical_product_id'],r['event_date'])].append(r)
 skus=sorted({r['canonical_product_id'] for r in rows});require(set(spec['unit_costs_krw'])==set(skus),'단가의 SKU와 감사된 SKU가 다릅니다.')
 require(len(groups)==len(skus)*len(periods) and all((sku,p) in groups for sku in skus for p in periods),'SKU/주 그리드가 불완전합니다. 빠진 주를0으로 만들지 않습니다.')
 series=[];lineage=[]
 with localcontext() as ctx:
  ctx.prec=400
  for sku in skus:
   vals=[]
   for p in periods:
    rs=groups[(sku,p)];total=sum((Decimal(str(r['quantity'])) for r in rs),Decimal(0));value=float(total);require(Decimal(str(value))==total,'주간 수량을 float로 옮길 때 정밀도가 달라집니다.')
    vals.append(value);lineage.append(dict(sku=sku,period=p,quantity=str(total),source_rows=[dict(row_id=r['row_id'],mapping_id=r['mapping_id'],quantity=str(r['quantity'])) for r in rs]))
   series.append(dict(sku=sku,pattern='audited synthetic code aliases; observed shipments',values=vals,statuses=['observed']*len(periods),stockouts=[False]*len(periods),returns=[0]*len(periods),unit_cost_krw=spec['unit_costs_krw'][sku]))
 payload=dict(schema_version=inputs.SCHEMA,synthetic=True,version=spec['version'],target='observed_gross_shipments',unit='each',currency='KRW',org_id=next(iter(orgs)),warehouse_id=next(iter(warehouses)),periods=periods,series=series,source=dict(manifest_sha256=audit['input_sha256'],generator_sha256=digest(Path(__file__).read_bytes())))
 quality=inputs.validate(payload)
 return payload,dict(kind='audited_identity_weekly',mapping_version=source['mapping_version'],mapping_sha256=audit['mapping_sha256'],identity_input_sha256=audit['input_sha256'],identity_engine_sha256=audit['engine_sha256'],bridge_engine_sha256=digest(Path(__file__).read_bytes()),mapping_known_before_first_period=True,coverage_assertion=spec['coverage_assertion'],audit=audit,weekly_lineage=lineage,quality=quality)
