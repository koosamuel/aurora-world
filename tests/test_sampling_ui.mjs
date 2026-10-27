import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8879';
try{
 await page.goto(base+'/#/labeling');await page.locator('#sampling-product option').last().waitFor({state:'attached'});
 assert.equal(await page.locator('[role=tab]').count(),2);await page.locator('#sampling-product').selectOption('SYN-BUNNY');
 await page.waitForFunction(()=>document.getElementById('sampling-name').textContent==='가상 앉은 토끼');
 assert.match(await page.locator('#sampling-mode').textContent(),/로컬 합성 등록/);assert.ok(await page.locator('#sampling-height').isDisabled());
 await page.waitForFunction(()=>document.getElementById('sampling-artwork').complete&&document.getElementById('sampling-artwork').naturalWidth>0);
 const oldVersion=Number(await page.locator('#sampling-version').inputValue());const oldHeight=Number(await page.locator('#sampling-height').inputValue());
 await page.locator('#sampling-revise').click();await page.locator('#sampling-height').fill(String(oldHeight+17));assert.ok(await page.locator('#sampling-save').isDisabled());
 await page.locator('#sampling-validate').click();await page.waitForFunction(()=>!document.getElementById('sampling-save').disabled);
 // Any subsequent edit must invalidate the previous validation.
 await page.locator('#sampling-height').fill(String(oldHeight+18));assert.ok(await page.locator('#sampling-save').isDisabled());
 await page.locator('#sampling-validate').click();await page.waitForFunction(()=>!document.getElementById('sampling-save').disabled);
 await page.locator('#sampling-save').click();await page.waitForFunction(()=>document.getElementById('sampling-status').textContent.includes('새 명세 버전을 로컬에 등록'));
 assert.equal(Number(await page.locator('#sampling-version').inputValue()),oldVersion+1);assert.equal(Number(await page.locator('#sampling-height').inputValue()),oldHeight+18);
 await page.reload();await page.locator('#sampling-product option').last().waitFor({state:'attached'});await page.locator('#sampling-product').selectOption('SYN-BUNNY');
 await page.waitForFunction(v=>Number(document.getElementById('sampling-version').value)===v,oldVersion+1);
 await page.locator('#sampling-version').selectOption(String(oldVersion));await page.waitForFunction(h=>Number(document.getElementById('sampling-height').value)===h,oldHeight);
 assert.ok(await page.locator('#sampling-revise').isDisabled());
 await page.locator('#sampling-product').selectOption('SYN-FRUIT');await page.waitForFunction(()=>document.getElementById('sampling-baseline').textContent.includes('미측정'));
 assert.doesNotMatch(await page.locator('#sampling-baseline').textContent(),/실물 0/);
 const download=page.waitForEvent('download');await page.locator('#sampling-export').click();const file=await download;const body=JSON.parse(await readFile(await file.path(),'utf8'));assert.equal(body.product_id,'SYN-FRUIT');
 // Malicious SVG is rehashed to prove validation is more than a checksum comparison.
 const bad=structuredClone(body);bad.artwork.svg=bad.artwork.svg.replace('</svg>','<script>alert(1)</script></svg>');bad.artwork.sha256=createHash('sha256').update(bad.artwork.svg).digest('hex');
 await page.locator('#sampling-file').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(bad))});
 await page.waitForFunction(()=>document.getElementById('sampling-status').textContent.includes('파일 검증 실패'));assert.ok(await page.locator('#sampling-save').isDisabled());
 // A valid existing file can be idempotently registered.
 await page.locator('#sampling-file').setInputFiles({name:'valid.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(body))});
 await page.waitForFunction(()=>!document.getElementById('sampling-save').disabled);await page.locator('#sampling-save').click();await page.waitForFunction(()=>document.getElementById('sampling-status').textContent.includes('이미 등록된 동일 명세'));
 await page.locator('.sampling-panel').screenshot({path:'/tmp/aurora-sampling-desktop.png'});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('.sampling-panel').screenshot({path:'/tmp/aurora-sampling-mobile.png'});
 // The pre-existing labeling demo still classifies pieces.
 await page.locator('#label-run').click();await page.locator('#label-workspace').waitFor({state:'visible'});assert.equal(await page.locator('#label-rows tr').count(),12);
 await page.route('**/api/health',r=>r.fulfill({status:404,contentType:'application/json',body:'{}'}));await page.reload();await page.locator('#sampling-product option').last().waitFor({state:'attached'});
 assert.match(await page.locator('#sampling-mode').textContent(),/저장된 합성 명세/);assert.ok(await page.locator('#sampling-file').isDisabled());assert.ok(await page.locator('#sampling-revise').isDisabled());assert.ok(await page.locator('#sampling-save').isDisabled());assert.ok(await page.locator('#sampling-export').isEnabled());
 assert.deepEqual(errors,[]);console.log('U20 UI passed: immutable revision/persistence, validation invalidation, original preserved, unknown baseline, export/import, malicious SVG rejection, idempotency, mobile, original labeling and saved-only mode.');
}finally{await browser.close();}
