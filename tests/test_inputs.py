import copy,hashlib,json,unittest
from datetime import date,timedelta
from aurora.inputs import validate,encode,decode,run_input
from aurora.registered import provision,read_registered,RemoteError

def fixture():
    return dict(schema_version='aurora-weekly-input-v1',synthetic=True,version='test-weekly-v1',target='observed_gross_shipments',unit='each',currency='KRW',org_id='TEST-ORG',warehouse_id='TEST-WH',periods=[(date(2024,1,1)+timedelta(weeks=t)).isoformat() for t in range(60)],series=[dict(sku='X-1',pattern='synthetic test',values=[2]*60,statuses=['observed']*60,stockouts=[False]*60,returns=[0]*60,unit_cost_krw=800)],source=dict(manifest_sha256='a'*64,generator_sha256='b'*64))

PROJECT='10000000-0000-4000-8000-000000000001'
class FakeRemote:
    def __init__(self):self.row=None;self.object=None;self.statuses=[];self.corrupt=False
    def request(self,path,method='GET',body=None,data=None,raw=False):
        if path.startswith('/rest/v1/projects'):return [dict(id=PROJECT,project_type='forecast')]
        if path.startswith('/rest/v1/datasets'):
            if method=='GET':return [self.row] if self.row else []
            if method=='POST':self.row=body.copy();self.statuses.append(body['status']);return None
            if method=='PATCH':self.row.update(body);self.statuses.append(body['status']);return None
        if path.startswith('/storage/v1/object/'):
            if method=='POST':
                if self.object is not None:raise RemoteError(409)
                self.object=data;return {}
            return self.object+b'corrupt' if self.corrupt else self.object
        raise AssertionError(path)

class InputTests(unittest.TestCase):
    def test_grid_status_units_duplicates_numbers(self):
        def changed(fn):
            p=fixture();fn(p)
            with self.assertRaises(ValueError):validate(p)
        for fn in [lambda p:p['series'].append(copy.deepcopy(p['series'][0])),lambda p:p.update(unit='kg'),lambda p:p.update(currency='USD'),lambda p:p['periods'].__setitem__(1,p['periods'][0]),lambda p:p['series'][0]['values'].__setitem__(0,True),lambda p:p['series'][0]['values'].__setitem__(0,float('inf')),lambda p:p['series'][0]['values'].__setitem__(0,-1),lambda p:p['series'][0]['values'].pop(),lambda p:p['series'][0]['statuses'].__setitem__(0,'missing'),lambda p:p.update(synthetic=False)]:changed(fn)
    def test_missing_zero_returns_remain_distinct(self):
        p=fixture();r=p['series'][0];r['values'][0]=None;r['statuses'][0]='missing';r['returns'][0]=None;r['values'][1]=0;r['returns'][2]=1;r['stockouts'][3]=True
        q=validate(p);self.assertEqual(q['missing'],1);self.assertEqual(q['returns'],1);self.assertEqual(q['stockouts'],1)
        result=run_input(p);self.assertEqual(result['quality'],q);self.assertEqual(result['input_manifest']['target'],'observed_gross_shipments');self.assertEqual(result['splits'][-1]['target_start'],p['periods'][-4])
    def test_bytes_and_no_latent_fields(self):
        p=fixture();self.assertEqual(decode(encode(p)),p)
        with self.assertRaises(ValueError):decode(b'{"duplicate":1,"duplicate":2}')
        p['latent_demand']=[100]
        with self.assertRaises(ValueError):validate(p)
    def test_canonical_reproducible_and_file_boundaries(self):
        p=fixture();q={k:p[k] for k in reversed(p)};self.assertEqual(encode(p),encode(q));self.assertEqual(run_input(p),run_input(q))
        with self.assertRaises(ValueError):run_input(p,{'weeks':10})
    def test_holdout_not_used_for_model_selection(self):
        p=fixture();q=copy.deepcopy(p);q['series'][0]['values'][-4:]=[9999]*4
        a,b=run_input(p),run_input(q);self.assertEqual(a['decisions']['assignments'],b['decisions']['assignments'])
        self.assertNotEqual(a['dataset_checksum'],b['dataset_checksum'])
    def test_registration_roundtrip_and_idempotency(self):
        remote=FakeRemote();p=fixture();first=provision(remote,p,PROJECT);second=provision(remote,p,PROJECT)
        self.assertEqual(first['dataset_id'],second['dataset_id']);self.assertTrue(second['reused']);self.assertEqual(remote.statuses,['validating','validating','ready']);self.assertEqual(read_registered(remote,remote.row['generator_config'],PROJECT),p)
    def test_same_version_cannot_overwrite_different_data(self):
        remote=FakeRemote();p=fixture();provision(remote,p,PROJECT);p['series'][0]['values'][0]=33
        with self.assertRaises(ValueError):provision(remote,p,PROJECT)
        self.assertEqual(remote.row['status'],'ready')
    def test_hash_failure_never_marks_ready(self):
        remote=FakeRemote();remote.corrupt=True
        with self.assertRaises(ValueError):provision(remote,fixture(),PROJECT)
        self.assertEqual(remote.row['status'],'rejected');self.assertNotIn('ready',remote.statuses)
    def test_namespace_and_metadata_tampering_rejected(self):
        remote=FakeRemote();provision(remote,fixture(),PROJECT);c=remote.row['generator_config']
        with self.assertRaises(ValueError):read_registered(remote,c,'10000000-0000-4000-8000-000000000002')
        c=copy.deepcopy(c);c['weeks']=61
        with self.assertRaises(ValueError):read_registered(remote,c,PROJECT)
