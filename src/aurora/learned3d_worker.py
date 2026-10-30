"""Local TripoSR adapter: neural single-image reconstruction, never a procedural fallback.

Upstream code is installed separately under its MIT license. skimage replaces only
marching cubes, not learned weights. rembg runs in a separate process (OpenMP isolation).
"""
import argparse, hashlib, json, os, sys, time, types
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def prepare(path, output, ratio=.85):
    from PIL import Image, ImageOps
    image=ImageOps.exif_transpose(Image.open(path)).convert('RGBA')
    box=image.getchannel('A').getbbox()
    if box is None: raise ValueError('Empty foreground')
    image=image.crop(box); image.thumbnail((round(512*ratio),round(512*ratio)))
    background=Image.new('RGBA',(512,512),(128,128,128,255))
    background.alpha_composite(image,((512-image.width)//2,(512-image.height)//2))
    image=background.convert('RGB'); image.save(output); return image

def generate(root,input_path,output,resolution=128,ratio=.85):
    root=Path(root); output=Path(output); output.mkdir(parents=True,exist_ok=True)
    c=json.loads((root/'.learned3d-local.json').read_text())
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTORCH_ENABLE_MPS_FALLBACK='1')
    sys.path.insert(0,str(root/'.models/tripo-python'))
    manifest=json.loads((root/'configs/ai/triposr-manifest.json').read_text())
    for entry in manifest['source_files']:
        if sha(Path(c['source'])/entry['file'])!=entry['sha256']:raise ValueError('TripoSR source integrity error')
    for entry in manifest['model_files']:
        if sha(Path(c['weights'])/entry['file'])!=entry['sha256']:raise ValueError('TripoSR model integrity error')
    import numpy as np
    import torch
    from skimage.measure import marching_cubes
    # Upstream utilities import rembg even for pre-segmented inputs. Avoid loading
    # a second OpenMP runtime; background removal has already completed separately.
    rembg=types.ModuleType('rembg')
    def unused(*a,**kw):raise RuntimeError('Use the isolated segmentation process')
    rembg.remove=unused; sys.modules['rembg']=rembg
    cubes=types.ModuleType('torchmcubes')
    def mc(level,threshold):
        vertices,faces,_,_=marching_cubes(level.detach().cpu().numpy(),level=threshold)
        return torch.from_numpy(vertices[:,[2,1,0]].copy()),torch.from_numpy(faces.copy().astype('int64'))
    cubes.marching_cubes=mc; sys.modules['torchmcubes']=cubes
    sys.path.insert(0,c['source'])
    from huggingface_hub import hf_hub_download
    entry=manifest['image_encoder_config']
    dino_config=hf_hub_download(entry['repository'],'config.json',revision=entry['revision'],local_files_only=True)
    if sha(dino_config)!=entry['sha256']:raise ValueError('DINO config integrity error')
    import tsr.models.tokenizers.image as image_tokenizer
    image_tokenizer.hf_hub_download=lambda **kwargs:dino_config
    from tsr.system import TSR
    from omegaconf import OmegaConf
    tick=time.perf_counter(); device='mps' if torch.backends.mps.is_available() else 'cpu'
    torch.manual_seed(42); torch.set_num_threads(4)
    image=prepare(input_path,output/'condition.png',ratio)
    cfg=OmegaConf.load(str(Path(c['weights'])/'config.yaml'))
    OmegaConf.resolve(cfg)
    model=TSR(cfg)
    # Only official locally pinned tensor checkpoint, never a user-supplied pickle.
    model.load_state_dict(torch.load(Path(c['weights'])/'model.ckpt',map_location='cpu',weights_only=True))
    model.eval().to(device);model.renderer.set_chunk_size(8192)
    print('model ready on '+device,flush=True)
    with torch.inference_mode():
        codes=model([image],device=device)
        print('scene inferred',flush=True)
        mesh=model.extract_mesh(codes,has_vertex_color=True,resolution=resolution)[0]
    # TripoSR is Z-up. Existing U21 viewer is Y-up; preserve handedness.
    mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],dtype=float))
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces)<100 or not np.isfinite(mesh.vertices).all():raise ValueError('Invalid mesh')
    mesh.export(output/'model.glb')
    report=dict(engine='TripoSR',learned_model=True,resolution=resolution,foreground_ratio=ratio,
        device=device,elapsed_seconds=time.perf_counter()-tick,vertices=len(mesh.vertices),faces=len(mesh.faces),
        watertight=bool(mesh.is_watertight),bounds=mesh.bounds.tolist(),input_sha256=sha(input_path),
        checkpoint_sha256=sha(Path(c['weights'])/'model.ckpt'),source_revision=manifest['source_revision'],
        model_revision=Path(c['weights']).name,seed=42,dimensions_verified=False,design_approved=False,
        manufacturing_verified=False,quality_status='needs_visual_review',
        limitations=['Unseen surfaces are inferred, not measured','No sewing pattern, BOM, material physics or Meshy-equivalence validation'],
        packages={k:__import__('importlib.metadata',fromlist=['version']).version(k) for k in ('torch','transformers','scikit-image','trimesh')})
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--resolution',type=int,choices=(128,192,256),default=128);p.add_argument('--ratio',type=float,default=.85);a=p.parse_args()
    generate(a.root,a.input,a.output,a.resolution,a.ratio)
