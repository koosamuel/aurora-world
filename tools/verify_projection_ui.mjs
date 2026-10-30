// Opt-in REAL local inference + projection check. No mocks, upload service or paid APIs.
// PLAYWRIGHT_MODULE=file:///absolute/playwright/index.mjs AURORA_SKETCH=/absolute/input.jpg
// AURORA_URL=http://127.0.0.1:9878 AURORA_EVIDENCE=/absolute/private/output node tools/verify_projection_ui.mjs
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {join,isAbsolute} from 'node:path';
import {createHash} from 'node:crypto';
const base=process.env.AURORA_URL||'http://127.0.0.1:9878',input=process.env.AURORA_SKETCH,out=process.env.AURORA_EVIDENCE;
if(!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)||!input||!isAbsolute(input)||!out||!isAbsolute(out))throw Error('Explicit loopback URL, absolute input and private evidence paths required');
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
try{
 const p=await browser.newPage({viewport:{width:1280,height:950}}),errors=[];p.on('pageerror',e=>errors.push(e.message));
 let projectionPosts=0;p.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/projections'))projectionPosts++;});
 await p.goto(base+'/index.html#/labeling');await p.locator('#tab-labeling').click();
 await p.waitForFunction(()=>document.querySelectorAll('#generation-source option').length>0);
 const sources=await p.locator('#generation-source option').evaluateAll(os=>os.map(o=>o.value));const bunny=sources.find(x=>x.includes('BUNNY'));assert(bunny);
 await p.locator('#generation-source').selectOption(bunny);await p.waitForFunction(()=>!document.querySelector('#l3-run').disabled);
 assert.equal(await p.locator('#l3-project').isDisabled(),true);
 await p.locator('#l3-file').setInputFiles(input);await p.locator('#l3-store-consent').check();await p.locator('#l3-run').click();
 await p.locator('#l3-preflight').waitFor({state:'visible',timeout:90000});assert.equal(await p.locator('#l3-confirm').isDisabled(),true);
 await p.locator('#l3-foreground-confirmed').check();await p.locator('#l3-confirm').click();
 await p.locator('#l3-result').waitFor({state:'visible',timeout:180000});await p.waitForFunction(()=>document.querySelector('#l3-viewer').dataset.ready==='true');
 await p.waitForFunction(()=>!document.querySelector('#l3-run').disabled);assert.equal(projectionPosts,0);assert.equal(await p.locator('#l3-project').isDisabled(),true);
 const parent=JSON.parse(await p.locator('#l3-report').textContent());assert.equal(parent.engine,'TripoSG-scribble');assert.equal(parent.status,'succeeded');assert.equal(parent.foreground_confirmed,true);assert.notEqual(parent.report.integration_test_replay,true);
 const payload={parent_model_sha256:parent.artifacts.find(x=>x.file==='model.glb').sha256,source_image_sha256:parent.foreground_sha256,settings:{yaw:0,offset_x:0,offset_y:.1,scale:1},projection_confirmed:true},path=base+'/api/learned3d/runs/'+parent.id+'/projections';
 const rejected={};for(const [name,body,status,headers] of [['false', {...payload,projection_confirmed:false},400,{}],['stale',{...payload,parent_model_sha256:'0'.repeat(64)},400,{}],['range',{...payload,settings:{...payload.settings,yaw:90}},400,{}],['origin',payload,403,{Origin:'https://invalid.example'}]]){const r=await p.request.post(path,{data:body,headers});assert.equal(r.status(),status,name);rejected[name]=r.status();}
 await p.locator('#l3-projection-offset_y').fill('0.1');await p.locator('#l3-projection-confirmed').check();await p.locator('#l3-project').click();
 await p.locator('#l3-projected-result').waitFor({state:'visible',timeout:90000});await p.waitForFunction(()=>document.querySelector('#l3-projected-viewer').dataset.ready==='true');await p.waitForFunction(()=>!document.querySelector('#l3-project').disabled);
 const row=JSON.parse(await p.locator('#l3-projection-report').textContent());assert.equal(row.status,'succeeded');assert.equal(row.parent_run_id,parent.id);assert.equal(row.report.geometry_preserved,true);assert.equal(row.report.learned_texture,false);
 const duplicate=await p.request.post(path,{data:payload});assert.equal(duplicate.status(),201);assert.equal((await duplicate.json()).id,row.id);
 for(const m of row.artifacts){const response=await p.request.get(base+'/api/learned3d/projection-artifacts/'+row.id+'/'+m.file);assert.equal(response.status(),200);const bytes=await response.body();assert.equal(bytes.length,m.bytes);assert.equal(createHash('sha256').update(bytes).digest('hex'),m.sha256);await writeFile(join(out,m.file),bytes);}
 const original=await p.request.get(base+'/api/learned3d/artifacts/'+parent.id+'/model.glb');assert.equal(createHash('sha256').update(await original.body()).digest('hex'),payload.parent_model_sha256);
 const forbidden=await p.request.get(base+'/api/learned3d/projection-artifacts/'+row.id+'/worker.log');assert.equal(forbidden.status(),400);
 await p.locator('#learned3d-panel').screenshot({path:join(out,'integrated.png')});
 await p.setViewportSize({width:390,height:844});await p.waitForTimeout(200);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'mobile overflow');
 await p.locator('#l3-projection').screenshot({path:join(out,'mobile.png')});
 await p.locator('#generation-source').selectOption(sources.find(x=>!x.includes('BUNNY')));assert.equal(await p.locator('#l3-project').isDisabled(),true);assert.equal(await p.locator('#l3-result').isVisible(),false);
 assert.deepEqual(errors,[]);
 const evidence={parent_run_id:parent.id,projection_id:row.id,new_neural_inference:true,real_cpu_projection:true,rejected,idempotent:true,parent_file_unchanged:true,artifact_hashes_verified:true,private_file_blocked:true,mobile_overflow:false,source_change_clears:true,page_errors:errors,projection_ui_posts:projectionPosts,report:row.report};
 await writeFile(join(out,'parent-state.json'),JSON.stringify(parent,null,2));await writeFile(join(out,'projection-state.json'),JSON.stringify(row,null,2));await writeFile(join(out,'verification.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
}finally{await browser.close();}
