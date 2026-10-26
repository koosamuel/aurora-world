from pathlib import Path
import urllib.request,json,hashlib,concurrent.futures
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
base=parser.parse_args().root
raw=base/'04_데이터/원본/공개연구데이터';raw.mkdir(parents=True,exist_ok=True)
records=[]
def download(item):
 name,url=item;target=raw/name;target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():
  with urllib.request.urlopen(url,timeout=60) as r:payload=r.read()
  if name.endswith('.pdf') and not payload.startswith(b'%PDF'):raise ValueError('Not a PDF: '+name)
  target.write_bytes(payload)
 payload=target.read_bytes()
 return {'file':name,'source_url':url,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'retrieved':'2026-10-26','scope':'complete_file'}
items=[
 ('M4/Weekly-train.csv','https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/Dataset/Train/Weekly-train.csv'),
 ('M4/Weekly-test.csv','https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/Dataset/Test/Weekly-test.csv'),
 ('M4/M4-info.csv','https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/Dataset/M4-info.csv'),
 ('M4/README.md','https://raw.githubusercontent.com/Mcompetitions/M4-methods/master/README.md'),
 ('QuickDraw/README.md','https://raw.githubusercontent.com/googlecreativelab/quickdraw-dataset/master/README.md'),
 ('papers/A Neural Representation of Sketch Drawings.pdf','https://research.google.com/pubs/archive/46008.pdf'),
 ('papers/Correlated daily time series and forecasting in the M4 competition.pdf','https://arxiv.org/pdf/2003.12796'),
 ('papers/M4 Competitors Guide.pdf','https://www.unic.ac.cy/test/wp-content/uploads/sites/2/2018/09/M4-Competitors-Guide.pdf'),
]
errors=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 tasks={pool.submit(download,item):item for item in items}
 for future in concurrent.futures.as_completed(tasks):
  item=tasks[future]
  try:
   res=future.result();records.append(res);print(item[0],res['bytes'],flush=True)
  except Exception as e:
   errors.append({'file':item[0],'source_url':item[1],'error':str(e)});print('Unavailable:',item[0],str(e),flush=True)
for category in ['bear','cat','rabbit']:
 url='https://storage.googleapis.com/quickdraw_dataset/full/simplified/'+category+'.ndjson'
 target=raw/'QuickDraw'/f'{category}.first300.ndjson'
 if not target.exists():
  with urllib.request.urlopen(url,timeout=60) as response:
   payload=b''.join(response.readline() for _ in range(300))
  lines=payload.splitlines();assert len(lines)==300
  for line in lines:assert json.loads(line)['word']==category
  target.write_bytes(payload)
 data=target.read_bytes();records.append({'file':str(target.relative_to(raw)),'source_url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'retrieved':'2026-10-26','scope':'first_300_lines_streamed_not_full_category','license':'CC-BY-4.0'})
 print(category,'300 sketches',len(data),flush=True)
(raw/'download_manifest.json').write_text(json.dumps({'schema_version':'aurora-public-sources-v1','records':records,'unavailable':errors,'M4_license_note':'Public organizer distribution; no dataset redistribution license asserted. Original data stays outside code repository.','quickdraw_license':'CC-BY-4.0; attribution Google, Inc. / Quick, Draw! contributors; derivatives labeled.'},ensure_ascii=False,indent=2))
