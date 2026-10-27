import test from 'node:test';
import assert from 'node:assert/strict';
import {PreviewApi,SupabaseApi} from '../client/js/api.js';
test('preview data selection isolates run IDs and files',async()=>{
 const old=globalThis.fetch;let requested=[];
 globalThis.fetch=async url=>{requested.push(url);return {ok:true,json:async()=>({source:url})};};
 try{
  const api=new PreviewApi();assert.equal((await api.listRuns())[0].id,'saved-demo');await api.getRun('saved-demo');
  api.dataset=api.datasets[1];assert.equal((await api.listRuns())[0].id,'saved-research');await api.getRun('saved-research');
  await assert.rejects(api.getRun('saved-demo'));assert.deepEqual(requested,['./demo/baseline.json','./demo/research.json']);
 }finally{globalThis.fetch=old;}
});
test('cloud dataset choice filters runs and requests chosen dataset',async()=>{
 const api=new SupabaseApi('https://example.supabase.co','sb_publishable_synthetic-test-key');api.session={};let calls=[];
 api.call=async(path,options={})=>{calls.push([path,options]);if(path.startsWith('/rest/v1/projects'))return [{id:'project',project_type:'forecast'}];if(path.startsWith('/rest/v1/datasets'))return [{id:'new',generator_config:{skus:100}},{id:'old',generator_config:{skus:50}}];if(path.startsWith('/rest/v1/runs?select=*'))return [{id:'run'}];return [];};
 await api.loadProjects();assert.equal(api.dataset.id,'new');api.dataset=api.datasets[1];await api.loadProjects();assert.equal(api.dataset.id,'old');await api.listRuns();await api.getRun('run');await api.requestRun({horizon:4,season_length:52,validation_origins:3},'key');
 assert.ok(calls.some(([url])=>url.includes('dataset_id=eq.old')));
 assert.equal(JSON.parse(calls.at(-1)[1].body).p_dataset_id,'old');
});
test('local registered files isolate dataset runs and never send generator size controls',async()=>{
 const old=globalThis.fetch;const calls=[];globalThis.fetch=async(url,options={})=>{calls.push([url,options]);return {ok:true,json:async()=>url==='./api/datasets'?[{id:'local-generated'},{id:'weekly-abc',dataset_kind:'weekly_file'}]:{id:'job'}};};
 try{const {LocalApi}=await import('../client/js/api.js');const api=new LocalApi();await api.loadDatasets();api.dataset=api.datasets[1];await api.loadDatasets();assert.equal(api.dataset.id,'weekly-abc');await api.listRuns();await api.getRun('job');await api.requestRun({horizon:4,season_length:13,validation_origins:3},'key');const request=JSON.parse(calls.at(-1)[1].body);assert.equal(request.dataset_id,'weekly-abc');assert.equal(request.config.skus,undefined);assert.ok(calls.some(([url])=>url.includes('runs/job?dataset_id=weekly-abc')));await api.cancelRun('job');assert.equal(JSON.parse(calls.at(-1)[1].body).dataset_id,'weekly-abc');}finally{globalThis.fetch=old;}
});
