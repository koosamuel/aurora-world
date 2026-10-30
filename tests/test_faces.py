import json,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np,trimesh
from PIL import Image
from aurora.face_edit import DEFAULT_SETTINGS,presets,validate,generate
from aurora.faces import FaceService,decode
from aurora.learned3d_worker import sha

def planes():
 return trimesh.Trimesh(vertices=[[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1]],faces=[[0,1,2],[0,2,3],[4,5,6],[4,6,7]],process=False)
class GeometryTests(unittest.TestCase):
 def test_settings_and_anchors_strict(self):
  a=presets()['BUNNY']['anchors'];validate(a,DEFAULT_SETTINGS)
  for options in [DEFAULT_SETTINGS|dict(eye_size=True),DEFAULT_SETTINGS|dict(eye_size=float('nan')),DEFAULT_SETTINGS|dict(mouth_radius=.1),DEFAULT_SETTINGS|dict(style='free'),DEFAULT_SETTINGS|dict(eyes_enabled=1),DEFAULT_SETTINGS|dict(eyes_enabled=False,nose_enabled=False,mouth_enabled=False)]:
   with self.assertRaises(ValueError):validate(a,options)
  for anchors in [{},a|dict(nose=[1,2,3]),a|dict(nose=[True,0,0]),a|dict(nose=[0,float('inf'),0])]:
   with self.assertRaises(ValueError):validate(anchors,DEFAULT_SETTINGS)
 def test_saved_face_contains_parts_and_preserves_parent(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);model=d/'base.glb';planes().export(model);Image.new('RGBA',(32,32),'white').save(d/'im.png');before=sha(model);v=presets()['BUNNY'];report=generate(model,d/'im.png',d/'face',v['anchors'],v['settings'],'BUNNY','preset');self.assertEqual(before,sha(model));self.assertTrue(report['original_body_preserved']);self.assertFalse(report['geometry_preserved']);self.assertFalse(report['single_fused_mesh']);self.assertEqual(set(report['added_parts']),{'face_eye_left','face_eye_right','face_nose','face_mouth'});scene=trimesh.load(d/'face/face.glb',force='scene',process=False);self.assertIn('face_mouth',scene.geometry)
   for part in report['placements'].values():self.assertAlmostEqual(part['position'][2],1.)
   with self.assertRaises(ValueError):generate(model,d/'im.png',d/'face',v['anchors'],v['settings'],'BUNNY','preset')
 def test_duck_does_not_get_mammal_nose(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);planes().export(d/'base.glb');Image.new('RGBA',(32,32),'white').save(d/'im.png');v=presets()['DUCK'];report=generate(d/'base.glb',d/'im.png',d/'face',v['anchors'],v['settings'],'DUCK','preset');self.assertEqual(report['added_parts'],['face_eye_left','face_eye_right'])
   with self.assertRaises(ValueError):generate(d/'base.glb',d/'im.png',d/'bad',v['anchors'],v['settings']|dict(nose_enabled=True),'DUCK','preset')
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.id='a'*32;self.d=self.root/'jobs'/self.id;self.d.mkdir(parents=True);(self.d/'preview').mkdir();planes().export(self.d/'model.glb');Image.new('RGBA',(64,64),'red').save(self.d/'preview/foreground.png')
        self.parent=dict(id=self.id,status='succeeded',engine='TripoSG-scribble',foreground_confirmed=True,foreground_sha256=sha(self.d/'preview/foreground.png'),source_id='unit:synthetic',source_checksum='b'*64)
        self.l=SimpleNamespace(jobs=self.root/'jobs',get=lambda id:self.parent if id==self.id else None,source=lambda row:None,artifact=lambda id,n:self.d/n,config=lambda:dict(python='/unit/python'))
        self.s=FaceService(self.root,self.l);self.calls=0
        self.mock=patch('aurora.projections.subprocess.run',side_effect=self.worker);self.mock.start();self.addCleanup(self.mock.stop)
    def worker(self,cmd,**kw):
        self.calls+=1;self.assertFalse(kw.get('shell',False));self.assertEqual(kw['timeout'],60)
        generate(Path(cmd[cmd.index('--model')+1]),Path(cmd[cmd.index('--image')+1]),Path(cmd[cmd.index('--output')+1]),json.loads(cmd[cmd.index('--anchors')+1]),json.loads(cmd[cmd.index('--settings')+1]),cmd[cmd.index('--family')+1],cmd[cmd.index('--origin')+1]);return SimpleNamespace(returncode=0)
    def raw(self,**changes):
        return json.dumps(dict(parent_model_sha256=sha(self.d/'model.glb'),source_image_sha256=self.parent['foreground_sha256'],settings=DEFAULT_SETTINGS,anchors=presets()['BUNNY']['anchors'],anchor_origin='preset',face_confirmed=True)|changes).encode()
    def test_confirmation_and_json_guards(self):
        for raw in [b'',b'[]',b'{"a":1,"a":2}',b'null',b'x'*65537,self.raw(face_confirmed=1),self.raw(settings=DEFAULT_SETTINGS|dict(eye_size=True)),self.raw(extra=1),self.raw(parent_model_sha256='../x')]:
            with self.assertRaises(ValueError):decode(raw)
        self.assertEqual(self.calls,0)
    def test_success_idempotent_and_separate_copies(self):
        before=sha(self.d/'model.glb');a=self.s.create(self.id,self.raw());b=self.s.create(self.id,self.raw());self.assertEqual(a['id'],b['id']);self.assertEqual(self.calls,1);self.assertEqual(before,sha(self.d/'model.glb'));self.assertFalse(a['design_approved']);self.assertTrue(self.s.artifact(a['id'],'face.glb').is_file())
        c=self.s.create(self.id,self.raw(settings=DEFAULT_SETTINGS|dict(eye_size=.03)));self.assertNotEqual(a['id'],c['id']);self.assertEqual(self.calls,2)
    def test_only_confirmed_successful_sg(self):
        for k,v in [('status','prepared'),('engine','TripoSR'),('foreground_confirmed',False)]:
            old=self.parent[k];self.parent[k]=v
            with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
            self.parent[k]=old
        with self.assertRaises(ValueError):self.s.create('b'*32,self.raw())
        self.assertEqual(self.calls,0)
    def test_parent_and_image_integrity(self):
        raw=self.raw();(self.d/'model.glb').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.s.create(self.id,raw)
        planes().export(self.d/'model.glb');(self.d/'preview/foreground.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        self.assertEqual(self.calls,0)
    def test_stale_source_rejected(self):
        def stale(_):raise ValueError('stale source')
        self.l.source=stale
        with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        self.assertEqual(self.calls,0)
    def test_capacity_lock(self):
        self.s.lock.acquire()
        with self.assertRaises(RuntimeError):self.s.create(self.id,self.raw())
        self.s.lock.release()
    def test_timeout_releases_and_hides(self):
        with patch('aurora.projections.subprocess.run',side_effect=subprocess.TimeoutExpired('unit',60)):
            with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        self.assertFalse(self.s.lock.locked());row=json.loads(next(self.s.folder.glob('*/state.json')).read_text());self.assertEqual(row['status'],'failed');self.assertIsNone(self.s.artifact(row['id'],'face.glb'))
    def test_worker_failure_no_fallback(self):
        with patch('aurora.projections.subprocess.run',return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        self.assertFalse(self.s.lock.locked())
    def test_artifact_and_duplicate_integrity(self):
        a=self.s.create(self.id,self.raw());self.s.artifact(a['id'],'face.glb').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.s.artifact(a['id'],'face.glb')
        with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        for id,name in [('../x','face.glb'),(a['id'],'worker.log')]:
            with self.assertRaises(ValueError):self.s.artifact(id,name)
    def test_list_keeps_parent_and_does_not_generate(self):
        row=self.s.create(self.id,self.raw());before=self.calls;self.assertEqual([r['id'] for r in self.s.list(self.id)],[row['id']]);self.assertEqual(self.s.list('b'*32),[]);self.assertEqual(before,self.calls)
    def test_restart_fails_inflight(self):
        d=self.s.folder/('c'*32);d.mkdir();self.s.save(d,dict(id='c'*32,status='running'));other=FaceService(self.root,self.l);self.assertEqual(other.get('c'*32)['status'],'failed')
if __name__=='__main__':unittest.main()
