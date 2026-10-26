import copy,csv,json,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
from aurora.public_retail import aggregate,evaluate_public,export_result,validate,START,STOP,OVERLAP
from aurora.inventory import replay,policy_for

SOURCE=dict(dataset='UCI Online Retail II',license='CC-BY-4.0',workbook_sha256='a'*64)
def row(d,qty=5,code='12345',invoice='100001',price=2,country='United Kingdom'):
    return ('Year 2010-2011' if d>=OVERLAP else 'Year 2009-2010',dict(invoice=invoice,sku=code,quantity=qty,when=d,price=price,country=country))
def rows():
    return [row(START+timedelta(weeks=t),4+(t%13),code=code) for code in ['12345','23456'] for t in range(104)]
def fixture():return aggregate(rows(),SOURCE)

class PublicRetailTests(unittest.TestCase):
    def test_overlap_cancellations_and_partial_boundaries(self):
        data=rows();dup=row(OVERLAP,9);data.extend([('Year 2009-2010',dup[1]),dup,row(START,qty=-2,invoice='C200001'),row(START-timedelta(days=1)),row(STOP)])
        p=aggregate(data,SOURCE);item=p['series'][0];week=(OVERLAP-START).days//7
        self.assertEqual(item['values'][week],4+(week%13)+9)
        self.assertEqual(item['cancellations'][0],2);self.assertEqual(item['values'][0],4)
        self.assertEqual(p['audit']['counts']['overlap_first_sheet_excluded'],1)
        self.assertEqual(p['audit']['counts']['partial_boundary_week_excluded'],2)
        self.assertEqual(len(p['periods']),104);self.assertTrue(all(x is None for x in item['stockouts']))
    def test_future_volume_does_not_change_prefix_selection(self):
        a=aggregate(rows(),SOURCE,sku_limit=1);data=rows()+[row(START+timedelta(weeks=90),100000,code='99999')]
        b=aggregate(data,SOURCE,sku_limit=1)
        self.assertEqual([x['sku'] for x in a['series']],[x['sku'] for x in b['series']])
        self.assertEqual(a['selection'],b['selection'])
    def test_nonproduct_country_adjustment_and_null_customer_not_required(self):
        p=aggregate(rows()+[row(START,code='POST'),row(START,qty=0),row(START,price=-1),row(START,country='France')],SOURCE)
        self.assertEqual(p['series'][0]['values'][0],4)
        self.assertEqual(p['audit']['counts']['non_product_code'],1)
        self.assertNotIn('Customer',json.dumps(p));self.assertTrue(all(r['unit_cost'] is None for r in p['series']))
    def test_first_seen_proxy_is_not_filled_with_sales_zero(self):
        p=aggregate([row(START+timedelta(weeks=t),5) for t in range(10,104)],SOURCE)
        self.assertEqual(p['series'][0]['values'][:10],[None]*10)
        self.assertEqual(p['series'][0]['statuses'][9],'not_started')
        self.assertEqual(p['series'][0]['values'][10],5)
    def test_invalid_contract_and_duplicate_sku_rejected(self):
        for change in [lambda p:p['series'].append(copy.deepcopy(p['series'][0])),lambda p:p['series'][0]['stockouts'].__setitem__(0,False),lambda p:p['series'][0]['values'].__setitem__(0,True),lambda p:p['series'][0].update(unit_cost=3),lambda p:p['selection'].update(cutoff=100),lambda p:p.update(synthetic=True)]:
            p=fixture();change(p)
            with self.assertRaises(ValueError):validate(p)
    def test_frozen_assignment_and_early_actions_invariant_to_late_target(self):
        p=fixture();q=copy.deepcopy(p);q['series'][0]['values'][-1]=9999
        a=evaluate_public(p);b=evaluate_public(q)
        self.assertEqual(a['assignments'],b['assignments'])
        self.assertEqual(a['evaluation'],b['evaluation'])
        self.assertEqual(a['inventory_details'][0]['rows'][:-1],b['inventory_details'][0]['rows'][:-1])
        self.assertEqual(a['inventory_details'][0]['rows'][-1]['ordered'],b['inventory_details'][0]['rows'][-1]['ordered'])
        self.assertFalse(a['company_performance_claim']);self.assertTrue(a['inventory_is_scenario'])
    def test_common_cells_reproducible_and_money_remains_unknown(self):
        a=evaluate_public(fixture());self.assertEqual(a,evaluate_public(fixture()))
        self.assertEqual(len(a['inventory_summaries']),12)
        for scenario in a['evaluation']['scenario_grid']:
            cells=[r for r in a['inventory_summaries'] if r['scenario']==scenario['id']]
            self.assertEqual(len({r['demand'] for r in cells}),1);self.assertEqual(len({r['skus'] for r in cells}),1)
        for d in a['inventory_details']:
            self.assertEqual(d['evaluation_weeks'],32);self.assertIsNone(d['invested_value']);self.assertIsNone(d['total_cost'])
            self.assertTrue(all(r['action_probability'] is None for r in d['rows']))
    def test_artifact_csv_matches_json_not_an_independent_recalculation(self):
        r=evaluate_public(fixture(),{'UCI-12345':{'policy':dict(currency='GBP',unit_cost=5,holding_cost_per_unit_week=.1,shortage_cost_per_unit=2,fixed_order_cost=3,moq=2,max_order_quantity=10),'initial_stock':3,'initial_pipeline':[dict(due=1,quantity=2)]}})
        costed=[d for d in r['inventory_details'] if d['sku']=='UCI-12345']
        self.assertTrue(all(d['total_cost'] is not None and d['currency']=='GBP' for d in costed))
        self.assertTrue(all(d['initial_stock']==0 for d in costed if d['scenario']=='lead2_zero'))
        with tempfile.TemporaryDirectory() as td:
            export_result(r,td);dest=Path(td)
            with (dest/'forecast.csv').open(encoding='utf-8-sig') as f:rs=list(csv.DictReader(f))
            self.assertEqual(len(rs),len(r['predictions']))
            self.assertAlmostEqual(float(rs[0]['predicted']),r['predictions'][0]['predicted'])
            with (dest/'decisions.csv').open(encoding='utf-8-sig') as f:logs=list(csv.DictReader(f))
            self.assertEqual(len(logs),sum(len(d['rows']) for d in r['inventory_details']))
            self.assertTrue(all(x['currency']=='GBP' for x in logs if x['sku']=='UCI-12345'))
            self.assertEqual(len(json.loads((dest/'artifacts.json').read_text())['files']),5)

class ReplayTests(unittest.TestCase):
    def test_hand_calculated_cost_moq_and_leadtime(self):
        p=dict(lead_time=2,moq=4,max_order_quantity=5,currency='GBP',unit_cost=10,holding_cost_per_unit_week=1,shortage_cost_per_unit=2,fixed_order_cost=5)
        r=replay([1]*20,[3,3,3,3],'naive',policy=p,initial_stock=0,initial_pipeline=[dict(due=1,quantity=2)])
        self.assertEqual(r['rows'][0]['ordered'],4);self.assertEqual(r['rows'][0]['total_cost'],11)
        self.assertEqual(r['rows'][0]['reward'],-11);self.assertEqual(r['rows'][1]['received'],2);self.assertEqual(r['rows'][2]['received'],4)
        self.assertTrue(all(x['ordered']%4==0 and x['ordered']<=5 for x in r['rows']))
        self.assertEqual(sum(x['total_cost'] for x in r['rows']),r['total_cost'])
    def test_warmup_scoring_does_not_reset_state_and_terminal_pipeline_remains(self):
        a=replay([1]*30,[4]*12,'naive',initial_stock=0,initial_pipeline=[dict(due=10,quantity=2)],warmup=4)
        b=replay([1]*30,[4]*12,'naive',initial_stock=0,initial_pipeline=[dict(due=10,quantity=2)],warmup=0)
        self.assertEqual([{k:v for k,v in r.items() if k!='phase'} for r in a['rows']],[{k:v for k,v in r.items() if k!='phase'} for r in b['rows']])
        self.assertEqual(a['demand'],32);self.assertEqual(a['evaluation_weeks'],8)
        self.assertEqual(sum(x['quantity'] for x in a['terminal_pipeline']),a['rows'][-1]['pipeline'])
    def test_strict_invalid_state_constraints_cost_and_gap(self):
        for policy in [dict(lead_time=0),dict(moq=True),dict(max_order_quantity=-1),dict(unit_cost=1),dict(currency='KRW',fixed_order_cost=float('inf')),dict(fill_rate_target=0),dict(unknown=1)]:
            with self.assertRaises(ValueError):policy_for(policy)
        for kwargs in [dict(initial_stock=-1),dict(initial_pipeline=[dict(due=-1,quantity=2)]),dict(warmup=3),dict(buffer=-1)]:
            with self.assertRaises(ValueError):replay([1]*20,[1]*3,'naive',**kwargs)
        with self.assertRaises(ValueError):replay([1]*20,[1,None,2],'naive')
    def test_balance_and_no_future_use_over_long_trace(self):
        actual=[1,5,0,3]*12
        a=replay([2]*60,actual,'ses',initial_pipeline=[dict(due=0,quantity=7)],warmup=4)
        b=replay([2]*60,actual[:-1]+[1000],'ses',initial_pipeline=[dict(due=0,quantity=7)],warmup=4)
        self.assertEqual(a['rows'][:-1],b['rows'][:-1]);self.assertEqual(a['rows'][-1]['ordered'],b['rows'][-1]['ordered'])
        self.assertEqual(a['initial_stock']+sum(r['received']-r['served'] for r in a['rows']),a['rows'][-1]['closing'])
        self.assertEqual(7+sum(r['ordered']-r['received'] for r in a['rows']),a['rows'][-1]['pipeline'])
        zero=replay([0]*20,[0]*8,'naive');self.assertIsNone(zero['fill_rate']);self.assertIsNone(zero['service_met'])

if __name__=='__main__':unittest.main()
