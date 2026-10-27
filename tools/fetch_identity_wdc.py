"""Download pinned official WDC Products archives without overwriting local originals."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile
from prepare_identity_wdc import ARCHIVES, SOURCE


def fetch(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    files=[]
    for name,expected in ARCHIVES.items():
        url='https://data.dws.informatik.uni-mannheim.de/largescaleproductcorpus/data/wdc-products/'+name
        with urlopen(Request(url,headers={'User-Agent':'Aurora-World-Research/0.1'}),timeout=45) as response:
            data=response.read(40*1024*1024+1);final=response.url
        if len(data)>40*1024*1024 or sha256(data).hexdigest()!=expected:raise ValueError('source changed; review before use')
        path=output/name;path.write_bytes(data)
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:raise ValueError('ZIP CRC failure')
        files.append(dict(file=name,url=url,resolved_url=final,bytes=len(data),sha256=expected))
    from datetime import datetime, timezone
    manifest=dict(source=SOURCE,acquired_at=datetime.now(timezone.utc).isoformat(),files=files,license_status='Official free public download; no data-specific redistribution license established. Local use; do not bundle raw content with public code.')
    (output/'download_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();print(json.dumps(fetch(args.output),indent=2))
