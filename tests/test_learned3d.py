import base64,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image,ImageDraw
from aurora.learned3d import Learned3DService,sha
DIMS=dict(width=180,height=300,depth=120)
SOURCE=dict(id='u20:test:2',family='BUNNY',data_kind='synthetic',checksum='a'*64,dimensions_mm=DIMS)
def request(**changes):
    im=Image.new('RGB',(128,128),'white');ImageDraw.Draw(im).ellipse((30,5,100,120),fill='gray');b=io.BytesIO();im.save(b,format='PNG')
    return json.dumps(dict(image_base64=base64.b64encode(b.getvalue()).decode(),dimensions_mm=DIMS,view='single',source_id=SOURCE['id'],source_checksum=SOURCE['checksum'])|changes).encode()
class Pool:
    def submit(self,*args):self.args=args
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name);self.s=Learned3DService(self.r,object());self.c=dict(python='/usr/bin/python3')
        self.p=patch.object(self.s,'config',return_value=self.c);self.p.start();self.addCleanup(self.p.stop)
        self.cat=patch('aurora.learned3d.catalog',return_value=dict(sources=[SOURCE]));self.cat.start();self.addCleanup(self.cat.stop)
    def test_validation_and_queue(self):
        for changes in [dict(source_checksum='b'*64),dict(view='front'),dict(dimensions_mm=DIMS|{'height':400}),dict(image_base64=base64.b64encode(b'bad').decode())]:
            with self.assertRaises(ValueError):self.s.request(request(**changes),Pool())
        pool=Pool();row=self.s.request(request(),pool);self.assertEqual(self.s.get(row['id'])['status'],'queued');self.assertEqual(pool.args[0],self.s.work)
        with self.assertRaises(RuntimeError):self.s.request(request(),Pool())
        self.s.lock.release()
    def test_worker_failure_and_restart(self):
        row=self.s.request(request(),Pool());d=self.s.jobs/row['id']
        with patch('aurora.learned3d.subprocess.run',return_value=SimpleNamespace(returncode=1)):
            self.s.work(d,row,self.c)
        self.assertEqual(self.s.get(row['id'])['status'],'failed');self.assertFalse(self.s.lock.locked())
        row=self.s.request(request(),Pool());restarted=Learned3DService(self.r,object());self.assertEqual(restarted.get(row['id'])['status'],'failed');self.s.lock.release()
    def test_success_and_integrity_allowlist(self):
        row=self.s.request(request(),Pool());d=self.s.jobs/row['id']
        def run(*args,**kw):
            out=d/'output';out.mkdir(exist_ok=True);(out/'report.json').write_text('{}');(out/'model.glb').write_bytes(b'unit test fixture, not a real mesh');(out/'condition.png').write_bytes(b'unit test fixture')
            self.assertFalse(kw.get('shell',False));self.assertEqual(kw['timeout'],1200);return SimpleNamespace(returncode=0)
        with patch('aurora.learned3d.subprocess.run',side_effect=run):self.s.work(d,row,self.c)
        self.assertEqual(self.s.get(row['id'])['status'],'succeeded');p=self.s.artifact(row['id'],'model.glb');self.assertTrue(p.exists())
        for id,name in [('../x','model.glb'),(row['id'],'input.png'),(row['id'],'../state.json')]:
            with self.assertRaises(ValueError):self.s.artifact(id,name)
        p.write_bytes(b'corruption')
        with self.assertRaises(ValueError):self.s.artifact(row['id'],'model.glb')
    def test_missing_models_disable(self):
        self.p.stop();self.assertFalse(self.s.capabilities()['available'])
    def test_sketch_preprocessor(self):
        from aurora.learned3d_segment import segment
        p=self.r/'in.png';q=self.r/'out.png';im=Image.new('RGB',(128,128),'white');ImageDraw.Draw(im).ellipse((30,5,100,120),outline=(170,170,170),width=2);im.save(p);segment(p,q)
        with Image.open(q) as got:self.assertEqual(got.getpixel((64,64))[3],255);self.assertEqual(got.getpixel((0,0))[3],0)
        Image.new('RGB',(128,128),'white').save(p)
        with self.assertRaises(ValueError):segment(p,q)
if __name__=='__main__':unittest.main()
