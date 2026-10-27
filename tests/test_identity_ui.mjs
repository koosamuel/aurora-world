import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const page=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8878';
try{
 await page.goto(base);await page.locator('#identity-panel>summary').click();
 await page.locator('#identity-run').click();await page.waitForFunction(()=>!document.getElementById('identity-result').hidden);
 assert.match(await page.locator('#identity-status').textContent(),/로컬에서 새로 계산/);
 assert.match(await page.locator('#identity-summary').textContent(),/원천 5행 = 연결 5행 \+ 격리 0행/);
 assert.equal(JSON.parse(await page.locator('#identity-json').textContent()).accepted[0].source_code,'0012');
 await page.locator('#identity-case').selectOption('conflicts');await page.locator('#identity-run').click();
 await page.waitForFunction(()=>document.getElementById('identity-summary').textContent.includes('격리 8행'));
 assert.match(await page.locator('#identity-status').textContent(),/격리·대응표 확인 필요/);
 assert.match(await page.locator('#identity-balance').textContent(),/수량 수지 보존 확인/);
 await page.screenshot({path:'/tmp/aurora-identity-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:'/tmp/aurora-identity-mobile.png',fullPage:true});
 await page.locator('#tab-labeling').click();assert.equal(await page.locator('#identity-panel').isVisible(),false);
 await page.locator('#tab-forecast').click();assert.equal(await page.locator('#identity-panel').isVisible(),true);
 // Static deployment is a saved result, never represented as a new computation.
 await page.route('**/api/health',route=>route.fulfill({status:404,body:'{}'}));
 await page.locator('#identity-run').click();await page.waitForFunction(()=>document.getElementById('identity-status').textContent.includes('저장된 합성 점검 결과'));
 // A functioning local health endpoint with a failed audit must remain failed.
 await page.unroute('**/api/health');await page.route('**/api/identity-demo?*',route=>route.fulfill({status:400,body:'{"error":"invalid"}'}));
 await page.locator('#identity-run').click();await page.waitForFunction(()=>document.getElementById('identity-status').textContent.includes('점검 실패'));
 assert.equal(await page.locator('#identity-result').isVisible(),false);assert.deepEqual(errors,[]);
 console.log('Identity UI passed: local calculation, quarantine/balance, scope separation, mobile, saved fallback and fail-closed local errors.');
}finally{await browser.close();}
