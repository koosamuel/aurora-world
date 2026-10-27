import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from aurora import identity as i

ROOT=Path(__file__).resolve().parents[1]


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.p=i.load(ROOT/'configs/examples/identity-valid.json')

    def test_scopes_aliases_leading_zero_and_trace(self):
        a=i.audit(self.p)
        self.assertTrue(a['ready_for_downstream'])
        self.assertEqual([r['canonical_product_id'] for r in a['accepted'][:3]],['P001','P001','P002'])
        self.assertEqual(a['accepted'][0]['source_code'],'0012')
        self.assertEqual(a['accepted'][0]['mapping_id'],'m1')
        self.assertTrue(all(t['preserved'] for t in a['quantity_audit']))

    def test_exclusive_validity_and_known_at(self):
        p=self.p;p['records']=p['records'][:1];m=p['mappings'][0];m['valid_to']='2026-09-07'
        self.assertEqual(i.audit(p)['quarantine'][0]['reason'],'no_effective_mapping')
        later=copy.deepcopy(m);later.update(mapping_id='new',canonical_product_id='NEW',valid_from='2026-09-07',valid_to=None,known_at='2026-10-01');p['mappings'].append(later)
        self.assertEqual(i.audit(p)['quarantine'][0]['reason'],'mapping_not_yet_known')
        later['known_at']='2026-09-30';a=i.audit(p)
        self.assertTrue(a['ready_for_downstream']);self.assertEqual(a['accepted'][0]['canonical_product_id'],'NEW')

    def test_overlap_even_if_no_record_references_it(self):
        p=self.p;m=copy.deepcopy(p['mappings'][0]);m.update(mapping_id='other',source_code='BEAR-A');p['mappings'].append(m)
        p['records']=p['records'][:1]
        a=i.audit(p);self.assertFalse(a['ready_for_downstream']);self.assertEqual(a['counts']['mapping_issues'],1)
        m['known_at']='2026-10-01';self.assertTrue(i.audit(p)['ready_for_downstream'])

    def test_conflicts_quarantine_but_preserve_quantity(self):
        a=i.demo(ROOT,'conflicts')
        self.assertEqual(a['counts'],dict(source=12,accepted=4,quarantined=8,mapping_issues=1))
        self.assertEqual(a['quarantine_reasons'],dict(ambiguous_approved_mapping=1,duplicate_canonical_snapshot=2,duplicate_source_record=2,mapping_not_approved=1,mapping_not_yet_known=1,unmapped_code=1))
        self.assertTrue(all(t['preserved'] for t in a['quantity_audit']))

    def test_rejected_and_future_records(self):
        p=self.p;p['records']=p['records'][:1];p['mappings'][0]['approval_status']='rejected'
        self.assertEqual(i.audit(p)['quarantine'][0]['reason'],'mapping_not_approved')
        p['records'][0]['event_date']='2026-10-01'
        self.assertEqual(i.audit(p)['quarantine'][0]['reason'],'future_record')

    def test_snapshot_locations_and_dates_not_pooled(self):
        p=self.p;r=copy.deepcopy(p['records'][3]);r.update(row_id='stock-b',record_key='other',location_id='WH-B');p['records'].append(r)
        self.assertTrue(i.audit(p)['ready_for_downstream'])
        r['location_id']='WH-A';self.assertEqual(i.audit(p)['quarantine_reasons']['duplicate_canonical_snapshot'],2)
        r['event_date']='2026-09-08';self.assertTrue(i.audit(p)['ready_for_downstream'])

    def test_decimal_groups(self):
        p=self.p;p['records']=p['records'][:2]
        for r,q in zip(p['records'],[0.1,0.2]):r['quantity']=q
        a=i.audit(p);self.assertEqual(a['quantity_audit'][0]['source_quantity'],'0.3')
        r=copy.deepcopy(p['records'][0]);r.update(row_id='kg',record_key='kg',unit='kg',quantity=200);p['records'].append(r)
        self.assertEqual(len(i.audit(p)['quantity_audit']),2)

    def test_malformed_contracts(self):
        for field,value in [('quantity',True),('quantity',float('nan')),('quantity',float('inf')),('event_date','2026-02-30'),('source_code',12),('source_code',' 0012')]:
            p=copy.deepcopy(self.p);p['records'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):i.audit(p)
        p=copy.deepcopy(self.p);p['mappings'][0]['approved_by']=None
        with self.assertRaises(ValueError):i.audit(p)
        p=copy.deepcopy(self.p);p['records'][1]['row_id']='row-1'
        with self.assertRaises(ValueError):i.audit(p)
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'x'*(i.MAX_BYTES+1)]:
            with self.assertRaises(ValueError):i.decode(raw)
        with self.assertRaises(ValueError):i.demo(ROOT,'../../private')

    def test_unknown_fields_are_not_ignored(self):
        self.p['records'][0]['name']='bear'
        with self.assertRaises(ValueError):i.audit(self.p)

    def test_export_is_reproducible_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a';b=Path(tmp)/'b';i.export(self.p,a);i.export(self.p,b)
            self.assertEqual((a/'artifacts.json').read_bytes(),(b/'artifacts.json').read_bytes())
            for f in json.loads((a/'artifacts.json').read_bytes())['files']:
                self.assertEqual(hashlib.sha256((a/f['file']).read_bytes()).hexdigest(),f['sha256'])
            with self.assertRaises(FileExistsError):i.export(self.p,a)

    def test_cli_returns_failure_with_retained_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case,code in [('valid',0),('conflicts',2)]:
                output=Path(tmp)/case
                p=subprocess.run([sys.executable,'-m','aurora','identity','--input',str(ROOT/'configs/examples'/f'identity-{case}.json'),'--output',str(output)],capture_output=True,text=True)
                self.assertEqual(p.returncode,code,p.stderr);self.assertTrue((output/'audit.json').exists())

if __name__=='__main__':unittest.main()
