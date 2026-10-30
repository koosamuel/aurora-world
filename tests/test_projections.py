import json,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import trimesh
from PIL import Image
from aurora.sketch_projection import DEFAULT,settings,transfer,generate
from aurora.projections import ProjectionService,decode
from aurora.learned3d_worker import sha

def planes():
    return trimesh.Trimesh(vertices=[[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1],[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1]],faces=[[0,1,2],[0,2,3],[4,5,6],[4,6,7]],process=False)
class MathTests(unittest.TestCase):
    def test_settings_strict(self):
        self.assertEqual(settings(DEFAULT),DEFAULT)
        for x in [None,{},DEFAULT|dict(extra=1),DEFAULT|dict(yaw=True),DEFAULT|dict(yaw=float('nan')),DEFAULT|dict(scale=float('inf')),DEFAULT|dict(offset_y=.16),DEFAULT|dict(scale=.7),DEFAULT|dict(yaw=46)]:
            with self.assertRaises(ValueError):settings(x)
    def test_only_front_visible_surface_painted(self):
        mesh=planes();before=mesh.vertices.copy();colors,metrics=transfer(mesh,Image.new('RGBA',(64,64),(30,60,90,255)),DEFAULT)
        self.assertEqual(metrics['projected_vertices'],4);np.testing.assert_array_equal(colors[:4,:3],np.tile([30,60,90],(4,1)));np.testing.assert_array_equal(colors[4:],np.tile([225,220,210,255],(4,1)));np.testing.assert_array_equal(before,mesh.vertices)
    def test_empty_alpha_and_degenerate(self):
        with self.assertRaises(ValueError):transfer(planes(),Image.new('RGBA',(32,32)),DEFAULT)
        mesh=planes();mesh.vertices[:,0]=0
        with self.assertRaises(ValueError):transfer(mesh,Image.new('RGBA',(32,32),'red'),DEFAULT)
    def test_export_preserves_original_geometry_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);model=d/'input.glb';planes().export(model);Image.new('RGBA',(64,64),'red').save(d/'in.png');before=sha(model)
            report=generate(model,d/'in.png',d/'copy',DEFAULT);self.assertEqual(before,sha(model));self.assertTrue(report['geometry_preserved']);self.assertFalse(report['learned_texture']);self.assertFalse(report['backside_textured']);self.assertEqual(report['parent_model_sha256'],before)
            with self.assertRaises(ValueError):generate(model,d/'in.png',d/'copy',DEFAULT)
class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.id='a'*32;self.d=self.root/'jobs'/self.id;self.d.mkdir(parents=True);(self.d/'preview').mkdir();planes().export(self.d/'model.glb');Image.new('RGBA',(64,64),'red').save(self.d/'preview/foreground.png')
        self.parent=dict(id=self.id,status='succeeded',engine='TripoSG-scribble',foreground_confirmed=True,foreground_sha256=sha(self.d/'preview/foreground.png'),source_id='unit:synthetic',source_checksum='b'*64)
        self.l=SimpleNamespace(jobs=self.root/'jobs',get=lambda id:self.parent if id==self.id else None,source=lambda row:None,artifact=lambda id,n:self.d/n,config=lambda:dict(python='/unit/python'))
        self.s=ProjectionService(self.root,self.l);self.calls=0
        self.mock=patch('aurora.projections.subprocess.run',side_effect=self.worker);self.mock.start();self.addCleanup(self.mock.stop)
    def worker(self,cmd,**kw):
        self.calls+=1;self.assertFalse(kw.get('shell',False));self.assertEqual(kw['timeout'],60)
        generate(Path(cmd[cmd.index('--model')+1]),Path(cmd[cmd.index('--image')+1]),Path(cmd[cmd.index('--output')+1]),json.loads(cmd[cmd.index('--settings')+1]));return SimpleNamespace(returncode=0)
    def raw(self,**changes):
        return json.dumps(dict(parent_model_sha256=sha(self.d/'model.glb'),source_image_sha256=self.parent['foreground_sha256'],settings=DEFAULT,projection_confirmed=True)|changes).encode()
    def test_confirmation_and_json_guards(self):
        for raw in [b'',b'[]',b'{"a":1,"a":2}',b'null',b'x'*65537,self.raw(projection_confirmed=1),self.raw(settings=DEFAULT|dict(yaw=True)),self.raw(extra=1),self.raw(parent_model_sha256='../x')]:
            with self.assertRaises(ValueError):decode(raw)
        self.assertEqual(self.calls,0)
    def test_success_idempotent_and_separate_copies(self):
        before=sha(self.d/'model.glb');a=self.s.create(self.id,self.raw());b=self.s.create(self.id,self.raw());self.assertEqual(a['id'],b['id']);self.assertEqual(self.calls,1);self.assertEqual(before,sha(self.d/'model.glb'));self.assertFalse(a['design_approved']);self.assertTrue(self.s.artifact(a['id'],'projected.glb').is_file())
        c=self.s.create(self.id,self.raw(settings=DEFAULT|dict(yaw=5)));self.assertNotEqual(a['id'],c['id']);self.assertEqual(self.calls,2)
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
        self.assertFalse(self.s.lock.locked());row=json.loads(next(self.s.folder.glob('*/state.json')).read_text());self.assertEqual(row['status'],'failed');self.assertIsNone(self.s.artifact(row['id'],'projected.glb'))
    def test_worker_failure_no_fallback(self):
        with patch('aurora.projections.subprocess.run',return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        self.assertFalse(self.s.lock.locked())
    def test_artifact_and_duplicate_integrity(self):
        a=self.s.create(self.id,self.raw());self.s.artifact(a['id'],'projected.glb').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.s.artifact(a['id'],'projected.glb')
        with self.assertRaises(ValueError):self.s.create(self.id,self.raw())
        for id,name in [('../x','projected.glb'),(a['id'],'worker.log')]:
            with self.assertRaises(ValueError):self.s.artifact(id,name)
    def test_restart_fails_inflight(self):
        d=self.s.folder/('c'*32);d.mkdir();self.s.save(d,dict(id='c'*32,status='running'));other=ProjectionService(self.root,self.l);self.assertEqual(other.get('c'*32)['status'],'failed')
if __name__=='__main__':unittest.main()
