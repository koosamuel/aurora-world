"""Execute synthetic U22 scenarios against real review transitions and export them."""
from pathlib import Path
import argparse,copy,json,shutil,tempfile,uuid
from aurora.sample_reviews import ReviewStore,Denied
from aurora.sampling import BriefStore,seed,Conflict
from aurora.identity import serialized
from aurora.generation import digest

def build(root,out):
    root=Path(root);out=Path(out)
    if out.exists():raise ValueError('Use a new output directory.')
    out.mkdir(parents=True);(out/'products').mkdir();(out/'assets').mkdir()
    rejected=[]
    with tempfile.TemporaryDirectory() as temp:
        work=Path(temp);(work/'client').symlink_to(root/'client',target_is_directory=True)
        briefs=BriefStore(work/'briefs.sqlite');seed(briefs,root);s=ReviewStore(work,briefs)
        tokens={k:s.session(dict(persona_id=k))['token'] for k in ('designer','reviewer','approver','viewer')}
        candidates=s.catalog()['candidates']
        def event(pid,action,status='pass',role=None):
            r=s.get(pid);v=r['revisions'][-1]
            req=dict(product_id=pid,version=v['version'],expected_seq=r['seq'],action=action,
                     comment='합성 시나리오 · '+action,checks=[dict(id=c['id'],status=status,note='합성 검토 · 현업/제작 판정 아님') for c in v['checklist']] if action=='review' else [],request_key=uuid.uuid4().hex)
            role=role or {'submit':'designer','review':'reviewer','approve':'approver','hold':'reviewer','request_changes':'reviewer'}[action]
            return s.event(tokens[role],req)
        def reject(label,fn):
            try:fn()
            except (ValueError,Denied,Conflict) as e:rejected.append(dict(case=label,result='rejected',reason=str(e)))
            else:raise AssertionError('Expected rejection: '+label)
        for pid in ['SYN-BUNNY','SYN-CAT','SYN-FRUIT','SYN-COW','SYN-DOG','SYN-CACTUS']:
            kind='ai' if pid in ('SYN-BUNNY','SYN-CAT','SYN-FRUIT') else 'geometry'
            pair=[c for c in candidates if c['product_id']==pid and c['kind']==kind]
            for i,c in enumerate(pair):
                r=s.get(pid)
                req=dict(candidate_id=c['id'],candidate_checksum=c['checksum'],parent_version=r['head_version'] if r else None,expected_seq=r['seq'] if r else 0,change_reason='합성 최초 후보' if i==0 else '합성 검토 의견에 따라 다른 U21 후보로 교체',request_key=uuid.uuid4().hex)
                s.revision(tokens['designer'],req)
                if i==0:
                    event(pid,'submit');event(pid,'review',status='pass' if pid=='SYN-CAT' else 'fail')
                    reject(pid+' viewer cannot approve',lambda:event(pid,'approve',role='viewer'))
                    if pid=='SYN-CAT':event(pid,'approve')
                    else:
                        reject(pid+' failed checklist',lambda:event(pid,'approve'))
                        event(pid,'request_changes')
                else:
                    if pid=='SYN-CAT':continue
                    event(pid,'submit')
                    if pid=='SYN-CACTUS':
                        reject(pid+' missing review',lambda:event(pid,'approve'));continue
                    event(pid,'review',status='fail' if pid=='SYN-FRUIT' else 'pass')
                    if pid=='SYN-FRUIT':event(pid,'hold')
                    else:
                        event(pid,'approve')
                        if pid=='SYN-DOG':event(pid,'hold',role='approver')
            r=s.export(pid);(out/'products'/(pid+'.json')).write_bytes(serialized(r))
            for rev in r['revisions']:
                for a in rev['assets']:
                    target=out/'assets'/a['asset']
                    if not target.exists():shutil.copy2(s.asset(a['asset']),target)
        cat=s.catalog();cat.update(mode='saved_synthetic',authentication='saved_demo_only');(out/'catalog.json').write_bytes(serialized(cat))
    (out/'rejections.json').write_bytes(serialized(rejected))
    manifest=[dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=digest(p.read_bytes())) for p in sorted(out.rglob('*')) if p.is_file()]
    (out/'manifest.json').write_bytes(serialized(dict(schema_version='aurora-review-demo-manifest-v1',files=manifest)))
    print(json.dumps(dict(products=len(cat['products']),revisions=sum(len(json.loads(p.read_text())['revisions']) for p in (out/'products').glob('*.json')),rejected=len(rejected),files=len(manifest)+1)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(Path(__file__).resolve().parents[1],a.output)
