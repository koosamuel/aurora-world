// U23 local synthetic links; Pages only reads frozen, hash-checked demo files.
export function initPatternLinks(){
 const $=id=>document.getElementById(id);if(!$('pattern-mode'))return;
 let local=false,cat,record,bundle,manifest,busy=false,actor=null,serial=0,urls=[];
 const reasons={approval_changed_or_inactive:'승인 해제 또는 샘플·명세 변경',new_pattern_bom_version:'새 패턴/BOM 버전',bundle_removed_or_changed:'묶음 제거·내용 변경',superseded_link:'다음 연결로 대체'};
 const reasonText=xs=>xs.map(x=>reasons[x]||x).join(', ');
 const say=s=>$('pattern-status').textContent=s;
 async function json(url,options){const r=await fetch(url,options);if(!r.ok){let e;try{e=await r.json();}catch{}throw new Error(e?.error||'응답 '+r.status);}return r.json();}
 async function checked(url,meta){if(!meta)throw new Error('파일 명세 없음');const r=await fetch(url);if(!r.ok)throw new Error('파일 응답 '+r.status);const raw=await r.arrayBuffer();const sha=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(n=>n.toString(16).padStart(2,'0')).join('');if(sha!==meta.sha256||raw.byteLength!==meta.bytes)throw new Error('파일 크기/SHA-256 불일치');return raw;}
 async function saved(path){if(!/^(products\/SYN-[A-Z0-9_-]+\.json|bundles\/SYN-[A-Z0-9_-]+-v[0-9]+\.json)$/.test(path))throw new Error('저장 경로 오류');return JSON.parse(new TextDecoder().decode(await checked('./demo/pattern-links/'+path,manifest.files.find(f=>f.path===path))));}
 const selectedLink=()=>record?.links.find(r=>r.version===Number($('pattern-link-version').value));
 function controls(){
  for(const id of ['pattern-product','pattern-bundle','pattern-link-version','pattern-refresh','pattern-persona'])$(id).disabled=busy;
  $('pattern-persona-apply').disabled=busy||!local;$('pattern-persona').disabled=busy||!local;
  $('pattern-create').disabled=busy||!local||actor?.role!=='designer'||!record?.current_approval||!bundle?.audit.passed||bundle?.bundle.version!==record?.latest_bundle_version||!!record?.links.at(-1)?.current_valid;
  $('pattern-reason').disabled=busy||!local||actor?.role!=='designer';$('pattern-export').disabled=busy||!record;
 }
 function table(target,rows){$(target).replaceChildren(...rows.map(row=>{const tr=document.createElement('tr');for(const value of row){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}return tr;}));}
 function download(raw,name,type='application/json'){const url=URL.createObjectURL(new Blob([raw],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function show(){
  const ticket=++serial;controls();if(!record||!bundle)return;
  const b=bundle.bundle,l=selectedLink();
  $('pattern-chain').replaceChildren(...[
   ['01 승인 샘플',l?'v'+l.sample_version+' · '+(l.current_valid?'현재 가상 승인':'연결 당시 승인 · 재확인 필요'):(record.current_approval?'v'+record.current_approval.sample_version+' · 현재 가상 승인':'현재 유효한 U22 승인 없음')],
   ['02 패턴 · '+b.pattern_id,b.pattern_version+' / 묶음 v'+b.version],
   ['03 조각 · 자재/BOM',b.pieces.length+'조각 · '+b.materials.length+'자재 / '+b.bom_version],
  ].map(([label,value])=>{const x=document.createElement('article');const h=document.createElement('h3');h.textContent=label;const p=document.createElement('p');p.textContent=value;x.append(h,p);return x;}));
  $('pattern-summary').textContent=record.product_id+' · '+(l?'연결 v'+l.version+' · '+(l.current_valid?'현재 유효':'재확인 필요: '+reasonText(l.invalid_reasons)):'아직 연결 이력 없음');
  $('pattern-audit').textContent=(bundle.audit.passed?'감사 통과':'감사 실패')+' · '+bundle.audit.piece_count+'조각 / BOM '+bundle.audit.bom_count+'행 · 재단 수량 '+bundle.audit.cut_quantity+' pcs · 이론 면적 '+bundle.audit.estimated_area_mm2.toLocaleString()+' mm²';
  $('pattern-origin').textContent='수동 합성 대응 · '+b.provenance.dataset+' / 원본 합성 PAT에서 수동 선정 · 샘플과의 형상 대응/제작 적합성 미검증'+'. 면적은 합성 윤곽×수량이며 로스·시접·배치·원단 폭·충전재·공임을 포함하지 않습니다.';
  const materials=new Map(b.materials.map(m=>[m.material_id,m]));const bom=new Map(b.bom.map(r=>[r.piece_id,r]));
  table('pattern-rows',b.pieces.map(p=>{const line=bom.get(p.piece_id);return [p.piece_id,p.standard_part_id,p.width_mm+' × '+p.height_mm+' mm',p.material_id+' · '+materials.get(p.material_id)?.name,line?.quantity+' '+line?.quantity_unit,line?.consumption.toFixed(3)+' '+line?.consumption_unit];}));
  const im=l?.impact;$('pattern-impact').textContent=im?(im.initial?'최초 연결 · '+im.added.length+'조각':`이전 연결 대비 추가 ${im.added.length} / 제거 ${im.removed.length} / 변경 ${im.changed.length}조각. `+im.material_totals.map(m=>m.material_id+': '+m.before_mm2+' → '+m.after_mm2+' mm² (차이 '+m.delta_mm2+')').join(' · ')):'연결을 저장하면 이전 패턴/BOM과의 변경 영향을 기록합니다.';
  table('pattern-history',record.links.map(x=>['v'+x.version,'샘플 v'+x.sample_version,x.bundle.pattern_version+' / '+x.bundle.bom_version,x.current_valid?'현재 유효':reasonText(x.invalid_reasons),x.reason]));
  $('pattern-json').textContent=JSON.stringify(record,null,2);$('pattern-issues').textContent=JSON.stringify(bundle.audit.errors,null,2);
  for(const u of urls)URL.revokeObjectURL(u);urls=[];$('pattern-previews').replaceChildren();
  // Only fixed registered link assets are exposed by the local server.
  if(!l||l.bundle_sha256!==bundle.sha256)return;
  for(const p of b.pieces){
   if(ticket!==serial)return;
   const raw=await checked((local?'./api/pattern-links/assets/':'./demo/pattern-links/assets/')+p.asset,{bytes:p.asset_bytes,sha256:p.asset.slice(0,-4)});
   if(ticket!==serial)return;
   const url=URL.createObjectURL(new Blob([raw],{type:'image/svg+xml'}));urls.push(url);
   const button=document.createElement('button');button.className='pattern-piece secondary';button.setAttribute('aria-label',p.piece_id+' SVG 다운로드');const img=document.createElement('img');img.src=url;img.alt=p.standard_part_id+' 합성 윤곽';const span=document.createElement('span');span.textContent=p.piece_id+' · '+p.standard_part_id;button.append(img,span);button.onclick=()=>{download(raw,p.piece_id+'.svg','image/svg+xml');say('조각 SVG 크기/SHA-256 확인 후 다운로드했습니다.');};$('pattern-previews').append(button);
  }
 }
 async function load(pid){
  const oldVersion=$('pattern-link-version').value;
  record=local?await json('./api/pattern-links/products/'+pid):await saved('products/'+pid+'.json');
  const choices=cat.bundles.filter(b=>b.product_id===pid);$('pattern-bundle').replaceChildren(...choices.map(b=>new Option('묶음 v'+b.version+(b.version===record.latest_bundle_version?' · 최신':' · 이전'),b.version)));$('pattern-bundle').value=String(record.latest_bundle_version);
  $('pattern-link-version').replaceChildren(new Option('최신 연결 또는 미연결',''),...record.links.map(l=>new Option('연결 v'+l.version,l.version)));$('pattern-link-version').value=record.links.length?String(record.head_version):'';
  if(oldVersion&&record.links.some(l=>String(l.version)===oldVersion)&&!busy)$('pattern-link-version').value=oldVersion;
  await chooseBundle();
 }
 async function chooseBundle(){
  const pid=record.product_id,v=Number($('pattern-bundle').value);
  bundle=local?await json('./api/pattern-links/bundles/'+pid+'/'+v):{bundle:await saved('bundles/'+pid+'-v'+v+'.json'),...cat.bundles.find(b=>b.product_id===pid&&b.version===v)};
  const frozen=selectedLink();if(frozen&&frozen.bundle.version===v)bundle={bundle:frozen.bundle,sha256:frozen.bundle_sha256,audit:frozen.audit};
  await show();say((local?'로컬 합성 연결':'저장된 합성 연결')+' 조회 완료 · 승인·버전 유효성 확인.');
 }
 async function refresh(pid){
  if(!local)manifest=await json('./demo/pattern-links/manifest.json');cat=await json(local?'./api/pattern-links/catalog':'./demo/pattern-links/catalog.json');
  const selected=pid||$('pattern-product').value;$('pattern-product').replaceChildren(...cat.products.map(p=>new Option(p.product_id+(p.active_approval?' · 가상 승인':' · 미승인/보류'),p.product_id)));if(cat.products.some(p=>p.product_id===selected))$('pattern-product').value=selected;
  if(local){let token;try{token=sessionStorage.getItem('aurora-review-token');}catch{}actor=null;if(token)try{actor=(await json('./api/sample-reviews/session',{headers:{Authorization:'Bearer '+token}})).actor;}catch{}}
  $('pattern-actor').textContent=actor?actor.name+' · '+actor.role+' · 합성 시뮬레이션':'합성 역할 미선택';await load($('pattern-product').value);
 }
 async function run(fn){if(busy)return;busy=true;controls();say('승인·패턴/BOM 상태를 확인하고 있습니다…');try{await fn();}catch(e){say('패턴/BOM 처리 실패: '+e.message);}finally{busy=false;controls();}}
 $('pattern-refresh').onclick=()=>run(()=>refresh());$('pattern-product').onchange=()=>run(()=>load($('pattern-product').value));$('pattern-bundle').onchange=()=>run(chooseBundle);
 $('pattern-link-version').onchange=()=>run(async()=>{const l=selectedLink();if(l)$('pattern-bundle').value=String(l.bundle.version);await chooseBundle();});
 $('pattern-persona-apply').onclick=()=>run(async()=>{const r=await json('./api/sample-reviews/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({persona_id:$('pattern-persona').value})});sessionStorage.setItem('aurora-review-token',r.token);await refresh();say('합성 역할 적용 완료 · '+actor.role);});
 $('pattern-create').onclick=()=>run(async()=>{
  const a=record.current_approval;let token=sessionStorage.getItem('aurora-review-token');const r=await json('./api/pattern-links/links',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify({product_id:record.product_id,bundle_version:bundle.bundle.version,bundle_sha256:bundle.sha256,sample_revision_sha256:a.revision_sha256,approval_event_sha256:a.approval_event_sha256,expected_review_seq:a.review_seq,parent_version:record.head_version,reason:$('pattern-reason').value.trim(),request_key:crypto.randomUUID()})});await refresh(r.product_id);say('패턴/BOM 연결 저장 완료 · 연결 v'+r.head_version+' · 현재 유효성 재조회.');
 });
 $('pattern-export').onclick=()=>run(async()=>{const r=local?await json('./api/pattern-links/export/'+record.product_id):await saved('products/'+record.product_id+'.json');download(JSON.stringify(r,null,2),r.product_id+'-pattern-links.json');say('연결·승인 해시·BOM·변경 영향 이력을 내보냈습니다.');});
 for(const e of ['digital-review-updated','sampling-brief-selected'])window.addEventListener(e,()=>{if(local&&!busy)run(()=>refresh(record?.product_id));});
 run(async()=>{if(['localhost','127.0.0.1'].includes(location.hostname))try{local=(await json('./api/health')).mode==='local';}catch{}$('pattern-mode').textContent=local?'U23 · 로컬 합성 연결':'U23 · 저장된 합성 연결';await refresh();});
}
