const $=id=>document.getElementById(id);
const fmt=n=>n==null?'해당 없음':new Intl.NumberFormat('ko-KR',{maximumFractionDigits:3}).format(n);
const pct=n=>n==null?'해당 없음':fmt(n*100)+'%';
const names={naive:'Naive',seasonal_naive:'계절 Naive',selected:'검증으로 선택'};
function rows(id,items){$(id).replaceChildren(...items.map(values=>{const tr=document.createElement('tr');for(const x of values){const td=document.createElement('td');td.textContent=x;tr.append(td);}return tr;}));}
export function renderPublic(data,download){
 if(data.schema_version!=='aurora-public-evaluation-v1'||data.synthetic!==false||data.inventory_is_scenario!==true)throw new Error('공개 거래 결과 계약을 확인하세요.');
 const e=data.evaluation;
 $('public-summary').textContent=`공개 거래 · ${data.assignments.length} SKU · 앞 ${e.selection_cutoff}주에서 모델 선택 고정 → ${e.warmup_weeks}주 워밍업 → ${e.evaluation_weeks}주 순차 평가. 오로라월드 거래가 아닙니다.`;
 const naive=data.paired_metrics.find(x=>x.model==='naive'),selected=data.paired_metrics.find(x=>x.model==='selected');
 $('public-n').textContent=fmt(naive?.skus);$('public-naive').textContent=fmt(naive?.mae);$('public-selected').textContent=fmt(selected?.mae);
 $('public-verdict').textContent=naive?.mae!=null&&selected?.mae!=null?(selected.mae>naive.mae?'선택 모델이 Naive보다 나빴습니다. 개선으로 판정하지 않습니다.':'같은 대상의 오차 비교입니다. 회사의 개선 실적이나 재고 절감을 입증한 것은 아닙니다.'):'공통 평가 대상이 부족합니다.';
 rows('public-models',data.paired_metrics.map(m=>[names[m.model],m.n,m.skus,fmt(m.mae),fmt(m.bias),`${fmt(m.mase)} (n=${m.mase_n})`]));
 const ids=[...new Set(data.inventory_summaries.map(s=>s.scenario))];
 $('public-scenario').replaceChildren(new Option('전체 초기 상태·리드타임','all'),...ids.map(id=>new Option(id,id)));
 const render=()=>rows('public-inventory',data.inventory_summaries.filter(s=>$('public-scenario').value==='all'||s.scenario===$('public-scenario').value).map(s=>[s.scenario,`${names[s.role]} / ${s.buffer_policy==='no_buffer'?'버퍼 없음':'검증 버퍼'}`,s.skus,pct(s.fill_rate),s.service_met_skus,pct(s.worst_sku_fill_rate),fmt(s.average_on_hand),fmt(s.average_pipeline)]));
 $('public-scenario').onchange=render;render();
 $('public-downloads').replaceChildren(...(data.artifacts||[]).map(a=>{const b=document.createElement('button');b.className='secondary small';b.textContent=`${a.name} 받기`;b.addEventListener('click',async()=>{b.disabled=true;try{await download(a);$('public-download-status').textContent='다운로드 파일의 크기·SHA-256 확인 완료';}catch(e){$('public-download-status').textContent=e.message;}finally{b.disabled=false;}});return b;}));
 $('public-download-status').textContent=data.artifacts?.length?'파일 크기·SHA-256을 확인해 내려받습니다.':'이 실행에는 다운로드 산출물이 없습니다.';
 $('public-manifest').textContent=JSON.stringify({source:data.source,data_sha256:data.data_sha256,evaluation:e,coverage_metrics:data.coverage_metrics,excluded_counts:data.excluded_counts,assignments:data.assignments,limitations:data.limitations},null,2);
}
