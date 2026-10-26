export const normalizeName = value => String(value).normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
export function predictFamily(model, features) {
  if(features.length!==model.features.length || !features.every(Number.isFinite))throw new Error('조각 특성을 확인하세요.');
  const neighbors=model.train_x.map((x,i)=>({label:model.train_y[i],i,d:x.reduce((sum,v,j)=>sum+((v-features[j])/model.scales[j])**2,0)})).sort((a,b)=>a.d-b.d||a.i-b.i).slice(0,model.k);
  const votes=new Map();for(const n of neighbors){const v=votes.get(n.label)||{family:n.label,count:0,distance:0};v.count++;v.distance+=n.d;votes.set(n.label,v);}
  const ranked=[...votes.values()].sort((a,b)=>b.count-a.count||a.distance-b.distance||(a.family<b.family?-1:1));
  return {family:ranked[0].family,support:ranked[0].count/neighbors.length,votes:ranked.map(v=>({...v,support:v.count/neighbors.length}))};
}
function similarity(a,b) {
  if(!a||!b)return 0;let prev=Array.from({length:b.length+1},(_,i)=>i);
  for(let i=1;i<=a.length;i++){const next=[i];for(let j=1;j<=b.length;j++)next[j]=Math.min(next[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));prev=next;}
  return 1-prev[b.length]/Math.max(a.length,b.length);
}
export function mapName(dataset, rawName) {
  const normalized=normalizeName(rawName);if(!normalized)return {kind:'empty',candidates:[]};
  const exact=dataset.aliases[normalized];
  if(exact)return {kind:exact.length===1?'exact':'ambiguous',candidates:exact.map(id=>({id,score:1}))};
  const scores=new Map();for(const [alias,ids] of Object.entries(dataset.aliases)){const score=similarity(normalized,alias);if(score>=.55)for(const id of ids)scores.set(id,Math.max(scores.get(id)||0,score));}
  return {kind:'unregistered',candidates:[...scores.entries()].map(([id,score])=>({id,score})).sort((a,b)=>b.score-a.score||(a.id<b.id?-1:1)).slice(0,4)};
}
export function analyzePiece(dataset, model, piece, rawName=piece.raw_name) {
  const geometry=predictFamily(model,piece.features),mapping=mapName(dataset,rawName);
  const geometricCandidates=dataset.master.filter(m=>m.standard_part_id.split('_')[0]===geometry.family).map(m=>m.standard_part_id);
  const proposal=mapping.kind==='exact'&&mapping.candidates[0].id.split('_')[0]===geometry.family?mapping.candidates[0].id:null;
  return {geometry,mapping,geometricCandidates,proposal,requiresReview:!proposal||geometricCandidates.length>1,rawName};
}
export function approveReview(review,id,master) {
  if(!master.some(m=>m.standard_part_id===id))throw new Error('확정할 표준 부위를 선택하세요.');
  return {...review,selected:id,status:'approved',updated_at:new Date().toISOString()};
}
