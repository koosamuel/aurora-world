"""Select own PAT synthetic contours and build explicit provisional manual crosswalks."""
import argparse,copy,json
from pathlib import Path
from aurora.generation import digest
from aurora.identity import serialized
from aurora.pattern_links import audit

def build(source,out):
 source=Path(source);out=Path(out)
 if out.exists():raise ValueError('Use a new output directory.')
 (out/'bundles').mkdir(parents=True);(out/'assets').mkdir()
 read=lambda name:[json.loads(line) for line in (source/name).read_text().splitlines()]
 pieces=read('patterns/pieces.jsonl');labels={r['piece_id']:r for r in read('patterns/labels.jsonl')};bom={r['piece_id']:r for r in read('patterns/bom.jsonl')}
 provenance=dict(dataset='2026-10-26_가상데이터_v1',source_files=[dict(path=n,sha256=digest((source/n).read_bytes())) for n in ('manifest.json','patterns/pieces.jsonl','patterns/bom.jsonl','patterns/labels.jsonl')],mapping_basis='manual synthetic demonstration; design family and sample shape are NOT a verified fit',manufacturing_verified=False,material_master_origin='synthetic area bookkeeping only; no supplier material master')
 metas=[]
 for pid,design in zip(['SYN-BUNNY','SYN-CAT','SYN-FRUIT','SYN-COW','SYN-DOG','SYN-CACTUS'],['DESIGN-001','DESIGN-006','DESIGN-011','DESIGN-016','DESIGN-021','DESIGN-026']):
  subset=[p for p in pieces if p['design_id']==design];assert len(subset)==12
  bundle=dict(schema_version='aurora-pattern-bundle-v1',data_kind='synthetic',product_id=pid,version=1,pattern_id=design,pattern_version='synthetic-v1',bom_version='u23-bom-v1',mapping_method='manual_synthetic_crosswalk',provenance=provenance,materials=[dict(material_id=subset[0]['material_id'],name='합성 기준 원단 · 물성 미확인',unit='mm2')],pieces=[],bom=[])
  for p in subset:
   assert p['synthetic'] and bom[p['piece_id']]['material_id']==p['material_id']
   raw=(source/p['svg_path']).read_bytes();name=digest(raw)+'.svg';(out/'assets'/name).write_bytes(raw)
   bundle['pieces'].append({**{k:p[k] for k in ('piece_id','width_mm','height_mm','area_mm2','cut_qty','material_id')},'standard_part_id':labels[p['piece_id']]['standard_part_id'],'asset':name,'asset_bytes':len(raw)})
   bundle['bom'].append(dict(piece_id=p['piece_id'],pattern_version=bundle['pattern_version'],material_id=p['material_id'],quantity=p['cut_qty'],quantity_unit='pcs',consumption=p['area_mm2']*p['cut_qty'],consumption_unit='mm2'))
  for version in (1,2):
   if version==2:
    bundle=copy.deepcopy(bundle);bundle.update(version=2,pattern_version='synthetic-v2',bom_version='u23-bom-v2')
    bundle['materials'][0]['unit']='cm2';bundle['materials'].append(dict(material_id='FABRIC-PATCH',name='합성 배 패치용 원단 · 물성 미확인',unit='cm2'))
    for p,b in zip(bundle['pieces'],bundle['bom']):
     if p['standard_part_id']=='BELLY_PATCH':p.update(material_id='FABRIC-PATCH',cut_qty=2)
     b.update(pattern_version='synthetic-v2',material_id=p['material_id'],quantity=p['cut_qty'],consumption=p['area_mm2']*p['cut_qty']/100,consumption_unit='cm2')
   assert audit(bundle)['passed'],audit(bundle)
   raw=serialized(bundle);(out/'bundles'/f'{pid}-v{version}.json').write_bytes(raw);metas.append(dict(product_id=pid,version=version,sha256=digest(raw),bytes=len(raw)))
 (out/'library.json').write_bytes(serialized(dict(schema_version='aurora-pattern-library-v1',bundles=metas,scope='own synthetic PAT contours, manual mapping; no sewing/fit certification')))
 print(json.dumps(dict(bundles=len(metas),unique_piece_assets=len(list((out/'assets').glob('*.svg'))))))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.source,a.output)
