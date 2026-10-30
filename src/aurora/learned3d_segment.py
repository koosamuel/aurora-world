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
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();segment(a.input,a.output)
