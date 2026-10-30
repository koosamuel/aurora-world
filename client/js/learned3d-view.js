import {samplingCloud} from './sampling-connection.js';
export function initLearned3D(){
 const $=id=>document.getElementById('l3-'+id);
 let source=null,prepared=null,available=false,busy=false,epoch=0,viewer=null,urls=[],unavailableReason='';
 const say=t=>{$('status').textContent=t;};
 function controls(){
  $('run').disabled=!available||!source||busy||samplingCloud();
  $('confirm').disabled=!prepared||busy||!$('foreground-confirmed').checked||samplingCloud();
 }
 function clear(){prepared=null;$('preflight').hidden=true;$('result').hidden=true;$('foreground-confirmed').checked=false;for(const u of urls)URL.revokeObjectURL(u);urls=[];viewer?.clear();controls();}
 async function api(path,opts={}){
  const r=await fetch('./api/learned3d/'+path,{...opts,signal:AbortSignal.timeout(90000)});
  const d=await r.json();if(!r.ok)throw new Error(d.error||'HTTP '+r.status);return d;
 }
 async function artifact(id,m){
  if(!['preview.png','mask.png','preflight.json','condition.png','model.glb','report.json'].includes(m.file))throw new Error('산출물 이름 오류');
  const r=await fetch('./api/learned3d/artifacts/'+id+'/'+m.file,{signal:AbortSignal.timeout(30000)});if(!r.ok)throw new Error('산출물 조회 오류');
  const bytes=await r.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
  if(bytes.byteLength!==m.bytes||hash!==m.sha256)throw new Error('산출물 무결성 오류');
  const url=URL.createObjectURL(new Blob([bytes],{type:m.file.endsWith('.glb')?'model/gltf-binary':m.file.endsWith('.png')?'image/png':'application/json'}));urls.push(url);return {bytes,url};
 }
 $('form').addEventListener('submit',async e=>{
  e.preventDefault();if(busy||!source||samplingCloud()||!available)return;const ticket=epoch,s=source;clear();busy=true;controls();say('전경 마스크·미리보기 준비 중… 아직 3D 생성하지 않습니다.');
  try{
   const file=$('file').files[0];if(!file||!file.size||file.size>2*1024*1024)throw new Error('2MiB 이하 이미지 필요');
   const data=await new Promise((ok,no)=>{const reader=new FileReader();reader.onload=()=>ok(reader.result.split(',')[1]);reader.onerror=()=>no(new Error('파일 읽기 실패'));reader.readAsDataURL(file);});if(ticket!==epoch)return;
   const row=await api('runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_base64:data,dimensions_mm:s.dimensions_mm,view:'single',source_id:s.id,source_checksum:s.checksum})});
   if(ticket!==epoch)return;if(row.status!=='prepared'||!/^[0-9a-f]{32}$/.test(row.id))throw new Error('입력 준비 상태 오류');
   for(const m of row.preparation_artifacts){const {url}=await artifact(row.id,m);if(ticket!==epoch)return;if(m.file==='preview.png')$('preview').src=url;if(m.file==='mask.png')$('mask').src=url;}
   if(ticket!==epoch)return;prepared=row;$('preflight-metrics').textContent=`그림의 어두운 픽셀 보존 ${(100*row.preflight.ink_coverage).toFixed(1)}% · 전경 영역 ${(100*row.preflight.foreground_fraction).toFixed(1)}% · 부위 완전성 미검증`;
   $('preflight').hidden=false;say('미리보기에서 귀·몸통·팔다리 보존을 확인한 뒤 생성 버튼을 누르세요.');
  }catch(e){if(ticket===epoch)say('입력 준비 실패: '+e.message);}finally{busy=false;controls();}
 });
 $('foreground-confirmed').addEventListener('change',controls);
 $('confirm').addEventListener('click',async()=>{
  if(!prepared||busy||!$('foreground-confirmed').checked||samplingCloud())return;const ticket=epoch,p=prepared;busy=true;controls();
  try{
   let row=await api('runs/'+p.id+'/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preparation_sha256:p.preparation_sha256,foreground_confirmed:true})});
   prepared=null;controls();
   while(['queued','running'].includes(row.status)){
    if(ticket!==epoch)return;say(row.engine+' · '+row.status+' · 로컬 3D 복원 중…');await new Promise(ok=>setTimeout(ok,2000));row=await api('runs/'+row.id);
   }
   if(ticket!==epoch)return;if(row.status!=='succeeded')throw new Error(row.error||'생성 실패');
   $('downloads').replaceChildren();let glb;
   for(const m of row.artifacts){const {bytes,url}=await artifact(row.id,m);if(ticket!==epoch)return;const a=document.createElement('a');a.href=url;a.download=m.file;a.textContent=m.file;a.className='secondary';a.style.marginRight='16px';$('downloads').append(a);if(m.file==='condition.png')$('condition').src=url;if(m.file==='model.glb')glb=bytes;}
   $('preflight').hidden=true;$('result').hidden=false;$('report').textContent=JSON.stringify(row,null,2);
   if(!viewer){const {createSampleViewer}=await import('../vendor/sample-viewer.js');viewer=createSampleViewer($('viewer'));}viewer.clear();await viewer.load(glb);if(ticket!==epoch)return;
   say(row.engine+' 생성 완료 · 형상/뒷면과 디자인 일치를 검토하세요. 무채색 표시는 텍스처 생성·제작 승인이 아닙니다.');
  }catch(e){if(ticket===epoch)say('생성/표시 실패: '+e.message);}finally{busy=false;controls();}
 });
 $('file').addEventListener('change',()=>{epoch++;clear();});
 window.addEventListener('generation-source-selected',e=>{
  epoch++;const s=e.detail.source;source=s?.family==='BUNNY'&&s?.data_kind==='synthetic'?s:null;clear();
  $('source').textContent=source?'연결 명세: '+source.id+' · '+source.checksum.slice(0,12):'기존 U21에서 U20 토끼 명세를 선택하세요.';controls();
 });
 window.addEventListener('sampling-connection-changed',()=>{epoch++;source=null;clear();say(unavailableReason||'로컬 모드에서 토끼 명세를 다시 선택하세요.');});
 (async()=>{try{const c=await api('capabilities');available=c.available===true&&c.requires_confirmation===true;$('engine').textContent=c.engine?c.engine+' · 로컬 전용 · '+(c.engine==='TripoSG-scribble'?'스케치/설명 조건의 무채색 형상 생성':'이미지 기반 컬러 형상 생성'):'로컬 모델 미설정';unavailableReason=available?'':c.available?'서버를 새 버전으로 다시 시작하세요. 입력 확인을 지원하지 않는 서버에서는 생성하지 않습니다.':c.reason||'로컬 모델 설치 필요';say(available?'스케치를 선택하고 입력을 먼저 준비하세요.':unavailableReason);}catch{say('로컬 서버 연결 필요');}controls();})();
}
