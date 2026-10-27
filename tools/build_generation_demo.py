"""Build saved U21 public/synthetic outputs; never a learned model invocation."""
from pathlib import Path
import argparse,json,shutil
from aurora.generation import catalog,generate,digest,serialized
p=argparse.ArgumentParser();p.add_argument('--reference-root',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('client/demo/generation'));args=p.parse_args();root=Path(__file__).resolve().parents[1];out=args.output
require_new=not out.exists()
if not require_new:raise SystemExit('Use a new output directory to preserve existing saved results.')
out.mkdir(parents=True);data=catalog(root,reference_root=args.reference_root);sources=[s for s in data['sources'] if not s['id'].startswith('u20:') or s['brief']['brief_version']==2];mapping={}
for source in sources:
 id='demo-'+source['checksum'][:16];result=generate(source,42,out/id,args.reference_root);row=dict(id=id,state='succeeded',source=source,seed=42,result=result,error=None,created_at=None);(out/id/'run.json').write_bytes(serialized(row));mapping[source['id']]=id
(out/'catalog.json').write_bytes(serialized(dict(**{k:v for k,v in data.items() if k!='sources'},sources=sources,demo_runs=mapping)));print(json.dumps(dict(sources=len(sources),files=len(list(out.rglob('*'))),output=str(out))))
