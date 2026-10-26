import copy,json,unittest
from aurora.forecast import config_for,synthetic_data,run_baseline,usable
from aurora.decisions import segment,forecast,choose,simulate,build,SETTINGS

class DecisionTests(unittest.TestCase):
    def test_segments_edge_cases_and_gaps(self):
        self.assertEqual(segment([0]*30)['segment'],'all_zero');self.assertIsNone(segment([0]*30)['adi'])
        self.assertEqual(segment([0]*20+[4])['segment'],'single_positive');self.assertIsNone(segment([0]*20+[4])['cv2'])
        self.assertEqual(segment([2]*20)['cv2'],0)
        self.assertEqual(segment([0,0,0,4]*10)['segment'],'intermittent')
        self.assertEqual(segment([4,None,0,0])['history_n'],2)
        self.assertEqual(segment([4,-2,1,2])['discarded_prefix'],2)
        self.assertEqual(segment([None])['segment'],'unobserved')
    def test_intermittent_hand_calculations_and_obsolescence(self):
        x=[0,2,0,4,0]
        self.assertAlmostEqual(forecast(x,1,'croston')[0][0],1.1)
        self.assertAlmostEqual(forecast(x,1,'sba')[0][0],1.045)
        self.assertAlmostEqual(forecast(x,1,'tsb')[0][0],.9999)
        self.assertLess(forecast(x+[0]*20,1,'tsb')[0][0],forecast(x,1,'tsb')[0][0])
        self.assertEqual(forecast(x+[0]*20,1,'croston')[0],forecast(x,1,'croston')[0])
        self.assertEqual(forecast([0]*10,3,'tsb')[0],[0]*3)
        self.assertIsNone(forecast([1,None],3,'sba')[0])
    def test_holdout_cannot_change_selection_or_fixed_origin_intervals(self):
        c=config_for({'skus':8});items=synthetic_data(c);a=build(items,c);changed=copy.deepcopy(items);end=c['weeks']-c['horizon']
        for x in changed:x['values'][end:]=[10000 if usable(v) else v for v in x['values'][end:]]
        b=build(changed,c);self.assertEqual(a['assignments'],b['assignments'])
        def points(r):return [(x['sku'],x['model'],x['horizon'],x['predicted']) for x in r['predictions']]
        self.assertEqual(points(a),points(b))
        def bounds(r):return [(x['sku'],x['lower'],x['upper']) for x in r['intervals']]
        self.assertEqual(bounds(a),bounds(b))
    def test_inventory_hand_balance_pipeline_and_lost_sales(self):
        c=config_for();r,reason=simulate([1]*20,[2,2,2,2],'naive',c,initial_stock=0,initial_pipeline=[{'due':1,'quantity':2}])
        self.assertIsNone(reason);rows=r['rows'];self.assertEqual(rows[0]['received'],0);self.assertEqual(rows[0]['lost'],2)
        self.assertEqual(rows[0]['ordered'],1);self.assertEqual(rows[1]['received'],2);self.assertEqual(rows[2]['received'],1)
        self.assertEqual(r['initial_stock']+sum(x['received'] for x in rows)-sum(x['served'] for x in rows),rows[-1]['closing'])
        self.assertEqual(2+sum(x['ordered'] for x in rows)-sum(x['received'] for x in rows),rows[-1]['pipeline'])
        self.assertTrue(all(x['closing']>=0 and x['pipeline']>=0 for x in rows));self.assertLess(r['fill_rate'],.95)
    def test_inventory_no_future_use_and_missing_is_not_zero(self):
        c=config_for();a,_=simulate([1]*30,[1,2,3,4],'naive',c);b,_=simulate([1]*30,[1,2,3,9999],'naive',c)
        self.assertEqual(a['rows'][:3],b['rows'][:3]);self.assertEqual(a['rows'][3]['ordered'],b['rows'][3]['ordered'])
        self.assertEqual(simulate([1]*30,[None],'naive',c)[1],'inventory_target_unobserved')
        z,_=simulate([0]*30,[0]*4,'naive',c);self.assertIsNone(z['fill_rate'])
    def test_equal_comparisons_reproducible_and_service_gate(self):
        a=run_baseline({'skus':16});b=run_baseline({'skus':16});self.assertEqual(a,b);r=a['decisions'];json.dumps(r,allow_nan=False)
        self.assertEqual(len({x['n'] for x in r['paired_metrics']}),1)
        self.assertEqual(len({x['skus'] for x in r['inventory']['scenarios']}),1)
        self.assertEqual(len({x['demand'] for x in r['inventory']['scenarios']}),1)
        for x in r['inventory']['comparisons']:
            for q in x['qualified']:
                sims=[i for i in r['inventory']['details'] if i['sku']==q['sku'] and i['policy']==x['policy']]
                self.assertTrue(all(i['fill_rate'] is not None and i['fill_rate']>=SETTINGS['fill_rate_target'] for i in sims))
            self.assertFalse(x['positive_saving_claim'])

    def test_short_horizon_excludes_uncalibrated_inventory_comparison(self):
        r=run_baseline({'skus':3,'weeks':20,'horizon':1})['decisions']
        self.assertEqual(r['inventory']['common_skus'],0)
        self.assertTrue(any(x.get('reason')=='no_protection_period_calibration' for x in r['excluded']))
        json.dumps(r,allow_nan=False)
