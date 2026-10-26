export async function jsonFetch(url, options = {}) {
  const response = await fetch(url, {cache: 'no-store', ...options});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error_description || body.message || body.error || `요청 실패 (${response.status})`);
  return body;
}
export function validatePublicConfig(url, key) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) throw new Error('HTTPS 프로젝트 URL을 확인하세요.');
  let valid = key.startsWith('sb_publishable_') && key.length > 20;
  if (!valid && key.split('.').length === 3) {
    try { const payload = key.split('.')[1].replace(/-/g,'+').replace(/_/g,'/'); valid = JSON.parse(atob(payload)).role === 'anon'; } catch { /* invalid public JWT */ }
  }
  if (!valid) throw new Error('공개 publishable / anon 키만 사용할 수 있습니다.');
  return {url: parsed.origin, key};
}
export class LocalApi {
  mode = 'local'; datasets=[]; dataset=null;
  async loadDatasets(){this.datasets=await jsonFetch('./api/datasets');this.dataset=this.datasets[0]||null;}
  public(){return this.dataset?.dataset_kind==='public_retail';}
  async downloadArtifact(a){return checkedBlob(a.url,a);}
  listRuns() { return jsonFetch(this.public()?'./api/public/runs':'./api/runs?project_type=forecast'); }
  getRun(id) { return jsonFetch(this.public()?`./api/public/runs/${encodeURIComponent(id)}`:`./api/runs/${encodeURIComponent(id)}?project_type=forecast`); }
  requestRun(config, key) { return jsonFetch(this.public()?'./api/public/runs':'./api/runs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({project_type:'forecast', request_key:key, config})}); }
}
export class PreviewApi {
  mode = 'preview';
  datasets=[{id:'saved-demo',name:'기본 합성 · 50 SKU / 156주',file:'baseline.json',generator_config:{skus:50,weeks:156}}, {id:'saved-research',name:'연구 참고 합성 · 100 SKU / 156주',file:'research.json',generator_config:{skus:100,weeks:156}}, {id:'saved-public-retail',name:'UCI 공개 거래 · 100 SKU / 104주',dataset_kind:'public_retail',file:'public-retail.json',generator_config:{skus:100,weeks:104}}];
  dataset=this.datasets[0];
  async downloadArtifact(a){return checkedBlob('./demo/public-retail/'+a.name,a);}
  async listRuns() { return [{id:this.dataset.id,status:'succeeded'}]; }
  async getRun(id) { if(id!==this.dataset.id)throw new Error('선택한 자료의 실행이 아닙니다.');return {id,status:'succeeded',result:await jsonFetch('./demo/'+this.dataset.file)}; }
  async requestRun() { return {id:this.dataset.id,status:'succeeded'}; }
}
export class SupabaseApi {
  mode = 'supabase'; session = null; projects = []; datasets = []; dataset = null;
  constructor(url,key) { Object.assign(this,validatePublicConfig(url,key)); }
  async call(path, options={}) {
    if (this.session && Date.now() > this.expires - 30000) await this.refresh();
    return jsonFetch(this.url+path, {...options, headers:{apikey:this.key, ...(this.session ? {Authorization:`Bearer ${this.session.access_token}`} : {}), 'Content-Type':'application/json', ...options.headers}});
  }
  async login(email,password) {
    this.session = await jsonFetch(this.url+'/auth/v1/token?grant_type=password',{method:'POST',headers:{apikey:this.key,'Content-Type':'application/json'},body:JSON.stringify({email,password})});
    this.expires = Date.now()+this.session.expires_in*1000;
    await this.loadProjects();
  }
  async refresh() {
    try {
      this.session = await jsonFetch(this.url+'/auth/v1/token?grant_type=refresh_token',{method:'POST',headers:{apikey:this.key,'Content-Type':'application/json'},body:JSON.stringify({refresh_token:this.session.refresh_token})});
      this.expires = Date.now()+this.session.expires_in*1000;
    } catch (error) { this.session=null; this.projects=[]; this.datasets=[]; this.dataset=null; throw error; }
  }
  async logout() { try { if(this.session) await this.call('/auth/v1/logout',{method:'POST'}); } finally { this.session=null; this.projects=[]; this.datasets=[]; this.dataset=null; } }
  project() { const p=this.projects.find(p=>p.project_type==='forecast'); if(!p) throw new Error('접근 가능한 수요예측 프로젝트가 없습니다.'); return p; }
  async loadProjects() {
    this.projects = await this.call('/rest/v1/projects?select=id,name,project_type&order=created_at');
    const p=this.projects.find(p=>p.project_type==='forecast');
    this.datasets=[];
    if(p){try{this.datasets=await this.call(`/rest/v1/datasets?select=id,name,dataset_kind,synthetic,generator_config&project_id=eq.${p.id}&status=eq.ready&order=created_at.desc&limit=30`);this.publicExecutionReady=true;}catch(e){if(!/dataset_kind|column|schema cache/i.test(e.message))throw e;this.datasets=await this.call(`/rest/v1/datasets?select=id,name,generator_config&project_id=eq.${p.id}&status=eq.ready&synthetic=eq.true&order=created_at.desc&limit=30`);this.publicExecutionReady=false;}}
    this.dataset=this.datasets.find(d=>d.id===this.dataset?.id)||this.datasets[0]||null;
  }
  async listRuns() { if(!this.session||!this.dataset) return []; return this.call(`/rest/v1/runs?select=id,status,created_at,error&project_id=eq.${this.project().id}&dataset_id=eq.${this.dataset.id}&order=created_at.desc&limit=30`); }
  async getRun(id) { const rows=await this.call(`/rest/v1/runs?select=*&id=eq.${encodeURIComponent(id)}&project_id=eq.${this.project().id}&dataset_id=eq.${this.dataset.id}`); if(!rows.length) throw new Error('실행을 찾을 수 없습니다.');
    if(rows[0].result?.schema_version==='aurora-public-evaluation-v1') rows[0].result.artifacts=await this.call(`/rest/v1/artifacts?select=id,name,bytes,sha256,mime&run_id=eq.${encodeURIComponent(id)}&project_id=eq.${this.project().id}&order=name`);
    return rows[0]; }
  async downloadArtifact(item){
    if(!this.session)throw new Error('로그인이 필요합니다.');
    const a=await this.call('/rest/v1/rpc/request_artifact_download',{method:'POST',body:JSON.stringify({p_artifact_id:item.id})});
    const signed=await this.call('/storage/v1/object/sign/'+a.bucket+'/'+a.path,{method:'POST',body:JSON.stringify({expiresIn:120})});
    const url=new URL(signed.signedURL,this.url+'/storage/v1/');
    if(signed.signedURL?.startsWith('/object/'))url.pathname='/storage/v1'+url.pathname;
    if(url.origin!==this.url||!url.pathname.startsWith('/storage/v1/object/sign/aurora-artifacts/'))throw new Error('서명 다운로드 경로 오류');
    return checkedBlob(url.href,a);
  }
  async requestRun(config,key) {
    if(!this.session || !this.dataset) throw new Error('로그인 후 준비된 데이터셋이 필요합니다.');
    const {horizon,season_length,validation_origins}=config;
    const chosen=this.dataset.dataset_kind==='public_retail'?{policy_inputs:config.policy_inputs||{}}:{horizon,season_length,validation_origins};
    return this.call('/rest/v1/rpc/request_forecast',{method:'POST',body:JSON.stringify({p_project_id:this.project().id,p_dataset_id:this.dataset.id,p_idempotency_key:key,p_config:chosen})});
  }
}
export async function demoApi() {
  try { const health=await jsonFetch('./api/health',{signal:AbortSignal.timeout(1500)}); if(health.mode==='local'){const api=new LocalApi();await api.loadDatasets();return api;} } catch { /* GitHub Pages provides only the saved synthetic snapshot. */ }
  return new PreviewApi();
}

export async function checkedBlob(url,meta){
 const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error('다운로드 권한·연결을 확인하세요.');
 const data=await response.arrayBuffer();if(data.byteLength!==meta.bytes||data.byteLength>48*1024*1024)throw new Error('파일 크기가 다릅니다.');
 const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data)),n=>n.toString(16).padStart(2,'0')).join('');
 if(sha!==meta.sha256)throw new Error('파일 SHA-256이 다릅니다.');return new Blob([data],{type:meta.mime||'application/octet-stream'});
}
