// U22 stores local synthetic review events; Pages remains read-only.
export function initSampleReviews(){
 const $=id=>document.getElementById(id);let local=false,cat=null,record=null,actor=null,token=null,busy=false,manifest=null,serial=0,urls=[];
 const states={draft:'초안',in_review:'검토 중',changes_requested:'수정 요청',on_hold:'보류',approved:'가상 디지털 승인',superseded:'이전 버전'};
 const actions={revision_created:'후보 등록',superseded:'새 버전으로 대체',submit:'검토 요청',review:'조건 검토',request_changes:'수정 요청',hold:'보류·승인 철회',approve:'가상 디지털 승인',comment:'의견'};
 const permissions={submit:['designer'],review:['reviewer'],request_changes:['reviewer','approver'],hold:['reviewer','approver'],approve:['approver'],comment:['designer','reviewer','approver']};
 const say=t=>$('review-status').textContent=t;
 async function json(url,options={}){const r=await fetch(url,{...options,signal:AbortSignal.timeout(15000)});const body=await r.json();if(!r.ok){const e=new Error(body.error||'응답 '+r.status);e.status=r.status;throw e;}return body;}
 const selected=()=>record?.revisions.find(r=>r.version===Number($('review-version').value));
 const source=()=>cat?.candidates.find(c=>c.id===$('review-candidate').value);
 async function verified(url,meta){if(!meta)throw new Error('검토 파일 명세 없음');const r=await fetch(url,{signal:AbortSignal.timeout(15000)});if(!r.ok)throw new Error('검토 파일 응답 '+r.status);const data=await r.arrayBuffer();const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(v=>v.toString(16).padStart(2,'0')).join('');if(sha!==meta.sha256||data.byteLength!==meta.bytes)throw new Error('검토 파일 크기/SHA-256 불일치');return data;}
 async function getRecord(pid,exporting=false){
  if(!/^SYN-[A-Z0-9_-]+$/.test(pid))throw new Error('제품 ID 오류');
  if(local)return json('./api/sample-reviews/'+(exporting?'export/':'products/')+pid);
  const name='products/'+pid+'.json';const raw=await verified('./demo/reviews/'+name,manifest.files.find(f=>f.path===name));return JSON.parse(new TextDecoder().decode(raw));
 }
 function controls(){
  const v=selected(),role=actor?.role,head=v&&v.version===record.head_version;
  $('review-persona-apply').disabled=busy||!local;$('review-persona').disabled=busy||!local;
  $('review-new').disabled=busy||!local||role!=='designer'||!source()||!source().latest_brief;
  $('review-new').textContent=record?'수정본 등록':'첫 후보 등록';$('review-reason').disabled=busy||!local||role!=='designer';$('review-candidate').disabled=busy||!local||role!=='designer';
  $('review-send').disabled=busy||!local||!head||!permissions[$('review-action').value].includes(role)||(v.stale_brief&&$('review-action').value!=='comment');
  $('review-action').disabled=busy||!local||!head;$('review-comment').disabled=busy||!local||role==='viewer'||!head;
  $('review-download').disabled=busy||!record;
  for(const id of ['review-product','review-version','review-refresh'])$(id).disabled=busy;
  for(const e of $('review-checks').querySelectorAll('select,textarea'))e.disabled=busy||!local||role!=='reviewer'||!head||v.stale_brief||v.state!=='in_review';
 }
 function renderChecks(v){
  const previous=new Map((v.review?.payload.checks||[]).map(c=>[c.id,c]));$('review-checks').replaceChildren();
  for(const c of v.checklist){const tr=document.createElement('tr'),label=document.createElement('td'),status=document.createElement('td'),note=document.createElement('td');label.textContent=c.label;
   const s=document.createElement('select');s.dataset.check=c.id;s.setAttribute('aria-label',c.label+' 판정');for(const [value,text] of [['unreviewed','미검토'],['pass','검토 적합'],['fail','미충족']])s.add(new Option(text,value));s.value=previous.get(c.id)?.status||'unreviewed';status.append(s);
   const n=document.createElement('textarea');n.rows=2;n.maxLength=500;n.dataset.note=c.id;n.setAttribute('aria-label',c.label+' 메모');n.value=previous.get(c.id)?.note||'';note.append(n);tr.append(label,status,note);$('review-checks').append(tr);
  }
 }
 async function asset(a){if(!/^[0-9a-f]{64}\.(png|svg|glb)$/.test(a.asset))throw new Error('검토 자산 경로 오류');return verified((local?'./api/sample-reviews/assets/':'./demo/reviews/assets/')+a.asset,a);}
 async function show(){
  const ticket=++serial,v=selected();$('review-content').hidden=!v;controls();if(!v)return;
  $('review-summary').textContent=`${record.product_id} · 샘플 v${v.version} · ${states[v.state]} · ${v.active_approval?'현재 유효한 가상 승인':'현재 유효한 승인 없음'}${v.stale_brief?' · U20 명세 변경: 재생성·재검토 필요':''}`;
  $('review-version-detail').textContent=`명세 v${v.sample.source.brief.brief_version} · ${v.sample.kind}/${v.sample.candidate_id} · 수정 사유: ${v.change_reason} · ${v.visual_changed?'미리보기 변경':'미리보기 동일'}${v.brief_changed?' / 명세 변경':''}. 수정본/승인/부모·검토 해시는 서버의 별도 이력이며 U21 생성 보고서를 덮어쓰지 않습니다.`;
  $('review-assets').replaceChildren(...v.assets.map(a=>{const b=document.createElement('button');b.className='secondary small';b.textContent=a.file;b.onclick=async()=>{b.disabled=true;try{const raw=await asset(a);const u=URL.createObjectURL(new Blob([raw],{type:a.asset.endsWith('.glb')?'model/gltf-binary':a.asset.endsWith('.svg')?'image/svg+xml':'image/png'}));const link=document.createElement('a');link.href=u;link.download='sample-v'+v.version+'-'+a.file;link.click();setTimeout(()=>URL.revokeObjectURL(u),1000);say('샘플 v'+v.version+' 파일의 크기/SHA-256을 확인하고 다운로드했습니다.');}catch(e){say(e.message);}finally{b.disabled=false;}};return b;}));
  renderChecks(v);controls();$('review-history').replaceChildren();
  for(const e of record.events){const tr=document.createElement('tr');for(const value of [e.seq,'v'+e.version,actions[e.action],e.actor.name,e.recorded_at,e.payload.comment||e.payload.change_reason||('새 버전 '+(e.payload.new_version||''))]){const td=document.createElement('td');td.textContent=value;tr.append(td);}$('review-history').append(tr);}
  $('review-json').textContent=JSON.stringify(record,null,2);
  for(const u of urls)URL.revokeObjectURL(u);urls=[];
  const previous=record.revisions.find(r=>r.version===v.version-1);
  for(const [id,rev] of [['review-before',previous],['review-after',v]]){
   const el=$(id);el.removeAttribute('src');el.hidden=!rev;$(id+'-label').textContent=rev?'샘플 v'+rev.version+' · '+states[rev.state]:'이전 샘플 없음';
   if(rev){const a=rev.assets[0],raw=await asset(a);if(ticket!==serial)return;const u=URL.createObjectURL(new Blob([raw],{type:a.asset.endsWith('.svg')?'image/svg+xml':'image/png'}));urls.push(u);el.src=u;}
  }
  if(ticket===serial)say((local?'로컬 검토 이력 조회':'저장된 합성 검토 이력 조회')+' · 미리보기 크기/SHA-256 확인. '+(v.active_approval?'합성 디지털 승인입니다.':'현재 승인 상태를 확인하세요.'));
 }
 async function load(pid,version){record=pid?await getRecord(pid):null;$('review-version').replaceChildren(...(record?.revisions||[]).map(v=>new Option('v'+v.version+' · '+states[v.state],v.version)));if(record)$('review-version').value=String(version||record.head_version);const old=$('review-candidate').value;const choices=cat.candidates.filter(c=>!pid||c.product_id===pid);$('review-candidate').replaceChildren(...choices.map(c=>new Option(c.name+(c.latest_brief?'':' · 이전 명세'),c.id)));if(choices.some(c=>c.id===old))$('review-candidate').value=old;else if(choices.some(c=>c.latest_brief))$('review-candidate').value=choices.find(c=>c.latest_brief).id;try{sessionStorage.setItem('aurora-review-product',pid||'');}catch{}await show();}
 async function refresh(pid){
  cat=await json(local?'./api/sample-reviews/catalog':'./demo/reviews/catalog.json');if(!local)manifest=await json('./demo/reviews/manifest.json');
  $('review-persona').replaceChildren(...cat.actors.map(a=>new Option(a.name+' · '+a.role,a.id)));if(actor)$('review-persona').value=actor.id;
  const current=pid||$('review-product').value;$('review-product').replaceChildren(new Option('새 제품 후보 선택',''),...cat.products.map(p=>new Option(p.product_id+' · v'+p.head_version+' · '+states[p.state],p.product_id)));
  if(cat.products.some(p=>p.product_id===current))$('review-product').value=current;
  const old=$('review-candidate').value;$('review-candidate').replaceChildren(...cat.candidates.map(c=>new Option(c.name+(c.latest_brief?'':' · 이전 명세'),c.id)));if(cat.candidates.some(c=>c.id===old))$('review-candidate').value=old;
  await load($('review-product').value);
 }
 async function mutate(path,body){
  if(busy)return;busy=true;controls();say('검토 사건을 저장하고 최신 상태를 확인하고 있습니다…');
  try{const r=await json('./api/sample-reviews/'+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({...body,request_key:crypto.randomUUID()})});await refresh(r.product_id);window.dispatchEvent(new Event('digital-review-updated'));say('합성 '+(path==='revisions'?'수정본':'검토 사건')+' 저장 완료 · 이력 '+r.seq+' · 현재 상태를 다시 조회했습니다.');}
  catch(e){if(e.status===409)await refresh(record?.product_id);say('검토 저장 실패: '+e.message);}finally{busy=false;controls();}
 }
 $('review-persona-apply').onclick=async()=>{try{const r=await json('./api/sample-reviews/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona_id:$('review-persona').value})});token=r.token;actor=r.actor;try{sessionStorage.setItem('aurora-review-token',token);}catch{}$('review-actor').textContent=actor.name+' · '+actor.role+' · 합성 역할 시뮬레이션';controls();window.dispatchEvent(new Event('digital-review-updated'));}catch(e){say(e.message);}};
 $('review-product').onchange=()=>load($('review-product').value).catch(e=>say(e.message));$('review-version').onchange=()=>show().catch(e=>say(e.message));$('review-action').onchange=controls;$('review-candidate').onchange=controls;
 $('review-refresh').onclick=()=>refresh().catch(e=>say(e.message));
 $('review-new').onclick=()=>{const c=source();if(!c)return;if(record&&c.product_id!==record.product_id){say('선택한 제품과 생성 후보가 다릅니다. 새 제품 후보 선택 또는 같은 제품을 선택하세요.');return;}mutate('revisions',{candidate_id:c.id,candidate_checksum:c.checksum,parent_version:record?.head_version||null,expected_seq:record?.seq||0,change_reason:$('review-reason').value.trim()});};
 $('review-send').onclick=()=>{const action=$('review-action').value;mutate('events',{product_id:record.product_id,version:selected().version,expected_seq:record.seq,action,comment:$('review-comment').value.trim(),checks:action==='review'?[...$('review-checks').querySelectorAll('select')].map(s=>({id:s.dataset.check,status:s.value,note:[...$('review-checks').querySelectorAll('textarea')].find(n=>n.dataset.note===s.dataset.check).value})):[]});};
 $('review-download').onclick=async()=>{try{const r=await getRecord(record.product_id,true);const u=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download=r.product_id+'-review-history.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);say('샘플/조건 검토/승인 사건·해시 이력을 내보냈습니다.');}catch(e){say(e.message);}};
 for(const event of ['digital-sample-generated','sampling-brief-selected'])window.addEventListener(event,()=>{if(local&&!busy)refresh(record?.product_id).catch(e=>say(e.message));});
 (async()=>{busy=true;try{if(['127.0.0.1','localhost'].includes(location.hostname)){try{local=(await json('./api/health')).mode==='local';}catch{}}
  $('review-mode').textContent=local?'U22 · 로컬 합성 검토':'U22 · 저장된 합성 이력';let pid;try{pid=sessionStorage.getItem('aurora-review-product');token=sessionStorage.getItem('aurora-review-token');}catch{}
  if(local&&token){try{actor=(await json('./api/sample-reviews/session',{headers:{Authorization:'Bearer '+token}})).actor;$('review-actor').textContent=actor.name+' · '+actor.role+' · 합성 역할 시뮬레이션';}catch{token=null;}}
  await refresh(pid);if(!local&&!record&&cat.products.length){$('review-product').value=cat.products[0].product_id;await load($('review-product').value);}
  if(!record)say(local?'합성 역할을 적용한 뒤 완료한 U21 후보를 등록하세요.':'저장된 합성 검토 이력을 선택하세요.');
 }catch(e){say('검토 준비 실패: '+e.message);}finally{busy=false;controls();}})();
}
