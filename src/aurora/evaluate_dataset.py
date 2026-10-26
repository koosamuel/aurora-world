"""Evaluate existing baselines on exported synthetic gross shipments, not latent demand."""
import argparse,json
from pathlib import Path
from .forecast import config_for,evaluate,digest

def evaluate_dataset(root,output):
    products=[json.loads(x) for x in (root/'products.jsonl').read_text().splitlines()]
    observations=[json.loads(x) for x in (root/'forecast/sales_observations.jsonl').read_text().splitlines()]
    by_sku={p['sku_id']:[] for p in products}
    for row in observations:by_sku[row['sku_id']].append(row)
    series=[]
    for sku,rows in sorted(by_sku.items()):
        rows.sort(key=lambda x:x['period']);series.append(dict(sku=sku,values=[x['quantity'] for x in rows]))
    c=config_for({'skus':len(products),'weeks':156,'assumption_version':'research-informed-v1'})
    evaluated=evaluate(series,c)
    report=dict(schema_version='aurora-research-evaluation-v1',synthetic=True,target='observed gross shipments; stockouts censor demand',config=c,dataset_manifest_sha256=__import__('hashlib').sha256((root/'manifest.json').read_bytes()).hexdigest(),M4_test_used=False,metrics=evaluated['metrics'],paired_metrics=evaluated['paired_metrics'],skipped=evaluated['skipped'],exclusions='missing and not-started are null; returns excluded from gross demand target; latent truth kept evaluation-only')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report['paired_metrics'],indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();evaluate_dataset(a.root,a.output)
