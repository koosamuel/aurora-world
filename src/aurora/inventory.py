"""Deterministic long-horizon policy replay, independent of the synthetic UI contract.

Observed sales are scenario demand, not uncensored demand. No policy learning,
causal off-policy evaluation, stockout reconstruction or empirical cost inference.
"""
import math
import statistics
from .forecast import usable, digest
from .decisions import forecast

DEFAULT_POLICY = dict(version='inventory-replay-v1', lead_time=2, review_period=1,
                      moq=1, max_order_quantity=None, fill_rate_target=.95,
                      currency=None, unit_cost=None, holding_cost_per_unit_week=None,
                      shortage_cost_per_unit=None, fixed_order_cost=None)


def finite_nonnegative(x):
    return type(x) in (int, float) and math.isfinite(x) and x >= 0


def policy_for(options=None):
    if options is not None and (not isinstance(options, dict) or set(options)-set(DEFAULT_POLICY)):
        raise ValueError('Unknown inventory policy field')
    p=DEFAULT_POLICY | (options or {})
    for k,lo,hi in [('lead_time',1,26),('review_period',1,4),('moq',1,1000000)]:
        if type(p[k]) is not int or not lo<=p[k]<=hi:raise ValueError('Invalid '+k)
    cap=p['max_order_quantity']
    if cap is not None and (type(cap) is not int or cap<0):raise ValueError('Invalid order capacity')
    if not finite_nonnegative(p['fill_rate_target']) or not 0<p['fill_rate_target']<=1:raise ValueError('Invalid service target')
    if not isinstance(p['version'],str) or not p['version']:raise ValueError('Policy version required')
    costs=['unit_cost','holding_cost_per_unit_week','shortage_cost_per_unit','fixed_order_cost']
    for k in costs:
        if p[k] is not None and not finite_nonnegative(p[k]):raise ValueError('Invalid '+k)
    currency=p['currency']
    if currency is not None and (not isinstance(currency,str) or len(currency)!=3 or not currency.isascii() or not currency.isupper() or not currency.isalpha()):raise ValueError('ISO currency required')
    if any(p[k] is not None for k in costs) and currency is None:raise ValueError('Cost currency required')
    return p


def replay(history, actual, model, season_length=52, *, policy=None, buffer=0,
           initial_stock=None, initial_pipeline=None, warmup=0):
    p=policy_for(policy)
    if not isinstance(actual,list) or not actual:raise ValueError('Nonempty observed scenario required')
    if type(warmup) is not int or not 0<=warmup<len(actual):raise ValueError('Invalid warmup')
    if not finite_nonnegative(buffer):raise ValueError('Invalid buffer')
    if not all(usable(x) and type(x) is not bool for x in actual):raise ValueError('Unobserved scenario; do not fill missing values with zero')
    if any(x is not None and not finite_nonnegative(x) for x in history):raise ValueError('Invalid history')
    valid=[x for x in history[-26:] if usable(x)]
    protection=p['lead_time']+p['review_period']
    if initial_stock is None:
        if not valid:raise ValueError('Initial stock requires history or an explicit value')
        initial_stock=math.ceil(statistics.mean(valid)*protection)
    if not finite_nonnegative(initial_stock):raise ValueError('Invalid initial stock')
    if initial_pipeline is not None and not isinstance(initial_pipeline,list):raise ValueError('Initial pipeline must be a list')
    pipeline=[]
    for entry in initial_pipeline or []:
        if not isinstance(entry,dict) or set(entry)!={'due','quantity'} or type(entry['due']) is not int or entry['due']<0 or not finite_nonnegative(entry['quantity']):raise ValueError('Invalid initial pipeline arrival')
        pipeline.append(dict(entry))
    initial_pipeline=[dict(x) for x in pipeline]
    stock=initial_stock;rows=[]
    for t,demand in enumerate(actual):
        preds,reason=forecast(history+actual[:t],protection,model,season_length)
        if preds is None:raise ValueError('Forecast unavailable: '+str(reason))
        opening=stock
        received=sum(x['quantity'] for x in pipeline if x['due']==t)
        pipeline=[x for x in pipeline if x['due']!=t];stock+=received
        position=stock+sum(x['quantity'] for x in pipeline)
        target=math.ceil(sum(preds)+buffer)
        desired=max(0,target-position) if t%p['review_period']==0 else 0
        ordered=math.ceil(desired/p['moq'])*p['moq']
        if p['max_order_quantity'] is not None:ordered=min(ordered,(p['max_order_quantity']//p['moq'])*p['moq'])
        if ordered:pipeline.append(dict(due=t+p['lead_time'],quantity=ordered))
        served=min(stock,demand);lost=demand-served;stock-=served
        pending=sum(x['quantity'] for x in pipeline)
        assert math.isclose(opening+received-served,stock,abs_tol=1e-8)
        assert math.isclose(initial_stock+sum(r['received'] for r in rows)+received-sum(r['served'] for r in rows)-served,stock,abs_tol=1e-8)
        assert math.isclose(sum(x['quantity'] for x in initial_pipeline)+sum(r['ordered'] for r in rows)+ordered-sum(r['received'] for r in rows)-received,pending,abs_tol=1e-8)
        holding=stock*p['holding_cost_per_unit_week'] if p['holding_cost_per_unit_week'] is not None else None
        shortage=lost*p['shortage_cost_per_unit'] if p['shortage_cost_per_unit'] is not None else None
        ordercost=(p['fixed_order_cost'] if ordered else 0) if p['fixed_order_cost'] is not None else None
        total=sum([holding,shortage,ordercost]) if all(v is not None for v in [holding,shortage,ordercost]) else None
        rows.append(dict(week=t,information_end_exclusive=len(history)+t,phase='warmup' if t<warmup else 'evaluation',
                         opening=opening,received=received,ordered=ordered,target=target,demand=demand,served=served,lost=lost,
                         closing=stock,pipeline=pending,capacity_shortfall=max(0,desired-ordered),
                         holding_cost=holding,shortage_cost=shortage,order_cost=ordercost,total_cost=total,
                         reward=-total if total is not None else None,action_probability=None))
    scored=rows[warmup:];demand=sum(r['demand'] for r in scored);served=sum(r['served'] for r in scored)
    avg=statistics.mean(r['closing'] for r in scored);pipe=statistics.mean(r['pipeline'] for r in scored)
    fill=served/demand if demand else None
    return dict(policy=p,policy_hash=digest(p),model=model,buffer=buffer,warmup_weeks=warmup,evaluation_weeks=len(scored),
                initial_stock=initial_stock,initial_pipeline=initial_pipeline,terminal_pipeline=pipeline,
                demand=demand,served=served,fill_rate=fill,service_met=fill>=p['fill_rate_target'] if fill is not None else None,
                lost=sum(r['lost'] for r in scored),stockout_weeks=sum(r['lost']>0 for r in scored),
                average_on_hand=avg,average_pipeline=pipe,
                invested_value=(avg+pipe)*p['unit_cost'] if p['unit_cost'] is not None else None,
                total_cost=sum(r['total_cost'] for r in scored) if all(r['total_cost'] is not None for r in scored) else None,
                currency=p['currency'],costs_are_user_scenarios=True,rows=rows)
