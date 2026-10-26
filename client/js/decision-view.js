const $=id=>document.getElementById(id);
const models={naive:'Naive',seasonal_naive:'계절 naive',ses:'지수평활 (SES)',croston:'Croston',sba:'SBA',tsb:'TSB',selected:'검증으로 선택',segment_rule:'세그먼트 규칙 배정'};
const segments={smooth:'평활',erratic:'불규칙',intermittent:'간헐',lumpy:'덩어리',all_zero:'전기간 0',single_positive:'양의 수요 1회',short_history:'짧은 이력',unobserved:'관측 불가'};
const policies={no_buffer:'버퍼 없음',validation_buffer:'검증 오차 버퍼'};
const f=n=>n==null?'해당 없음':new Intl.NumberFormat('ko-KR',{maximumFractionDigits:3}).format(n);
const pct=n=>n==null?'해당 없음':f(n*100)+'%';
const money=n=>f(n)+'원';
function table(id,rows){$(id).replaceChildren(...rows.map(values=>{const tr=document.createElement('tr');for(const v of values){const td=document.createElement('td');td.textContent=v;tr.append(td);}return tr;}));}
export function renderDecisionSku(d,sku){
 if(!d)return;const a=d.assignments.find(x=>x.sku===sku);if(!a)return;
 const stability=d.segment_stability.find(x=>x.sku===sku);
 $('decision-sku').textContent=`${sku} · ${segments[a.segment]} · ADI ${f(a.adi)} / CV² ${f(a.cv2)} · 연속 이력 ${a.history_n}주 · 선택 ${models[a.selected]||'불가'} · 규칙 ${models[a.rule_model]||'불가'} · 분류 변경 ${stability.transitions}회`;
 const points=d.predictions.filter(x=>x.sku===sku&&x.model==='selected');
 table('decision-points',points.map(p=>{const i=d.intervals.find(x=>x.sku===sku&&x.horizon===p.horizon);return [p.horizon,p.actual,f(p.predicted),i?`${f(i.lower)}–${f(i.upper)}`:'평가 불가'];}));
}
export function renderDecisions(d,sku){
 $('decision-panel').hidden=!d;if(!d)return;
 $('decision-summary').textContent=`6개 후보와 2개 배정 방식을 비교합니다. 선택 원점 ${d.selection_cutoff}주 이전 검증 자료로 SKU별 모델을 정하고 최종 보류에서 고정 평가했습니다. 회사 기존 방식은 대체 기준선으로 표시합니다.`;
 $('segment-summary').textContent=Object.entries(d.segment_counts).map(([s,n])=>`${segments[s]} ${n}개`).join(' · ')+'. 임시 분류 경계 ADI 1.32 / CV² 0.49; 분류만으로 모델 적합성이 보장되지는 않습니다.';
 table('decision-models',d.paired_metrics.map(m=>[models[m.model],m.n,f(m.mae),f(m.bias),`${f(m.mase)} (${m.mase_n})`]));
 const i=d.interval_summary;$('interval-summary').textContent=`경험 10–90% 구간: 독자 평가 ${i.n}건 · 포함률 ${pct(i.coverage)} · 평균 폭 ${f(i.mean_width)}. 선택 모델의 검증 잔차를 합쳐 만든 참고 범위이며 확률 보장은 없습니다. 검증 표본이 작고 모델 선택에 사용돼 독립 보정 집합도 아닙니다.`;
 const inv=d.inventory;$('inventory-summary').textContent=`공통 ${inv.common_skus} SKU · 최종 ${inv.evaluation_weeks}주 · 서비스 목표 ${pct(d.settings.fill_rate_target)}. 매주 직전 관측까지만 반영해 재예측하므로 위 고정 원점 예측 평가와 실행 방식이 다릅니다. 버퍼는 검증 보호기간 누적 오차의 양수 95% 경험 분위수이며 기본 표본은 3개입니다.`;
 table('inventory-scenarios',(inv.common_skus?inv.scenarios:[]).map(s=>[`${models[s.role]} / ${policies[s.policy]}`,pct(s.fill_rate)+(s.fill_rate!=null&&s.fill_rate<d.settings.fill_rate_target?' · 목표 미달':''),s.stockout_weeks,money(s.on_hand_krw),money(s.pipeline_krw),money(s.invested_krw)]));
 $('inventory-impact').textContent=!inv.common_skus?'비교 가능한 공통 SKU가 없습니다. 보호기간보다 예측기간이 짧거나 관측/검증 이력이 부족하면 제외합니다.':inv.comparisons.map(x=>`${policies[x.policy]}: Naive−선택의 전체 투자 차이 ${money(x.raw_difference_krw)}; 두 예측 모두 서비스 목표를 충족한 ${x.qualified_skus} SKU의 차이 ${money(x.qualified_difference_krw)}.`).join(' ')+' 양수는 합성 비교에서의 감소이며 기업 절감 성공 판정은 아닙니다. 목표 미달·수요 0 SKU는 조건부 차이에서 제외했습니다.';
 $('decision-manifest').textContent=JSON.stringify({settings:d.settings,settings_hash:d.settings_hash,code_revision:d.code_revision,coverage_metrics:d.coverage_metrics,assignment:d.assignments,segment_history:d.segment_history,segment_metrics:d.segment_metrics,excluded:d.excluded,inventory:inv},null,2);
 renderDecisionSku(d,sku);
}
