// Shared real Auth adapter; never stores credentials or falls back to saved results on cloud errors.
import {checkedBlob} from './api.js';
let adapter=null,fingerprint='',epoch=0,lastValidation=null;
export const samplingCloud=()=>adapter?.mode==='supabase';
export const samplingWritable=()=>samplingCloud()&&!!adapter?.session&&['runner','admin'].includes(adapter.samplingRole);
export function setSamplingConnection(next){adapter=next;const key=[next.mode,next.url,next.session?.user?.id,next.samplingRole].join(':');if(key===fingerprint)return;fingerprint=key;epoch++;lastValidation=null;window.dispatchEvent(new CustomEvent('sampling-connection-changed'));}
const cloud=()=>{if(!samplingCloud()||!adapter.session)throw new Error('상단 연결 설정에서 Supabase에 로그인하세요.');const project=adapter.projects.find(p=>p.project_type==='labeling');if(!project)throw new Error('디지털 샘플링 프로젝트 멤버 권한이 필요합니다.');return {api:adapter,project:project.id};};
async function rpc(name,body){const {api}=cloud();return api.call('/rest/v1/rpc/'+name,{method:'POST',body:JSON.stringify(body)});}
async function briefs(){const {api,project}=cloud();return api.call('/rest/v1/sampling_briefs?select=envelope,source,created_at&project_id=eq.'+project+'&order=product_id,version.desc&limit=300');}
async function getJob(id){const {api,project}=cloud();const rows=await api.call('/rest/v1/sampling_runs?select=*&id=eq.'+encodeURIComponent(id)+'&project_id=eq.'+project);if(rows.length!==1)throw new Error('이 프로젝트의 샘플 작업이 없습니다.');const r=rows[0];const result=r.result?structuredClone(r.result):null;if(r.status==='succeeded'&&r.kind!=='validate_brief'){const files=await api.call('/rest/v1/sampling_artifacts?select=id,name,bytes,sha256,mime&run_id=eq.'+encodeURIComponent(id)+'&project_id=eq.'+project+'&attempt=eq.'+r.attempt+'&order=name');result.artifacts=files.map(a=>({...a,file:a.name}));}return {id:r.id,state:r.status,kind:r.kind,source:r.payload.source,seed:r.payload.seed,result,error:r.error,created_at:r.created_at,attempt:r.attempt};}
async function submit(kind,payload,key){const {project}=cloud();const r=await rpc('request_sampling',{p_project_id:project,p_kind:kind,p_request_key:key,p_payload:payload});window.dispatchEvent(new CustomEvent('sampling-job-created',{detail:r.id}));return r;}
async function validated(raw){const ticket=epoch;const r=await submit('validate_brief',{raw_brief:raw},crypto.randomUUID());for(let i=0;i<180;i++){if(ticket!==epoch)throw new Error('연결/로그인 상태가 바뀌었습니다.');const row=await getJob(r.id);if(row.state==='succeeded'){lastValidation={id:row.id,body:JSON.stringify(row.result.envelope.brief)};return row.result.envelope;}if(!['queued','running'].includes(row.state))throw new Error(row.error||'명세 검증 취소/실패');window.dispatchEvent(new CustomEvent('sampling-validation-wait',{detail:{id:r.id,state:row.state}}));await new Promise(resolve=>setTimeout(resolve,1000));}throw new Error('검증 작업이 대기 중입니다. 워커 상태를 확인한 뒤 다시 검증하세요.');}
async function dispatch(path,options={}){
 if(!samplingCloud()){const r=await fetch(path,{...options,signal:AbortSignal.timeout(15000)});const b=await r.json();if(!r.ok)throw new Error(b.error||'응답 '+r.status);return b;}
 const method=options.method||'GET';
 if(path==='./api/sampling/validate'&&method==='POST')return validated(options.body);
 if(path==='./api/sampling/briefs'&&method==='POST'){if(!lastValidation||JSON.stringify(JSON.parse(options.body))!==lastValidation.body)throw new Error('등록할 명세를 서버에서 먼저 검증하세요.');const {project}=cloud();return rpc('register_sampling_brief',{p_project_id:project,p_validation_run:lastValidation.id});}
 if(path==='./api/sampling/briefs')return (await briefs()).map(r=>({...r.envelope,registered_at:r.created_at}));
 if(path.startsWith('./api/sampling/briefs/')){const bits=path.split('/');const rows=await briefs();const found=rows.find(r=>r.envelope.brief.product_id===decodeURIComponent(bits.at(-2))&&r.envelope.brief.brief_version===Number(bits.at(-1)));if(!found)throw new Error('원격 명세가 없습니다.');return {...found.envelope,registered_at:found.created_at};}
 const ai=path.includes('/ai-sampling/');
 if(path.endsWith('/catalog')){const {project}=cloud();const rows=await briefs();const worker=await rpc('sampling_worker_status',{p_project_id:project});return {sources:rows.map(r=>r.source),runtime_available:worker.ai_available,worker_online:worker.online,runtime_message:worker.online?'Supabase 연결 · 개발 PC 워커 온라인 · 실제 생성 요청 가능':'Supabase 연결 · 워커 오프라인/대기 · 개발 PC 워커가 켜져야 계산합니다.'};}
 if(path.endsWith('/runs')&&method==='POST'){const b=JSON.parse(options.body);const r=await submit(ai?'ai':'geometry',{source_id:b.source_id,source_checksum:b.source_checksum,seed:b.seed},b.request_key);return getJob(r.id);}
 if(path.includes('/runs/'))return getJob(path.split('/').at(-1));
 throw new Error('지원하지 않는 원격 샘플 경로');
}
export async function samplingArtifact(row,meta){
 const a=await rpc('sampling_download',{p_artifact_id:meta.id});if(a.run_id!==row.id||a.name!==meta.file||a.sha256!==meta.sha256||a.bytes!==meta.bytes)throw new Error('샘플 산출물 메타데이터 불일치');const {api}=cloud();const signed=await api.call('/storage/v1/object/sign/'+a.bucket+'/'+a.path,{method:'POST',body:JSON.stringify({expiresIn:120})});const url=new URL(signed.signedURL,api.url+'/storage/v1/');if(signed.signedURL?.startsWith('/object/'))url.pathname='/storage/v1'+url.pathname;if(url.origin!==api.url||!url.pathname.startsWith('/storage/v1/object/sign/aurora-sampling/'))throw new Error('샘플 서명 경로 오류');return (await checkedBlob(url.href,a)).arrayBuffer();
}
export async function samplingHistory(kind){const {api,project}=cloud();return api.call('/rest/v1/sampling_runs?select=id,status,kind,created_at,error&project_id=eq.'+project+(kind?'&kind=eq.'+kind:'')+'&order=created_at.desc&limit=20');}
export async function cancelSampling(id){return rpc('cancel_sampling',{p_run_id:id});}

export async function samplingRequest(path,options={}){const ticket=epoch;const value=await dispatch(path,options);if(ticket!==epoch)throw new Error("연결이 바뀌어 이전 응답을 표시하지 않습니다.");return value;}

export function initSamplingQueue(){
 const $=id=>document.getElementById(id);let timer=null,selected=null;
 async function refresh(){clearTimeout(timer);const ticket=epoch;$('sampling-queue').hidden=!samplingCloud();if(!samplingCloud())return;if(!adapter?.session){$('sampling-job-list').replaceChildren();$('sampling-job-detail').textContent='로그인하면 원격 실행 이력을 조회합니다.';$('sampling-job-open').disabled=true;$('sampling-job-cancel').disabled=true;return;}
  try{const rows=await samplingHistory();if(ticket!==epoch)return;const prev=selected||$('sampling-job-list').value;$('sampling-job-list').replaceChildren(...rows.map(r=>new Option(`${r.kind} · ${r.status} · ${r.id.slice(0,8)}`,r.id)));if(rows.some(r=>r.id===prev))$('sampling-job-list').value=prev;selected=$('sampling-job-list').value;const row=rows.find(r=>r.id===selected);$('sampling-job-detail').textContent=row?`${row.id} · ${row.status}${row.error?' · '+row.error:''}`:'아직 실행 이력이 없습니다.';$('sampling-job-open').disabled=!row||row.status!=='succeeded'||row.kind==='validate_brief';$('sampling-job-cancel').disabled=!row||!samplingWritable()||!['queued','running'].includes(row.status);if(rows.some(r=>['queued','running'].includes(r.status)))timer=setTimeout(refresh,2500);
  }catch(e){if(ticket===epoch)$('sampling-job-detail').textContent=e.message;}
 }
 $('sampling-job-refresh').onclick=()=>{selected=null;refresh();};$('sampling-job-list').onchange=()=>{selected=$('sampling-job-list').value;refresh();};
 $('sampling-job-cancel').onclick=async()=>{try{await cancelSampling(selected);await refresh();}catch(e){$('sampling-job-detail').textContent=e.message;}};
 $('sampling-job-open').onclick=async()=>{const ticket=epoch;try{const r=await getJob(selected);if(ticket===epoch&&r.state==='succeeded')window.dispatchEvent(new CustomEvent('sampling-cloud-run-selected',{detail:r}));}catch(e){$('sampling-job-detail').textContent=e.message;}};
 window.addEventListener('sampling-connection-changed',()=>{selected=null;refresh();});window.addEventListener('sampling-job-created',e=>{selected=e.detail;refresh();});refresh();
}
