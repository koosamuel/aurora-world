import {demoApi,SupabaseApi} from './api.js';
import {drawChart} from './chart.js';
import {initLabeling} from './labeling.js';
import {renderDecisions,renderDecisionSku} from './decision-view.js';
const $=id=>document.getElementById(id);
const names={queued:'대기',running:'계산 중',succeeded:'완료',failed:'실패',cancelled:'취소'};
const modelNames={naive:'Naive',seasonal_naive:'계절 naive'};
const fmt=n=>n===null || n===undefined ? '해당 없음' : new Intl.NumberFormat('ko-KR',{maximumFractionDigits:3}).format(n);
let api, epoch=0, viewSeq=0, selected=null, result=null, polling=null, busy=false, pendingRequest=null;
function saved(key,value) { try {if(value===undefined)return sessionStorage.getItem(key);if(value===null)sessionStorage.removeItem(key);else sessionStorage.setItem(key,value);} catch{} }
function notice(message) { $('notice').textContent=message||'';$('notice').hidden=!message; }
function empty(message='첫 번째 예측을 시작하세요') {result=null;$('result-content').hidden=true;$('empty-state').hidden=false;$('empty-state').querySelector('h3').textContent=message;}
function tab(type) {
  if(!['forecast','labeling'].includes(type))type='forecast';
  for(const t of ['forecast','labeling']) { const active=t===type;$(`tab-${t}`).setAttribute('aria-selected',String(active));$(`tab-${t}`).tabIndex=active?0:-1;$(`${t}-panel`).hidden=!active; }
  if(location.hash!==`#/${type}`)location.hash=`/${type}`;
}
window.addEventListener('hashchange',()=>tab(location.hash.slice(2)));
for(const b of document.querySelectorAll('[data-tab]')) {
  b.addEventListener('click',()=>tab(b.dataset.tab));
  b.addEventListener('keydown',e=>{if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;e.preventDefault();const type=e.key==='Home'?'forecast':e.key==='End'?'labeling':b.dataset.tab==='forecast'?'labeling':'forecast';tab(type);$(`tab-${type}`).focus();});
}
function config() {return {skus:Number($('skus').value),weeks:Number($('weeks').value),horizon:Number($('horizon').value),season_length:Number($('season').value),validation_origins:3};}
function renderSeries() {
  if(!result)return;const series=result.series.find(s=>s.sku===$('sku-select').value)||result.series[0];
  renderDecisionSku(result.decisions,series.sku);
  saved(`aurora-sku-${api.mode}`,series.sku);drawChart($('chart'),series);
  $('series-note').textContent=`${series.sku} · ${series.pattern} · 결측·미개시·반품은 수요 0으로 채우지 않습니다. ${Object.entries(series.unavailable).filter(([,v])=>v).map(([k,v])=>`${modelNames[k]}: ${v}`).join(' / ')}`;
}
function renderResult(data) {
  if(data.schema_version!=='aurora-baseline-v1'||data.synthetic!==true)throw new Error('지원하는 합성 기준선 결과가 아닙니다.');
  result=data;$('input-notice').hidden=!data.input_manifest;$('input-notice').textContent=data.input_manifest?'관측 총출하량 입력 · 품절 '+data.quality.stockouts+'건. 잠재 수요와 다릅니다. 반품은 별도 기록하며, 아래 재고 비교의 단가는 공통 가상값 1,000원입니다.':'';$('empty-state').hidden=true;$('result-content').hidden=false;
  $('metric-skus').textContent=fmt(data.quality.series);$('metric-weeks').textContent=`${data.config.weeks}주 · ${data.input_manifest?"입력 파일":"Seed "+data.config.seed}`;
  for(const [id,model] of [['metric-naive','naive'],['metric-seasonal','seasonal_naive']])$(''+id).textContent=fmt(data.paired_metrics.find(m=>m.model===model&&m.split==='test')?.mae);
  $('sku-select').replaceChildren(...data.series.map(s=>new Option(s.sku,s.sku)));
  const remembered=saved(`aurora-sku-${api.mode}`);if(data.series.some(s=>s.sku===remembered))$('sku-select').value=remembered;
  $('metrics-table').replaceChildren(...data.paired_metrics.map(m=>{const tr=document.createElement('tr');for(const value of [m.split==='test'?'최종 보류':'검증',modelNames[m.model],fmt(m.n),fmt(m.mae),fmt(m.bias),`${fmt(m.mase)} (n=${m.mase_n})`]){const td=document.createElement('td');td.textContent=value;tr.append(td);}return tr;}));
  const {series,predictions,skipped,...manifest}=data;
  manifest.exclusion_counts=skipped.reduce((out,s)=>(out[s.reason]=(out[s.reason]||0)+1,out),{});
  $('manifest').textContent=JSON.stringify({...manifest,decisions:undefined},null,2);renderDecisions(data.decisions,$('sku-select').value);renderSeries();
}
async function selectRun(id, ticket=epoch) {
  const adapter=api, viewTicket=++viewSeq;
  const run=await adapter.getRun(id);if(ticket!==epoch||adapter!==api||viewTicket!==viewSeq)return;
  selected=id;for(const b of $('run-list').querySelectorAll('[data-run-id]'))b.setAttribute('aria-pressed',String(b.dataset.runId===id));saved(`aurora-run-${api.mode}`,id);
  if(run.status==='succeeded')renderResult(run.result);
  else {empty(run.status==='queued'?'워커 실행을 기다리고 있습니다':names[run.status]||run.status);if(run.error)notice(run.error);}
}
function updateControls() {
  const cloud=api.mode==='supabase',preview=api.mode==='preview';
  const datasets=api.datasets||[];$('dataset-picker-label').hidden=!datasets.length;
  $('dataset-picker').replaceChildren(...datasets.map(d=>new Option(d.name,d.id)));
  if(api.dataset)$('dataset-picker').value=api.dataset.id;$('dataset-picker').disabled=busy;
  $('connection').textContent=cloud?(api.session?'Supabase · 로그인됨':'Supabase · 로그인 필요'):preview?'저장된 합성 결과 · 미리보기':'로컬 · 합성 계산';
  for(const id of ['skus','weeks'])$(id).disabled=cloud||preview;
  for(const id of ['horizon','season'])$(id).disabled=preview;
  $('run').disabled=busy || cloud&&(!api.session||!api.dataset);
  $('run').textContent=busy?'요청 중…':preview?'합성 데모 불러오기':'합성 기준선 실행 ↗';
  $('login-form').hidden=!cloud;$('logout').hidden=!cloud||!api.session;
  for(const el of $('login-form').querySelectorAll('input,button[type="submit"]'))el.hidden=cloud&&!!api.session;
  $('auth-state').textContent=cloud?(api.session?`로그인: ${api.session.user.email} · 세션은 메모리에만 유지됩니다.`:'로그인 후 프로젝트 멤버 권한을 확인합니다.'):'로컬에서는 새로 계산합니다. GitHub Pages 미리보기는 미리 계산한 합성 결과를 표시합니다.';
  $('dataset-label').textContent=cloud?(api.dataset?.name||'준비된 합성 데이터셋 없음'):preview?(api.dataset?.name+' · 저장된 결과'):'합성 주간 수요 · 요청마다 계산';
  if(cloud&&api.dataset){$('skus').value=api.dataset.generator_config.skus;$('weeks').value=api.dataset.generator_config.weeks;}
  if(preview){$('skus').value=api.dataset.generator_config.skus;$('weeks').value=156;$('horizon').value=4;$('season').value=52;}
  $('label-project').textContent='브라우저 합성 데모 · 로그인 없이 실행 · 검수는 현재 브라우저 세션에만 저장됩니다.';
}
async function refresh() {
  const ticket=epoch,adapter=api;clearTimeout(polling);
  try {
    const runs=await adapter.listRuns();if(ticket!==epoch||adapter!==api)return;
    $('run-list').replaceChildren();
    if(!runs.length){const p=document.createElement('p');p.className='muted small';p.textContent='아직 실행 이력이 없습니다.';$('run-list').append(p);}
    for(const r of runs){const b=document.createElement('button');b.className='run-item';b.dataset.runId=r.id;b.textContent=`${names[r.status]||r.status} · ${r.id.slice(0,8)}`;b.setAttribute('aria-pressed',String(r.id===selected));b.addEventListener('click',()=>selectRun(r.id).catch(e=>notice(e.message)));$('run-list').append(b);}
    const remembered=selected||saved(`aurora-run-${api.mode}`);
    if(remembered&&runs.some(r=>r.id===remembered))await selectRun(remembered,ticket);
    if(runs.some(r=>['queued','running'].includes(r.status)))polling=setTimeout(refresh,1500);
  } catch(error){if(ticket===epoch)notice(error.message);}
}
async function changeMode(adapter) {
  epoch++;clearTimeout(polling);api=adapter;restoreDataset();selected=null;pendingRequest=null;busy=false;notice('');empty();$('run-list').replaceChildren();updateControls();await refresh();
}
$('run-form').addEventListener('submit',async e=>{
  e.preventDefault();if(busy)return;const ticket=epoch,adapter=api,c=config(),signature=JSON.stringify(c);
  if(c.weeks<=c.horizon*4){notice('검증과 최종 평가를 나눌 이력이 부족합니다.');return;}
  busy=true;notice('');updateControls();
  if(!pendingRequest||pendingRequest.signature!==signature)pendingRequest={signature,key:crypto.randomUUID()};
  try {const run=await adapter.requestRun(c,pendingRequest.key);if(ticket!==epoch)return;pendingRequest=null;selected=run.id;await selectRun(run.id,ticket);await refresh();if(adapter.mode==='preview')notice('Python으로 미리 계산한 고정 합성 결과입니다. 새 계산은 로컬 실행 모드를 사용하세요.');}
  catch(error){if(ticket===epoch)notice(error.message);}
  finally{if(ticket===epoch){busy=false;updateControls();}}
});
function restoreDataset(){const id=saved(`aurora-dataset-${api.mode}`);const d=api.datasets?.find(d=>d.id===id);if(d)api.dataset=d;}
$('dataset-picker').addEventListener('change',async()=>{const d=api.datasets?.find(d=>d.id===$('dataset-picker').value);if(!d)return;epoch++;viewSeq++;clearTimeout(polling);api.dataset=d;saved(`aurora-dataset-${api.mode}`,d.id);selected=null;pendingRequest=null;empty();notice('');updateControls();await refresh();});
$('refresh').addEventListener('click',refresh);$('sku-select').addEventListener('change',renderSeries);
$('download').addEventListener('click',()=>{if(!result)return;const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='aurora-synthetic-baseline.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('settings-toggle').addEventListener('click',()=>{$('settings').hidden=!$('settings').hidden;$('settings-toggle').setAttribute('aria-expanded',String(!$('settings').hidden));});
$('connect-form').addEventListener('submit',e=>{e.preventDefault();const fd=new FormData(e.currentTarget);try{changeMode(new SupabaseApi(fd.get('url').trim(),fd.get('key').trim()));}catch(error){notice(error.message);}});
$('login-form').addEventListener('submit',async e=>{e.preventDefault();const adapter=api,ticket=epoch,fd=new FormData(e.currentTarget);try{await adapter.login(fd.get('email').trim(),fd.get('password'));if(ticket!==epoch)return;restoreDataset();notice('');updateControls();await refresh();}catch(error){if(ticket===epoch){updateControls();notice(error.message);}}finally{e.target.elements.password.value='';}});
$('logout').addEventListener('click',async()=>{const adapter=api;epoch++;selected=null;empty('로그아웃되었습니다');clearTimeout(polling);$('run-list').replaceChildren();try{await adapter.logout();}catch(error){notice(error.message);}finally{if(adapter===api)updateControls();}});
$('demo-mode').addEventListener('click',async()=>{const old=api;if(old.mode==='supabase')await old.logout().catch(()=>{});await changeMode(await demoApi());});
initLabeling();
tab(location.hash.slice(2));
const configured=window.AURORA_CONFIG;
if(configured?.supabaseUrl){$('connect-form').elements.url.value=configured.supabaseUrl;$('connect-form').elements.key.value=configured.publishableKey;}
try {await changeMode(configured?.defaultMode==='supabase'&&configured?.supabaseUrl&&configured?.publishableKey?new SupabaseApi(configured.supabaseUrl,configured.publishableKey):await demoApi());}catch(error){notice(error.message);}
