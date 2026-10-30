import {samplingCloud} from "./sampling-connection.js";
export function initSketchFit(){
const $=id=>document.getElementById(id);let busy=false,available=false,viewers=null,urls=[],source=null,epoch=0;const linked=!!document.getElementById("sketch-fit-panel")?.dataset.linkedBrief;
const say=t=>{$('fit-status').textContent=t;};
function controls(){$('fit-run').disabled=busy||!available||samplingCloud()||(linked&&!source);}
async function json(url,options={}){const r=await fetch(url,{...options,signal:AbortSignal.timeout(90000)});const data=await r.json();if(!r.ok)throw new Error(data.error||'HTTP '+r.status);return data;}
async function artifact(row,meta){const r=await fetch(`./api/sketch-fit/artifacts/${row.id}/${meta.file}`,{signal:AbortSignal.timeout(30000)});if(!r.ok)throw new Error('산출물 조회 실패');const buf=await r.arrayBuffer();const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',buf))].map(x=>x.toString(16).padStart(2,'0')).join('');if(buf.byteLength!==meta.bytes||sha!==meta.sha256)throw new Error('산출물 무결성 오류');return buf;}
$('fit-form').addEventListener('submit',async e=>{e.preventDefault();if(busy||!available||samplingCloud()||(linked&&!source)||!$('fit-form').reportValidity())return;const ticket=epoch;const submittedSource=source;busy=true;controls();$('fit-result').hidden=true;say('목표 마스크 추출 및 부위 비율 보정 중…');try{
const file=$('fit-file').files[0];if(!file||!file.size||file.size>2*1024*1024)throw new Error('2MiB 이하 PNG/JPEG를 선택하세요.');
const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('파일 읽기 실패'));reader.readAsDataURL(file);});
if(ticket!==epoch)throw new Error('명세 또는 연결 모드가 바뀌었습니다. 다시 실행하세요.');
const dimensions_mm=Object.fromEntries(['width','height','depth'].map(k=>[k,Number($('fit-'+k).value)]));
const row=await json('./api/sketch-fit/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image_base64:data,dimensions_mm,view:'front',...(submittedSource?{source_id:submittedSource.id,source_checksum:submittedSource.checksum}:{})})});
if(ticket!==epoch)throw new Error('명세/연결이 바뀌어 이전 결과를 표시하지 않습니다.');
if(!/^[0-9a-f]{32}$/.test(row.id))throw new Error('실행 ID 오류');
for(const u of urls)URL.revokeObjectURL(u);urls=[];$('fit-downloads').replaceChildren();
const artifacts={};for(const meta of row.artifacts){if(!/^(before|after)\.(glb|png)$|^target\.png$|^report\.json$/.test(meta.file))throw new Error('파일명 오류');const bytes=await artifact(row,meta);artifacts[meta.file]=bytes;const u=URL.createObjectURL(new Blob([bytes],{type:meta.file.endsWith('.png')?'image/png':meta.file.endsWith('.glb')?'model/gltf-binary':'application/json'}));urls.push(u);const a=document.createElement('a');a.href=u;a.download=meta.file;a.textContent=meta.file;a.className='secondary';a.style.marginRight='16px';$('fit-downloads').append(a);if(meta.file.endsWith('.png'))$('fit-'+meta.file.replace('.png','')).src=u;}
$('fit-metrics').textContent=`윤곽 IoU: ${row.metrics.before_iou.toFixed(3)} → ${row.metrics.after_iou.toFixed(3)} · 겹침 점수이며 3D 정확도·봉제 적합성 점수가 아닙니다.`;
$('fit-warnings').replaceChildren(...row.warnings.map(t=>{const li=document.createElement('li');li.textContent=t;return li;}));$('fit-report').textContent=JSON.stringify(row,null,2);$('fit-result').hidden=false;
try{if(!viewers){const {createSampleViewer}=await import('../vendor/sample-viewer.js');viewers=Object.fromEntries(['before','after'].map(k=>[k,createSampleViewer($('fit-'+k+'-3d'))]));}for(const k of ['before','after']){viewers[k].clear();await viewers[k].load(artifacts[k+'.glb']);}$('fit-view-status').textContent='드래그로 회전·휠로 확대할 수 있습니다.';}catch(err){$('fit-view-status').textContent='3D 표시 불가: '+err.message+' · PNG 비교와 GLB 다운로드는 이용 가능합니다.';}
say(row.metrics.after_iou>row.metrics.before_iou?'보정 완료. 목표 마스크와 전후 윤곽을 확인하세요.':'완료. 현재 탐색 범위에서 개선되지 않아 기존 형상을 유지했습니다.');
}catch(err){say('보정 실패: '+err.message);}finally{busy=false;controls();}});
async function start(){if(!['127.0.0.1','localhost'].includes(location.hostname)){say('정적 Pages/Supabase에서는 미지원입니다. 로컬 서버에서 이 페이지를 여세요.');return;}try{const c=await json('./api/sketch-fit/capabilities');available=c.available===true;say(available?'로컬 전용 · 정면 스케치를 선택하세요.':c.reason||'이용 불가');}catch{say('로컬 aurora 서버에 연결할 수 없습니다.');}controls();}
window.addEventListener('generation-source-selected',e=>{if(!linked)return;epoch++;const selected=e.detail.source;source=selected?.family==='BUNNY'&&selected?.data_kind==='synthetic'?selected:null;$('fit-result').hidden=true;for(const k of ['width','height','depth']){if(source)$('fit-'+k).value=source.dimensions_mm[k];$('fit-'+k).readOnly=true;}$('fit-source').textContent=source?'연결 명세: '+source.id+' · 입력 해시 '+source.checksum.slice(0,12):'기존 U21 입력 목록에서 U20 토끼 명세를 선택하세요. 다른 상품군은 미지원입니다.';controls();});
window.addEventListener('sampling-connection-changed',()=>{epoch++;source=null;$('fit-result').hidden=true;controls();say(samplingCloud()?'Supabase 모드에서는 윤곽 보정 미지원입니다. 로컬 모드로 전환하세요.':'U20 토끼 명세를 다시 선택하세요.');});
start();
}
