"""Synthetic labeling demo: training-only feature scaling and 7-family kNN.

Fine labels (left/right/front/back) remain separate mapping/review candidates.
No neural sketch generator or real production-pattern classifier is claimed.
"""
import argparse,collections,hashlib,json,math,statistics,xml.etree.ElementTree as ET
from pathlib import Path

FAMILIES={'HEAD':'머리','BODY':'몸통','EAR':'귀','ARM':'팔','LEG':'다리','TAIL':'꼬리','BELLY':'배 패치'}
FEATURES=['log_width_mm','log_height_mm','relative_area','fill_ratio']

def load_rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def family(code):return code.split('_')[0]
def vector(piece):
    w,h,a=piece['width_mm'],piece['height_mm'],piece['area_mm2']
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (w,h,a)):raise ValueError('Invalid dimensions')
    return [round(math.log(w),9),round(math.log(h),9),round(piece['relative_area'],9),round(a/(w*h),9)]
def fit(pieces,labels,k=5):
    train=[p for p in pieces if p['split']=='train']
    if not train:raise ValueError('Training data required')
    xs=[vector(p) for p in train];means=[statistics.mean(col) for col in zip(*xs)];scales=[statistics.pstdev(col) or 1.0 for col in zip(*xs)]
    return dict(schema_version='aurora-part-knn-v1',k=k,features=FEATURES,means=means,scales=scales,train_x=xs,train_y=[family(labels[p['piece_id']]['standard_part_id']) for p in train],training_families=sorted({p['family_id'] for p in train}),fine_label_inference=False)
def predict(model,x):
    distances=[]
    for i,(tx,label) in enumerate(zip(model['train_x'],model['train_y'])):
        distance=sum(((a-b)/scale)**2 for a,b,scale in zip(tx,x,model['scales']))
        distances.append((distance,i,label))
    neighbors=sorted(distances)[:model['k']];counts=collections.Counter(label for _,_,label in neighbors)
    sums={label:sum(d for d,_,y in neighbors if y==label) for label in counts}
    ranked=sorted(counts,key=lambda y:(-counts[y],sums[y],y))
    return dict(family=ranked[0],support=counts[ranked[0]]/len(neighbors),votes=[dict(family=y,count=counts[y],support=counts[y]/len(neighbors)) for y in ranked])
def score(model,pieces,labels,split):
    rows=[p for p in pieces if p['split']==split];confusion={a:{b:0 for b in FAMILIES} for a in FAMILIES}
    for p in rows:
        true=family(labels[p['piece_id']]['standard_part_id']);pred=predict(model,vector(p))['family'];confusion[true][pred]+=1
    per=[]
    for y in FAMILIES:
        tp=confusion[y][y];support=sum(confusion[y].values());predicted=sum(r[y] for r in confusion.values());den=support+predicted
        per.append(dict(family=y,support=support,f1=2*tp/den if den else 0))
    return dict(split=split,n=len(rows),accuracy=sum(confusion[y][y] for y in FAMILIES)/len(rows),macro_f1=sum(r['f1'] for r in per)/len(per),per_family=per,confusion=confusion)
def normalize(value):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKC',value).lower() if c.isalnum())
def build(root,out):
    pieces=load_rows(root/'patterns/pieces.jsonl');products=load_rows(root/'products.jsonl');labels={r['piece_id']:r for r in load_rows(root/'patterns/labels.jsonl')};mapping={r['piece_id']:r for r in load_rows(root/'patterns/name_mapping.jsonl')};master=json.loads((root/'standard_parts.json').read_text())
    splits={p['piece_id']:p['split'] for p in pieces};groups={split:{p['family_id'] for p in pieces if p['split']==split} for split in ('train','validation','test')}
    if any(groups[a]&groups[b] for a in groups for b in groups if a!=b):raise ValueError('Family leakage')
    model=fit(pieces,labels);report=dict(schema_version='aurora-labeling-report-v1',synthetic=True,target='7 coarse part families; not 12 fine labels',model='standardized 5-nearest neighbors',training_n=len(model['train_x']),training_groups=len(groups['train']),validation=score(model,pieces,labels,'validation'),test=score(model,pieces,labels,'test'),fine_labels_require_review=True,score_is_not_enterprise_performance=True)
    aliases=collections.defaultdict(set)
    for m in master:
        for name in (m['name'],m['standard_part_id']):aliases[normalize(name)].add(m['standard_part_id'])
    for pid,m in mapping.items():
        if splits[pid]=='train':aliases[normalize(m['raw_name'])].add(m['standard_part_id'])
    exported=[]
    for p in pieces:
        svg=ET.parse(root/p['svg_path']).getroot();polygon=svg.find('{http://www.w3.org/2000/svg}polygon');pts=[[float(v) for v in point.split(',')] for point in polygon.attrib['points'].split()]
        exported.append({k:p[k] for k in ('piece_id','design_id','family_id','split','width_mm','height_mm','area_mm2','relative_area','material_id','cut_qty')}|dict(raw_name=mapping[p['piece_id']]['raw_name'],features=vector(p),view_box=[float(v) for v in svg.attrib['viewBox'].split()],points=pts))
    source_hash=hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
    dataset=dict(schema_version='aurora-labeling-dataset-v1',synthetic=True,dataset_version='research-informed-synthetic-v1',source_manifest_sha256=source_hash,products=[{k:p[k] for k in ('design_id','sku_id','name','family_id','split')} for p in products],master=master,families=FAMILIES,aliases={k:sorted(v) for k,v in sorted(aliases.items())},pieces=exported)
    truth=dict(schema_version='aurora-labeling-truth-v1',source_manifest_sha256=source_hash,labels={pid:r['standard_part_id'] for pid,r in labels.items()})
    out.mkdir(parents=True,exist_ok=True)
    for name,value in [('dataset',dataset),('model',model),('report',report),('truth',truth)]:
        (out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return dataset,model,report,truth
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.root,a.output)
