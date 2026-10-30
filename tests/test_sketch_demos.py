import base64,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw
from aurora import sketch_demos as demo
from aurora.learned3d import Learned3DService
from aurora.learned3d_segment import preflight
class DemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'repo';self.root.mkdir();self.folder=self.root.parent/demo.FOLDER;self.folder.mkdir(parents=True)
        for i,(_,_,_,name) in enumerate(demo.ITEMS):
            im=Image.new('RGB',(96,96),'white');ImageDraw.Draw(im).ellipse((15+i,4,80,90),fill=(100+i*10,)*3);im.save(self.folder/name)
        self.service=Learned3DService(self.root,None);self.config=patch.object(self.service,'config',return_value=dict(engine='TripoSG-scribble',python='/unit/python'));self.config.start();self.addCleanup(self.config.stop)
    def raw(self,id='rabbit',**changes):
        row=next(x for x in demo.catalog(self.root) if x['demo_id']==id);return json.dumps(dict(demo_id=id,source_checksum=row['checksum'],storage_consent=True)|changes).encode()
    def execute(self,cmd,**kw):
        self.assertIn('--preflight',cmd);preflight(cmd[cmd.index('--input')+1],cmd[cmd.index('--output')+1]);return SimpleNamespace(returncode=0)
    def test_four_independent_sources_and_prompts(self):
        rows=demo.catalog(self.root);self.assertEqual(len(rows),4);self.assertEqual(len({x['checksum'] for x in rows}),4)
        for row in rows:self.assertTrue(row['id'].startswith('local-demo:'));self.assertEqual(row['source_kind'],'local_sketch_demo');self.assertEqual(row['prompt'],demo.PROMPTS[row['family']]);self.assertEqual(self.service.source(dict(source_id=row['id'],source_checksum=row['checksum'],dimensions_mm=row['dimensions_mm']))['family'],row['family'])
    def test_prepare_four_only_preflight(self):
        with patch('aurora.learned3d.subprocess.run',side_effect=self.execute) as run:
            for id,_,family,_ in demo.ITEMS:
                row=demo.prepare(self.service,self.raw(id));self.assertEqual(row['family'],family);self.assertEqual(row['source_kind'],'local_sketch_demo');self.assertEqual(row['status'],'prepared');self.assertNotIn('artifacts',row)
            self.assertEqual(run.call_count,4)
    def test_requires_consent_current_hash_and_strict_json(self):
        for raw in [b'',b'x'*65537,b'[]',b'{}',b'{"a":1,"a":2}',self.raw(storage_consent=1),self.raw(storage_consent=False),self.raw(source_checksum='0'*64),self.raw(extra=1)]:
            with self.assertRaises(ValueError):demo.prepare(self.service,raw)
    def test_unknown_paths_and_missing_files(self):
        for id in ['../rabbit','rabbit.jpg','RABBIT','']:
            with self.assertRaises(ValueError):demo.image_path(self.root,id)
        (self.folder/demo.ITEMS[0][3]).unlink();self.assertEqual(len(demo.catalog(self.root)),3)
    def test_modified_file_invalidates_source(self):
        row=demo.catalog(self.root)[0];demo.image_path(self.root,'rabbit').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.service.source(dict(source_id=row['id'],source_checksum=row['checksum'],dimensions_mm=row['dimensions_mm']))
    def test_demo_id_cannot_accept_another_image(self):
        row=demo.catalog(self.root)[0];data=dict(image_base64=base64.b64encode(demo.image_path(self.root,'bear').read_bytes()).decode(),source_id=row['id'],source_checksum=row['checksum'],dimensions_mm=row['dimensions_mm'],view='single')
        with self.assertRaises(ValueError):self.service.request(json.dumps(data).encode())
    def test_sg_only(self):
        with patch.object(self.service,'config',return_value=dict(engine='TripoSR')):
            with self.assertRaises(ValueError):demo.prepare(self.service,self.raw())
    def test_stale_demo_confirmation_and_existing_u20_guard(self):
        with patch('aurora.learned3d.subprocess.run',side_effect=self.execute):row=demo.prepare(self.service,self.raw('bear'))
        demo.image_path(self.root,'bear').write_bytes(b'changed')
        pool=Mock()
        with self.assertRaises(ValueError):self.service.confirm(row['id'],json.dumps(dict(preparation_sha256=row['preparation_sha256'],foreground_confirmed=True)).encode(),pool)
        pool.submit.assert_not_called();self.assertFalse(self.service.lock.locked())
        with patch('aurora.learned3d.catalog',return_value=dict(sources=[dict(id='u20:bear',family='BEAR',data_kind='synthetic')])):
            with self.assertRaises(ValueError):self.service.source(dict(source_id='u20:bear'))
if __name__=='__main__':unittest.main()
