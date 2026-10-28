import {samplingCloud,samplingWritable,samplingRequest,samplingArtifact} from './sampling-connection.js';
// Learned 2D images are separate from the existing geometric 3D candidates.
export function initAISampling(){
 const $=id=>document.getElementById(id);let local=false,catalog=null,busy=false,urls=[],ticket=0;
 const say=t=>$('ai-status').textContent=t;
 async function json(url,options={}){return samplingRequest(url,options);}
 const current=()=>catalog?.sources.find(s=>s.id===$('ai-source').value);
 function controls(){$('ai-run').disabled=busy||!current()||((local||samplingCloud())&&!catalog?.runtime_available)||(samplingCloud()&&!samplingWritable());$('ai-source').disabled=busy;$('ai-seed').disabled=busy||!(local||samplingWritable());}
 async function refresh(id){catalog=await json((local||samplingCloud())?'./api/ai-sampling/catalog':'./demo/ai-sampling/catalog.json');const prev=id||$('ai-source').value;$('ai-source').replaceChildren(...catalog.sources.map(s=>new Option(s.name,s.id)));if(catalog.sources.some(s=>s.id===prev))$('ai-source').value=prev;controls();}
 async function bytes(row,meta){if(samplingCloud())return samplingArtifact(row,meta);if(!meta||!/^[a-z][a-z0-9.-]+$/.test(meta.file))throw new Error('AI 파일 경로 오류');const base=local?`./api/ai-sampling/artifacts/${row.id}/`:`./demo/ai-sampling/${row.id}/`;const r=await fetch(base+meta.file,{signal:AbortSignal.timeout(30000)});if(!r.ok)throw new Error('AI 파일 응답 '+r.status);const b=await r.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',b))].map(n=>n.toString(16).padStart(2,'0')).join('');if(b.byteLength!==meta.bytes||hash!==meta.sha256)throw new Error('AI 파일 크기/SHA-256이 다릅니다.');return b;}
 async function show(row){
  if(row.state!=='succeeded')throw new Error(row.error||'완료된 AI 결과가 없습니다.');
  const n=++ticket,report=row.result.report;
  if(report.schema_version!=='aurora-ai-sample-v1'||!report.learned_model)throw new Error('AI 보고서 형식 오류');
  $('ai-result').hidden=false;$('ai-report').textContent=JSON.stringify(report,null,2);
  const a=report.input_analysis;$('ai-interpretation').textContent=`픽셀 해석 후보: ${a.ranked.slice(0,3).map(x=>x.label+' '+x.cosine_similarity.toFixed(3)).join(' / ')} · 1·2위 차이 ${a.top_two_margin.toFixed(3)}${a.ambiguous?' · 모호하여 생성 프롬프트에는 일반 봉제인형 사용':''}. 코사인 유사도이며 정답 확률이 아닙니다. 후보 선택은 사람 확인이 필요합니다.`;
  $('ai-condition-review').textContent='조건 반영은 프롬프트 힌트입니다. 충족 판정은 미측정: '+report.conditions.map(c=>c.condition+' ['+(c.prompt_terms.join(', ')||'사람 검토 전용')+']').join(' / ');
  $('ai-prompt').textContent=report.prompt;
  for(const u of urls)URL.revokeObjectURL(u);urls=[];
  for(const name of ['input','preserve','reinterpret']){
   $('ai-'+name).removeAttribute('src');const data=await bytes(row,row.result.artifacts.find(a=>a.file===name+'.png'));if(n!==ticket)return;
   const url=URL.createObjectURL(new Blob([data],{type:'image/png'}));urls.push(url);$('ai-'+name).src=url;
   if(name!=='input'){const c=report.candidates.find(x=>x.id===name);$('ai-'+name+'-detail').textContent=`강도 ${c.strength} · ${c.generation_seconds.toFixed(1)}초 · 출력 분류 1위: ${c.interpretation.ranked[0].label}. 외관·필수 조건은 검수 전입니다.`;}
  }
  $('ai-downloads').replaceChildren(...row.result.artifacts.map(meta=>{const b=document.createElement('button');b.className='secondary small';b.textContent=meta.file;b.onclick=async()=>{b.disabled=true;try{const data=await bytes(row,meta);const u=URL.createObjectURL(new Blob([data],{type:meta.file.endsWith('.png')?'image/png':'application/json'}));const link=document.createElement('a');link.href=u;link.download=meta.file;link.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}catch(e){say(e.message);}finally{b.disabled=false;}};return b;}));
  say((samplingCloud()?'Supabase AI 추론 완료':local?'로컬 AI 추론 완료':'저장된 실제 AI 추론 조회 완료')+' · 원화·출력 PNG의 크기/SHA-256 확인. 2D 시각 후보이며 3D·치수·봉제 적합성은 미검증입니다.');
  if(local&&!samplingCloud())window.dispatchEvent(new CustomEvent('digital-sample-generated',{detail:{kind:'ai',run_id:row.id}}));
 }
 async function poll(row){
  for(let i=0;i<660&&['queued','running'].includes(row.state);i++){
   say(row.state==='queued'?'AI 작업 대기 중…':'CLIP 원화 해석·모델 해시 확인·이미지 2개 생성 중… (첫 실행은 수 분 걸릴 수 있습니다)');
   await new Promise(r=>setTimeout(r,1000));row=await json('./api/ai-sampling/runs/'+row.id);
  }
  if(row.state!=='succeeded')throw new Error(row.error||'추론이 아직 진행 중입니다. 새로고침하면 이어서 조회합니다.');await show(row);
 }
 $('ai-source').onchange=()=>{ticket++;$('ai-result').hidden=true;say('선택한 원화로 생성하거나 저장 결과를 조회하세요.');};
 window.addEventListener('sampling-brief-selected',e=>{if((local||samplingCloud())&&!busy)refresh(e.detail.id).catch(x=>say(x.message));});
 $('ai-run').onclick=async()=>{
  if(busy||!current())return;busy=true;controls();$('ai-result').hidden=true;
  try{const s=current();if(local||samplingCloud()){const seed=Number($('ai-seed').value);if(!Number.isInteger(seed)||seed<0||seed>2147483647)throw new Error('시드는0~2147483647 정수입니다.');const row=await json('./api/ai-sampling/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:s.id,source_checksum:s.checksum,seed,request_key:crypto.randomUUID()})});try{sessionStorage.setItem(samplingCloud()?'aurora-ai-cloud-run':'aurora-ai-run',row.id);}catch{}await poll(row);
   }else{const id=catalog.demo_runs[s.id];if(!/^ai-[0-9a-f]{16}$/.test(id))throw new Error('저장된 AI 결과가 없습니다.');await show(await json('./demo/ai-sampling/'+id+'/run.json'));}
  }catch(e){say('AI 생성/조회 실패: '+e.message);}finally{busy=false;controls();}
 };
 async function start(){busy=true;local=false;controls();try{
  if(!samplingCloud()&&['127.0.0.1','localhost'].includes(location.hostname)){try{local=(await json('./api/health')).mode==='local';}catch{}}
  $('ai-mode').textContent=samplingCloud()?'U21 · Supabase AI 추론':local?'U21 · 로컬 AI 추론':'U21 · 저장된 AI 결과';$('ai-run').textContent=(local||samplingCloud())?'원화 해석·AI 이미지 2개 생성':'저장된 AI 이미지 비교';await refresh();say(catalog.runtime_message);
  if(local||samplingCloud()){let id;try{id=sessionStorage.getItem(samplingCloud()?'aurora-ai-cloud-run':'aurora-ai-run');}catch{}if(id&&(samplingCloud()?/^[0-9a-f-]{36}$/:/^[0-9a-f]{32}$/).test(id)){const row=await json('./api/ai-sampling/runs/'+id);if(catalog.sources.some(s=>s.id===row.source.id))$('ai-source').value=row.source.id;await poll(row);}}
 }catch(e){say('AI 준비 실패: '+e.message);}finally{busy=false;controls();}}
 window.addEventListener('sampling-connection-changed',()=>{ticket++;catalog=null;$('ai-result').hidden=true;start();}); window.addEventListener('sampling-cloud-run-selected',e=>{if(e.detail.kind==='ai'&&samplingCloud()){show(e.detail).catch(x=>say(x.message));}});
start();
}
