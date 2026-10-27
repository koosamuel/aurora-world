import argparse
import json
from pathlib import Path
from .forecast import run_baseline


def main():
    parser=argparse.ArgumentParser(description='Aurora World synthetic forecasting')
    sub=parser.add_subparsers(dest='command',required=True)
    demo=sub.add_parser('demo');demo.add_argument('--config',default='configs/demo.json');demo.add_argument('--output',default='results/baseline.json');demo.add_argument('--report',type=Path)
    server=sub.add_parser('serve');server.add_argument('--port',type=int,default=8765);server.add_argument('--public-input',type=Path);server.add_argument('--reference-root',type=Path)
    worker=sub.add_parser('worker');worker.add_argument('--once',action='store_true');worker.add_argument('--env-file',type=Path)
    identity=sub.add_parser('identity');identity.add_argument('--input',type=Path,required=True);identity.add_argument('--output',type=Path,required=True)
    sampling=sub.add_parser('sampling');sampling.add_argument('--input',type=Path,required=True);sampling.add_argument('--output',type=Path,required=True)
    generate=sub.add_parser('generate');generate.add_argument('--source',required=True);generate.add_argument('--seed',type=int,default=42);generate.add_argument('--output',type=Path,required=True);generate.add_argument('--reference-root',type=Path)
    args=parser.parse_args()
    if args.command=='demo':
        result=run_baseline(json.loads(Path(args.config).read_text()))
        out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
        if args.report:
            from .reports import decision_report
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(decision_report(result))
        print(json.dumps(dict(output=str(out),quality=result['quality'],paired_metrics=result['paired_metrics']),ensure_ascii=False,indent=2))
    elif args.command=='serve':
        from .server import serve
        serve(Path(__file__).resolve().parents[2],port=args.port,public_input=args.public_input,reference_root=args.reference_root)
    elif args.command=='identity':
        from .identity import load, export
        try:
            result=export(load(args.input),args.output)
        except (ValueError,OSError) as error:
            parser.exit(1,f'Identity audit: {error}\n')
        print(json.dumps(dict(output=str(args.output),counts=result['counts'],ready_for_downstream=result['ready_for_downstream'])))
        if not result['ready_for_downstream']:parser.exit(2)
    elif args.command=='sampling':
        from .sampling import load, export
        try:result=export(load(args.input),args.output)
        except (ValueError,OSError) as error:parser.exit(1,f'Sampling brief: {error}\n')
        print(json.dumps(dict(output=str(args.output),checksum=result['checksum'],summary=result['summary']),ensure_ascii=False,indent=2))
    elif args.command=='generate':
        from .generation import catalog,generate
        try:
            sources={x['id']:x for x in catalog(Path(__file__).resolve().parents[2],reference_root=args.reference_root)['sources']}
            if args.source not in sources:raise ValueError('지원하지 않는 source_id')
            result=generate(sources[args.source],args.seed,args.output,args.reference_root)
        except (ValueError,OSError) as error:parser.exit(1,f'Digital sample: {error}\n')
        print(json.dumps(dict(output=str(args.output),candidates=[x['method'] for x in result['report']['candidates']],data_kind=result['report']['data_kind']),ensure_ascii=False))
    elif args.command=='worker':
        if args.env_file:
            import os
            for line in args.env_file.read_text().splitlines():
                if '=' in line:
                    key,value=line.split('=',1)
                    if key in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'):os.environ[key]=value
        from .cloud import SupabaseWorker
        SupabaseWorker().run(once=args.once)


if __name__=='__main__':main()
