import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {predictFamily,mapName,analyzePiece,approveReview} from '../client/js/label-model.js';
const read=n=>JSON.parse(readFileSync(new URL(`../client/demo/labeling/${n}.json`,import.meta.url)));
const d=read('dataset'),m=read('model'),r=read('report'),truth=read('truth');
test('JS inference reproduces Python holdout confusion matrix on all 180 pieces',()=>{
 const confusion=Object.fromEntries(Object.keys(d.families).map(x=>[x,Object.fromEntries(Object.keys(d.families).map(y=>[y,0]))]));
 for(const p of d.pieces.filter(p=>p.split==='test'))confusion[truth.labels[p.piece_id].split('_')[0]][predictFamily(m,p.features).family]++;
 assert.deepEqual(confusion,r.test.confusion);
 const train=new Set(d.pieces.filter(p=>p.split==='train').map(p=>p.family_id));
 assert.ok(d.pieces.filter(p=>p.split!=='train').every(p=>!train.has(p.family_id)));
 assert.equal(m.train_y.length,840);assert.ok(m.train_y.every(v=>!v.includes('_')));
});
test('ambiguous names remain candidates; geometry is independent of name and ID',()=>{
 assert.deepEqual(mapName(d,'귀').candidates.map(c=>c.id),['EAR_LEFT','EAR_RIGHT']);
 const p=d.pieces[0],a=analyzePiece(d,m,p),b=analyzePiece(d,m,{...p,piece_id:'unknown',design_id:'other'},'귀');
 assert.deepEqual(a.geometry,b.geometry);assert.equal(b.proposal,null);assert.equal(b.requiresReview,true);
 assert.equal(mapName(d,'zzzzzz').kind,'unregistered');assert.equal(mapName(d,'').kind,'empty');
 assert.throws(()=>predictFamily(m,[NaN,1,2,3]));
});
test('approval is explicit and requires a standard ID',()=>{
 assert.throws(()=>approveReview({},'',d.master));assert.throws(()=>approveReview({},'unknown',d.master));
 const approved=approveReview({status:'pending'},'EAR_LEFT',d.master);assert.equal(approved.status,'approved');assert.equal(approved.selected,'EAR_LEFT');
});
