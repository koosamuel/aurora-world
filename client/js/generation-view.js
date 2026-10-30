import {samplingCloud,samplingWritable,samplingRequest,samplingArtifact,samplingHistory,cancelSampling} from './sampling-connection.js';
// U21: local queued geometric generation; Pages can inspect saved outputs only.
export function initGeneration(){
 const $=id=>document.getElementById(id);let local=false,catalog=null,pending=false,row=null,viewers=null,serial=0,urls=[];
 const say=t=>$('generation-status').textContent=t;
 async function request(url,options={}){return samplingRequest(url,options);}
 function current(){return catalog?.sources.find(x=>x.id===$('generation-source').value);}
 function controls(){$('generation-run').disabled=pending||!current()||(samplingCloud()&&!samplingWritable());$('generation-source').disabled=pending;$('generation-seed').disabled=pending||!(local||samplingWritable());}
 function describe(){const s=current();if(!s)return;window.dispatchEvent(new CustomEvent('generation-source-selected',{detail:{source:s}}));$('generation-source-detail').textContent=`${s.data_kind==='mixed'?'공개 ABO 형상 + 가상 목표 치수':'U20 자체 합성 명세'} · 너비 ${s.dimensions_mm.width} × 높이 ${s.dimensions_mm.height} × 깊이 ${s.dimensions_mm.depth} mm · ${s.data_kind==='mixed'?'공개 쿠션의 텍스처는 유지하며 크기를 변환합니다. 실제 상품 치수가 아닙니다.':'원화의 자유로운 해석 대신 정해진 부위 기하로 후보를 생성합니다.'}`;}
 async function refresh(selectId){const ticket=++serial;const data=await request((local||samplingCloud())?'./api/generation/catalog':'./demo/generation/catalog.json');if(ticket!==serial)return;catalog=data;const prev=selectId||$('generation-source').value;$('generation-source').replaceChildren(...data.sources.map(s=>new Option(s.name,s.id)));if(data.sources.some(x=>x.id===prev))$('generation-source').value=prev;describe();controls();}
 const artifactUrl=(run,file)=>local?`./api/generation/artifacts/${encodeURIComponent(run.id)}/${encodeURIComponent(file)}`:`./demo/generation/${run.id}/${file}`;
 async function artifact(run,meta){if(samplingCloud())return samplingArtifact(run,meta);if(!/^[a-z][a-z0-9.-]+$/.test(meta.file))throw new Error('파일 경로 형식을 확인하세요.');const r=await fetch(artifactUrl(run,meta.file),{signal:AbortSignal.timeout(30000)});if(!r.ok)throw new Error('생성 파일 응답 '+r.status);const bytes=await r.arrayBuffer();if(bytes.byteLength!==meta.bytes)throw new Error('생성 파일 크기가 다릅니다.');const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');if(hash!==meta.sha256)throw new Error('생성 파일 SHA-256이 다릅니다.');return bytes;}
 async function show(run){
  const ticket=++serial;row=run;const report=run.result.report;const files=run.result.artifacts;const byName=new Map(files.map(f=>[f.file,f]));
  $('generation-result').hidden=false;$('generation-json').textContent=JSON.stringify(report,null,2);$('generation-metrics').replaceChildren();
  for(const c of report.candidates){const tr=document.createElement('tr');for(const value of [c.method,`${c.mesh_parts} / ${c.triangles}`,['width','height','depth'].map(k=>c.dimensions_mm[k].toFixed(1)).join(' × '),c.max_dimension_error_mm.toFixed(5),c.generation_seconds.toFixed(3)+'초']){const td=document.createElement('td');td.textContent=value;tr.append(td);}$('generation-metrics').append(tr);$('generation-'+c.id+'-method').textContent=c.method+' · '+(c.data_kind==='mixed'?'공개 형상 변환':'자체 합성 기하');}
  const conditions=report.candidates[1].must_have_review;
  $('generation-conditions').textContent='자동 검사: 형상 경계 치수. 사람 확인 필요: '+(conditions.length?conditions.map(x=>x.condition).join(' / ')+' · ':'')+'색상·원단/질감·외관·봉제 적합성. 2D 투영은 기하 표현이며 공개 모델의 텍스처를 재현하지 않습니다.';
  $('generation-attribution').textContent=report.source.attribution?report.source.attribution+' · '+report.source.license+' · '+report.source.license_url+' · 변경: 가상 치수로 비균일 크기 변환.':'출처: '+report.source.provenance;
  $('generation-downloads').replaceChildren();
  for(const meta of files){const button=document.createElement('button');button.className='secondary';button.textContent=meta.file;button.addEventListener('click',async()=>{button.disabled=true;try{const bytes=await artifact(run,meta);const u=URL.createObjectURL(new Blob([bytes],{type:meta.file.endsWith('.glb')?'model/gltf-binary':'application/octet-stream'}));const a=document.createElement('a');a.href=u;a.download=meta.file;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);say(`${meta.file} · 크기/SHA-256 확인 후 다운로드했습니다.`);}catch(e){say('다운로드 실패: '+e.message);}finally{button.disabled=false;}});$('generation-downloads').append(button);}
  if(!viewers){const module=await import('../vendor/sample-viewer.js');viewers=Object.fromEntries(['baseline','candidate'].map(k=>[k,module.createSampleViewer($('generation-'+k+'-3d'))]));document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>viewers[b.dataset.view].view(b.dataset.side==='true')));}
  for(const viewer of Object.values(viewers))viewer.clear();for(const key of ['baseline','candidate'])for(const view of ['front','side'])$('generation-'+key+'-'+view).removeAttribute('src');
  for(const u of urls)URL.revokeObjectURL(u);urls=[];
  await Promise.all(['baseline','candidate'].map(async key=>{
   const bytes=await artifact(run,byName.get(key+'.glb'));if(ticket!==serial)return;await viewers[key].load(bytes);
   for(const view of ['front','side']){const b=await artifact(run,byName.get(key+'.'+view+'.svg'));if(ticket!==serial)return;const u=URL.createObjectURL(new Blob([b],{type:'image/svg+xml'}));urls.push(u);$('generation-'+key+'-'+view).src=u;}
  }));
  if(ticket===serial){say((samplingCloud()?'새 Supabase 기하 생성 완료':local?'새 로컬 기하 생성 완료':'저장된 생성 결과 조회 완료')+' · GLB·2D 투영의 크기/SHA-256을 확인했습니다. 현업 승인·제작/효과 검증은 아직 하지 않았습니다.');if(local&&!samplingCloud())window.dispatchEvent(new CustomEvent('digital-sample-generated',{detail:{kind:'geometry',run_id:run.id}}));}
 }
 $('generation-source').addEventListener('change',()=>{describe();$('generation-result').hidden=true;say('입력을 바꿨습니다. 생성/저장 결과 조회를 실행하세요.');});
 window.addEventListener('sampling-brief-selected',e=>{if((local||samplingCloud())&&!pending)refresh(e.detail.id).catch(x=>say('명세 연결 실패: '+x.message));});
 $('generation-run').addEventListener('click',async()=>{
  if(pending||!current())return;pending=true;controls();$('generation-result').hidden=true;say((local||samplingCloud())?'생성 요청을 보내고 있습니다…':'저장된 생성 결과를 읽고 있습니다…');
  try{
   const source=current();if(local||samplingCloud()){const seed=Number($('generation-seed').value);if(!Number.isInteger(seed)||seed<0||seed>2147483647)throw new Error('시드는0~2147483647 정수입니다.');row=await request('./api/generation/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:source.id,source_checksum:source.checksum,seed,request_key:crypto.randomUUID()})});try{sessionStorage.setItem(samplingCloud()?'aurora-generation-cloud-run':'aurora-generation-run',row.id);}catch{}
    for(let i=0;i<660&&['queued','running'].includes(row.state);i++){say(row.state==='queued'?'생성 작업 대기 중…':'명세 치수에 맞춰 형상·투영·검사 보고서를 생성하고 있습니다…');await new Promise(r=>setTimeout(r,1000));row=await request('./api/generation/runs/'+row.id);}
    if(row.state!=='succeeded')throw new Error(row.error||'아직 생성 중입니다. 잠시 후 다시 확인하세요.');try{sessionStorage.setItem(samplingCloud()?'aurora-generation-cloud-run':'aurora-generation-run',row.id);}catch{}
   }else{const id=catalog.demo_runs[source.id];if(!/^demo-[0-9a-f]{16}$/.test(id))throw new Error('저장된 생성 결과가 없습니다.');row=await request('./demo/generation/'+id+'/run.json');}
   await show(row);
  }catch(e){say('생성/조회 실패: '+e.message);}finally{pending=false;controls();}
 });
 async function start(){pending=true;local=false;controls();try{if(!samplingCloud()&&['localhost','127.0.0.1'].includes(location.hostname)){const h=await fetch('./api/health',{signal:AbortSignal.timeout(3000)});if(h.ok)local=(await h.json()).mode==='local';}
  $('generation-mode').textContent=samplingCloud()?'U21 · Supabase 실제 생성':local?'U21 · 로컬 새 생성':'U21 · 저장된 생성 결과';$('generation-run').textContent=(local||samplingCloud())?'샘플 2개 생성·비교':'저장된 샘플 비교';await refresh();say(samplingCloud()?(catalog.worker_online?'Supabase 워커 온라인 · 명세/시드로 새 샘플을 생성하세요.':'Supabase 워커 대기 · 개발 PC의 샘플 워커가 켜져야 계산합니다.'):local?'명세·시드를 정하고 기준선과 후보를 생성하세요.':'게시 화면은 저장된 생성 결과를 비교합니다. 새 시드·명세의 생성은 로컬 실행에서 제공합니다.');
  if(local||samplingCloud()){let id;try{id=sessionStorage.getItem(samplingCloud()?'aurora-generation-cloud-run':'aurora-generation-run');}catch{}if(id&&(samplingCloud()?/^[0-9a-f-]{36}$/:/^[0-9a-f]{32}$/).test(id)){const saved=await request('./api/generation/runs/'+id);if(saved.state==='succeeded'){if(catalog.sources.some(x=>x.id===saved.source.id))$('generation-source').value=saved.source.id;describe();await show(saved);}}}
 }catch(e){say('생성 자료 준비 실패: '+e.message);}finally{pending=false;controls();}}
 window.addEventListener('sampling-connection-changed',()=>{serial++;catalog=null;row=null;$('generation-result').hidden=true;start();});
 window.addEventListener('sampling-cloud-run-selected',e=>{if(e.detail.kind==='geometry'&&samplingCloud()){show(e.detail).catch(x=>say(x.message));}});
 start();
}
