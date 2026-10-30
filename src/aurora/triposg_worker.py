"""Official TripoSG-scribble adapter; neutral shape mesh, not texture synthesis."""
import argparse,functools,json,os,sys,time,types
from pathlib import Path
from .learned3d_worker import sha
from .sketch_demos import PROMPTS
PROMPT=PROMPTS['BUNNY']

def generate(root,input_path,output,family='BUNNY'):
    if family not in PROMPTS:raise ValueError('미지원 동물 유형')
    prompt=PROMPTS[family]
    root=Path(root);output=Path(output)
    if output.exists():raise ValueError('출력 폴더 덮어쓰기 거부')
    c=json.loads((root/'.learned3d-local.json').read_text())
    m=json.loads((root/'configs/ai/triposg-manifest.json').read_text())
    for key,base in [('source_files',Path(c['triposg_source'])),('model_files',Path(c['triposg_weights']))]:
        for f in m[key]:
            if sha(base/f['file'])!=f['sha256']:raise ValueError('TripoSG 무결성 오류: '+f['file'])
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTORCH_ENABLE_MPS_FALLBACK='1')
    sys.path[:0]=[str(root/'.models/triposg-python'),c['triposg_source']]
    import numpy as np
    import torch,trimesh
    from PIL import Image,ImageOps
    # CUDA-only diso is unused with the documented non-flash decoder. Fail if called.
    diso=types.ModuleType('diso')
    def unavailable(*a,**kw):raise RuntimeError('CUDA DiffDMC disabled; use CPU marching cubes')
    diso.DiffDMC=unavailable;sys.modules['diso']=diso
    from triposg.pipelines.pipeline_triposg_scribble import TripoSGScribblePipeline
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    dtype=torch.float16 if device=='mps' else torch.float32
    tick=time.perf_counter();torch.set_num_threads(4);torch.manual_seed(42)
    im=ImageOps.exif_transpose(Image.open(input_path)).convert('RGBA')
    # The sketch model consumes the entire approved drawing on WHITE, not a rembg photo mask.
    white=Image.new('RGBA',im.size,'white');white.alpha_composite(im);white=white.convert('RGB');white=ImageOps.pad(white,(512,512),color='white')
    output.mkdir(parents=True);white.save(output/'condition.png')
    pipe=TripoSGScribblePipeline.from_pretrained(c['triposg_weights'],torch_dtype=dtype,local_files_only=True,use_safetensors=True).to(device)
    # Retain upstream dense SDF extraction, avoiding CUDA-only hierarchical refinement.
    # Smaller VAE query chunks bound peak MPS memory; cached KV stays inside upstream decoder.
    pipe.vae._decode=functools.partial(pipe.vae._decode,num_chunks=4096)
    print('TripoSG model ready on '+device,flush=True)
    with torch.inference_mode():
        result=pipe(image=white,prompt=prompt,num_tokens=512,num_inference_steps=16,guidance_scale=0,
          generator=torch.Generator(device='cpu').manual_seed(42),
          attention_kwargs={'cross_attention_scale':1.0,'cross_attention_2_scale':.4},
          use_flash_decoder=False,dense_octree_depth=7,hierarchical_octree_depth=7).meshes[0]
    mesh=trimesh.Trimesh(np.asarray(result.vertices,dtype=np.float32),np.asarray(result.faces),process=True)
    if len(mesh.faces)<100 or not np.isfinite(mesh.vertices).all():raise ValueError('유효한 메시가 생성되지 않았습니다.')
    mesh.remove_unreferenced_vertices();mesh.fix_normals(multibody=True);mesh.visual.vertex_colors=np.tile([225,220,210,255],(len(mesh.vertices),1))
    mesh.export(output/'model.glb')
    report=dict(engine='TripoSG-scribble',learned_model=True,texture_generated=False,vertex_color='constant neutral display material',
        prompt=prompt,family=family,prompt_origin='fixed developer/demo caption for selected family; not automatically extracted requirements',
        seed=42,steps=16,sketch_confidence=.4,prompt_confidence=1.0,num_tokens=512,grid_resolution=128,
        device=device,elapsed_seconds=time.perf_counter()-tick,vertices=len(mesh.vertices),faces=len(mesh.faces),
        bounds=mesh.bounds.tolist(),watertight=bool(mesh.is_watertight),input_sha256=sha(input_path),
        adapter_sha256=sha(Path(__file__)),normal_orientation_repaired=True,source_revision=m['source_revision'],model_revision=m['model_revision'],model_manifest_sha256=sha(root/'configs/ai/triposg-manifest.json'),
        packages={k:__import__('importlib.metadata',fromlist=['version']).version(k) for k in ('torch','diffusers','transformers','trimesh')},dimensions_verified=False,design_approved=False,manufacturing_verified=False,quality_status='needs_visual_review',
        limitations=['Shape only; neutral material is not generated fabric texture','Unseen surfaces are inferred','No validated scale, sewing pattern, BOM or Meshy-equivalence'])
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report),flush=True);return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--family',choices=sorted(PROMPTS),default='BUNNY');a=p.parse_args();generate(a.root,a.input,a.output,a.family)
