# Experimental evaluation only. Changes design; not the production default.
import os,json,gc,time
from pathlib import Path
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
import torch
from PIL import Image,ImageOps,ImageStat
from diffusers import StableDiffusionImg2ImgPipeline,DDIMScheduler
import argparse
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--input',type=Path,required=True);a=p.parse_args();r=a.root;c=json.loads((r/'.ai-local.json').read_text());t=time.perf_counter()
im=Image.open(a.input).convert('RGB');im=ImageOps.contain(im,(512,512));bg=Image.new('RGB',(512,512),'white');bg.paste(im,((512-im.width)//2,(512-im.height)//2))
pipe=StableDiffusionImg2ImgPipeline.from_pretrained(c['sd15'],local_files_only=True,dtype=torch.float16,use_safetensors=True);assert pipe.safety_checker is not None
pipe.scheduler=DDIMScheduler.from_config(pipe.scheduler.config);pipe.to('mps');pipe.enable_attention_slicing()
prompt='studio product photograph of a single cute white plush rabbit toy, full body, standing, long floppy ears, round head, short arms, long soft feet, three quarter view, soft fabric, solid three dimensional volume, ambient occlusion, soft studio lighting, plain white background'
negative='drawing, sketch, pencil, illustration, text, logo, watermark, people, hands, multiple objects, cropped, flat paper, extra limbs'
result=pipe(prompt=prompt,negative_prompt=negative,image=bg,strength=.55,num_inference_steps=30,guidance_scale=7.5,generator=torch.Generator(device='cpu').manual_seed(42))
assert result.nsfw_content_detected is not None and not any(result.nsfw_content_detected),'Safety checker rejected'
assert max(ImageStat.Stat(result.images[0]).stddev)>2
p=r/'results/learned3d-evaluation';result.images[0].save(p/'iteration3-conditioned.png');(p/'iteration3-condition-report.json').write_text(json.dumps(dict(prompt=prompt,negative_prompt=negative,strength=.55,steps=30,seed=42,safety_flagged=False,seconds=time.perf_counter()-t),indent=2));print('conditioning complete')
