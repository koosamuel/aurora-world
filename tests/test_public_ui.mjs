import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const page=await browser.newPage();const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8877';const errors=[];
page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(base);await page.locator('#dataset-picker option').last().waitFor({state:'attached'});
 const options=await page.locator('#dataset-picker option').evaluateAll(xs=>xs.map(x=>({id:x.value,text:x.textContent})));const pub=options.find(x=>x.text.includes('UCI'));
 assert.ok(pub);await page.locator('#dataset-picker').selectOption(pub.id);
 await page.locator('#run').click();await page.locator('#public-result').waitFor({state:'visible',timeout:45000});
 assert.equal((await page.locator('#public-naive').textContent()).trim(),'178.269');assert.match(await page.locator('#public-verdict').textContent(),/나빴/);
 assert.equal(await page.locator('#public-inventory tr').count(),12);
 await page.locator('#public-scenario').selectOption('lead2_history');assert.equal(await page.locator('#public-inventory tr').count(),4);
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'report.md 받기',exact:true}).click();const file=await download;
 assert.match(await readFile(await file.path(),'utf8'),/공개 거래 자료/);await page.getByText('다운로드 파일의 크기·SHA-256 확인 완료',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:'/tmp/aurora-public-local.png',fullPage:true});
 await page.locator('#public-policy').fill('[');await page.locator('#run').click();assert.match(await page.locator('#notice').textContent(),/실행 설정/);
 await page.route('**/api/health',r=>r.fulfill({status:404,contentType:'application/json',body:'{}'}));
 await page.reload();await page.locator('#dataset-picker').selectOption('saved-public-retail');await page.locator('#run').click();await page.locator('#public-result').waitFor({state:'visible'});
 assert.equal(await page.locator('#public-downloads button').count(),3);assert.ok(await page.locator('#public-policy').isDisabled());
 assert.equal(errors.length,0,errors.join('\n'));console.log('Public UI passed: actual local compute, 12/4 scenarios, verified report download, malformed policy, mobile overflow, static public preview.');
}finally{await browser.close();}
