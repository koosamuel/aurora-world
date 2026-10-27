"""Generate original geometric U20 fixtures; no company images, brands or measurements."""
from pathlib import Path
import copy
import json
from hashlib import sha256
from aurora.sampling import checksum,validate,envelope
from aurora.identity import serialized

REFERENCE='사용자가 제공한 브랜드 소개 화면의 일반적인 동물·자세·색상·둥근 외형만 참고. 로고·캐릭터·사진은 포함하지 않음. 원화는 독립 기하 도형이며 치수·원단·조건·현행 이력은 모두 가상.'
FAMILIES=[('BUNNY','앉은 토끼','bunny','#E8D9BB'),('COW','둥근 젖소','cow','#F6F3EB'),('DOG','둥근 강아지','dog','#B88A61'),('CAT','앉은 고양이','cat','#D9AB76'),('CACTUS','선인장형 쿠션','cactus','#6C9B78'),('FRUIT','과일형 쿠션','fruit','#E8C951')]


def artwork(kind,color):
    def ellipse(x,y,rx,ry,fill):return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}"/>'
    def circle(x,y,r,fill):return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>'
    shapes=['<rect x="0" y="0" width="210" height="210" fill="#F8FAF7"/>']
    if kind=='bunny':shapes += [ellipse(80,47,14,33,color),ellipse(130,47,14,33,color)]
    elif kind=='cat':shapes += [f'<path d="M 60 86 L 64 37 L 92 66 Z" fill="{color}"/>',f'<path d="M 118 66 L 146 37 L 150 86 Z" fill="{color}"/>']
    elif kind=='cow':shapes += [ellipse(60,79,24,14,'#414B48'),ellipse(150,79,24,14,'#414B48')]
    elif kind=='dog':shapes += [ellipse(62,92,17,34,'#785940'),ellipse(148,92,17,34,'#785940')]
    elif kind=='cactus':shapes += [ellipse(55,113,17,34,color),ellipse(155,113,17,34,color)]
    elif kind=='fruit':shapes += [f'<path d="M 104 72 L 77 30 L 106 44 L 127 24 L 125 66 Z" fill="#688E55"/>']
    shapes += [ellipse(105,144,58,45,color),ellipse(105,100,49,42,color)]
    if kind=='cow':shapes += [ellipse(126,79,20,14,'#414B48'),ellipse(104,114,28,17,'#E7B9AB')]
    shapes += [circle(87,97,4,'#253D3D'),circle(123,97,4,'#253D3D'),f'<path d="M 96 116 Q 105 124 114 116" fill="none" stroke="#253D3D" stroke-width="2"/>']
    raw='<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="210mm" viewBox="0 0 210 210">'+''.join(shapes)+'</svg>'
    return dict(file_name=kind+'-concept.svg',media_type='image/svg+xml',sha256=sha256(raw.encode()).hexdigest(),width_mm=210,height_mm=210,svg=raw)


def build(root):
    root=Path(root);output=root/'configs/examples/sampling';output.mkdir(parents=True,exist_ok=True);catalog=[]
    for index,(code,name,kind,color) in enumerate(FAMILIES):
        measured=index%3!=2
        baseline=dict(status='synthetic_recorded' if measured else 'unmeasured',window_start='2026-09-01',window_end='2026-09-30',time_definition='合성 기준: 명세 접수부터 기존 샘플 최종 검토 완료까지의 달력 경과시간'.replace('合성','합성'),started_at='2026-09-01T09:00:00Z' if measured else None,ended_at='2026-09-15T09:00:00Z' if measured else None,physical_samples=[dict(event_id='MAKE-1',occurred_at='2026-09-03T09:00:00Z',quantity=1),dict(event_id='MAKE-2',occurred_at='2026-09-10T09:00:00Z',quantity=2)] if measured else [],bom_changes=[dict(event_id='BOM-1',occurred_at='2026-09-05T09:00:00Z',reason='error_correction',description='합성 원단 수량 기입 오류 수정'),dict(event_id='BOM-2',occurred_at='2026-09-11T09:00:00Z',reason='design_change',description='합성 디자인 조건 변경')] if measured else [])
        payload=dict(schema_version='aurora-sampling-brief-v1',data_kind='synthetic',product_id='SYN-'+code,product_name='가상 '+name,brief_version=1,previous_checksum=None,artwork_version=1,artwork=artwork(kind,color),requirements=dict(dimensions=dict(height=140+index*10,width=110+index*5,depth=90+index*5,unit='mm'),fabric=dict(code='SYN-FAB-'+str(index+1),description='가상 봉제 원단 · 제품 실사양 아님'),colors=[dict(part='body',name='가상 기본색',hex=color)],must_have=['부드러운 둥근 외형','작은 부자재 분리 방지 검토 · 합성 조건']),rights=dict(source_type='self_generated_synthetic',company_data=False,allowed_use='public_synthetic_demo',provenance=REFERENCE),baseline=baseline)
        for version in (1,2):
            validate(payload);path=output/f'{index+1:02d}-{kind}-v{version}.json';path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');catalog.append(envelope(payload))
            previous=copy.deepcopy(payload);payload=copy.deepcopy(previous);payload.update(brief_version=2,previous_checksum=checksum(previous));payload['requirements']['dimensions']['height']+=10;payload['requirements']['must_have'].append('크기 수정본 검토 · 합성')
    client=root/'client/demo/sampling';client.mkdir(parents=True,exist_ok=True);(client/'catalog.json').write_bytes(serialized(dict(schema_version='aurora-sampling-catalog-v1',data_kind='synthetic',records=catalog)))
    return catalog


if __name__=='__main__':
    rows=build(Path(__file__).resolve().parents[1]);print(f'Generated {len(rows)} versions for {len(FAMILIES)} synthetic product families.')
