// Independent synthetic crosswalk audit; never changes the selected forecast dataset.
export function initIdentity(){
 const $=id=>document.getElementById(id);let pending=false;
 const labels={ambiguous_approved_mapping:'승인 코드 충돌',duplicate_canonical_snapshot:'동일 재고 스냅샷 중복',duplicate_source_record:'원천 업무 행 중복',mapping_not_approved:'미승인 대응',mapping_not_yet_known:'기준일 이후 등록',unmapped_code:'미매칭 코드',no_effective_mapping:'유효기간 밖',future_record:'기준일 이후 자료'};
 async function read(url){const r=await fetch(url,{signal:AbortSignal.timeout(5000)});if(!r.ok)throw new Error(`점검 자료 응답 ${r.status}`);return r.json();}
 $('identity-run').addEventListener('click',async()=>{
  if(pending)return;pending=true;$('identity-run').disabled=true;$('identity-case').disabled=true;$('identity-result').hidden=true;$('identity-status').textContent='제품 코드 대응을 확인하고 있습니다…';
  try{
   const selected=$('identity-case').value;let local=false;
   // A failed local audit must not silently become a successful saved result.
   if(['localhost','127.0.0.1'].includes(location.hostname)){
    const response=await fetch('./api/health',{signal:AbortSignal.timeout(3000)});
    if(response.ok)local=(await response.json()).mode==='local';
    else if(response.status!==404)throw new Error(`로컬 상태 응답 ${response.status}`);
   }
   const a=await read(local?`./api/identity-demo?case=${encodeURIComponent(selected)}`:`./demo/identity/${selected}.json`);
   if(a.schema_version!=='aurora-product-identity-audit-v1')throw new Error('지원하지 않는 점검 형식');
   const c=a.counts;
   $('identity-status').textContent=`${local?'로컬에서 새로 계산':'저장된 합성 점검 결과'} · ${a.ready_for_downstream?'이 예제의 결합 조건 충족':'격리·대응표 확인 필요'}`;
   $('identity-summary').textContent=`원천 ${c.source}행 = 연결 ${c.accepted}행 + 격리 ${c.quarantined}행 · 대응표 충돌 ${c.mapping_issues}건`;
   $('identity-reasons').replaceChildren();
   for(const [reason,count] of Object.entries(a.quarantine_reasons)){const li=document.createElement('li');li.textContent=`${labels[reason]||reason}: ${count}행`;$('identity-reasons').append(li);}
   if(!c.quarantined){const li=document.createElement('li');li.textContent='격리된 행이 없습니다.';$('identity-reasons').append(li);}
   $('identity-balance').textContent=`수량 수지 ${a.quantity_audit.every(g=>g.preserved)?'보존 확인':'불일치'} · 자료 종류·조직·위치·날짜·단위별 ${a.quantity_audit.length}개 그룹을 따로 점검합니다. 미매칭은 0으로 바꾸지 않습니다.`;
   $('identity-json').textContent=JSON.stringify(a,null,2);$('identity-result').hidden=false;
  }catch(e){$('identity-status').textContent=`점검 실패: ${e.message}`;}
  finally{pending=false;$('identity-run').disabled=false;$('identity-case').disabled=false;}
 });
}
