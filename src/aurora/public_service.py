"""Private, versioned public-retail inputs and fenced run artifacts."""
import argparse,hashlib,json,tempfile,uuid
from pathlib import Path
from urllib.parse import quote
from .inputs import MAX_BYTES,require
from .registered import RemoteError
from .public_retail import validate,evaluate_public,export_result

MAX_ARTIFACT=48*1024*1024
NAMES=('result.json','forecast.csv','inventory.csv','decisions.csv','report.md')

def canonical(payload):
    validate(payload)
    data=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    require(len(data)<=MAX_BYTES,'공개 주간 입력은 최대 4 MiB입니다.')
    return data

def decode(data):
    require(isinstance(data,bytes) and 0<len(data)<=MAX_BYTES,'입력 크기를 확인하세요.')
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'JSON 중복 키입니다.');d[k]=v
        return d
    p=json.loads(data,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite JSON')))
    validate(p);return p

def public_summary(result):
    # Full prediction/decision traces belong in private artifacts, not JSONB/DOM.
    keys=('schema_version','synthetic','inventory_is_scenario','company_performance_claim','version','source','data_sha256','code_sha256','inventory_code_sha256','forecast_code_sha256','evaluation','paired_metrics','coverage_metrics','inventory_summaries','limitations')
    s={k:result[k] for k in keys}
    s['assignments']=[{k:r[k] for k in ('sku','selected','segment','selection_origin')} for r in result['assignments']]
    s['excluded_counts']={reason:sum(r['reason']==reason for r in result['excluded']) for reason in sorted({r['reason'] for r in result['excluded']})}
    s['artifact_names']=list(NAMES)
    return s

def read_public(remote,config,project_id):
    project=str(uuid.UUID(project_id));source=config.get('input',{})
    require(config.get('mode')=='public_file_v1' and set(source)=={'bucket','path','sha256','bytes'},'공개 파일 메타데이터를 확인하세요.')
    checksum=source['sha256'];require(isinstance(checksum,str) and len(checksum)==64 and all(c in '0123456789abcdef' for c in checksum),'파일 해시를 확인하세요.')
    require(source['bucket']=='aurora-artifacts' and source['path']==f'{project}/inputs/{checksum}.json','다른 프로젝트 파일은 읽을 수 없습니다.')
    require(type(source['bytes']) is int and 0<source['bytes']<=MAX_BYTES,'등록 크기를 확인하세요.')
    data=remote.request('/storage/v1/object/authenticated/aurora-artifacts/'+source['path'],raw=True)
    require(len(data)==source['bytes'] and hashlib.sha256(data).hexdigest()==checksum,'입력 파일 해시/크기가 다릅니다.')
    p=decode(data);require(config.get('skus')==len(p['series']) and config.get('weeks')==len(p['periods']),'등록 기간/품목 수가 다릅니다.')
    return p

def provision_public(remote,payload,project_id):
    project=str(uuid.UUID(project_id));data=canonical(payload);checksum=hashlib.sha256(data).hexdigest()
    projects=remote.request('/rest/v1/projects?select=id,project_type&id=eq.'+project)
    require(len(projects)==1 and projects[0]['project_type']=='forecast','수요예측 프로젝트를 확인하세요.')
    version=payload['version']
    require(isinstance(version,str) and 1<=len(version)<=80,'자료 버전을 확인하세요.')
    config=dict(mode='public_file_v1',skus=len(payload['series']),weeks=len(payload['periods']),input=dict(bucket='aurora-artifacts',path=f'{project}/inputs/{checksum}.json',sha256=checksum,bytes=len(data)))
    query='/rest/v1/datasets?project_id=eq.'+project+'&version=eq.'+quote(version,safe='')
    def existing():
        rows=remote.request(query+'&select=id,status,generator_config,dataset_kind');return rows[0] if rows else None
    row=existing()
    if row:
        require(row['generator_config']==config and row.get('dataset_kind')=='public_retail','같은 버전의 다른 입력을 덮어쓰지 않습니다.')
        if row['status']=='ready':read_public(remote,config,project);return dict(dataset_id=row['id'],status='ready',reused=True,sha256=checksum)
    else:
        ident=str(uuid.uuid4())
        remote.request('/rest/v1/datasets','POST',body=dict(id=ident,project_id=project,name=f"UCI 공개 거래 · {len(payload['series'])} SKU / {len(payload['periods'])}주",version=version,synthetic=False,dataset_kind='public_retail',status='validating',generator_config=config))
        row=existing();require(row is not None,'데이터 등록을 확인하세요.')
    path='/rest/v1/datasets?id=eq.'+row['id']
    try:
        remote.request(path,'PATCH',body=dict(status='validating'))
        try:remote.request('/storage/v1/object/aurora-artifacts/'+config['input']['path'],'POST',data=data)
        except RemoteError as e:
            if e.status not in (400,409):raise
        read_public(remote,config,project)
        remote.request(path,'PATCH',body=dict(status='ready'))
    except Exception:
        remote.request(path,'PATCH',body=dict(status='rejected'));raise
    return dict(dataset_id=row['id'],status='ready',reused=False,sha256=checksum)

def compute_public_job(remote,job):
    rows=remote.request('/rest/v1/runs?select=project_id&id=eq.'+str(uuid.UUID(job['id'])))
    require(len(rows)==1,'작업 프로젝트가 없습니다.')
    project=str(uuid.UUID(rows[0]['project_id']));payload=read_public(remote,job['generator_config'],project)
    options=job['config'];require(isinstance(options,dict) and not set(options)-{'policy_inputs'},'공개 거래 실행 설정을 확인하세요.')
    result=evaluate_public(payload,options.get('policy_inputs'))
    artifacts=[]
    with tempfile.TemporaryDirectory(prefix='aurora-artifacts-') as td:
        export_result(result,td)
        for name in NAMES:
            data=(Path(td)/name).read_bytes();require(0<len(data)<=MAX_ARTIFACT,'산출물 크기 한도입니다.')
            sha=hashlib.sha256(data).hexdigest();mime='application/json' if name.endswith('.json') else 'text/markdown' if name.endswith('.md') else 'text/csv'
            path=f"{project}/runs/{uuid.UUID(job['id'])}/attempt-{job['attempt']}/{sha}/{name}"
            try:remote.request('/storage/v1/object/aurora-artifacts/'+path,'POST',data=data,content_type=mime)
            except RemoteError as e:
                if e.status not in (400,409):raise
                existing=remote.request('/storage/v1/object/authenticated/aurora-artifacts/'+path,raw=True,max_bytes=MAX_ARTIFACT)
                require(hashlib.sha256(existing).hexdigest()==sha,'기존 산출물 해시가 다릅니다.')
            artifacts.append(dict(name=name,bucket='aurora-artifacts',path=path,sha256=sha,bytes=len(data),mime=mime))
    return dict(summary=public_summary(result),artifacts=artifacts)

if __name__=='__main__':
    from .registered import Remote,env_file
    p=argparse.ArgumentParser();p.add_argument('--input',required=True,type=Path);p.add_argument('--project',required=True);p.add_argument('--env-file',required=True,type=Path);a=p.parse_args()
    payload=decode(a.input.read_bytes());env_file(a.env_file)
    print(json.dumps(provision_public(Remote(),payload,a.project),ensure_ascii=False,indent=2))
