import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from aurora.forecast import config_for,predict,mase_scale,run_baseline,synthetic_data,evaluate,split_origins
from aurora.jobs import Store,work_once

class ForecastTests(unittest.TestCase):
    def test_hand_calculated_forecasts(self):
        self.assertEqual(predict([1,2,3,4],5,'naive',2)[0],[4]*5)
        self.assertEqual(predict([1,2,3,4],5,'seasonal_naive',2)[0],[3,4,3,4,3])
        self.assertEqual(mase_scale([1,2,3,4],2),2)
    def test_invalid_settings(self):
        for value in [{'skus':True},{'horizon':0},{'skus':101},{'unexpected':1},{'weeks':20,'horizon':12},[]]:
            with self.subTest(value=value),self.assertRaises(ValueError):config_for(value)
    def test_missing_returns_and_zero_are_distinct(self):
        for value in [None,-3]:self.assertIsNone(predict([4,value],4,'naive')[0])
        self.assertEqual(predict([0,0],2,'naive')[0],[0,0])
        self.assertIsNone(mase_scale([0]*100,52))
        self.assertIsNone(predict([None]*60+[1]*12,4,'seasonal_naive')[0])
    def test_no_future_leakage(self):
        c=config_for({'skus':8});items=synthetic_data(c);origin=split_origins(c)[0][1]
        before=evaluate(items,c)
        changed=copy.deepcopy(items)
        for item in changed:item['values'][origin:]=[10000]*(c['weeks']-origin)
        after=evaluate(changed,c)
        def forecasts(result):return [(r['sku'],r['model'],r['horizon'],r['predicted'],r['mase_scale']) for r in result['predictions'] if r['origin']==origin]
        self.assertEqual(forecasts(before),forecasts(after))
    def test_reproducible_paired_coverage(self):
        a=run_baseline();b=run_baseline()
        self.assertEqual(a,b)
        self.assertEqual(a['quality']['observations'],7800)
        for split in ['validation','test']:
            metrics=[m for m in a['paired_metrics'] if m['split']==split]
            self.assertEqual(metrics[0]['n'],metrics[1]['n'])
        self.assertTrue(a['quality']['missing']>0 and a['quality']['returns']>0)
        json.dumps(a,allow_nan=False)
        self.assertEqual(a['splits'][-1]['origin'],152)

class JobTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'jobs.db')
    def tearDown(self):self.tmp.cleanup()
    def test_idempotency_and_project_isolation(self):
        a=self.store.request('forecast','key')
        self.assertEqual(a['id'],self.store.request('forecast','key')['id'])
        with self.assertRaises(ValueError):self.store.request('forecast','key',{'skus':3})
        self.assertIsNone(self.store.get(a['id'],'labeling'))
        self.assertEqual(self.store.list('labeling'),[])
        with self.assertRaises(ValueError):self.store.request('labeling','x')
    def test_concurrent_claim_is_single(self):
        self.store.request('forecast','once')
        with ThreadPoolExecutor(4) as pool:jobs=list(pool.map(lambda _:self.store.claim(),range(4)))
        self.assertEqual(sum(j is not None for j in jobs),1)
    def test_expired_attempt_cannot_finish_and_cancel(self):
        r=self.store.request('forecast','lease');old=self.store.claim(-1);new=self.store.claim()
        self.assertNotEqual(old['token'],new['token'])
        self.assertFalse(self.store.finish(old,{}))
        self.store.cancel(r['id'],'forecast')
        self.assertFalse(self.store.finish(new,{}))
        self.assertEqual(self.store.get(r['id'],'forecast')['status'],'cancelled')
    def test_retry_limit(self):
        r=self.store.request('forecast','retry')
        for _ in range(3):self.assertIsNotNone(self.store.claim(-1))
        self.assertIsNone(self.store.claim())
        self.assertEqual(self.store.get(r['id'],'forecast')['status'],'failed')
    def test_worker_returns_actual_computation(self):
        r=self.store.request('forecast','run',{'skus':8})
        self.assertTrue(work_once(self.store))
        actual=self.store.get(r['id'],'forecast')
        self.assertEqual(actual['status'],'succeeded')
        self.assertEqual(actual['result'],run_baseline({'skus':8}))

if __name__=='__main__':unittest.main()
