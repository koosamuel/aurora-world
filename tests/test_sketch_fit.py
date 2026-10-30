import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image,ImageDraw
from aurora.sketch_fit import decode,input_mask,model,silhouette,optimize,SketchFitService,PARAMS
from aurora.generation import bounds,parse_glb
DIMS=dict(width=180,height=300,depth=120)
def request(im=None):
    if im is None: im=silhouette(model({k:1. for k in PARAMS},DIMS)).resize((256,256))
    # Bright background with dark foreground, like the supported sketch convention.
    im=im.point(lambda x:255-x)
    b=io.BytesIO();im.save(b,format='PNG')
    return json.dumps(dict(image_base64=base64.b64encode(b.getvalue()).decode(),dimensions_mm=DIMS,view='front')).encode()
class SketchFitTests(unittest.TestCase):
    def test_strict_request(self):
        base=json.loads(request())
        for change in [dict(view='side'),dict(dimensions_mm=dict(width=True,height=300,depth=120)),dict(image_base64='!!!'),dict(extra=3),dict(dimensions_mm=dict(width=0,height=300,depth=120))]:
            with self.assertRaises(ValueError):decode(json.dumps(base|change).encode())
        for raw in [b'[]',b'{"a":1,"a":2}',b'{"x":NaN}',b'x'*(3*1024*1024+1)]:
            with self.assertRaises(ValueError):decode(raw)
    def test_blank_and_unsupported(self):
        for color in ['white','black']:
            im=Image.new('RGB',(128,128),color);raw=decode(request(im.point(lambda x:255-x)))[1]
            with self.assertRaises(ValueError):input_mask(raw)
        b=io.BytesIO();Image.new('RGB',(128,128)).save(b,format='GIF')
        with self.assertRaises(ValueError):input_mask(b.getvalue())
        with self.assertRaises(ValueError):input_mask(b'not an image')
    def test_outline_fill_and_transparency(self):
        im=Image.new('RGBA',(220,220),(0,0,0,0));d=ImageDraw.Draw(im);d.ellipse((40,25,180,200),outline='black',width=3)
        b=io.BytesIO();im.save(b,format='PNG');m=input_mask(b.getvalue());self.assertEqual(m.getpixel((64,64)),255)
    def test_non_degrading_deterministic_and_dimensions(self):
        target=silhouette(model({k:1.2 if k=='ear_spacing' else .82 if k=='body_width' else 1. for k in PARAMS},DIMS))
        a,b,m=optimize(target,DIMS)
        self.assertGreater(m['after_iou'],m['before_iou'])
        self.assertEqual(m,optimize(target,DIMS)[2]);self.assertEqual(sorted(m['history']),m['history'])
        lo,hi=bounds(b)
        for i,k in enumerate(['width','height','depth']):self.assertAlmostEqual((hi[i]-lo[i])*1000,DIMS[k],places=5)
    def test_artifact_integrity_restart_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=SketchFitService(tmp);row=s.run(request());self.assertFalse(row['manufacturing_verified'])
            self.assertEqual(row['depth_source'],'user_assumption_not_reconstructed')
            restarted=SketchFitService(tmp);p=restarted.artifact(row['id'],'after.glb');parse_glb(p.read_bytes())
            for run,name in [('../x','after.glb'),(row['id'],'../input.bin'),(row['id'],'input.bin')]:
                with self.assertRaises(ValueError):s.artifact(run,name)
            p.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):s.artifact(row['id'],'after.glb')
    def test_concurrency_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=SketchFitService(tmp);s.lock.acquire()
            try:
                with self.assertRaises(RuntimeError):s.run(request())
            finally:s.lock.release()
if __name__=='__main__':unittest.main()
