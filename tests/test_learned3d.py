import base64,io,json,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image,ImageDraw
from aurora.learned3d import Learned3DService,confirmation
from aurora.learned3d_segment import preflight,segment
DIMS=dict(width=180,height=300,depth=120)
SOURCE=dict(id='u20:test:2',family='BUNNY',data_kind='synthetic',checksum='a'*64,dimensions_mm=DIMS)
def request(**changes):
    im=Image.new('RGB',(128,128),'white');ImageDraw.Draw(im).ellipse((30,5,100,120),fill='gray');b=io.BytesIO();im.save(b,format='PNG')
    return json.dumps(dict(image_base64=base64.b64encode(b.getvalue()).decode(),dimensions_mm=DIMS,view='single',source_id=SOURCE['id'],source_checksum=SOURCE['checksum'])|changes).encode()
class Pool:
    def __init__(self):self.calls=[]
    def submit(self,*args):self.calls.append(args)
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name);self.s=Learned3DService(self.r,object());self.c=dict(python='/usr/bin/python3',engine='TripoSG-scribble')
        self.p=patch.object(self.s,'config',return_value=self.c);self.p.start();self.addCleanup(self.p.stop)
        self.cat=patch('aurora.learned3d.catalog',return_value=dict(sources=[SOURCE]));self.cat.start();self.addCleanup(self.cat.stop)
        self.sub=patch('aurora.learned3d.subprocess.run',side_effect=self.execute);self.sub.start();self.addCleanup(self.sub.stop)
    def execute(self,command,**kw):
        if '--preflight' in command:
            preflight(command[command.index('--input')+1],command[command.index('--output')+1])
        else:
            self.assertIn('aurora.triposg_worker',command);self.assertEqual(kw['timeout'],1200);self.assertFalse(kw.get('shell',False))
            out=Path(command[command.index('--output')+1]);out.mkdir();(out/'report.json').write_text('{"unit_test_fixture":true}');(out/'model.glb').write_bytes(b'unit fixture, not a mesh');(out/'condition.png').write_bytes(b'unit fixture')
        return SimpleNamespace(returncode=0)
    def confirm(self,row,**changes):
        return json.dumps(dict(preparation_sha256=row['preparation_sha256'],foreground_confirmed=True)|changes).encode()
    def test_preparation_never_infers(self):
        pool=Pool();row=self.s.request(request(),pool);self.assertEqual(row['status'],'prepared');self.assertEqual(pool.calls,[]);self.assertFalse(self.s.lock.locked());self.assertNotIn('artifacts',row)
        self.assertTrue(self.s.artifact(row['id'],'preview.png').exists());self.assertIsNone(self.s.artifact(row['id'],'model.glb'));self.assertFalse(row['preflight']['semantic_completeness_verified'])
    def test_input_validation(self):
        for changes in [dict(source_checksum='b'*64),dict(view='front'),dict(dimensions_mm=DIMS|{'height':400}),dict(image_base64=base64.b64encode(b'bad').decode())]:
            with self.assertRaises(ValueError):self.s.request(request(**changes))
    def test_confirmation_required_and_strict(self):
        row=self.s.request(request());pool=Pool()
        for changes in [dict(foreground_confirmed=False),dict(foreground_confirmed=1),dict(preparation_sha256='0'*64),dict(extra=True)]:
            with self.assertRaises(ValueError):self.s.confirm(row['id'],self.confirm(row,**changes),pool)
        with self.assertRaises(ValueError):confirmation(b'{"foreground_confirmed":true,"foreground_confirmed":false}')
        self.assertEqual(pool.calls,[])
    def test_confirm_queue_idempotent_and_capacity(self):
        a=self.s.request(request());b=self.s.request(request());pool=Pool();row=self.s.confirm(a['id'],self.confirm(a),pool);self.assertEqual(row['status'],'queued');self.assertTrue(row['foreground_confirmed']);self.assertEqual(len(pool.calls),1)
        self.s.confirm(a['id'],self.confirm(a),pool);self.assertEqual(len(pool.calls),1)
        with self.assertRaises(RuntimeError):self.s.confirm(b['id'],self.confirm(b),pool)
        self.s.lock.release()
    def test_stale_brief_after_preview(self):
        row=self.s.request(request())
        with patch('aurora.learned3d.catalog',return_value=dict(sources=[SOURCE|dict(checksum='b'*64)])):
            with self.assertRaises(ValueError):self.s.confirm(row['id'],self.confirm(row),Pool())
        self.assertFalse(self.s.lock.locked())
    def test_prepared_input_corruption(self):
        row=self.s.request(request());(self.s.jobs/row['id']/'preview/foreground.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.s.confirm(row['id'],self.confirm(row),Pool())
        self.assertFalse(self.s.lock.locked())
    def test_preview_corruption(self):
        row=self.s.request(request());p=self.s.artifact(row['id'],'preview.png');p.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.s.artifact(row['id'],'preview.png')
        with self.assertRaises(ValueError):self.s.confirm(row['id'],self.confirm(row),Pool())
    def test_worker_success_and_artifact_integrity(self):
        row=self.s.request(request());pool=Pool();self.s.confirm(row['id'],self.confirm(row),pool);pool.calls[0][0](*pool.calls[0][1:]);done=self.s.get(row['id']);self.assertEqual(done['status'],'succeeded');self.assertEqual(done['report']['original_input_sha256'],row['input_sha256']);self.assertTrue(done['report']['foreground_confirmed']);p=self.s.artifact(row['id'],'model.glb');self.assertTrue(p.exists());p.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.s.artifact(row['id'],'model.glb')
        for id,name in [('../x','model.glb'),(row['id'],'input.png'),(row['id'],'foreground.png')]:
            with self.assertRaises(ValueError):self.s.artifact(id,name)
    def test_failure_no_fallback(self):
        row=self.s.request(request());pool=Pool();self.s.confirm(row['id'],self.confirm(row),pool)
        with patch('aurora.learned3d.subprocess.run',return_value=SimpleNamespace(returncode=1)):pool.calls[0][0](*pool.calls[0][1:])
        self.assertEqual(self.s.get(row['id'])['status'],'failed');self.assertFalse(self.s.lock.locked());self.assertIsNone(self.s.artifact(row['id'],'model.glb'))
    def test_restart_preserves_prepared_fails_queued(self):
        a=self.s.request(request());b=self.s.request(request());self.s.confirm(b['id'],self.confirm(b),Pool());s=Learned3DService(self.r,object());self.assertEqual(s.get(a['id'])['status'],'prepared');self.assertEqual(s.get(b['id'])['status'],'failed');self.s.lock.release()
    def test_preflight_timeout_releases_lock(self):
        with patch('aurora.learned3d.subprocess.run',side_effect=subprocess.TimeoutExpired('preflight',60)):
            with self.assertRaises(ValueError):self.s.request(request())
        self.assertFalse(self.s.lock.locked())
    def test_missing_models(self):
        self.p.stop();self.assertFalse(self.s.capabilities()['available'])
    def test_mask_and_empty_input(self):
        p=self.r/'in.png';q=self.r/'out.png';im=Image.new('RGB',(128,128),'white');ImageDraw.Draw(im).ellipse((30,5,100,120),outline=(170,170,170),width=2);im.save(p);segment(p,q)
        with Image.open(q) as got:self.assertEqual(got.getpixel((64,64))[3],255);self.assertEqual(got.getpixel((0,0))[3],0)
        Image.new('RGB',(128,128),'white').save(p)
        with self.assertRaises(ValueError):segment(p,q)
if __name__=='__main__':unittest.main()
