import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
const page=await browser.newPage();
const base=process.env.AURORA_TEST_URL||'http://127.0.0.1:8765';
const snapshot=await (await fetch(base+'/demo/baseline.json')).json();
const project='10000000-0000-4000-8000-000000000001',dataset='20000000-0000-4000-8000-000000000001';
let requested=false,loggedOut=false;
try {
 await page.route('**/api/health',r=>r.fulfill({status:404,contentType:'application/json',body:'{}'}));
 await page.goto(base);await page.locator('#run').filter({hasText:'불러오기'}).waitFor();
 await page.locator('#run').click();await page.locator('#result-content').waitFor({state:'visible'});
 await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('미리 계산'));
 assert.match(await page.locator('#notice').textContent(),/미리 계산/);
 await page.reload();await page.locator('#result-content').waitFor({state:'visible'});
 await page.route('https://example.supabase.co/**',async route=>{
   const req=route.request(),url=new URL(req.url());let body;
   if(url.pathname==='/auth/v1/token')body={access_token:'fake-access',refresh_token:'fake-refresh',expires_in:3600,user:{email:'demo@example.com'}};
   else if(url.pathname==='/auth/v1/logout'){loggedOut=true;body={};}
   else {
     assert.equal(req.headers().authorization,'Bearer fake-access');
     if(url.pathname==='/rest/v1/projects')body=[{id:project,name:'예측',project_type:'forecast'}];
     else if(url.pathname==='/rest/v1/datasets'){assert.equal(url.searchParams.get('project_id'),'eq.'+project);body=[{id:dataset,name:'합성 테스트',generator_config:{skus:50,weeks:156}}];}
     else if(url.pathname==='/rest/v1/rpc/request_forecast'){
       const payload=req.postDataJSON();assert.equal(payload.p_project_id,project);assert.equal(payload.p_dataset_id,dataset);assert.deepEqual(payload.p_config,{horizon:4,season_length:52,validation_origins:3});assert.ok(payload.p_idempotency_key);requested=true;body={id:'cloud-run',status:'queued'};
     }else if(url.pathname==='/rest/v1/runs'){
       assert.equal(url.searchParams.get('project_id'),'eq.'+project);
       body=requested?[{id:'cloud-run',status:'succeeded',...(url.searchParams.has('id')?{result:snapshot}:{})}]:[];
     }else throw new Error('Unexpected cloud request '+url.pathname);
   }
   await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.locator('#settings-toggle').click();
 await page.locator('[name=url]').fill('https://example.supabase.co');
 await page.locator('[name=key]').fill('sb_publishable_synthetic-test-only');
 await page.locator('#connect-form button[type=submit]').click();
 await page.locator('#login-form').waitFor({state:'visible'});
 assert.equal(await page.locator('#result-content').isVisible(),false);
 await page.locator('[name=email]').fill('demo@example.com');await page.locator('[name=password]').fill('synthetic-password');
 await page.locator('#login-form button[type=submit]').click();
 await page.getByText('Supabase · 로그인됨',{exact:true}).waitFor();
 await page.waitForFunction(()=>!document.getElementById('run').disabled);
 await page.locator('#run').click();await page.locator('#result-content').waitFor({state:'visible'});
 assert.ok(requested);assert.equal(await page.locator('#metric-skus').textContent(),'50');
 await page.locator('#logout').click();
 await page.getByText('Supabase · 로그인 필요',{exact:true}).waitFor();
 assert.ok(loggedOut);assert.equal(await page.locator('#result-content').isVisible(),false);
 console.log('Modes passed: saved synthetic preview + reload, mocked Supabase login/projects/dataset/request/result/logout; no live Supabase connection claimed.');
}finally{await browser.close();}
