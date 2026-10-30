import {samplingCloud} from './sampling-connection.js';
export function initLearned3D(){
 const $=id=>document.getElementById('l3-'+id);
 let source=null,prepared=null,available=false,busy=false,epoch=0,viewer=null,urls=[],unavailableReason='',supportsProjection=false,currentRow=null,projectedViewer=null,demoSelected=null,briefSource=null,demoRows=[],supportsFaces=false,facePresets=null,faceOrigin='preset',faceViewer=null,detachedResult=false;
 const say=t=>{$('status').textContent=t;};
 function controls(){
  for(const e of $('face').querySelectorAll('input,select,button'))e.disabled=busy;
  if(currentRow?.family==='DUCK'){$('face-nose_enabled').disabled=true;$('face-mouth_enabled').disabled=true;}
  $('face-load').disabled=busy||samplingCloud()||!$('face-history').value;
  $('face-save').disabled=!currentRow||!supportsFaces||busy||!$('face-confirmed').checked||samplingCloud();
  $('load-saved').disabled=busy||samplingCloud()||!$('saved').value;$('refresh-saved').disabled=busy||samplingCloud();
  for(const b of $('demo-cards').querySelectorAll('button'))b.disabled=busy||!available||samplingCloud();
  $('upload-mode').disabled=busy||samplingCloud();
  $('project').disabled=!supportsProjection||!currentRow||busy||!$('projection-confirmed').checked||samplingCloud();
  $('run').disabled=!available||!source||busy||samplingCloud();
  $('confirm').disabled=!prepared||busy||!$('foreground-confirmed').checked||samplingCloud();
 }
 function clear(){$('face-history').replaceChildren();$('face').hidden=true;$('face-result').hidden=true;$('face-confirmed').checked=false;faceViewer?.clear();currentRow=null;$('projection').hidden=true;$('projected-result').hidden=true;$('projection-confirmed').checked=false;projectedViewer?.clear();prepared=null;$('preflight').hidden=true;$('result').hidden=true;$('foreground-confirmed').checked=false;for(const u of urls)URL.revokeObjectURL(u);urls=[];viewer?.clear();controls();}
 async function api(path,opts={}){
  const r=await fetch('./api/learned3d/'+path,{...opts,signal:AbortSignal.timeout(90000)});
  const d=await r.json();if(!r.ok)throw new Error(d.error||'HTTP '+r.status);return d;
 }
 async function artifact(id,m,projection=false){
  if(!['preview.png','mask.png','preflight.json','condition.png','model.glb','report.json','projected.glb','projection-report.json','face.glb','face-report.json'].includes(m.file))throw new Error('산출물 이름 오류');
  const r=await fetch('./api/learned3d/'+(projection==='face'?'face-artifacts/':projection?'projection-artifacts/':'artifacts/')+id+'/'+m.file,{signal:AbortSignal.timeout(30000)});if(!r.ok)throw new Error('산출물 조회 오류');
  const bytes=await r.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
  if(bytes.byteLength!==m.bytes||hash!==m.sha256)throw new Error('산출물 무결성 오류');
  const url=URL.createObjectURL(new Blob([bytes],{type:m.file.endsWith('.glb')?'model/gltf-binary':m.file.endsWith('.png')?'image/png':'application/json'}));urls.push(url);return {bytes,url};
 }
 $('form').addEventListener('submit',async e=>{
  e.preventDefault();if(busy||!source||samplingCloud()||!available)return;const ticket=epoch,s=source;clear();busy=true;controls();say('전경 마스크·미리보기 준비 중… 아직 3D 생성하지 않습니다.');
  try{
   let row;if(demoSelected){row=await api('demo-runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({demo_id:demoSelected.demo_id,source_checksum:demoSelected.checksum,storage_consent:$('store-consent').checked})});}else{
   const file=$('file').files[0];if(!file||!file.size||file.size>2*1024*1024)throw new Error('2MiB 이하 이미지 필요');
   const data=await new Promise((ok,no)=>{const reader=new FileReader();reader.onload=()=>ok(reader.result.split(',')[1]);reader.onerror=()=>no(new Error('파일 읽기 실패'));reader.readAsDataURL(file);});if(ticket!==epoch)return;
   row=await api('runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_base64:data,dimensions_mm:s.dimensions_mm,view:'single',source_id:s.id,source_checksum:s.checksum})});}
   if(ticket!==epoch)return;if(row.status!=='prepared'||!/^[0-9a-f]{32}$/.test(row.id))throw new Error('입력 준비 상태 오류');
   for(const m of row.preparation_artifacts){const {url}=await artifact(row.id,m);if(ticket!==epoch)return;if(m.file==='preview.png')$('preview').src=url;if(m.file==='mask.png')$('mask').src=url;}
   if(ticket!==epoch)return;prepared=row;$('preflight-metrics').textContent=`그림의 어두운 픽셀 보존 ${(100*row.preflight.ink_coverage).toFixed(1)}% · 전경 영역 ${(100*row.preflight.foreground_fraction).toFixed(1)}% · 부위 완전성 미검증`;
   $('preflight').hidden=false;say('미리보기에서 선택 동물의 주요 부위 보존을 확인한 뒤 생성 버튼을 누르세요.');
  }catch(e){if(ticket===epoch)say('입력 준비 실패: '+e.message);}finally{busy=false;controls();}
 });
 async function showResult(row,ticket){
   $('downloads').replaceChildren();let glb;
   for(const m of row.artifacts){const {bytes,url}=await artifact(row.id,m);if(ticket!==epoch)return;const a=document.createElement('a');a.href=url;a.download=m.file;a.textContent=m.file;a.className='secondary';a.style.marginRight='16px';$('downloads').append(a);if(m.file==='condition.png')$('condition').src=url;if(m.file==='model.glb')glb=bytes;}
   $('preflight').hidden=true;$('result').hidden=false;$('report').textContent=JSON.stringify(row,null,2);
   if(!viewer){const {createSampleViewer}=await import('../vendor/sample-viewer.js');viewer=createSampleViewer($('viewer'),{toolbar:true});}viewer.clear();viewer.setModelSha(row.artifacts.find(x=>x.file==='model.glb').sha256);await viewer.load(glb);if(ticket!==epoch)return;
   currentRow=row;$('projection').hidden=!supportsProjection;$('face').hidden=!supportsFaces;if(supportsFaces){resetFace();await refreshFaceHistory();}controls();
 }
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
   await showResult(row,ticket);if(ticket!==epoch)return;await refreshSaved();
   say(row.engine+' 생성 완료 · 형상/뒷면과 디자인 일치를 검토하세요. 무채색 표시는 텍스처 생성·제작 승인이 아닙니다.');
  }catch(e){if(ticket===epoch)say('생성/표시 실패: '+e.message);}finally{busy=false;controls();}
 });
 $('projection-confirmed').addEventListener('change',controls);
 $('project').addEventListener('click',async()=>{
  if(busy||!currentRow||!supportsProjection||!$('projection-confirmed').checked||samplingCloud())return;
  const ticket=epoch,parent=currentRow;busy=true;controls();say('원본을 보존하며 별도 투영 사본을 만드는 중…');
  try{
   const options=Object.fromEntries(['yaw','offset_x','offset_y','scale'].map(k=>[k,Number($('projection-'+k).value)]));
   const row=await api('runs/'+parent.id+'/projections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent_model_sha256:parent.artifacts.find(x=>x.file==='model.glb').sha256,source_image_sha256:parent.foreground_sha256,settings:options,projection_confirmed:true})});
   if(ticket!==epoch)return;if(row.status!=='succeeded')throw new Error('투영 사본 생성 실패');
   $('projection-downloads').replaceChildren();let glb;
   for(const m of row.artifacts){const {bytes,url}=await artifact(row.id,m,true);if(ticket!==epoch)return;const a=document.createElement('a');a.href=url;a.download=m.file;a.textContent=m.file;a.style.marginRight='16px';$('projection-downloads').append(a);if(m.file==='projected.glb')glb=bytes;}
   $('projected-result').hidden=false;$('projection-report').textContent=JSON.stringify(row,null,2);
   if(!projectedViewer){const {createSampleViewer}=await import('../vendor/sample-viewer.js');projectedViewer=createSampleViewer($('projected-viewer'),{toolbar:true});}
   if(ticket!==epoch)return;projectedViewer.clear();projectedViewer.setModelSha(row.artifacts.find(x=>x.file==='projected.glb').sha256);await projectedViewer.load(glb);
   if(ticket===epoch)say('투영 사본 완료 · 원본 형상 보존 검증됨. 얼굴 위치·번짐은 직접 비교하세요. 뒷면은 무채색이며 AI 텍스처 생성이 아닙니다.');
  }catch(e){if(ticket===epoch)say('투영 실패: '+e.message);}finally{busy=false;controls();}
 });
 const anchorKeys=['eye_left','eye_right','nose','mouth_left','mouth_center','mouth_right'];
 const labels=['눈 A','눈 B','코','입 시작','입 곡선 중간','입 끝'];
 const numeric=['eye_size','eye_depth','nose_size','mouth_radius'],bools=['eyes_enabled','nose_enabled','mouth_enabled'];
 function manual(){faceOrigin='manual';$('face-origin').textContent='수동 대응점/설정 · 선택한 표면과 표정을 직접 확인하세요.';$('face-confirmed').checked=false;controls();}
 for(const [i,k] of anchorKeys.entries()){
  const box=document.createElement('div');box.className='face-anchor-row';const title=document.createElement('strong');title.textContent=labels[i];box.append(title);
  const inputs=document.createElement('div');inputs.className='face-anchor-values';
  for(const axis of ['x','y','z']){const label=document.createElement('label');label.textContent=axis.toUpperCase();const input=document.createElement('input');input.id='l3-anchor-'+k+'-'+axis;input.type='number';input.min='0';input.max='1';input.step='.005';input.addEventListener('input',manual);label.append(input);inputs.append(label);}box.append(inputs);
  const pick=document.createElement('button');pick.type='button';pick.textContent='3D에서 선택';pick.className='secondary';pick.dataset.anchor=k;pick.addEventListener('click',()=>{if(!viewer||!currentRow||busy)return;$('face-status').textContent=labels[i]+' 위치를 위 원본 3D 표면에서 클릭하세요.';$('viewer').scrollIntoView({block:'center',behavior:'instant'});viewer.onPick(v=>{v.forEach((x,j)=>document.getElementById('l3-anchor-'+k+'-'+['x','y','z'][j]).value=x.toFixed(5));viewer.onPick(null);manual();$('face-status').textContent=labels[i]+' 표면 대응점을 선택했습니다.';});});box.append(pick);$('face-anchors').append(box);
 }
 function resetFace(){if(!currentRow||!facePresets)return;const family=currentRow.family||'BUNNY',v=facePresets[family];if(!v){$('face').hidden=true;return;}
  const surface=viewer.surfaceAnchors(v.anchors);for(const k of anchorKeys)surface[k].forEach((x,i)=>document.getElementById('l3-anchor-'+k+'-'+['x','y','z'][i]).value=x);
  for(const k of numeric.concat(['nose_shape','style']))$('face-'+k).value=v.settings[k];for(const k of bools)$('face-'+k).checked=v.settings[k];
  $('face-nose_enabled').disabled=family==='DUCK';$('face-mouth_enabled').disabled=family==='DUCK';faceOrigin='preset';$('face-origin').textContent='가정 프리셋 · 자동 얼굴 복원이 아닙니다. 눈·코·입의 위치를 확인/수정하세요.';$('face-confirmed').checked=false;$('face-result').hidden=true;faceViewer?.clear();viewer?.onPick(null);controls();
 }
 $('face-reset').addEventListener('click',()=>{if(!busy)resetFace();});
 for(const k of numeric.concat(bools,['nose_shape','style']))$('face-'+k).addEventListener('change',manual);
 $('face-confirmed').addEventListener('change',controls);
 $('face-save').addEventListener('click',async()=>{
  if(!supportsFaces||!currentRow||busy||samplingCloud()||!$('face-confirmed').checked)return;
  const ticket=epoch,parent=currentRow;busy=true;$('face-result').hidden=true;controls();$('face-status').textContent='표면 대응·얼굴 부품 사본 생성 중…';
  try{
   const anchors=Object.fromEntries(anchorKeys.map(k=>[k,['x','y','z'].map(a=>Number(document.getElementById('l3-anchor-'+k+'-'+a).value))]));
   const settings=Object.fromEntries(numeric.map(k=>[k,Number($('face-'+k).value)]));for(const k of bools)settings[k]=$('face-'+k).checked;for(const k of ['nose_shape','style'])settings[k]=$('face-'+k).value;
   const row=await api('runs/'+parent.id+'/faces',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({parent_model_sha256:parent.artifacts.find(x=>x.file==='model.glb').sha256,source_image_sha256:parent.foreground_sha256,anchors,settings,anchor_origin:faceOrigin,face_confirmed:true})});
   if(ticket!==epoch)return;if(row.status!=='succeeded')throw Error('얼굴 사본 생성 실패');await showFace(row,ticket);if(ticket!==epoch)return;await refreshFaceHistory(row.id);
   if(ticket===epoch)$('face-status').textContent='얼굴 포함 사본 완료 · 위치/표정/관통을 정면·사선·측면에서 확인하세요. 기하가 추가되며 제작 승인이 아닙니다.';
  }catch(e){if(ticket===epoch)$('face-status').textContent='얼굴 사본 실패: '+e.message;}finally{busy=false;controls();}
 });
 async function showFace(row,ticket){
  if(row.parent_run_id!==currentRow?.id)throw Error('다른 원본의 얼굴 사본');
  $('face-downloads').replaceChildren();let glb;
   for(const m of row.artifacts){const{bytes,url}=await artifact(row.id,m,'face');if(ticket!==epoch)return;const a=document.createElement('a');a.href=url;a.download=m.file;a.textContent=m.file;a.style.marginRight='16px';$('face-downloads').append(a);if(m.file==='face.glb')glb=bytes;}
   $('face-result').hidden=false;$('face-report').textContent=JSON.stringify(row,null,2);
   if(!faceViewer){const{createSampleViewer}=await import('../vendor/sample-viewer.js');faceViewer=createSampleViewer($('face-viewer'),{toolbar:true});}if(ticket!==epoch)return;faceViewer.clear();faceViewer.setModelSha(row.artifacts.find(x=>x.file==='face.glb').sha256);await faceViewer.load(glb);
 }
 async function refreshFaceHistory(selected){if(!currentRow||!supportsFaces)return;const parent=currentRow.id,ticket=epoch;const data=await api('runs/'+parent+'/faces');if(ticket!==epoch||currentRow?.id!==parent)return;$('face-history').replaceChildren();for(const row of data.faces){const o=document.createElement('option');o.value=row.id;o.textContent=row.anchor_origin+' · '+row.id.slice(0,12);$('face-history').append(o);}if(selected&&data.faces.some(r=>r.id===selected))$('face-history').value=selected;controls();}
 $('face-history').addEventListener('change',controls);
 $('face-load').addEventListener('click',async()=>{
  if(busy||samplingCloud()||!currentRow||!$('face-history').value)return;const id=$('face-history').value,ticket=epoch;busy=true;controls();
  try{const row=await api('faces/'+id);if(ticket!==epoch)return;if(row.status!=='succeeded'||row.parent_run_id!==currentRow.id)throw Error('얼굴 사본 부모/상태 오류');
   for(const k of anchorKeys)row.anchors[k].forEach((x,i)=>document.getElementById('l3-anchor-'+k+'-'+['x','y','z'][i]).value=x);for(const k of numeric.concat(['nose_shape','style']))$('face-'+k).value=row.settings[k];for(const k of bools)$('face-'+k).checked=row.settings[k];faceOrigin=row.anchor_origin;$('face-origin').textContent='저장된 '+faceOrigin+' 대응점/설정 · 새 생성 없이 복원';$('face-confirmed').checked=false;
   await showFace(row,ticket);if(ticket===epoch)$('face-status').textContent='저장된 얼굴 포함 사본을 열었습니다. 새 생성은 하지 않았습니다.';
  }catch(e){if(ticket===epoch)$('face-status').textContent=e.message;}finally{busy=false;controls();}
 });
 async function refreshSaved(){if(!supportsFaces)return;const selected=$('saved').value,data=await api('runs');$('saved').replaceChildren();for(const row of data.runs){const o=document.createElement('option');o.value=row.id;o.textContent=(row.family||'BUNNY')+' · '+row.source_id+' · '+row.id.slice(0,10);$('saved').append(o);}if([...$('saved').options].some(o=>o.value===selected))$('saved').value=selected;$('saved-panel').hidden=false;controls();}
 $('saved').addEventListener('change',controls);
 $('refresh-saved').addEventListener('click',()=>{if(!busy&&!samplingCloud())refreshSaved().catch(e=>say(e.message));});
 $('load-saved').addEventListener('click',async()=>{if(busy||samplingCloud()||!$('saved').value)return;const id=$('saved').value;detachedResult=true;epoch++;clear();const ticket=epoch;busy=true;controls();try{const row=await api('runs/'+id);if(ticket!==epoch)return;if(row.status!=='succeeded')throw Error('완료한 결과가 아닙니다');await showResult(row,ticket);if(ticket===epoch){$('source').textContent='저장된 결과: '+row.source_id+' · '+row.id.slice(0,10);say('저장된 실제 생성 결과를 열었습니다. 새 추론은 실행하지 않았습니다.');}}catch(e){if(ticket===epoch)say(e.message);}finally{busy=false;controls();}});
 function selectInput(demo){
  detachedResult=false;epoch++;demoSelected=demo;source=demo||briefSource;clear();$('store-consent').checked=false;
  $('file').disabled=!!demo;$('file').required=!demo;$('file').value='';
  for(const b of $('demo-cards').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.demoId===demo?.demo_id));
  $('source').textContent=demo?'독립 로컬 데모: '+demo.label+' · '+demo.checksum.slice(0,12):source?'연결 명세: '+source.id+' · '+source.checksum.slice(0,12):'직접 업로드는 기존 U21에서 U20 토끼 명세를 선택하세요.';
  $('demo-detail').textContent=demo?'선택: '+demo.label+' · 고정 설명: '+demo.prompt+' · 치수 180×300×120mm는 기록용 가상값이며 형상에 적용하지 않습니다.':'';
  say(unavailableReason||(demo?'저장 동의를 체크하고 입력 준비를 누르세요.':'직접 업로드할 토끼 스케치를 선택하세요.'));controls();
 }
 $('upload-mode').addEventListener('click',()=>{if(!busy)selectInput(null);});
 $('file').addEventListener('change',()=>{detachedResult=false;source=briefSource;epoch++;clear();});
 window.addEventListener('generation-source-selected',e=>{
  const s=e.detail.source;briefSource=s?.family==='BUNNY'&&s?.data_kind==='synthetic'?s:null;
  if(!demoSelected&&!detachedResult)selectInput(null);
 });
 window.addEventListener('sampling-connection-changed',()=>{briefSource=null;selectInput(null);});
 async function loadDemos(){
  const data=await api('demos');demoRows=data.demos||[];
  for(const d of demoRows){
   if(!['rabbit','bear','elephant','duck'].includes(d.demo_id)||d.image_url!=='./api/learned3d/demo-images/'+d.demo_id)throw new Error('데모 경로 오류');
   const b=document.createElement('button');b.type='button';b.className='secondary';b.dataset.demoId=d.demo_id;b.setAttribute('aria-pressed','false');
   const img=document.createElement('img');img.src=d.image_url;img.alt=d.label+' 데모 스케치';img.style.height='180px';img.style.width='100%';img.style.objectFit='contain';b.append(img,document.createTextNode(d.label));b.addEventListener('click',()=>{if(!busy&&!samplingCloud())selectInput(d);});$('demo-cards').append(b);
  }
  $('demos').hidden=!demoRows.length;controls();
 }
 (async()=>{try{const c=await api('capabilities');supportsFaces=c.supports_faces===true;if(supportsFaces)facePresets=await api('face-presets');supportsProjection=c.supports_projection===true;available=c.available===true&&c.requires_confirmation===true;$('engine').textContent=c.engine?c.engine+' · 로컬 전용 · '+(c.engine==='TripoSG-scribble'?'스케치/설명 조건의 무채색 형상 생성':'이미지 기반 컬러 형상 생성'):'로컬 모델 미설정';unavailableReason=available?'':c.available?'서버를 새 버전으로 다시 시작하세요. 입력 확인을 지원하지 않는 서버에서는 생성하지 않습니다.':c.reason||'로컬 모델 설치 필요';say(available?'데모 그림 또는 직접 업로드를 선택하고 입력을 준비하세요.':unavailableReason);if(available&&c.supports_demos===true)await loadDemos();if(available&&supportsFaces)await refreshSaved();}catch{say('로컬 서버 연결 필요');}controls();})();
}
