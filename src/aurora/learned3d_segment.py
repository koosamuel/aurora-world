"""Sketch-oriented foreground extraction. Heuristic, inspect condition.png before adoption."""
import argparse,json
from PIL import Image,ImageOps

def segment(input_path,output):
    import numpy as np
    from scipy.ndimage import binary_closing,binary_fill_holes,label
    im=ImageOps.exif_transpose(Image.open(input_path)).convert('RGBA')
    # Honor user-authored transparency; otherwise close faint pencil contours.
    if im.getchannel('A').getextrema()[0]<255:
        im.thumbnail((768,768));im.save(output);return
    im=im.convert('RGB');im.thumbnail((768,768));a=np.array(ImageOps.grayscale(im))
    m=binary_fill_holes(binary_closing(a<242,iterations=5));labels,n=label(m);counts=np.bincount(labels.ravel());counts[0]=0
    if n==0 or not counts.max():raise ValueError('배경에서 분리되는 윤곽이 없습니다.')
    m=labels==counts.argmax()
    if not .04<float(m.mean())<.85:raise ValueError('분리 영역이 부적절합니다. 투명 배경 PNG로 확인해 주세요.')
    rgba=im.convert('RGBA');rgba.putalpha(Image.fromarray((m*255).astype('uint8')));rgba.save(output)
def preflight(input_path,directory):
    import hashlib,numpy as np
    from pathlib import Path
    d=Path(directory);d.mkdir(parents=True,exist_ok=True);segment(input_path,d/'foreground.png')
    foreground=Image.open(d/'foreground.png').convert('RGBA');alpha=foreground.getchannel('A');alpha.save(d/'mask.png')
    white=Image.new('RGBA',foreground.size,'white');white.alpha_composite(foreground)
    ImageOps.pad(white.convert('RGB'),(512,512),color='white').save(d/'preview.png')
    original=ImageOps.exif_transpose(Image.open(input_path)).convert('RGBA');background=Image.new('RGBA',original.size,'white');background.alpha_composite(original)
    gray=np.asarray(ImageOps.grayscale(background.resize(foreground.size)));ink=gray<220;mask=np.asarray(alpha)>127
    coverage=float((ink&mask).sum()/max(1,ink.sum()))
    report=dict(preprocessor='sketch-contour-v2',ink_coverage=coverage,foreground_fraction=float(mask.mean()),
        foreground_bbox=alpha.getbbox(),requires_human_confirmation=True,semantic_completeness_verified=False,
        warnings=['Check both ears, head, torso, arms and legs; segmentation is heuristic, not object understanding.'])
    if coverage<.95:report['warnings'].append('Foreground excludes more than 5% of dark drawing pixels; inspect before continuing.')
    (d/'preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--preflight',action='store_true');a=p.parse_args();preflight(a.input,a.output) if a.preflight else segment(a.input,a.output)
