import{n,pct,tone,esc}from'../shared/format.js';
import{lifecycleMeta}from'../shared/market-lifecycle.js';

const SORTS=new Set([
  'turnover_desc','turnover_asc',
  'return24h_desc','return24h_asc',
  'return7d_desc','return7d_asc',
  'return30d_desc','return30d_asc',
  'opportunity_desc','opportunity_asc'
]);
const WINDOWS=[['d5_pct','D-5'],['d4_pct','D-4'],['d3_pct','D-3'],['d2_pct','D-2'],['d1_pct','D-1'],['change_24h_pct','24H']];
const CUMULATIVE=[['cum_1d_pct','1D'],['cum_3d_pct','3D'],['cum_5d_pct','5D'],['cum_7d_pct','7D'],['cum_30d_pct','30D']];

export function safeSectorCoinSort(value){return SORTS.has(value)?value:'turnover_desc'}
export function sectorCoinSortKey(sort){
  if(sort.startsWith('return30d'))return'cum_30d_pct';
  if(sort.startsWith('return7d'))return'cum_7d_pct';
  if(sort.startsWith('return24h'))return'change_24h_pct';
  if(sort.startsWith('opportunity'))return'opportunity_score';
  return'turnover_24h';
}
export function sectorCoinSortArrow(current,key){
  if(!current.startsWith(key))return'↕';
  return current.endsWith('_desc')?'↓':'↑';
}

function hasNumber(value){return value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))}
function returnValue(value){return hasNumber(value)?pct(Number(value)):'-'}
function returnCell(coin,key,label){
  const value=coin?.[key];
  return`<i><small>${label}</small><b class="${hasNumber(value)?tone(value):''}">${returnValue(value)}</b></i>`;
}
function simpleReturn(coin,key){
  const value=coin?.[key];
  return`<span class="${hasNumber(value)?tone(value):''}">${returnValue(value)}</span>`;
}
function expandedReturns(coin){
  return`<span class="sector-coin-expanded"><span><small>완료 일별 구간</small><span class="sector-return-strip">${WINDOWS.map(([key,label])=>returnCell(coin,key,label)).join('')}</span></span><span><small>현재 기준 누적수익률</small><span class="sector-cumulative-strip">${CUMULATIVE.map(([key,label])=>returnCell(coin,key,label)).join('')}</span></span></span>`;
}

export function renderSectorCoinTable({coins,selected,sort,turnover}){
  const normalized=safeSectorCoinSort(sort);
  return`<section class="sector-coin-table"><header><div><h3>섹터 상세 코인</h3><span>${coins.length}종목 표시</span></div><small>기본 표는 핵심 기간만 표시하고, 선택한 코인에서 전체 일별·누적 구간을 펼쳐 봅니다.</small></header><div class="sector-coin-row columns"><span>코인</span><button data-sector-sort="return24h">24H <i>${sectorCoinSortArrow(normalized,'return24h')}</i></button><button data-sector-sort="return7d">7D <i>${sectorCoinSortArrow(normalized,'return7d')}</i></button><button data-sector-sort="return30d">30D <i>${sectorCoinSortArrow(normalized,'return30d')}</i></button><button data-sector-sort="turnover">거래대금 <i>${sectorCoinSortArrow(normalized,'turnover')}</i></button><button data-sector-sort="opportunity">기회 <i>${sectorCoinSortArrow(normalized,'opportunity')}</i></button></div><div class="sector-coin-list">${coins.map(c=>{
    const lifecycle=lifecycleMeta(c.lifecycle_state),isSelected=c.market===selected;
    return`<button class="sector-coin-row sector-coin-select ${isSelected?'selected':''}" data-sector-market="${esc(c.market)}"><span class="sector-coin-name"><b>${esc(c.name_ko||c.symbol)}</b><small>${esc(c.name_en||c.symbol)} · <em class="${lifecycle.className}">${esc(c.symbol)}</em>${lifecycle.label?`<strong class="market-lifecycle-label ${lifecycle.className}">${esc(lifecycle.label)}</strong>`:''}</small></span>${simpleReturn(c,'change_24h_pct')}${simpleReturn(c,'cum_7d_pct')}${simpleReturn(c,'cum_30d_pct')}<span>${turnover(c.turnover_24h)}</span><span>${n(c.opportunity_score).toFixed(0)}</span>${expandedReturns(c)}</button>`;
  }).join('')||'<p class="sector-empty-inline">조건에 맞는 코인이 없습니다.</p>'}</div></section>`;
}
