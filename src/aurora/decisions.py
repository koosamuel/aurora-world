"""Synthetic decision-support experiment, not an ERP policy or company improvement.

Independent Croston/SBA/TSB implementations. See docs/DECISIONS.md for equations,
initialization, missing-history policy, validation and inventory event order.
"""
import collections,hashlib,math,statistics
from pathlib import Path
from .forecast import usable,predict as baseline_predict,mase_scale,split_origins,digest

CANDIDATES=('naive','seasonal_naive','ses','croston','sba','tsb')
SETTINGS=dict(version='synthetic-decision-v1',alpha=.1,beta=.1,adi_cutoff=1.32,cv2_cutoff=.49,
              lead_time=2,review_period=1,unit_cost_krw=1000,fill_rate_target=.95,
              interval_quantiles=[.1,.9],buffer_quantile=.95,initial_pipeline=[],
              initial_stock='ceil(last 26 usable history mean * protection period)',
              missing_policy='contiguous usable suffix; gaps and returns are never zero')

def suffix(history):
    start=len(history)
    while start and usable(history[start-1]):start-=1
    return history[start:],start

def segment(history):
    xs,discarded=suffix(history);positive=[x for x in xs if x>0];n=len(xs);nz=len(positive)
    adi=n/nz if nz else None
    cv2=statistics.pvariance(positive)/statistics.mean(positive)**2 if nz>=2 else None
    if not n:kind='unobserved'
    elif not nz:kind='all_zero'
    elif nz==1:kind='single_positive'
    elif n<12:kind='short_history'
    elif adi<SETTINGS['adi_cutoff']:kind='smooth' if cv2<SETTINGS['cv2_cutoff'] else 'erratic'
    else:kind='intermittent' if cv2<SETTINGS['cv2_cutoff'] else 'lumpy'
    return dict(segment=kind,adi=adi,cv2=cv2,history_n=n,positive_n=nz,discarded_prefix=discarded)

def forecast(history,horizon,model,season_length=52):
    if model in ('naive','seasonal_naive'):return baseline_predict(history,horizon,model,season_length)
    if model not in CANDIDATES:raise ValueError('Unknown model')
    xs,_=suffix(history)
    if len(xs)<2:return None,'insufficient_contiguous_history'
    alpha,beta=SETTINGS['alpha'],SETTINGS['beta']
    if model=='ses':
        level=xs[0]
        for x in xs[1:]:level+=alpha*(x-level)
        return [level]*horizon,None
    nonzero=[i for i,x in enumerate(xs) if x>0]
    if not nonzero:return [0.0]*horizon,None
    first=nonzero[0];size=xs[first];interval=float(first+1);prob=1/(first+1);elapsed=1
    for x in xs[first+1:]:
        if model=='tsb':prob+=beta*((1 if x>0 else 0)-prob)
        if x>0:
            size+=alpha*(x-size);interval+=alpha*(elapsed-interval);elapsed=1
        else:elapsed+=1
    value=size*prob if model=='tsb' else size/interval*(1-alpha/2 if model=='sba' else 1)
    return [value]*horizon,None

def quantile(values,q):
    if not values:return None
    xs=sorted(values);return xs[max(0,math.ceil(q*len(xs))-1)]

def rule_model(seg):
    return 'sba' if seg in ('intermittent','lumpy') else 'ses' if seg in ('smooth','erratic') else 'naive'

def choose(history,c):
    """Only history ending BEFORE the final holdout is accepted here."""
    h=c['horizon'];origins=[len(history)-h*k for k in range(c['validation_origins'],0,-1)]
    scores={};residuals={};blocks={};exclusions={}
    for model in CANDIDATES:
        errors=[];block_errors=[];reason=None
        for origin in origins:
            preds,reason=forecast(history[:origin],h,model,c['season_length'])
            if preds is None:break
            actual=history[origin:origin+h]
            errors.extend(a-p for a,p in zip(actual,preds) if usable(a))
            protection=SETTINGS['lead_time']+SETTINGS['review_period']
            if h>=protection and all(usable(a) for a in actual[:protection]):block_errors.append(sum(actual[:protection])-sum(preds[:protection]))
        if reason or not errors:exclusions[model]=reason or 'no_usable_validation_targets'
        else:
            scores[model]=sum(abs(e) for e in errors)/len(errors);residuals[model]=errors;blocks[model]=block_errors
    selected=min(scores,key=lambda m:(scores[m],CANDIDATES.index(m))) if scores else None
    seg=segment(history);rule=rule_model(seg['segment']);rule=rule if rule in scores else selected
    return dict(selected=selected,rule_model=rule,validation_mae=scores,excluded_candidates=exclusions,
                residuals=residuals,protection_errors=blocks,**seg)

def simulate(history,actual,model,c,buffer=0,initial_stock=None,initial_pipeline=None):
    """Weekly review: receive -> order (due t+L) -> serve lost sales -> close."""
    lead=SETTINGS['lead_time'];protection=lead+SETTINGS['review_period'];valid=[x for x in history[-26:] if usable(x)]
    stock=math.ceil(statistics.mean(valid)*protection) if initial_stock is None and valid else (initial_stock or 0)
    pipeline=[dict(x) for x in (initial_pipeline or [])];initial=stock;rows=[]
    for t,demand in enumerate(actual):
        if not usable(demand):return None,'inventory_target_unobserved'
        preds,reason=forecast(history+actual[:t],protection,model,c['season_length'])
        if preds is None:return None,reason
        opening=stock;received=sum(x['quantity'] for x in pipeline if x['due']==t);pipeline=[x for x in pipeline if x['due']!=t];stock+=received
        position=stock+sum(x['quantity'] for x in pipeline)
        target=math.ceil(sum(preds)+buffer);ordered=max(0,target-position)
        if ordered:pipeline.append(dict(due=t+lead,quantity=ordered))
        served=min(stock,demand);lost=demand-served;stock-=served
        pending=sum(x['quantity'] for x in pipeline)
        if abs(opening+received-served-stock)>1e-8:raise AssertionError('Inventory imbalance')
        rows.append(dict(week=t,opening=opening,received=received,demand=demand,served=served,lost=lost,closing=stock,ordered=ordered,pipeline=pending,target=target))
    total=sum(actual);avg=statistics.mean(x['closing'] for x in rows);pipe=statistics.mean(x['pipeline'] for x in rows)
    return dict(initial_stock=initial,initial_pipeline=initial_pipeline or [],buffer=buffer,demand=total,served=sum(x['served'] for x in rows),fill_rate=sum(x['served'] for x in rows)/total if total else None,stockout_weeks=sum(x['lost']>0 for x in rows),average_on_hand=avg,average_pipeline=pipe,on_hand_krw=avg*SETTINGS['unit_cost_krw'],pipeline_krw=pipe*SETTINGS['unit_cost_krw'],invested_krw=(avg+pipe)*SETTINGS['unit_cost_krw'],rows=rows),None

def summary(rows):
    errors=[r['predicted']-r['actual'] for r in rows];scaled=[abs(r['predicted']-r['actual'])/r['scale'] for r in rows if r['scale']]
    return dict(n=len(rows),skus=len({r['sku'] for r in rows}),mae=statistics.mean(map(abs,errors)) if errors else None,bias=statistics.mean(errors) if errors else None,mase=statistics.mean(scaled) if scaled else None,mase_n=len(scaled))

def build(series,c):
    end=c['weeks']-c['horizon'];assignments=[];predictions=[];intervals=[];inventory=[];excluded=[];segments=[]
    for item in series:
        sku=item['sku'];history=item['values'][:end];actual=item['values'][end:];choice=choose(history,c);model=choice['selected']
        assignments.append(dict(sku=sku,selection_origin=end,**choice))
        for split,origin in split_origins(c):segments.append(dict(sku=sku,origin=origin,split=split,**segment(item['values'][:origin])))
        if model is None:excluded.append(dict(sku=sku,reason='no_validation_model'));continue
        scale=mase_scale(history,c['season_length']);roles={m:m for m in CANDIDATES}|{'selected':model,'segment_rule':choice['rule_model']}
        for role,m in roles.items():
            preds,reason=forecast(history,c['horizon'],m,c['season_length'])
            if preds is None:excluded.append(dict(sku=sku,role=role,reason=reason));continue
            for h,(a,p) in enumerate(zip(actual,preds)):
                if usable(a):predictions.append(dict(sku=sku,horizon=h+1,model=role,assigned=m,actual=a,predicted=p,scale=scale))
        errors=choice['residuals'][model];lo,hi=[quantile(errors,q) for q in SETTINGS['interval_quantiles']];point,_=forecast(history,c['horizon'],model,c['season_length'])
        if point is not None:
            for h,(a,p) in enumerate(zip(actual,point)):
                lower=max(0,p+lo);upper=max(lower,p+hi)
                if usable(a):intervals.append(dict(sku=sku,horizon=h+1,actual=a,lower=lower,upper=upper,covered=lower<=a<=upper,width=upper-lower,calibration_n=len(errors)))
        for role,m in [('naive','naive'),('selected',model)]:
            blocks=choice['protection_errors'].get(m,[])
            for policy in ('no_buffer','validation_buffer'):
                if policy=='validation_buffer' and not blocks:
                    excluded.append(dict(sku=sku,role=role,policy=policy,reason='no_protection_period_calibration'));continue
                buffer=0 if policy=='no_buffer' else max(0,quantile(blocks,SETTINGS['buffer_quantile']))
                sim,reason=simulate(history,actual,m,c,buffer)
                if sim:inventory.append(dict(sku=sku,role=role,model=m,policy=policy,calibration_n=len(blocks),**sim))
                else:excluded.append(dict(sku=sku,role=role,policy=policy,reason=reason))
    # Identical SKU/horizon keys for all roles, without hiding each role's own coverage.
    roles=[*CANDIDATES,'selected','segment_rule'];keys=[{(r['sku'],r['horizon']) for r in predictions if r['model']==m} for m in roles];common=set.intersection(*keys)
    metrics=[dict(model=m,**summary([r for r in predictions if r['model']==m and (r['sku'],r['horizon']) in common])) for m in roles]
    coverage=[dict(model=m,**summary([r for r in predictions if r['model']==m])) for m in roles]
    # All four forecast x policy cells share the SAME SKU population and demand.
    cells=[(r,p) for r in ('naive','selected') for p in ('no_buffer','validation_buffer')]
    eligible=set.intersection(*[{r['sku'] for r in inventory if (r['role'],r['policy'])==cell} for cell in cells]);scenarios=[];comparisons=[]
    for role,policy in cells:
        rows=[r for r in inventory if r['sku'] in eligible and r['role']==role and r['policy']==policy];demand=sum(r['demand'] for r in rows);served=sum(r['served'] for r in rows)
        scenarios.append(dict(role=role,policy=policy,skus=len(rows),demand=demand,fill_rate=served/demand if demand else None,stockout_weeks=sum(r['stockout_weeks'] for r in rows),on_hand_krw=sum(r['on_hand_krw'] for r in rows),pipeline_krw=sum(r['pipeline_krw'] for r in rows),invested_krw=sum(r['invested_krw'] for r in rows)))
    for policy in ('no_buffer','validation_buffer'):
        a=next(r for r in scenarios if r['role']=='naive' and r['policy']==policy);b=next(r for r in scenarios if r['role']=='selected' and r['policy']==policy)
        qualified=[]
        for sku in sorted(eligible):
            pair=[next(r for r in inventory if r['sku']==sku and r['role']==role and r['policy']==policy) for role in ('naive','selected')]
            if all(r['fill_rate'] is not None and r['fill_rate']>=SETTINGS['fill_rate_target'] for r in pair):qualified.append(dict(sku=sku,saving_krw=pair[0]['invested_krw']-pair[1]['invested_krw']))
        comparisons.append(dict(policy=policy,raw_difference_krw=a['invested_krw']-b['invested_krw'],qualified_skus=len(qualified),qualified_difference_krw=sum(r['saving_krw'] for r in qualified),qualified=qualified,positive_saving_claim=False))
    segment_metrics=[]
    for seg in sorted({a['segment'] for a in assignments}):
        members={a['sku'] for a in assignments if a['segment']==seg}
        for role in ('naive','selected','segment_rule'):
            segment_metrics.append(dict(segment=seg,model=role,**summary([r for r in predictions if r['sku'] in members and r['model']==role and (r['sku'],r['horizon']) in common])))
    stability=[]
    for item in series:
        rs=[r for r in segments if r['sku']==item['sku']];stability.append(dict(sku=item['sku'],transitions=sum(a['segment']!=b['segment'] for a,b in zip(rs,rs[1:]))))
    return dict(schema_version='aurora-decisions-v1',synthetic=True,settings=SETTINGS,settings_hash=digest(SETTINGS),code_revision=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),selection_cutoff=end,assignments=assignments,segment_history=segments,segment_stability=stability,segment_metrics=segment_metrics,segment_counts=dict(collections.Counter(a['segment'] for a in assignments)),paired_metrics=metrics,coverage_metrics=coverage,predictions=predictions,intervals=intervals,interval_summary=dict(n=len(intervals),coverage=statistics.mean(r['covered'] for r in intervals) if intervals else None,mean_width=statistics.mean(r['width'] for r in intervals) if intervals else None,nominal=.8,calibrated=False),inventory=dict(evaluation_weeks=c['horizon'],common_skus=len(eligible),scenarios=scenarios,comparisons=comparisons,details=inventory),excluded=excluded)
