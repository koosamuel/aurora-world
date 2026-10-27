import copy
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from aurora import sampling as s

ROOT=Path(__file__).resolve().parents[1]


class SamplingTests(unittest.TestCase):
    def setUp(self):self.p=s.load(ROOT/'configs/examples/sampling/01-bunny-v1.json')
    def revision(self,p=None):
        p=copy.deepcopy(p or self.p);parent=s.checksum(p);p.update(brief_version=p['brief_version']+1,previous_checksum=parent);return p
    def rehash(self,p):p['artwork']['sha256']=sha256(p['artwork']['svg'].encode()).hexdigest()

    def test_catalog_all_versions_and_measured_vs_unmeasured(self):
        rows=[s.load(p) for p in sorted((ROOT/'configs/examples/sampling').glob('*.json'))]
        self.assertEqual(len(rows),12);self.assertEqual(len({p['product_id'] for p in rows}),6)
        for p in rows:
            a=s.summary(p);self.assertFalse(a['effect_measured']);self.assertFalse(a['sample_generated']);self.assertFalse(a['design_approved'])
        unknown=next(p for p in rows if p['baseline']['status']=='unmeasured');self.assertIsNone(s.summary(unknown)['physical_sample_count'])
        b=s.summary(self.p);self.assertEqual(b['physical_sample_count'],3);self.assertEqual(b['physical_event_count'],2);self.assertEqual(b['elapsed_hours'],336);self.assertEqual(b['bom_error_corrections'],1);self.assertEqual(b['bom_design_changes'],1)

    def test_units_and_true_zero_are_distinct_from_unknown(self):
        p=self.p;p['requirements']['dimensions'].update(height=14,width=11,depth=9,unit='cm');self.assertEqual(s.summary(p)['dimensions_mm'],dict(height='140',width='110',depth='90'))
        p['baseline']['physical_samples']=[];p['baseline']['bom_changes']=[];a=s.summary(p);self.assertEqual(a['physical_sample_count'],0);self.assertEqual(a['bom_error_corrections'],0)

    def test_required_types_ranges_unknown_fields(self):
        variants=[]
        for field,value in [('brief_version',True),('data_kind','company'),('previous_checksum','bad'),('product_id','../../private')]:
            p=copy.deepcopy(self.p);p[field]=value;variants.append(p)
        for value in [0,-1,True,float('inf'),float('nan'),10**400]:
            p=copy.deepcopy(self.p);p['requirements']['dimensions']['height']=value;variants.append(p)
        p=copy.deepcopy(self.p);p['requirements']['dimensions']['unit']='inch';variants.append(p)
        p=copy.deepcopy(self.p);p['rights']['company_data']=True;variants.append(p)
        p=copy.deepcopy(self.p);p['unknown']='x';variants.append(p)
        p=copy.deepcopy(self.p);p['requirements']['fabric'].pop('code');variants.append(p)
        for p in variants:
            with self.subTest(p=p['product_id']),self.assertRaises(ValueError):s.validate(p)

    def test_colors_and_conditions(self):
        for change in ['duplicate-color','bad-color','empty-condition','duplicate-condition']:
            p=copy.deepcopy(self.p)
            if change=='duplicate-color':p['requirements']['colors']*=2
            elif change=='bad-color':p['requirements']['colors'][0]['hex']='red'
            elif change=='empty-condition':p['requirements']['must_have']=[]
            else:p['requirements']['must_have']*=2
            with self.subTest(change=change),self.assertRaises(ValueError):s.validate(p)

    def test_baseline_event_duplicates_periods_and_reasons(self):
        for change in ['duplicate','outside','reversed','unknown-reason','unmeasured-with-events','timezone','zero-quantity']:
            p=copy.deepcopy(self.p);b=p['baseline']
            if change=='duplicate':b['bom_changes'][0]['event_id']=b['physical_samples'][0]['event_id']
            elif change=='outside':b['physical_samples'][0]['occurred_at']='2026-10-01T00:00:00Z'
            elif change=='reversed':b['ended_at']='2026-08-01T00:00:00Z'
            elif change=='unknown-reason':b['bom_changes'][0]['reason']='unknown'
            elif change=='unmeasured-with-events':b['status']='unmeasured'
            elif change=='timezone':b['started_at']='2026-09-01T09:00:00'
            else:b['physical_samples'][0]['quantity']=0
            with self.subTest(change=change),self.assertRaises(ValueError):s.validate(p)

    def test_artwork_hash_and_filename_bounds(self):
        for field,value in [('sha256','0'*64),('file_name','../bad.svg'),('media_type','text/html'),('width_mm',211)]:
            p=copy.deepcopy(self.p);p['artwork'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):s.validate(p)

    def test_active_svg_and_malformed_paths_are_rejected(self):
        for fragment in ['<script>alert(1)</script>','<image href="https://example.com/x"/>','<foreignObject/>','<circle cx="2" cy="2" r="1" onload="alert(1)"/>','<path d="Z"/>','<path d="M 1"/>','<path d="M 1 1 A 1 1 0 5 0 1 1"/>']:
            p=copy.deepcopy(self.p);p['artwork']['svg']=p['artwork']['svg'].replace('</svg>',fragment+'</svg>');self.rehash(p)
            with self.subTest(fragment=fragment),self.assertRaises(ValueError):s.validate(p)
        p=copy.deepcopy(self.p);p['artwork']['svg']='<!DOCTYPE svg [<!ENTITY x "x">]>'+p['artwork']['svg'];self.rehash(p)
        with self.assertRaises(ValueError):s.validate(p)

    def test_decoder_duplicates_nonfinite_invalid_utf8_and_size(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff',b'x'*(s.MAX_BYTES+1)]:
            with self.assertRaises(ValueError):s.decode(raw)

    def test_immutable_registration_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'brief.sqlite3';store=s.BriefStore(path);a=store.register(self.p);self.assertFalse(a['reused']);self.assertTrue(store.register(self.p)['reused'])
            changed=copy.deepcopy(self.p);changed['product_name']='changed'
            with self.assertRaises(s.Conflict):store.register(changed)
            new=self.revision();new['requirements']['dimensions']['height']+=10;store.register(new)
            self.assertEqual(s.BriefStore(path).get(self.p['product_id'],1)['checksum'],a['checksum']);self.assertEqual(len(store.list()),2)

    def test_parent_and_artwork_version_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=s.BriefStore(Path(tmp)/'s.db');store.register(self.p)
            for change in ['wrong-parent','skip','unchanged-art-version','changed-art-no-version']:
                p=self.revision()
                if change=='wrong-parent':p['previous_checksum']='0'*64
                elif change=='skip':p['brief_version']=3
                elif change=='unchanged-art-version':p['artwork_version']=2
                else:p['artwork']['svg']=p['artwork']['svg'].replace('#E8D9BB','#E8D9BC');self.rehash(p)
                with self.subTest(change=change),self.assertRaises(s.Conflict):store.register(p)
            p=self.revision();p['artwork']['svg']=p['artwork']['svg'].replace('#E8D9BB','#E8D9BC');self.rehash(p);p['artwork_version']=2;store.register(p)

    def test_concurrent_revisions_only_one_can_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=s.BriefStore(Path(tmp)/'s.db');store.register(self.p);a=self.revision();b=copy.deepcopy(a);b['product_name']='other'
            def put(p):
                try:store.register(p);return 'ok'
                except s.Conflict:return 'conflict'
            with ThreadPoolExecutor(2) as pool:self.assertEqual(sorted(pool.map(put,[a,b])),['conflict','ok'])

    def test_seed_repeat_and_cli_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=s.BriefStore(Path(tmp)/'s.db');s.seed(store,ROOT);s.seed(store,ROOT);self.assertEqual(len(store.list()),12)
            out=Path(tmp)/'output';p=subprocess.run([sys.executable,'-m','aurora','sampling','--input',str(ROOT/'configs/examples/sampling/01-bunny-v1.json'),'--output',str(out)],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
            for f in json.loads((out/'artifacts.json').read_text())['files']:self.assertEqual(sha256((out/f['file']).read_bytes()).hexdigest(),f['sha256'])
            with self.assertRaises(FileExistsError):s.export(self.p,out)

if __name__=='__main__':unittest.main()
