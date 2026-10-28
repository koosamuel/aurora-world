import {samplingCloud,samplingWritable,samplingRequest} from './sampling-connection.js';
// U20 uses the loopback registry. Pages exposes saved synthetic briefs only.
export function initSampling(){
 const $=id=>document.getElementById(id);let local=false,records=[],selected=null,draft=null,validated=false,pending=false,seq=0,previewUrl=null;
 const fields=['sampling-height','sampling-width','sampling-depth','sampling-unit','sampling-fabric-code','sampling-fabric','sampling-condition'];
 const say=text=>$('sampling-status').textContent=text;
 async function request(path,options={}){return samplingRequest(path,options);}
 const version=r=>r.summary.brief_version;
 function controls(){
  $('sampling-version').disabled=pending;$('sampling-product').disabled=pending;$('sampling-file').disabled=!(local||samplingWritable())||pending;
  const latest=selected&&Math.max(...records.filter(r=>r.summary.product_id===selected.brief.product_id).map(version));
  $('sampling-revise').disabled=!(local||samplingWritable())||pending||!selected||version(selected)!==latest;
  $('sampling-validate').disabled=!(local||samplingWritable())||pending||!draft;$('sampling-save').disabled=!(local||samplingWritable())||pending||!draft||!validated;
  $('sampling-fields').disabled=!(local||samplingWritable())||pending||!draft;
  $('sampling-export').disabled=pending||!selected&&!draft;
 }
 function baseline(p,s){
  const b=p.baseline;const unknown=b.status==='unmeasured';
  $('sampling-baseline').textContent=unknown?'현행 기준 미측정 · 실물 횟수·기간·BOM 수정은 미확보입니다.':`가상 현행 기준 · 실물 ${s.physical_sample_count}개 / 제작 사건 ${s.physical_event_count}건 · 경과 ${s.elapsed_hours}시간 · BOM 오류 수정 ${s.bom_error_corrections}건 / 설계 변경 ${s.bom_design_changes}건`;
  $('sampling-events').textContent=b.time_definition+'\n측정기간 '+b.window_start+' ~ '+b.window_end+'\n'+(unknown?'미측정':b.physical_samples.map(e=>`제작 ${e.event_id}: ${e.occurred_at} / ${e.quantity}개`).concat(b.bom_changes.map(e=>`BOM ${e.event_id}: ${e.occurred_at} / ${e.reason==='error_correction'?'오류 수정':'설계 변경'} / ${e.description}`)).join('\n'));
 }
 function render(row){
  selected=row;draft=null;validated=false;const p=row.brief;const d=p.requirements.dimensions;
  $('sampling-name').textContent=p.product_name;$('sampling-version-label').textContent=`${p.product_id} · 명세 v${p.brief_version} · 원화 v${p.artwork_version}`;
  for(const k of ['height','width','depth'])$('sampling-'+k).value=d[k];$('sampling-unit').value=d.unit;
  $('sampling-fabric-code').value=p.requirements.fabric.code;$('sampling-fabric').value=p.requirements.fabric.description;$('sampling-condition').value=p.requirements.must_have.join('\n');
  $('sampling-colors').textContent=p.requirements.colors.map(c=>`${c.part}: ${c.name} (${c.hex})`).join(' · ');
  if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(new Blob([p.artwork.svg],{type:'image/svg+xml'}));$('sampling-artwork').src=previewUrl;
  $('sampling-provenance').textContent=p.rights.provenance;$('sampling-checksum').textContent='명세 SHA-256: '+row.checksum+'\n원화 SHA-256: '+p.artwork.sha256;
  $('sampling-json').textContent=JSON.stringify(p,null,2);baseline(p,row.summary);controls();window.dispatchEvent(new CustomEvent('sampling-brief-selected',{detail:{id:`u20:${p.product_id}:${p.brief_version}`}}));
 }
 async function choose(){
  const ticket=++seq;const pid=$('sampling-product').value,v=Number($('sampling-version').value);
  try{const r=(local||samplingCloud())?await request(`./api/sampling/briefs/${encodeURIComponent(pid)}/${v}`):records.find(r=>r.summary.product_id===pid&&version(r)===v);if(ticket!==seq)return;if(!r)throw new Error('명세를 찾을 수 없습니다.');render(r);say(samplingCloud()?'Supabase 합성 명세입니다. 수정/등록은 runner·admin 로그인과 실행 워커가 필요합니다.':local?'로컬에 등록된 합성 명세입니다. 수정본을 만들거나 파일을 검증할 수 있습니다.':'저장된 합성 명세 미리보기입니다. 파일 검증·버전 저장은 로컬 실행에서 사용합니다.');}
  catch(e){if(ticket===seq)say('불러오기 실패: '+e.message);}
 }
 function versions(){const pid=$('sampling-product').value;$('sampling-version').replaceChildren(...records.filter(r=>r.summary.product_id===pid).sort((a,b)=>version(b)-version(a)).map(r=>new Option(`명세 v${version(r)} · 원화 v${r.summary.artwork_version}`,String(version(r)))));}
 async function reload(pid,v){
  const data=(local||samplingCloud())?await request('./api/sampling/briefs'):(await request('./demo/sampling/catalog.json')).records;records=data;
  const names=new Map(data.map(r=>[r.summary.product_id,r.summary.product_name]));$('sampling-product').replaceChildren(...[...names].map(([id,name])=>new Option(name,id)));
  if(pid&&names.has(pid))$('sampling-product').value=pid;versions();if(v)$('sampling-version').value=String(v);await choose();
 }
 $('sampling-product').addEventListener('change',()=>{versions();choose();});$('sampling-version').addEventListener('change',choose);
 $('sampling-revise').addEventListener('click',()=>{
  if(!selected||!(local||samplingWritable()))return;draft=structuredClone(selected.brief);draft.brief_version++;draft.previous_checksum=selected.checksum;validated=false;
  $('sampling-version-label').textContent=`${draft.product_id} · 명세 v${draft.brief_version} 수정 중 · 원화 v${draft.artwork_version}`;
  say('새 명세 버전의 수정본입니다. 치수·원단·필수 조건을 수정하고 검증한 뒤 등록하세요. 원화·색상·현행 사건의 변경은 합성 명세 JSON 파일로 입력합니다.');controls();
 });
 function form(){if(!draft)return null;const p=structuredClone(draft);for(const k of ['height','width','depth'])p.requirements.dimensions[k]=Number($('sampling-'+k).value);p.requirements.dimensions.unit=$('sampling-unit').value;p.requirements.fabric={code:$('sampling-fabric-code').value,description:$('sampling-fabric').value};p.requirements.must_have=$('sampling-condition').value.split('\n').filter(s=>s.length);return p;}
 fields.forEach(id=>$(id).addEventListener('input',()=>{validated=false;controls();}));
 $('sampling-file').addEventListener('change',async e=>{
  const file=e.target.files[0];if(!file)return;pending=true;validated=false;draft=null;controls();
  try{if(file.size>512*1024)throw new Error('합성 명세 JSON은 512 KiB 이하입니다.');const raw=await file.text();const r=await request('./api/sampling/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:raw});render(r);draft=structuredClone(r.brief);validated=true;say('합성 명세 파일·원화 해시·단위·현행 기록 검증을 통과했습니다. 등록하면 현재 실행 모드에 불변 버전으로 저장합니다.');}
  catch(error){say('파일 검증 실패: '+error.message);}finally{pending=false;e.target.value='';controls();}
 });
 $('sampling-validate').addEventListener('click',async()=>{
  const body=form();if(!body||pending)return;pending=true;validated=false;controls();
  try{const r=await request('./api/sampling/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});draft=r.brief;validated=true;$('sampling-json').textContent=JSON.stringify(draft,null,2);say('입력 검증을 통과했습니다. 등록 시 최신 부모 버전도 다시 확인합니다.');}
  catch(e){say('입력 검증 실패: '+e.message);}finally{pending=false;controls();}
 });
 $('sampling-save').addEventListener('click',async()=>{
  if(!draft||!validated||pending)return;pending=true;controls();
  try{const r=await request('./api/sampling/briefs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form())});await reload(r.brief.product_id,r.brief.brief_version);say(r.reused?'이미 등록된 동일 명세입니다. 기존 버전을 유지합니다.':samplingCloud()?'새 명세 버전을 Supabase에 등록했습니다. 이전 버전과 원화는 보존됩니다.':'새 명세 버전을 로컬에 등록했습니다. 이전 버전과 원화는 보존됩니다.');}
  catch(e){say('등록 실패: '+e.message);}finally{pending=false;controls();}
 });
 $('sampling-export').addEventListener('click',()=>{
  const p=draft?form():selected?.brief;if(!p)return;const url=URL.createObjectURL(new Blob([JSON.stringify(p,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${p.product_id}-brief-v${p.brief_version}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
 async function start(){
  pending=true;local=false;controls();
  try{
   if(!samplingCloud()&&['localhost','127.0.0.1'].includes(location.hostname)){const h=await fetch('./api/health',{signal:AbortSignal.timeout(3000)});if(h.ok)local=(await h.json()).mode==='local';else if(h.status!==404)throw new Error('로컬 상태 응답 '+h.status);}
   $('sampling-mode').textContent=local?'U20 · 로컬 합성 등록':samplingCloud()?'U20 · Supabase 명세':'U20 · 저장된 합성 명세';await reload();
  }catch(e){say('명세 준비 실패: '+e.message);}finally{pending=false;controls();}
 }
 window.addEventListener('sampling-connection-changed',()=>{seq++;records=[];selected=null;draft=null;validated=false;$('sampling-artwork').removeAttribute('src');$('sampling-json').textContent='';$('sampling-checksum').textContent='';start();});
 window.addEventListener('sampling-validation-wait',e=>say('Supabase 명세 검증 '+(e.detail.state==='queued'?'대기 · 워커가 켜져 있어야 합니다.':'실행 중…')+' · '+e.detail.id));
 start();
}
