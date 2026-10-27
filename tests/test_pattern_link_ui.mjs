import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8887';let posts=0;
async function api(path,body,token){const r=await page.request.fetch(base+'/api/'+path,{method:body?'POST':'GET',headers:token?{Authorization:'Bearer '+token}:{},...(body?{data:body}:{})});assert.ok(r.ok(),await r.text());return r.json();}
async function ready(){await page.waitForFunction(()=>document.getElementById('pattern-status').textContent.includes('조회 완료'));}
try{
 await page.goto(base+'/#/labeling');await ready();
 if(!process.env.AURORA_PAGES){
  assert.ok(await page.locator('#pattern-create').isDisabled());
  const tokens={};for(const role of ['designer','reviewer','approver'])tokens[role]=(await api('sample-reviews/session',{persona_id:role})).token;
  const c=(await api('sample-reviews/catalog')).candidates.find(c=>c.product_id==='SYN-BUNNY'&&c.kind==='ai'&&c.candidate_id==='preserve');
  await api('sample-reviews/revisions',{candidate_id:c.id,candidate_checksum:c.checksum,parent_version:null,expected_seq:0,change_reason:'U23 브라우저용 합성 샘플',request_key:crypto.randomUUID()},tokens.designer);
  async function event(action){const r=await api('sample-reviews/products/SYN-BUNNY');const rev=r.revisions.at(-1);return api('sample-reviews/events',{product_id:'SYN-BUNNY',version:r.head_version,expected_seq:r.seq,action,comment:'U23 브라우저 합성 '+action,checks:action==='review'?rev.checklist.map(c=>({id:c.id,status:'pass',note:'합성 테스트'})):[],request_key:crypto.randomUUID()},tokens[{submit:'designer',review:'reviewer',approve:'approver',hold:'approver'}[action]]);}
  await event('submit');await event('review');await event('approve');
  await page.locator('#pattern-refresh').click();await ready();await page.locator('#pattern-persona').selectOption('designer');await page.locator('#pattern-persona-apply').click();await page.waitForFunction(()=>document.getElementById('pattern-status').textContent.includes('역할 적용 완료'));
  await page.locator('#pattern-bundle').selectOption('1');await ready();assert.ok(await page.locator('#pattern-create').isDisabled());await page.locator('#pattern-bundle').selectOption('2');await ready();
  await page.locator('#pattern-reason').fill('승인 샘플과 합성 PAT 버전의 수동 대응');await page.locator('#pattern-create').click();await page.waitForFunction(()=>document.getElementById('pattern-status').textContent.includes('연결 저장 완료'));
  assert.match(await page.locator('#pattern-summary').textContent(),/연결 v1 · 현재 유효/);assert.equal(await page.locator('#pattern-previews button').count(),12);
  await page.locator('.pattern-link-panel').screenshot({path:'/tmp/aurora-u23-local.png'});
  const dw=page.waitForEvent('download');await page.locator('#pattern-export').click();const dl=await dw;const r=JSON.parse(await readFile(await dl.path(),'utf8'));assert.equal(r.links[0].current_valid,true);assert.equal(r.asset_hashes_verified,true);
  await page.reload();await ready();assert.match(await page.locator('#pattern-summary').textContent(),/현재 유효/);
  await event('hold');await page.evaluate(()=>window.dispatchEvent(new Event('digital-review-updated')));await ready();await page.waitForFunction(()=>document.getElementById('pattern-summary').textContent.includes('승인 해제 또는 샘플·명세 변경'));assert.ok(await page.locator('#pattern-create').isDisabled());
  await event('submit');await event('review');await event('approve');await page.locator('#pattern-refresh').click();await ready();await page.locator('#pattern-reason').fill('재승인 사건에 새 연결');await page.locator('#pattern-create').click();await page.waitForFunction(()=>document.getElementById('pattern-status').textContent.includes('연결 저장 완료'));assert.equal(JSON.parse(await page.locator('#pattern-json').textContent()).head_version,2);assert.equal(await page.locator('#pattern-history tr').count(),2);
  await page.locator('#pattern-persona').selectOption('viewer');await page.locator('#pattern-persona-apply').click();await page.waitForFunction(()=>document.getElementById('pattern-status').textContent.includes('역할 적용 완료'));assert.ok(await page.locator('#pattern-create').isDisabled());
  await page.route('**/api/health',r=>r.fulfill({status:404,body:'{}'}));await page.reload();await ready();
 }
 page.on('request',r=>{if(r.method()==='POST'&&(/pattern-links|sample-reviews/.test(r.url())))posts++;});
 await page.locator('#pattern-product').selectOption('SYN-BUNNY');await ready();assert.ok(await page.locator('#pattern-create').isDisabled());assert.ok(await page.locator('#pattern-persona-apply').isDisabled());assert.match(await page.locator('#pattern-summary').textContent(),/연결 v2 · 현재 유효/);
 assert.equal(await page.locator('#pattern-rows tr').count(),12);assert.equal(await page.locator('#pattern-previews button').count(),12);assert.match(await page.locator('#pattern-audit').textContent(),/재단 수량 13 pcs/);assert.match(await page.locator('#pattern-impact').textContent(),/FABRIC-PATCH/);
 const dw=page.waitForEvent('download');await page.locator('#pattern-previews button').first().click();const dl=await dw;const raw=await readFile(await dl.path());const r=JSON.parse(await page.locator('#pattern-json').textContent());assert.equal(createHash('sha256').update(raw).digest('hex'),r.links[1].bundle.pieces[0].asset.slice(0,-4));
 await page.locator('.pattern-link-panel').screenshot({path:'/tmp/aurora-u23-saved.png'});
 await page.locator('#pattern-link-version').selectOption('1');await ready();assert.match(await page.locator('#pattern-summary').textContent(),/재확인 필요/);assert.equal(await page.locator('#pattern-bundle').inputValue(),'1');await page.locator('#pattern-link-version').selectOption('2');await ready();
 await page.locator('#pattern-product').selectOption('SYN-CAT');await ready();assert.match(await page.locator('#pattern-chain').textContent(),/현재 유효한 U22 승인 없음/);assert.equal(await page.locator('#pattern-history tr').count(),0);
 await page.locator('#pattern-product').selectOption('SYN-COW');await ready();await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('.pattern-link-panel').screenshot({path:'/tmp/aurora-u23-mobile.png'});
 await page.locator('#label-run').click();await page.locator('#label-workspace').waitFor({state:'visible'});assert.equal(await page.locator('#label-rows tr').count(),12);assert.equal(await page.locator('[role=tab]').count(),2);assert.equal(posts,0);assert.deepEqual(errors,[]);
 await writeFile('/tmp/aurora-u23-ui.json',JSON.stringify({base,pages:!!process.env.AURORA_PAGES,posts,errors,checks:[...(!process.env.AURORA_PAGES?['unapproved blocked','local role session','old bundle blocked','pin approval / bundle and store link','export / reload','revoke invalidates link / live event refresh','reapprove and relink / history','viewer blocked']:[]),'saved version / impact / units','12 hash-checked SVGs','SVG hash download','old link invalid','unapproved four cases','read only Pages','mobile','PAT / two tabs']},null,2));console.log('U23 browser passed: '+(process.env.AURORA_PAGES?'saved-only':'local lifecycle + saved')+'; no errors.');
}finally{await browser.close();}
