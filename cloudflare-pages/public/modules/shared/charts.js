import{n,esc}from'./format.js';
const RANGE_SECONDS={"1h":3600,"6h":21600,"24h":86400,"7d":604800,all:0};
function ts(row){let v=n(row?.ts||row?.signal_ts);if(v>1e12)v/=1000;return v}
function sorted(rows){return(Array.isArray(rows)?rows:[]).filter(r=>ts(r)>0).slice().sort((a,b)=>ts(a)-ts(b))}
export function rangeRows(rows,range='24h'){
  const list=sorted(rows);if(!list.length||range==='all')return list;const sec=RANGE_SECONDS[range]||RANGE_SECONDS['24h'],end=ts(list[list.length-1]),cut=end-sec,filtered=list.filter(r=>ts(r)>=cut);return filtered.length>=2?filtered:list.slice(-Math.min(2,list.length))
}
export function rangeControl(attr,current='24h'){
  return`<div class="history-range" role="group" aria-label="차트 기간">${[['1h','1H'],['6h','6H'],['24h','24H'],['7d','7D'],['all','전체']].map(([v,l])=>`<button ${attr}="${v}" class="${current===v?'active':''}">${l}</button>`).join('')}</div>`
}
function extent(values){const nums=values.map(n).filter(Number.isFinite);if(!nums.length)return[0,1];let lo=Math.min(...nums),hi=Math.max(...nums);if(lo===hi){const d=Math.abs(lo)*.01||1;lo-=d;hi+=d}return[lo,hi]}
function xScale(t,min,max,w,p){return min===max?w/2:p+(w-p*2)*(t-min)/(max-min)}
function yScale(v,lo,hi,h,p){return p+(h-p*2)*(1-(v-lo)/(hi-lo))}
function points(rows,key,w,h,p,lo,hi,t0,t1){return rows.map(r=>`${xScale(ts(r),t0,t1,w,p).toFixed(1)},${yScale(n(r[key]),lo,hi,h,p).toFixed(1)}`).join(' ')}
export function simpleLineChart(title,rows,key,{range='24h',className='primary',suffix=''}={}){
  const list=rangeRows(rows,range);if(list.length<2)return`<div class="history-empty">${esc(title)} 데이터 수집 중</div>`;const vals=list.map(r=>n(r[key])),[lo,hi]=extent(vals),t0=ts(list[0]),t1=ts(list[list.length-1]),last=vals[vals.length-1];return`<article class="history-chart"><header><div><b>${esc(title)}</b><small>${list.length}개 기록</small></div><strong>${last.toLocaleString('ko-KR',{maximumFractionDigits:2})}${esc(suffix)}</strong></header><svg viewBox="0 0 720 170" preserveAspectRatio="none"><polyline class="history-line ${className}" points="${points(list,key,720,170,10,lo,hi,t0,t1)}"></polyline></svg></article>`
}
export function scoreHistoryChart(memory,{range='24h'}={}){
  const list=rangeRows(memory,range);if(list.length<2)return'<div class="history-empty">판단 점수 이력 데이터 수집 중</div>';const t0=ts(list[0]),t1=ts(list[list.length-1]),w=720,h=190,p=10;const series=[['regime_score','시장','regime'],['entry_score','진입','entry'],['opportunity_score','기회','opportunity']];return`<article class="history-chart score-history"><header><div><b>판단 점수 이력</b><small>시장 · 진입 · 기회 3개 점수</small></div><div class="history-legend">${series.map(([,label,cls])=>`<span class="${cls}">${label}</span>`).join('')}</div></header><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><line class="score-guide" x1="0" y1="${h/2}" x2="${w}" y2="${h/2}"></line>${series.map(([key,,cls])=>`<polyline class="history-line ${cls}" points="${points(list,key,w,h,p,0,100,t0,t1)}"></polyline>`).join('')}</svg></article>`
}
export function priceFillChart(memory,fills,{range='24h',title='가격 · PAPER 체결'}={}){
  const prices=rangeRows(memory,range).filter(r=>n(r.price)>0);if(prices.length<2)return`<div class="history-empty">${esc(title)} 데이터 수집 중</div>`;const t0=ts(prices[0]),t1=ts(prices[prices.length-1]),inside=(Array.isArray(fills)?fills:[]).filter(f=>{const t=ts(f);return t>=t0&&t<=t1&&n(f.price)>0}),allPrices=[...prices.map(r=>n(r.price)),...inside.map(f=>n(f.price))],[lo,hi]=extent(allPrices),w=720,h=220,p=12,poly=points(prices,'price',w,h,p,lo,hi,t0,t1);return`<article class="history-chart price-history"><header><div><b>${esc(title)}</b><small>${prices.length}개 가격기록 · 체결 ${inside.length}건</small></div><div class="history-legend"><span class="buy">매수</span><span class="sell">매도</span></div></header><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline class="history-line price" points="${poly}"></polyline>${inside.map(f=>`<circle class="fill-marker ${f.side==='sell'?'sell':'buy'}" cx="${xScale(ts(f),t0,t1,w,p).toFixed(1)}" cy="${yScale(n(f.price),lo,hi,h,p).toFixed(1)}" r="5"><title>${f.side==='sell'?'매도':'매수'} ${n(f.price).toLocaleString('ko-KR',{maximumFractionDigits:8})}</title></circle>`).join('')}</svg></article>`
}
