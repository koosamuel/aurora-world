// Opt-in: REAL neural inference for all four local demos. No mock outputs.
// PLAYWRIGHT_MODULE=file:///.../playwright/index.mjs CHROME_PATH=/.../Chrome
// AURORA_URL=http://127.0.0.1:8765 AURORA_EVIDENCE=/absolute/private/output node tools/verify_sketch_demos.mjs
import assert from 'node:assert/strict';import{mkdir,writeFile}from'node:fs/promises';import{join,isAbsolute}from'node:path';import{createHash}from'node:crypto';
const base=process.env.AURORA_URL||'http://127.0.0.1:8765',out=process.env.AURORA_EVIDENCE;if(!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base)||!out||!isAbsolute(out))throw Error('Loopback URL and absolute private evidence path required');
const{chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');await mkdir(out,{recursive:true});const b=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
try{
 const p=await b.newPage({viewport:{width:1280,height:950}}),errors=[],results=[];let confirms=0;p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/confirm'))confirms++;});
 await p.goto(base+'/index.html#/labeling');await p.locator('#tab-labeling').click();await p.waitForFunction(()=>document.querySelectorAll('#l3-demo-cards button').length===4);
 const catalog=await(await p.request.get(base+'/api/learned3d/demos')).json();assert.equal(catalog.demos.length,4);
 for(const d of catalog.demos){
  const image=await p.request.get(base+'/api/learned3d/demo-images/'+d.demo_id);assert.equal(image.status(),200);assert.equal(createHash('sha256').update(await image.body()).digest('hex'),d.image_sha256);
  const before=confirms;await p.locator('[data-demo-id="'+d.demo_id+'"]').click();assert.equal(await p.locator('#l3-file').isDisabled(),true);assert.equal(await p.locator('#l3-store-consent').isChecked(),false);assert.equal(confirms,before);
  const invalid=await p.request.post(base+'/api/learned3d/demo-runs',{data:{demo_id:d.demo_id,source_checksum:d.checksum,storage_consent:false}});assert.equal(invalid.status(),400);
  const stale=await p.request.post(base+'/api/learned3d/demo-runs',{data:{demo_id:d.demo_id,source_checksum:'0'.repeat(64),storage_consent:true}});assert.equal(stale.status(),400);
  await p.locator('#l3-store-consent').check();await p.locator('#l3-run').click();await p.locator('#l3-preflight').waitFor({state:'visible',timeout:90000});assert.equal(confirms,before);assert.equal(await p.locator('#l3-confirm').isDisabled(),true);
  await p.locator('#l3-foreground-confirmed').check();await p.locator('#l3-confirm').click();await p.locator('#l3-result').waitFor({state:'visible',timeout:180000});await p.waitForFunction(()=>document.querySelector('#l3-viewer').dataset.ready==='true'&&!document.querySelector('#l3-run').disabled);
  const row=JSON.parse(await p.locator('#l3-report').textContent());assert.equal(row.source_id,d.id);assert.equal(row.source_kind,'local_sketch_demo');assert.equal(row.family,d.family);assert.equal(row.report.family,d.family);assert.equal(row.report.prompt,d.prompt);assert.equal(row.status,'succeeded');assert.equal(confirms,before+1);
  const dir=join(out,d.demo_id);await mkdir(dir,{recursive:true});await writeFile(join(dir,'state.json'),JSON.stringify(row,null,2));
  for(const m of row.artifacts){const response=await p.request.get(base+'/api/learned3d/artifacts/'+row.id+'/'+m.file),bytes=await response.body();assert.equal(response.status(),200);assert.equal(bytes.length,m.bytes);assert.equal(createHash('sha256').update(bytes).digest('hex'),m.sha256);await writeFile(join(dir,m.file),bytes);}
  if(d.demo_id==='duck'){await p.locator('#l3-projection-confirmed').check();await p.locator('#l3-project').click();await p.locator('#l3-projected-result').waitFor({state:'visible',timeout:90000});await p.waitForFunction(()=>document.querySelector('#l3-projected-viewer').dataset.ready==='true'&&!document.querySelector('#l3-project').disabled);const projection=JSON.parse(await p.locator('#l3-projection-report').textContent());assert.equal(projection.report.geometry_preserved,true);await writeFile(join(dir,'projection-state.json'),JSON.stringify(projection,null,2));}
  await p.locator('#learned3d-panel').screenshot({path:join(dir,'screen.png')});results.push({demo_id:d.demo_id,run_id:row.id,family:row.family,status:row.status,vertices:row.report.vertices,faces:row.report.faces,elapsed_seconds:row.report.elapsed_seconds,real_inference:true,artifact_hashes_verified:true});console.log(JSON.stringify(results.at(-1)));
 }
 await p.setViewportSize({width:390,height:844});await p.locator('[data-demo-id="bear"]').click();await p.waitForTimeout(200);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await p.locator('#l3-demos').screenshot({path:join(out,'mobile-cards.png')});
 await p.locator('#l3-upload-mode').click();assert.equal(await p.locator('#l3-file').isDisabled(),false);assert.equal(await p.locator('#l3-store-consent').isChecked(),false);assert.equal(await p.locator('#l3-result').isVisible(),false);assert.deepEqual(errors,[]);
 await writeFile(join(out,'verification.json'),JSON.stringify({results,confirms,no_automatic_inference:true,requires_consent:true,requires_foreground_confirmation:true,upload_mode_retained:true,mobile_overflow:false,page_errors:errors},null,2));
}finally{await b.close();}
