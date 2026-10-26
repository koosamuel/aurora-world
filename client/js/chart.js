const NS='http://www.w3.org/2000/svg';
function svgEl(name,attrs={},value) { const el=document.createElementNS(NS,name); for(const [k,v] of Object.entries(attrs)) el.setAttribute(k,v); if(value!==undefined) el.textContent=value; return el; }
export function drawChart(container, series) {
  container.replaceChildren();
  const history=series.history.map(p=>p.status==='observed' && p.value>=0 ? p.value : null);
  const h=history.length, future=series.future_periods.length, total=h+future;
  const valid=[...history,...Object.values(series.forecast).flatMap(x=>x||[])].filter(x=>x!==null && Number.isFinite(x));
  const max=Math.max(1,...valid)*1.12, W=800,H=260,left=44,right=20,top=20,bottom=34;
  const x=i=>left+i/(total-1)*(W-left-right), y=v=>H-bottom-v/max*(H-top-bottom);
  const svg=svgEl('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':`${series.sku} 관측 이력과 다음 ${future}주 기준선 예측`});
  svg.append(svgEl('title',{},`${series.sku}: 결측·반품은 선을 끊어 표시합니다.`));
  for(let i=0;i<=4;i++) { const v=max*i/4;svg.append(svgEl('line',{x1:left,y1:y(v),x2:W-right,y2:y(v),stroke:'#e1e7e3'}),svgEl('text',{x:left-8,y:y(v)+4,'text-anchor':'end',fill:'#67746d','font-size':11},Math.round(v))); }
  svg.append(svgEl('rect',{x:x(h-.5),y:top,width:W-right-x(h-.5),height:H-top-bottom,fill:'#ecf4ef'}));
  const path=(values,color,offset=0,dashed=false)=>{
    let d='',open=false; values.forEach((v,i)=>{if(v===null || !Number.isFinite(v)){open=false;return;} d+=`${open?'L':'M'}${x(i+offset)},${y(v)} `;open=true;});
    svg.append(svgEl('path',{d,fill:'none',stroke:color,'stroke-width':2.4,...(dashed?{'stroke-dasharray':'5 4'}:{})}));
    values.forEach((v,i)=>{if(v!==null && Number.isFinite(v)) svg.append(svgEl('circle',{cx:x(i+offset),cy:y(v),r:2.4,fill:color}));});
  };
  path(history,'#73877b');
  if(series.forecast.naive) path(series.forecast.naive,'#c08735',h,true);
  if(series.forecast.seasonal_naive) path(series.forecast.seasonal_naive,'#167060',h);
  const dates=[...series.history.map(p=>p.period),...series.future_periods];
  for(const i of [0,h-1,total-1]) svg.append(svgEl('text',{x:x(i),y:H-8,'text-anchor':i===0?'start':i===total-1?'end':'middle',fill:'#67746d','font-size':11},dates[i]));
  container.append(svg);
}
