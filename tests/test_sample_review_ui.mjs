import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8883';
async function role(id){await page.locator('#review-persona').selectOption(id);await page.locator('#review-persona-apply').click();await page.waitForFunction(id=>document.getElementById('review-actor').textContent.includes(' · '+id+' · '),id);}
async function event(action,expected='저장 완료'){
 await page.locator('#review-action').selectOption(action);await page.locator('#review-comment').fill('브라우저 합성 '+action);await page.locator('#review-send').click();await page.waitForFunction(text=>document.getElementById('review-status').textContent.includes(text),expected);
}
async function checks(status){for(const select of await page.locator('#review-checks select').all())await select.selectOption(status);for(const area of await page.locator('#review-checks textarea').all())await area.fill('브라우저 합성 검토 사유');}
try{
 await page.goto(base+'/#/labeling');await page.locator('#review-candidate option').last().waitFor({state:'attached'});
 if(!process.env.AURORA_PAGES){
  await role('designer');await page.locator('#review-register').evaluate(e=>e.open=true);
  const opts=await page.locator('#review-candidate option').evaluateAll(nodes=>nodes.map(n=>({value:n.value,text:n.textContent})));
  const one=opts.find(n=>n.value.includes(':ai:')&&n.value.endsWith(':preserve')&&n.text.includes('고양이'));
  const two=opts.find(n=>n.value.includes(':ai:')&&n.value.endsWith(':reinterpret')&&n.text.includes('고양이'));
  assert.ok(one&&two);await page.locator('#review-candidate').selectOption(one.value);await page.locator('#review-reason').fill('첫 합성 고양이 원화 보존 후보');await page.locator('#review-new').click();await page.waitForFunction(()=>document.getElementById('review-status').textContent.includes('저장 완료'));
  assert.equal(JSON.parse(await page.locator('#review-json').textContent()).head_version,1);
  await event('submit');await role('approver');await event('approve','실패');assert.match(await page.locator('#review-status').innerText(),/검토 결과/);
  await role('reviewer');await checks('fail');await event('review');await event('request_changes');
  await role('designer');await page.locator('#review-candidate').selectOption(two.value);await page.locator('#review-reason').fill('외형 표현을 바꾼 새 생성 후보로 수정');await page.locator('#review-new').click();await page.waitForFunction(()=>document.getElementById('review-status').textContent.includes('저장 완료'));
  assert.equal(JSON.parse(await page.locator('#review-json').textContent()).head_version,2);assert.match(await page.locator('#review-summary').innerText(),/승인 없음/);
  await event('submit');await role('reviewer');await checks('pass');await event('review');await role('approver');await event('approve');assert.match(await page.locator('#review-summary').innerText(),/현재 유효한 가상 승인/);
  const request=page.waitForEvent('download');await page.locator('#review-download').click();const dl=await request;const exported=JSON.parse(await readFile(await dl.path(),'utf8'));assert.equal(exported.revisions.length,2);assert.equal(exported.revisions[1].active_approval,true);assert.equal(exported.asset_hashes_verified,true);
  await page.locator('.sample-review-panel').screenshot({path:'/tmp/aurora-u22-local.png'});
  await page.locator('#review-version').selectOption('1');assert.ok(await page.locator('#review-send').isDisabled());await page.locator('#review-version').selectOption('2');await page.reload();await page.waitForFunction(()=>document.getElementById('review-summary').textContent.includes('현재 유효한 가상 승인'));
  // Change U20 through the real UI: the historical approval remains, active validity clears.
  await page.locator('#sampling-product').selectOption('SYN-CAT');await page.waitForFunction(()=>document.getElementById('sampling-name').textContent.includes('고양이'));
  await page.locator('#sampling-revise').click();await page.locator('#sampling-height').fill('211');await page.locator('#sampling-validate').click();await page.waitForFunction(()=>!document.getElementById('sampling-save').disabled);await page.locator('#sampling-save').click();await page.waitForFunction(()=>document.getElementById('review-summary').textContent.includes('U20 명세 변경'));
  await role('viewer');assert.ok(await page.locator('#review-new').isDisabled());assert.ok(await page.locator('#review-send').isDisabled());
  await page.route('**/api/health',r=>r.fulfill({status:404,body:'{}'}));await page.reload();
 }
 await page.locator('#review-product option').last().waitFor({state:'attached'});let posts=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('sample-reviews'))posts++;});
 await page.locator('#review-product').selectOption('SYN-BUNNY');await page.waitForFunction(()=>document.getElementById('review-summary').textContent.includes('SYN-BUNNY')&&document.getElementById('review-summary').textContent.includes('현재 유효한 가상 승인'));
 assert.ok(await page.locator('#review-new').isDisabled());assert.ok(await page.locator('#review-send').isDisabled());assert.ok(await page.locator('#review-persona-apply').isDisabled());assert.equal(await page.locator('#review-version option').count(),2);
 await page.waitForFunction(()=>document.getElementById('review-after').complete&&document.getElementById('review-after').naturalWidth===512);
 const fileWait=page.waitForEvent('download');await page.locator('#review-assets button').first().click();const fileDownload=await fileWait;const fileBytes=await readFile(await fileDownload.path());const snap=JSON.parse(await page.locator('#review-json').textContent()).revisions[1];assert.equal(createHash('sha256').update(fileBytes).digest('hex'),snap.assets[0].sha256);
 await page.locator('.sample-review-panel').screenshot({path:'/tmp/aurora-u22-pages.png'});
 await page.locator('#review-product').selectOption('SYN-CAT');await page.waitForFunction(()=>document.getElementById('review-summary').textContent.includes('SYN-CAT'));let r=JSON.parse(await page.locator('#review-json').textContent());assert.ok(r.revisions[0].approval);assert.equal(r.revisions[0].active_approval,false);assert.equal(r.revisions[1].active_approval,false);
 await page.locator('#review-product').selectOption('SYN-COW');await page.waitForFunction(()=>document.getElementById('review-status').textContent.includes('크기/SHA-256 확인')&&document.getElementById('review-summary').textContent.includes('SYN-COW'));
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('.sample-review-panel').screenshot({path:'/tmp/aurora-u22-mobile.png'});
 await page.locator('#label-run').click();await page.locator('#label-workspace').waitFor({state:'visible'});assert.equal(await page.locator('#label-rows tr').count(),12);assert.equal(await page.locator('[role=tab]').count(),2);assert.equal(posts,0);assert.deepEqual(errors,[]);
 await writeFile('/tmp/aurora-u22-ui.json',JSON.stringify({base,pages:!!process.env.AURORA_PAGES,posts,errors,checks:[...(!process.env.AURORA_PAGES?['role session','revision / failed review / changes requested / actual different candidate','pass review / bound approval','download / reload','old revision blocked','U20 change invalidates active approval']:[]),'saved AI and geometry version comparison','previous approval not inherited','read-only Pages','mobile','two tabs','PAT regression']},null,2));console.log('U22 browser passed: '+(process.env.AURORA_PAGES?'saved-only':'local lifecycle + saved mode')+'; no errors.');
}finally{await browser.close();}
