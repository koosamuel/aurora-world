import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{}),args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8882';
try{
 await page.goto(base+'/#/labeling');await page.locator('#ai-source option').last().waitFor({state:'attached'});
 assert.equal(await page.locator('[role=tab]').count(),2);
 if(!process.env.AURORA_PAGES){
  await page.locator('#ai-source').selectOption('u20:SYN-BUNNY:2');await page.locator('#ai-run').click();
  await page.waitForFunction(()=>/AI 생성\/조회 실패|로컬 AI 추론 완료/.test(document.getElementById('ai-status').textContent),undefined,{timeout:180000});
  assert.match(await page.locator('#ai-status').innerText(),/로컬 AI 추론 완료/);
  let r=JSON.parse(await page.locator('#ai-report').textContent());assert.equal(r.learned_model,true);assert.equal(r.output_type,'2D PNG');assert.equal(r.design_approved,false);assert.equal(r.dimensions_verified,false);assert.equal(r.candidates.length,2);assert.equal(r.input_analysis.hypothesis,'rabbit');
  await page.locator('.ai-panel').screenshot({path:'/tmp/aurora-ai-local.png'});
  const waiting=page.waitForEvent('download');await page.locator('#ai-downloads').getByRole('button',{name:'preserve.png',exact:true}).click();const dl=await waiting;const raw=await readFile(await dl.path());assert.equal(raw.subarray(0,8).toString('hex'),'89504e470d0a1a0a');const source=JSON.parse(await (await page.request.get(base+'/api/ai-sampling/runs/'+await page.evaluate(()=>sessionStorage.getItem('aurora-ai-run')))).text());assert.equal(createHash('sha256').update(raw).digest('hex'),source.result.artifacts.find(a=>a.file==='preserve.png').sha256);
  await page.reload();await page.waitForFunction(()=>document.getElementById('ai-status').textContent.includes('로컬 AI 추론 완료'),undefined,{timeout:30000});
  await page.route('**/api/health',r=>r.fulfill({status:404,body:'{}'}));await page.reload();
 }
 await page.locator('#ai-source option').last().waitFor({state:'attached'});assert.ok(await page.locator('#ai-seed').isDisabled());
 let posts=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().includes('ai-sampling'))posts++;});
 for(const source of ['u20:SYN-BUNNY:2','u20:SYN-CAT:2','u20:SYN-FRUIT:2']){
  await page.locator('#ai-source').selectOption(source);await page.locator('#ai-run').click();await page.waitForFunction(()=>document.getElementById('ai-status').textContent.includes('저장된 실제 AI 추론 조회 완료'),undefined,{timeout:30000});
  await page.waitForFunction(()=>['ai-preserve','ai-reinterpret'].every(id=>{const e=document.getElementById(id);return e.complete&&e.naturalWidth===512;}));
 }
 await page.locator('#ai-source').selectOption('u20:SYN-COW:2');await page.locator('#ai-run').click();await page.waitForFunction(()=>document.getElementById('ai-status').textContent.includes('실패'));assert.ok(await page.locator('#ai-result').isHidden());
 await page.locator('#ai-source').selectOption('u20:SYN-BUNNY:2');await page.locator('#ai-run').click();await page.waitForFunction(()=>document.getElementById('ai-status').textContent.includes('저장된 실제 AI 추론 조회 완료'));await page.locator('.ai-panel').screenshot({path:'/tmp/aurora-ai-pages.png'});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('.ai-panel').screenshot({path:'/tmp/aurora-ai-mobile.png'});
 await page.locator('#label-run').click();await page.locator('#label-workspace').waitFor({state:'visible'});assert.equal(await page.locator('#label-rows tr').count(),12);
 assert.equal(posts,0);assert.deepEqual(errors,[]);
 await writeFile('/tmp/aurora-ai-ui.json',JSON.stringify({base,pages:!!process.env.AURORA_PAGES,posts,errors,checks:[...(!process.env.AURORA_PAGES?['real local inference / refresh / PNG download']:[]),'three saved AI comparisons','explicit failed output','512px images','two tabs','mobile no overflow','PAT regression']},null,2));
 console.log(process.env.AURORA_PAGES?'AI Pages passed: saved real inference, hash-verified images, explicit failure, mobile, two tabs, PAT and zero POSTs.':'AI local UI passed: real inference, persisted lookup, hash-verified PNG download, saved results, failure, mobile, two tabs and PAT.');
}finally{await browser.close();}
