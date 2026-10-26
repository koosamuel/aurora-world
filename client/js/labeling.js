import {analyzePiece,approveReview} from './label-model.js';
const $=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
const state={data:null,model:null,report:null,truth:null,design:null,piece:null,predictions:new Map(),reviews:{},events:[],raw:{},busy:false};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function svg(tag,attrs){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;}
function notice(text){$('label-status').textContent=text;}
function pieces(){return state.data.pieces.filter(p=>p.design_id===state.design);}
function partName(id){return state.data.master.find(m=>m.standard_part_id===id)?.name||id;}
async function get(name){const response=await fetch(`./demo/labeling/${name}.json`,{cache:'no-store'});if(!response.ok)throw new Error('합성 라벨링 자료를 불러오지 못했습니다. 새로고침 후 다시 실행하세요.');return response.json();}
function persist(){try{sessionStorage.setItem('aurora-labeling-reviews-v1',JSON.stringify({source:state.data.source_manifest_sha256,reviews:state.reviews,raw:state.raw,events:state.events.slice(-500),design:state.design}));}catch{notice('이 브라우저에서는 검수 임시 저장을 사용할 수 없습니다. JSON으로 내려받으세요.');}}
function restore(){try{const v=JSON.parse(sessionStorage.getItem('aurora-labeling-reviews-v1'));if(v?.source===state.data.source_manifest_sha256){state.reviews=v.reviews||{};state.raw=v.raw||{};state.events=v.events||[];if(state.data.products.some(p=>p.design_id===v.design))state.design=v.design;}}catch{}}
function counters(){const rows=pieces();$('label-approved').textContent=`${rows.filter(p=>state.reviews[p.piece_id]?.status==='approved').length} / ${rows.length}`;}
function event(piece,action,selected=null){state.events.push({piece_id:piece.piece_id,action,selected,at:new Date().toISOString()});persist();}
function polygon(piece,attrs={}){return svg('polygon',{points:piece.points.map(p=>p.join(',')).join(' '),fill:'#f5f9f5',stroke:'#247265','stroke-width':.65,...attrs});}
function detail(id){
 state.piece=id;const p=pieces().find(p=>p.piece_id===id);if(!p)return;
 $('label-piece-title').textContent=p.piece_id;
 const image=svg('svg',{viewBox:p.view_box.join(' '),role:'img','aria-label':p.piece_id+' 가상 패턴 윤곽'});image.append(polygon(p));$('label-piece-preview').replaceChildren(image);
 const fields=[['폭 × 높이',`${p.width_mm.toFixed(1)} × ${p.height_mm.toFixed(1)} mm`],['면적',`${p.area_mm2.toFixed(1)} mm²`],['디자인 내 상대면적',`${(100*p.relative_area).toFixed(1)}%`],['원단 / 재단 수량',`${p.material_id} / ${p.cut_qty}`]];
 $('label-features').replaceChildren(...fields.flatMap(([k,v])=>[el('dt',k),el('dd',v)]));$('label-raw-name').value=state.raw[id]??p.raw_name;
 for(const g of $('label-sheet').querySelectorAll('[data-piece]'))g.setAttribute('aria-pressed',String(g.dataset.piece===id));
 for(const tr of $('label-rows').children)tr.classList.toggle('selected',tr.dataset.piece===id);
}
function sheet(){
 const canvas=svg('svg',{viewBox:'0 0 420 297',role:'group','aria-label':'가상 디자인의 패턴 조각 12개'});
 pieces().forEach((p,i)=>{const [,,w,h]=p.view_box;const scale=Math.min(92/w,82/h);const g=svg('g',{transform:`translate(${i%4*105+(105-w*scale)/2},${Math.floor(i/4)*99+(99-h*scale)/2}) scale(${scale})`,role:'button',tabindex:'0','aria-label':p.piece_id+' 조각 선택','data-piece':p.piece_id,'aria-pressed':'false'});g.append(polygon(p));g.addEventListener('click',()=>detail(p.piece_id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();detail(p.piece_id);}});canvas.append(g);});
 $('label-sheet').replaceChildren(canvas);
}
function renderRows(){
 $('label-rows').replaceChildren(...pieces().map(p=>{
   const prediction=state.predictions.get(p.piece_id),review=state.reviews[p.piece_id]||{status:'pending',selected:''};
   const tr=el('tr');tr.dataset.piece=p.piece_id;
   const identity=el('td'),pick=el('button',p.piece_id,'quiet piece-link');pick.type='button';pick.addEventListener('click',()=>detail(p.piece_id));identity.append(pick,el('span',state.raw[p.piece_id]??p.raw_name,'raw-name'));
   const geometry=el('td');geometry.append(el('strong',state.data.families[prediction.geometry.family]),el('small',`학습 이웃 ${Math.round(prediction.geometry.support*state.model.k)} / ${state.model.k}`));
   const choice=el('td'),select=el('select');select.setAttribute('aria-label',p.piece_id+' 표준 부위');select.append(new Option('표준 부위 선택',''));
   const suggested=new Set([...prediction.mapping.candidates.map(c=>c.id),...prediction.geometricCandidates]);
   for(const m of state.data.master)select.append(new Option(`${suggested.has(m.standard_part_id)?'후보 · ':''}${m.name}`,m.standard_part_id));
   select.value=review.selected||prediction.proposal||'';
   const info=el('small');info.textContent=prediction.mapping.kind==='ambiguous'?'동일 명칭 후보가 여러 개 · 좌우 검수':prediction.mapping.kind==='exact'?`명칭 일치 · ${prediction.geometricCandidates.length>1?'좌우·앞뒤는 검수 필요':'형상 후보도 확인하세요'}`:`미등록 명칭 · 유사 후보 ${prediction.mapping.candidates.length}개`;
   const candidateText=el('small',prediction.mapping.candidates.length?'명칭 후보: '+prediction.mapping.candidates.map(c=>`${partName(c.id)} ${c.score.toFixed(2)}`).join(' / '):'명칭 후보 없음 · 형상과 제품 맥락으로 검수');
   select.addEventListener('change',()=>{state.reviews[p.piece_id]={status:'pending',selected:select.value};event(p,'selection_changed',select.value);renderRows();counters();});
   choice.append(select,info,candidateText);
   const status=el('td'),badge=el('span',review.status==='approved'?'사람이 확정':review.status==='deferred'?'보류':'미검수',review.status==='approved'?'badge':'badge neutral');
   const buttons=el('div',undefined,'review-actions'),approve=el('button','확정','secondary small'),defer=el('button','보류','quiet small');approve.type=defer.type='button';
   approve.addEventListener('click',()=>{try{state.reviews[p.piece_id]=approveReview(review,select.value,state.data.master);event(p,'approved',select.value);renderRows();counters();}catch(e){notice(e.message);}});
   defer.addEventListener('click',()=>{state.reviews[p.piece_id]={status:'deferred',selected:select.value,updated_at:new Date().toISOString()};event(p,'deferred',select.value);renderRows();counters();});buttons.append(approve,defer);status.append(badge,buttons);
   if(state.truth){const truth=state.truth.labels[p.piece_id];status.append(el('small',`생성 정답: ${partName(truth)}`));if(review.status==='approved')status.append(el('small',review.selected===truth?'확정값 일치':'확정값 불일치',review.selected===truth?'match':'mismatch'));}
   tr.append(identity,geometry,choice,status);return tr;
 }));if(state.piece)detail(state.piece);
}
function analyzeDesign(){
 const selected=state.data.products.find(p=>p.design_id===state.design);$('label-design-info').textContent=`${selected.design_id} · ${selected.family_id} · ${selected.split}`;
 for(const p of pieces())state.predictions.set(p.piece_id,analyzePiece(state.data,state.model,p,state.raw[p.piece_id]??p.raw_name));
 $('label-count').textContent=`${pieces().length}개`;$('label-f1').textContent=state.report.test.macro_f1.toFixed(3);
 sheet();state.piece=pieces()[0].piece_id;renderRows();counters();persist();
 notice(`${selected.design_id}의 조각 ${pieces().length}개를 분류했습니다. 후보는 아직 승인되지 않았습니다. 형상만으로 구분하기 어려운 좌우·앞뒤를 검수해 보세요.`);
}
function designs(){
 const rows=state.data.products.filter(p=>p.split===$('label-split').value);$('label-design').replaceChildren(...rows.map(p=>new Option(`${p.design_id} · ${p.name}`,p.design_id)));
 if(rows.some(p=>p.design_id===state.design))$('label-design').value=state.design;else state.design=rows[0].design_id;
}
async function run(){
 if(state.busy)return;state.busy=true;$('label-run').disabled=true;
 try{
  if(!state.data){notice('합성 조각·마스터·학습된 기준선을 불러오는 중입니다…');[state.data,state.model,state.report]=await Promise.all([get('dataset'),get('model'),get('report')]);
   if(state.data.schema_version!=='aurora-labeling-dataset-v1'||state.data.synthetic!==true)throw new Error('지원하는 합성 자료가 아닙니다.');
   restore();if(state.design)$('label-split').value=state.data.products.find(p=>p.design_id===state.design).split;
   $('label-master').replaceChildren(...state.data.master.map(m=>{const tr=el('tr');for(const v of [m.standard_part_id,m.name,Object.values(state.data.aliases).filter(ids=>ids.includes(m.standard_part_id)).length])tr.append(el('td',v));return tr;}));
   $('label-evaluation').textContent=JSON.stringify({training_n:state.report.training_n,validation:state.report.validation,test:state.report.test,fine_labels_require_review:true},null,2);designs();
  }
  $('label-workspace').hidden=false;analyzeDesign();$('label-run').textContent='선택 디자인 다시 실행 ↗';
 }catch(e){notice(e.message);}finally{state.busy=false;$('label-run').disabled=false;}
}
export function initLabeling(){
 $('label-run').addEventListener('click',run);
 $('label-split').addEventListener('change',()=>{designs();analyzeDesign();});$('label-design').addEventListener('change',()=>{state.design=$('label-design').value;analyzeDesign();});
 $('label-remap-form').addEventListener('submit',e=>{e.preventDefault();if(!state.data)return;const p=pieces().find(p=>p.piece_id===state.piece);state.raw[p.piece_id]=$('label-raw-name').value.slice(0,100);state.reviews[p.piece_id]={status:'pending',selected:''};state.predictions.set(p.piece_id,analyzePiece(state.data,state.model,p,state.raw[p.piece_id]));event(p,'raw_name_edited');renderRows();counters();notice('원문 명칭 후보를 갱신하고 이전 확정을 해제했습니다. 형상 예측에는 명칭을 사용하지 않습니다.');});
 $('label-truth').addEventListener('click',async()=>{try{if(!state.truth){const truth=await get('truth');if(truth.source_manifest_sha256!==state.data.source_manifest_sha256)throw new Error('자료와 정답 버전이 다릅니다.');state.truth=truth;}$('label-comparison').textContent='생성 정답을 표시했습니다. 위 F1은 사람의 검수 결과가 아닌, 별도 최종 평가 180개에 대한 7개 부위군 점수입니다.';renderRows();}catch(e){notice(e.message);}});
 $('label-export').addEventListener('click',()=>{const output={schema_version:'aurora-label-review-v1',synthetic:true,storage:'browser-session-only',source_manifest_sha256:state.data.source_manifest_sha256,design_id:state.design,model:state.model.schema_version,results:pieces().map(p=>({piece_id:p.piece_id,prediction:state.predictions.get(p.piece_id),review:state.reviews[p.piece_id]||{status:'pending'}})),events:state.events.filter(e=>pieces().some(p=>p.piece_id===e.piece_id))};const url=URL.createObjectURL(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download=`aurora-label-review-${state.design}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
}
