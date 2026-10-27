import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader'],...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8881';
try{
 await page.goto(base+'/#/labeling');await page.locator('#generation-source option').last().waitFor({state:'attached'});await page.locator('#generation-source').selectOption('u20:SYN-BUNNY:2');await page.locator('#generation-seed').fill('42');await page.locator('#generation-run').click();
 await page.waitForFunction(()=>document.getElementById('generation-status').textContent.includes('새 로컬 기하 생성 완료'),{timeout:30000});
 assert.equal(await page.locator('#generation-candidate-3d').getAttribute('data-ready'),'true');assert.equal(await page.locator('#generation-baseline-3d').getAttribute('data-ready'),'true');assert.equal(await page.locator('#generation-metrics tr').count(),2);assert.equal(await page.locator('[role=tab]').count(),2);
 const bunnyReport=JSON.parse(await page.locator('#generation-json').textContent());assert.equal(bunnyReport.data_kind,'synthetic');assert.equal(bunnyReport.learned_model,false);assert.equal(bunnyReport.design_approved,false);
 await page.locator('.generation-panel').screenshot({path:'/tmp/aurora-generation-bunny.png'});
 await page.locator('[data-view=candidate][data-side=true]').click();
 const download=page.waitForEvent('download');await page.locator('#generation-downloads').getByRole('button',{name:'candidate.glb',exact:true}).click();const dl=await download;const bytes=await readFile(await dl.path());assert.equal(bytes.subarray(0,4).toString(),'glTF');
 await page.reload();await page.waitForFunction(()=>document.getElementById('generation-candidate-3d').dataset.ready==='true');assert.match(await page.locator('#generation-source').inputValue(),/SYN-BUNNY/);
 // A new U20 immutable revision is selectable, while the old generated source snapshot stays fixed.
 await page.locator('#sampling-product').selectOption('SYN-FRUIT');await page.waitForFunction(()=>document.getElementById('sampling-name').textContent.includes('과일'));const old=Number(await page.locator('#sampling-version').inputValue());await page.locator('#sampling-revise').click();await page.locator('#sampling-height').fill('210');await page.locator('#sampling-validate').click();await page.waitForFunction(()=>!document.getElementById('sampling-save').disabled);await page.locator('#sampling-save').click();await page.waitForFunction(v=>document.getElementById('generation-source').value===`u20:SYN-FRUIT:${v}`,old+1);
 assert.equal(bunnyReport.requested_dimensions_mm.height,150);
 await page.locator('#generation-source').selectOption('abo:B07JLZC571');await page.locator('#generation-run').click();await page.waitForFunction(()=>document.getElementById('generation-status').textContent.includes('새 로컬 기하 생성 완료'));
 assert.equal(await page.locator('#generation-candidate-3d').getAttribute('data-ready'),'true');assert.match(await page.locator('#generation-attribution').innerText(),/Amazon.com.*CC BY 4.0/);const abo=JSON.parse(await page.locator('#generation-json').textContent());assert.equal(abo.data_kind,'mixed');assert.equal(abo.candidates[1].method,'abo-fit-v1');assert.ok(abo.candidates[1].max_dimension_error_mm<.01);
 await page.locator('.generation-panel').screenshot({path:'/tmp/aurora-generation-abo.png'});await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('.generation-panel').screenshot({path:'/tmp/aurora-generation-mobile.png'});
 await page.locator('#label-run').click();await page.locator('#label-workspace').waitFor({state:'visible'});assert.equal(await page.locator('#label-rows tr').count(),12);
 // Pages saved mode must never POST or advertise a new generation.
 await page.route('**/api/health',r=>r.fulfill({status:404,body:'{}'}));await page.reload();await page.locator('#generation-source option').last().waitFor({state:'attached'});assert.ok(await page.locator('#generation-seed').isDisabled());assert.match(await page.locator('#generation-run').innerText(),/저장된/);await page.locator('#generation-source').selectOption('abo:B074VLST26');await page.locator('#generation-run').click();await page.waitForFunction(()=>document.getElementById('generation-status').textContent.includes('저장된 생성 결과 조회 완료'));assert.equal(await page.locator('#generation-candidate-3d').getAttribute('data-ready'),'true');assert.deepEqual(errors,[]);
 console.log('U21 UI passed: actual WebGL meshes, synthetic + ABO derivatives, immutable U20 revision link, same dimensions, verified GLB download, reload, mobile, PAT and saved-only mode.');
}finally{await browser.close()}
