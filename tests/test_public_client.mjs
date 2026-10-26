import assert from 'node:assert/strict';
import {test} from 'node:test';
import {SupabaseApi,checkedBlob} from '../client/js/api.js';
const sha=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),n=>n.toString(16).padStart(2,'0')).join('');
const api=()=>{const a=new SupabaseApi('https://example.supabase.co','sb_publishable_only-test-public');a.session={access_token:'fake'};a.expires=Infinity;a.projects=[{id:'p',project_type:'forecast'}];a.dataset={id:'d',dataset_kind:'public_retail'};return a;};
test('public request transmits only policy inputs, never synthetic horizon controls',async()=>{
 const old=globalThis.fetch;let body;globalThis.fetch=async(_url,options)=>{body=JSON.parse(options.body);return Response.json({id:'run',status:'queued'});};
 try{await api().requestRun({horizon:4,policy_inputs:{'UCI-12345':{initial_stock:2}}},'key');assert.deepEqual(body.p_config,{policy_inputs:{'UCI-12345':{initial_stock:2}}});}finally{globalThis.fetch=old;}
});
test('legacy server without new dataset column keeps existing synthetic access',async()=>{
 const old=globalThis.fetch;let fallback=false;globalThis.fetch=async url=>{
  if(url.includes('/projects?'))return Response.json([{id:'p',project_type:'forecast'}]);
  if(url.includes('dataset_kind'))return Response.json({message:'column dataset_kind does not exist'},{status:400});
  fallback=url.includes('synthetic=eq.true');return Response.json([{id:'legacy',name:'합성',generator_config:{skus:50,weeks:156}}]);
 };
 try{const a=api();await a.loadProjects();assert.equal(a.dataset.id,'legacy');assert.equal(a.publicExecutionReady,false);assert.ok(fallback);}finally{globalThis.fetch=old;}
});
test('private artifact uses audited request and same-project signed URL then checks bytes',async()=>{
 const old=globalThis.fetch;const bytes=new TextEncoder().encode('abc');const hash=await sha(bytes);let requested=false,signed=false;
 globalThis.fetch=async(url,options)=>{
  if(url.endsWith('request_artifact_download')){requested=true;assert.deepEqual(JSON.parse(options.body),{p_artifact_id:'a'});return Response.json({bucket:'aurora-artifacts',path:'p/runs/x/report.md',bytes:3,sha256:hash});}
  if(url.includes('/storage/v1/object/sign/')&&options.method==='POST'){signed=true;return Response.json({signedURL:'/object/sign/aurora-artifacts/p/runs/x/report.md?token=fake'});}
  assert.equal(url,'https://example.supabase.co/storage/v1/object/sign/aurora-artifacts/p/runs/x/report.md?token=fake');return new Response(bytes);
 };
 try{assert.equal(await (await api().downloadArtifact({id:'a'})).text(),'abc');assert.ok(requested&&signed);}finally{globalThis.fetch=old;}
});
test('download corruption cannot be reported as a verified file',async()=>{
 const old=globalThis.fetch;globalThis.fetch=async()=>new Response('bad');
 try{await assert.rejects(()=>checkedBlob('http://localhost/file',{bytes:3,sha256:'a'.repeat(64)}),/SHA-256/);}finally{globalThis.fetch=old;}
});
