"""Offline CLIP interpretation + SD1.5 image-to-image. Optional dependencies only.

The learned interpreter accepts PIL pixels alone, not brief names or truth labels.
No arbitrary user prompt, remote URL, pickle weights or external SVG resource.
"""
from pathlib import Path
from importlib.metadata import version
import argparse, gc, io, json, os, platform, time
from .identity import require, serialized
from .sampling import validate, checksum, integer
from .generation import digest
from .ai_sampling import SETTINGS, engine_hash, runtime

CATEGORIES = [
    ('rabbit','토끼','a drawing of a cute rabbit plush toy with long ears'),
    ('cow','소','a drawing of a cute cow plush toy'),
    ('dog','강아지','a drawing of a cute dog plush toy'),
    ('cat','고양이','a drawing of a cute cat plush toy'),
    ('cactus','선인장','a drawing of a cute cactus plush toy'),
    ('pineapple','파인애플','a drawing of a cute pineapple plush toy'),
    ('cushion','쿠션','a drawing of a plain cushion pillow'),
]
COLOR_NAMES = {'cream':(232,217,187), 'white':(240,240,235), 'brown':(157,108,72),
               'green':(89,157,107), 'yellow':(235,200,90), 'pink':(220,160,180),
               'gray':(150,150,150), 'blue':(100,160,200)}
NEGATIVE = 'text, logo, watermark, people, human, hands, blurry, extra limbs, multiple objects'

def verify_models(root, c):
    models=json.loads((Path(root)/'configs/ai/model-manifest.json').read_text())
    for model in models:
        base=Path(c[model['key']]).resolve()
        for f in model['files']:
            require('..' not in Path(f['path']).parts and not Path(f['path']).is_absolute(), '잘못된 모델 명세 경로')
            p=base/f['path']
            require(p.is_file() and p.stat().st_size==f['bytes'], '모델 파일 누락/크기 오류: '+f['path'])
            require(digest(p.read_bytes())==f['sha256'], '모델 SHA-256 오류: '+f['path'])
    return models

def render_artwork(artwork):
    import cairosvg
    from PIL import Image, ImageOps
    # U20 validator rejects external resources, scripts and unbounded primitives.
    w,h=artwork['width_mm'],artwork['height_mm']; scale=512/max(w,h)
    raw=cairosvg.svg2png(bytestring=artwork['svg'].encode(),
                        output_width=max(1,round(w*scale)), output_height=max(1,round(h*scale)))
    image=Image.open(io.BytesIO(raw)).convert('RGBA')
    image=ImageOps.contain(image,(512,512),Image.Resampling.LANCZOS)
    background=Image.new('RGB',(512,512),'white')
    background.paste(image,((512-image.width)//2,(512-image.height)//2),image)
    return background

def pixel_color(image):
    """Approximate foreground palette; an explicit pixel heuristic, not CLIP."""
    import numpy as np
    a=np.asarray(image.resize((128,128))).astype('int32')
    bg=np.median(np.concatenate([a[0],a[-1],a[:,0],a[:,-1]]),axis=0)
    mask=np.sqrt(((a-bg)**2).sum(axis=2))>30
    pixels=a[mask]; fraction=float(mask.mean())
    if len(pixels)<50:return dict(method='border-distance + quantized mode',name='neutral',hex=None,foreground_fraction=fraction)
    values,counts=np.unique((pixels//16)*16+8,axis=0,return_counts=True)
    color=values[counts.argmax()]; name=min(COLOR_NAMES,key=lambda k:sum((int(color[i])-COLOR_NAMES[k][i])**2 for i in range(3)))
    return dict(method='border-distance + quantized mode',name=name,hex='#'+''.join(f'{int(x):02x}' for x in color),foreground_fraction=fraction)

class Interpreter:
    def __init__(self, path):
        import open_clip, torch
        self.torch=torch
        self.model,_,self.preprocess=open_clip.create_model_and_transforms('ViT-B-32',pretrained=str(Path(path)/'open_clip_model.safetensors'),device='cpu')
        self.model.eval()
        tokenizer=open_clip.get_tokenizer('ViT-B-32')
        with torch.inference_mode():
            text=self.model.encode_text(tokenizer([c[2] for c in CATEGORIES])).float()
            self.text=text/text.norm(dim=-1,keepdim=True)

    def analyze(self, image):
        # This method intentionally has no source/brief argument: prevent truth leakage.
        with self.torch.inference_mode():
            encoded=self.model.encode_image(self.preprocess(image).unsqueeze(0)).float()
            scores=((encoded/encoded.norm(dim=-1,keepdim=True))@self.text.T)[0].tolist()
        ranked=sorted([dict(category=c[0],label=c[1],cosine_similarity=float(s)) for c,s in zip(CATEGORIES,scores)],key=lambda x:x['cosine_similarity'],reverse=True)
        margin=ranked[0]['cosine_similarity']-ranked[1]['cosine_similarity']
        # Review band is a disclosed demo heuristic, NOT a calibrated threshold.
        tentative=margin<0.03
        return dict(method='OpenCLIP ViT-B-32 · pixel-only zero-shot',ranked=ranked,top_two_margin=margin,
                    ambiguous=tentative,hypothesis=ranked[0]['category'],review_required=True,
                    score_interpretation='Cosine similarity among seven fixed text candidates; not probabilities or production accuracy.',
                    color=pixel_color(image))

def condition_plan(brief):
    result=[]
    for text in brief['requirements']['must_have']:
        words=[]
        if '부드러' in text:words.append('soft plush texture')
        if '둥근' in text:words.append('rounded silhouette')
        result.append(dict(condition=text,prompt_terms=words,status='prompt_hint_only' if words else 'manual_review_only',satisfied=None))
    return result

def make_prompt(analysis, conditions):
    category='plush toy' if analysis['ambiguous'] else analysis['hypothesis']+' plush toy'
    terms=list(dict.fromkeys(w for c in conditions for w in c['prompt_terms']))
    return ', '.join(['product photo of a single cute '+analysis['color']['name']+' '+category,
                     'soft fabric', 'embroidered eyes', 'front view', 'plain light background',
                     'studio lighting',*terms])

def generate(root, source, seed, output):
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    root=Path(root); out=Path(output)
    require(not out.exists(), 'AI 출력 폴더를 덮어쓰지 않습니다.')
    integer(seed,'seed',0,2147483647)
    b=source['brief'];validate(b)
    require(source['data_kind']=='synthetic' and source['source']['company_data'] is False and source['id'].startswith('u20:'), '자체 합성 U20 입력만 허용합니다.')
    require(checksum(b)==source['brief_checksum'] and digest(serialized({k:v for k,v in source.items() if k!='checksum'}))==source['checksum'], 'AI 입력/명세 해시가 다릅니다.')
    started=time.perf_counter();c=runtime(root);models=verify_models(root,c)
    import torch
    from PIL import ImageChops, ImageStat
    from diffusers import StableDiffusionImg2ImgPipeline, DDIMScheduler
    out.mkdir(parents=True)
    image=render_artwork(b['artwork']);image.save(out/'input.png')
    interpreter=Interpreter(c['clip']);analysis=interpreter.analyze(image)
    conditions=condition_plan(b);prompt=make_prompt(analysis,conditions)
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    pipe=StableDiffusionImg2ImgPipeline.from_pretrained(c['sd15'],local_files_only=True,
          dtype=torch.float16 if device=='mps' else torch.float32,use_safetensors=True)
    require(pipe.safety_checker is not None, '모델 safety checker가 없습니다.')
    pipe.scheduler=DDIMScheduler.from_config(pipe.scheduler.config)
    pipe.to(device);pipe.enable_attention_slicing();records=[]
    for name,strength in zip(('preserve','reinterpret'),SETTINGS['strengths']):
        tick=time.perf_counter()
        generated=pipe(prompt=prompt,negative_prompt=NEGATIVE,image=image,strength=strength,
                       num_inference_steps=SETTINGS['steps'],guidance_scale=SETTINGS['guidance_scale'],
                       generator=torch.Generator(device='cpu').manual_seed(seed))
        require(generated.nsfw_content_detected is not None and not any(generated.nsfw_content_detected), 'AI 이미지가 안전성 검사에서 제외됐습니다.')
        candidate=generated.images[0].convert('RGB')
        stats=ImageStat.Stat(candidate)
        require(max(stats.stddev)>2 and max(stats.mean)>5, '비어 있거나 검은 AI 출력입니다.')
        candidate.save(out/(name+'.png'))
        records.append(dict(id=name,file=name+'.png',strength=strength,denoising_steps=int(SETTINGS['steps']*strength),
                            generation_seconds=time.perf_counter()-tick,safety_flagged=False,
                            pixel_mae_from_input=sum(ImageStat.Stat(ImageChops.difference(image,candidate)).mean)/3,
                            interpretation=interpreter.analyze(candidate),design_approved=False))
    del pipe;gc.collect()
    if device=='mps':torch.mps.empty_cache()
    report=dict(schema_version='aurora-ai-sample-v1',data_kind='synthetic',source_id=source['id'],source_checksum=source['checksum'],
                brief_checksum=source['brief_checksum'],artwork_sha256=b['artwork']['sha256'],engine_sha256=engine_hash(),
                learned_model=True,output_type='2D PNG',model_training=False,models=models,
                input_analysis=analysis,prompt=prompt,negative_prompt=NEGATIVE,conditions=conditions,seed=seed,settings=SETTINGS,
                runtime=dict(device=device,python=platform.python_version(),platform=platform.system(),
                             packages={n:version(n) for n in ('torch','torchvision','diffusers','transformers','open_clip_torch','cairosvg','Pillow','numpy','safetensors','accelerate')}),
                candidates=records,elapsed_seconds=time.perf_counter()-started,sample_generated=True,design_approved=False,effect_measured=False,
                requested_dimensions_mm=source['dimensions_mm'],dimensions_verified=False,
                unsupported=['unrestricted artwork semantics','calibrated class probability','guaranteed condition satisfaction',
                             'AI-generated 3D','sewing pattern and BOM','fabric physics','manufacturing and business effects'],
                reproduction='Same-device seed/settings recorded; byte identity across hardware/library versions is not guaranteed.')
    for name,data in [('input.json',source),('analysis.json',analysis),('models.json',models),('report.json',report)]:
        (out/name).write_bytes(serialized(data))
    files=[]
    for p in sorted(out.iterdir()):files.append(dict(file=p.name,bytes=p.stat().st_size,sha256=digest(p.read_bytes())))
    manifest=dict(schema_version='aurora-ai-artifacts-v1',source_checksum=source['checksum'],files=files)
    raw=serialized(manifest);(out/'artifacts.json').write_bytes(raw)
    result=dict(report=report,artifacts=files+[dict(file='artifacts.json',bytes=len(raw),sha256=digest(raw))])
    (out/'result.json').write_bytes(serialized(result));return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--job',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    body=json.loads(a.job.read_text())
    require(body['engine_sha256']==engine_hash() and body['settings']==SETTINGS,'AI 코드/설정이 변경됐습니다.')
    require(body['manifest_sha256']==digest((a.root/'configs/ai/model-manifest.json').read_bytes()),'AI 모델 명세가 변경됐습니다.')
    require(body['runtime_config_sha256']==digest(serialized(runtime(a.root))),'AI 로컬 설정이 변경됐습니다.')
    generate(a.root,body['source'],body['seed'],a.output)

if __name__=='__main__':main()
