"""Manual/preset facial accessory geometry, not automatic reconstruction or sewing geometry."""
import argparse,json,math,time,hashlib
from pathlib import Path
from .learned3d_worker import sha
KEYS=('eye_left','eye_right','nose','mouth_left','mouth_center','mouth_right')
DEFAULT_SETTINGS=dict(eye_size=.024,eye_depth=.35,nose_size=.029,nose_shape='triangle',mouth_radius=.004,eyes_enabled=True,nose_enabled=True,mouth_enabled=True,style='button')
def presets():
    out={}
    for family,cx,cy,spacing in [('BUNNY',.5,.65,.075),('BEAR',.5,.76,.10),('ELEPHANT',.5,.77,.095),('DUCK',.21,.35,.045)]:
        a=dict(eye_left=[cx-spacing,cy+.025,1.],eye_right=[cx+spacing,cy+.025,1.],nose=[cx,cy-.035,1.],mouth_left=[cx-.04,cy-.06,1.],mouth_center=[cx,cy-.085,1.],mouth_right=[cx+.04,cy-.06,1.])
        s=dict(DEFAULT_SETTINGS)
        if family!='BUNNY':s['nose_shape']='round'
        if family in ('ELEPHANT','DUCK'):s.update(nose_enabled=False,mouth_enabled=False)
        out[family]=dict(anchors=a,settings=s,origin='preset',note='Approximate bbox preset; manually confirm all visible/hidden features. Duck uses existing bill.')
    return out

def validate(anchors,options):
    if not isinstance(anchors,dict) or set(anchors)!=set(KEYS):raise ValueError('얼굴 대응점 6개 필요')
    for v in anchors.values():
        if not isinstance(v,list) or len(v)!=3 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in v):raise ValueError('얼굴 대응점은 정규화 XYZ 0~1')
    if not isinstance(options,dict) or set(options)!=set(DEFAULT_SETTINGS):raise ValueError('얼굴 설정 필드 오류')
    for k,(lo,hi) in dict(eye_size=(.005,.07),eye_depth=(.05,.8),nose_size=(.005,.09),mouth_radius=(.001,.012)).items():
        v=options[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('얼굴 크기 범위 오류: '+k)
    if options['nose_shape'] not in ('round','triangle') or options['style'] not in ('button','stitch'):raise ValueError('얼굴 형태/스타일 오류')
    if any(type(options[k]) is not bool for k in ('eyes_enabled','nose_enabled','mouth_enabled')) or not any(options[k] for k in ('eyes_enabled','nose_enabled','mouth_enabled')):raise ValueError('얼굴 부위 선택 필요')

def generate(model,image,output,anchors,options,family,origin):
    import numpy as np,trimesh
    validate(anchors,options)
    if family not in presets() or origin not in ('preset','manual'):raise ValueError('얼굴 유형/출처 오류')
    if family=='DUCK' and (options['nose_enabled'] or options['mouth_enabled']):raise ValueError('오리는 기존 부리 유지: 코/입 추가 미지원')
    output=Path(output)
    if output.exists():raise ValueError('기존 얼굴 사본 덮어쓰기 거부')
    start=time.perf_counter();base=trimesh.load(model,force='mesh',process=False)
    if not 1<=len(base.faces)<=200000 or not np.isfinite(base.vertices).all():raise ValueError('얼굴 편집 메시 제한')
    lo,hi=base.bounds;extent=hi-lo;scale=float(extent.max())
    if scale<=0:raise ValueError('퇴화한 형상')
    scene=trimesh.Scene();scene.add_geometry(base,geom_name='original_body',node_name='original_body')
    # Nearest exact triangle surface, not a free-floating camera overlay.
    def snap(points):
        points=np.asarray(points);closest,dist,index=trimesh.proximity.closest_point_naive(base,points)
        normals=base.face_normals[index]
        if not np.isfinite(closest).all():raise ValueError('표면 대응 실패')
        return closest,normals,dist
    positions=np.array([anchors[k] for k in KEYS])*extent+lo
    # Preset Z is a front-view ray start, not a closest-point depth target.
    def front(points):
        points=np.asarray(points);tri=base.triangles;u,v,w=tri[:,0,:2],tri[:,1,:2],tri[:,2,:2];den=(v[:,1]-w[:,1])*(u[:,0]-w[:,0])+(w[:,0]-v[:,0])*(u[:,1]-w[:,1]);safe=np.where(abs(den)>1e-12,den,1.)
        ps=[];ns=[];ds=[]
        for point in points:
            x,y=point[:2];b0=((v[:,1]-w[:,1])*(x-w[:,0])+(w[:,0]-v[:,0])*(y-w[:,1]))/safe;b1=((w[:,1]-u[:,1])*(x-w[:,0])+(u[:,0]-w[:,0])*(y-w[:,1]))/safe;b2=1-b0-b1
            inside=(abs(den)>1e-12)&(b0>=-1e-6)&(b1>=-1e-6)&(b2>=-1e-6);z=b0*tri[:,0,2]+b1*tri[:,1,2]+b2*tri[:,2,2]
            if not inside.any():
                a,n,d=snap([point]);ps.append(a[0]);ns.append(n[0]);ds.append(d[0]);continue
            index=int(np.argmax(np.where(inside,z,-np.inf)));a=np.array([x,y,z[index]]);ps.append(a);ns.append(base.face_normals[index]);ds.append(np.linalg.norm(a-point))
        return np.asarray(ps),np.asarray(ns),np.asarray(ds)
    attach=front if origin=='preset' else snap
    positions,normals,dist=attach(positions);placements={k:dict(position=positions[i].tolist(),normal=normals[i].tolist(),snap_distance=float(dist[i])) for i,k in enumerate(KEYS)}
    names=[]
    def add(name,part):
        part.visual=trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(name='facial accessory',baseColorFactor=[28,23,22,255],metallicFactor=0.,roughnessFactor=.55))
        scene.add_geometry(part,geom_name=name,node_name=name);names.append(name)
    def oval(name,i,size,depth):
        part=trimesh.creation.icosphere(subdivisions=2,radius=1);part.apply_scale([size,size*.95,depth]);m=trimesh.geometry.align_vectors([0,0,1],normals[i]);m[:3,3]=positions[i]+normals[i]*depth*.2;part.apply_transform(m);add(name,part)
    if options['eyes_enabled']:
        for name,i in [('face_eye_left',0),('face_eye_right',1)]:
            radius=options['eye_size']*scale;oval(name,i,radius,radius*(options['eye_depth'] if options['style']=='button' else .06))
    if options['nose_enabled']:
        radius=options['nose_size']*scale
        if options['nose_shape']=='round':oval('face_nose',2,radius,radius*.5)
        else:
            v=np.array([[-1,.5,-.1],[1,.5,-.1],[0,-.7,-.1],[-1,.5,.45],[1,.5,.45],[0,-.7,.45]])*radius
            part=trimesh.Trimesh(v,[[0,2,1],[3,4,5],[0,1,4],[0,4,3],[1,2,5],[1,5,4],[2,0,3],[2,3,5]],process=True);m=trimesh.geometry.align_vectors([0,0,1],normals[2]);m[:3,3]=positions[2];part.apply_transform(m);add('face_nose',part)
    if options['mouth_enabled']:
        t=np.linspace(0,1,21)[:,None];curve=(1-t)**2*positions[3]+2*(1-t)*t*positions[4]+t**2*positions[5];points,ns,_=attach(curve);radius=options['mouth_radius']*scale;points=points+ns*radius*.5
        pieces=[]
        for a,b in zip(points[:-1],points[1:]):
            if np.linalg.norm(b-a)>radius*.05:pieces.append(trimesh.creation.cylinder(radius=radius,segment=[a,b],sections=8))
        if not pieces:raise ValueError('입 곡선 대응점을 벌려 주세요')
        add('face_mouth',trimesh.util.concatenate(pieces))
    output.mkdir(parents=True);scene.export(output/'face.glb');check=trimesh.load(output/'face.glb',force='scene',process=False)
    saved=check.geometry.get('original_body')
    if saved is None or not np.array_equal(np.asarray(saved.vertices).astype('<f4'),np.asarray(base.vertices).astype('<f4')) or not np.array_equal(saved.faces,base.faces) or not set(names)<=set(check.geometry):raise ValueError('얼굴 GLB 재읽기/부모 형상 보존 검증 실패')
    report=dict(method='manual-surface-facial-accessories-v1',family=family,anchor_origin=origin,anchors=anchors,settings=options,placements=placements,added_parts=names,parent_model_sha256=sha(model),source_image_sha256=sha(image),adapter_sha256=sha(Path(__file__)),original_body_preserved=True,geometry_preserved=False,overall_geometry_changed=True,download_contains_face=True,automatic_landmarks=False,uv_texture_generated=False,single_fused_mesh=False,design_approved=False,manufacturing_verified=False,elapsed_seconds=time.perf_counter()-start,limitations=['Preset landmarks are unverified assumptions; adjust/confirm manually','Surface accessories may intersect body intentionally; not fused sewing topology','Stitch style is shallow geometry, not recovered embroidery/UV fabric texture'])
    (output/'face-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--anchors',required=True);p.add_argument('--settings',required=True);p.add_argument('--family',required=True);p.add_argument('--origin',required=True);a=p.parse_args();print(json.dumps(generate(a.model,a.image,a.output,json.loads(a.anchors),json.loads(a.settings),a.family,a.origin)))
