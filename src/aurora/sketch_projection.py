"""Optional visible-surface sketch color transfer. No learned texture or camera recovery."""
import argparse,json,math,time
from pathlib import Path
from .learned3d_worker import sha

DEFAULT=dict(yaw=0,offset_x=0,offset_y=0,scale=1)
def settings(values):
    if not isinstance(values,dict) or set(values)!=set(DEFAULT):raise ValueError('투영 설정 필드 오류')
    for k,v in values.items():
        lo,hi=(-45,45) if k=='yaw' else (.8,1.2) if k=='scale' else (-.15,.15)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('투영 설정 범위 오류: '+k)
    return values

def transfer(mesh,image,options):
    import numpy as np
    from scipy.ndimage import maximum_filter
    from PIL import Image
    settings(options)
    if len(mesh.vertices)>250000 or len(mesh.faces)>500000 or len(mesh.faces)<1:raise ValueError('투영용 메시 크기 제한')
    vertices=np.asarray(mesh.vertices);faces=np.asarray(mesh.faces)
    if not np.isfinite(vertices).all():raise ValueError('비유한 메시')
    image=image.convert('RGBA');image.thumbnail((768,768));a=np.asarray(image);alpha=a[:,:,3];ys,xs=np.where(alpha>127)
    if not len(xs):raise ValueError('빈 전경 이미지')
    x0,x1,y0,y1=int(xs.min()),int(xs.max()),int(ys.min()),int(ys.max())
    angle=math.radians(options['yaw']);c,s=math.cos(angle),math.sin(angle)
    rotation=np.array([[c,0,s],[0,1,0],[-s,0,c]],dtype=float)
    view=vertices@rotation.T;lo=view.min(axis=0);extent=np.ptp(view,axis=0)
    if min(extent[:2])<=1e-8:raise ValueError('투영 평면이 퇴화했습니다.')
    uv=(view[:,:2]-lo[:2])/extent[:2];uv[:,1]=1-uv[:,1]
    uv=(uv-.5)*options['scale']+.5+np.array([options['offset_x'],options['offset_y']])
    pixels=uv*np.array([x1-x0,y1-y0])+np.array([x0,y0])
    depth=np.full(alpha.shape,-np.inf,dtype=np.float32);height,width=alpha.shape
    # Rasterized front-depth visibility prevents painting hidden/rear surfaces through the object.
    for face in faces:
        pts=pixels[face];z=view[face,2]
        xmin=max(0,int(np.floor(pts[:,0].min())));xmax=min(width-1,int(np.ceil(pts[:,0].max())))
        ymin=max(0,int(np.floor(pts[:,1].min())));ymax=min(height-1,int(np.ceil(pts[:,1].max())))
        if xmin>xmax or ymin>ymax:continue
        xx,yy=np.meshgrid(np.arange(xmin,xmax+1),np.arange(ymin,ymax+1))
        u,v,w=pts;den=(v[1]-w[1])*(u[0]-w[0])+(w[0]-v[0])*(u[1]-w[1])
        if abs(den)<1e-10:continue
        b0=((v[1]-w[1])*(xx-w[0])+(w[0]-v[0])*(yy-w[1]))/den
        b1=((w[1]-u[1])*(xx-w[0])+(u[0]-w[0])*(yy-w[1]))/den;b2=1-b0-b1
        inside=(b0>=-1e-5)&(b1>=-1e-5)&(b2>=-1e-5)
        values=np.where(inside,b0*z[0]+b1*z[1]+b2*z[2],-np.inf)
        region=depth[ymin:ymax+1,xmin:xmax+1];np.maximum(region,values,out=region)
    visible_depth=maximum_filter(depth,size=3)
    ix=np.rint(pixels[:,0]).astype(int);iy=np.rint(pixels[:,1]).astype(int)
    within=(ix>=0)&(ix<width)&(iy>=0)&(iy<height);ix=np.clip(ix,0,width-1);iy=np.clip(iy,0,height-1)
    normals=np.asarray(mesh.vertex_normals)@rotation.T
    eps=max(extent[2]*.02,1e-5)
    paint=within&(alpha[iy,ix]>127)&(normals[:,2]>.15)&(view[:,2]>=visible_depth[iy,ix]-eps)
    colors=np.tile([225,220,210,255],(len(vertices),1)).astype(np.uint8)
    # Fade to neutral around grazing-angle seams; unseen surfaces stay explicitly untextured.
    blend=np.clip((normals[:,2]-.15)/.35,0,1)*paint
    colors[:,:3]=np.rint(colors[:,:3]*(1-blend[:,None])+a[iy,ix,:3]*blend[:,None]).astype(np.uint8)
    return colors,dict(projected_vertices=int(paint.sum()),total_vertices=len(vertices),dark_projected_vertices=int((paint&(a[iy,ix,:3].mean(axis=1)<150)).sum()),
        image_foreground_bbox=[x0,y0,x1,y1],visibility='front-normal + rasterized z-buffer; 2% depth tolerance',
        assumption='manually adjusted orthographic bbox alignment, not recovered camera calibration')

def generate(model_path,image_path,output,options):
    import hashlib,numpy as np,trimesh
    from PIL import Image
    settings(options);output=Path(output)
    if output.exists():raise ValueError('기존 투영 사본 덮어쓰기 거부')
    started=time.perf_counter();mesh=trimesh.load(model_path,force='mesh',process=False)
    original_vertices=np.asarray(mesh.vertices).copy();original_faces=np.asarray(mesh.faces).copy()
    colors,metrics=transfer(mesh,Image.open(image_path),options)
    mesh.visual=trimesh.visual.ColorVisuals(mesh=mesh,vertex_colors=colors)
    if not np.array_equal(original_vertices,mesh.vertices) or not np.array_equal(original_faces,mesh.faces):raise ValueError('투영 중 형상 변경')
    output.mkdir(parents=True);mesh.export(output/'projected.glb')
    check=trimesh.load(output/'projected.glb',force='mesh',process=False)
    if not np.array_equal(original_vertices.astype('<f4'),np.asarray(check.vertices).astype('<f4')) or not np.array_equal(original_faces,check.faces):raise ValueError('저장된 사본의 형상이 원본과 다릅니다.')
    report=dict(method='visible-surface-sketch-projection-v1',settings=options,metrics=metrics,geometry_preserved=True,
        parent_model_sha256=sha(model_path),source_image_sha256=sha(image_path),adapter_sha256=sha(Path(__file__)),
        geometry_sha256=hashlib.sha256(original_vertices.astype('<f4').tobytes()+original_faces.astype('<i8').tobytes()).hexdigest(),
        elapsed_seconds=time.perf_counter()-started,learned_texture=False,camera_calibrated=False,backside_textured=False,
        design_approved=False,manufacturing_verified=False,
        limitations=['Approximate placement can distort facial marks; inspect manually','Back and occluded surfaces remain neutral','No fabric/physical material or sewing reconstruction'])
    (output/'projection-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--settings',required=True);a=p.parse_args();print(json.dumps(generate(a.model,a.image,a.output,json.loads(a.settings))))
