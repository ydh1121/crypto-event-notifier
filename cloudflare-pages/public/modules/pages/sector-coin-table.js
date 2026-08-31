import{n,pct,tone,esc}from'../shared/format.js';
import{lifecycleMeta}from'../shared/market-lifecycle.js';

const SORTS=new Set(['turnover_desc','turnover_asc','change_desc','change_asc','opportunity_desc','opportunity_asc']);
const WINDOWS=[['d5_pct','D-5'],['d4_pct','D-4'],['d3_pct','D-3'],['d2_pct','D-2'],['d1_pct','D-1'],['change_24h_pct','24H']];
const CUMULATIVE=[['cum_1d_pct','1D'],['cum_3d_pct','3D'],['cum_5d_pct','5D'],['cum_7d_pct','7D'],['cum_30d_pct','30D']];

export function safeSectorCoinSort(value){return SORTS.has(value)?value:'turnover_desc'}
export function sectorCoinSortKey(sort){return sort.startsWith('change')?'change_24h_pct':sort.startsWith('opportunity')?'opportunity_score':'turnover_24h'}
export function sectorCoinSortArrow(current,key){if(!current.startsWith(key))return'↕';return current.endsWith('_desc')?'↓':'↑'}

function hasNumber(value){return value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))}
function returnValue(value){return hasNumber(value)?pct(Number(value)):'-'}
function returnCell(coin,key,label){const value=coin?.[key];return`<i><small>${label}</small><b class="${hasNumber(value)?tone(value):''}">${returnValue(value)}</b></i>`}

export function renderSectorCoinTable({coins,selected,sort,turnover}){
  const normalized=safeSectorCoinSort(sort);
  return`<section class="sector-coin-table"><header><div><h3>섹터 상세 코인</h3><span>${coins.length}종목 표시</span></div><small>완료 일별 구간과 현재 기준 누적수익률을 분리해 비교합니다.</small></header><div class="sector-coin-row columns"><span>코인</span><button data-sector-sort="change">일별 D-5 · D-4 · D-3 · D-2 · D-1 · 24H / 누적 1 · 3 · 5 · 7 · 30D <i>${sectorCoinSortArrow(normalized,'change')}</i></button><button data-sector-sort="turnover">24H 거래대금 <i>${sectorCoinSortArrow(normalized,'turnover')}</i></button><button data-sector-sort="opportunity">기회점수 <i>${sectorCoinSortArrow(normalized,'opportunity')}</i></button></div><div class="sector-coin-list">${coins.map(c=>{
    const lifecycle=lifecycleMeta(c.lifecycle_state);
    return`<button class="sector-coin-row sector-coin-select ${c.market===selected?'selected':''}" data-sector-market="${esc(c.market)}"><span class="sector-coin-name"><b>${esc(c.name_ko||c.symbol)}</b><small>${esc(c.name_en||c.symbol)} · <em class="${lifecycle.className}">${esc(c.symbol)}</em>${lifecycle.label?`<strong class="market-lifecycle-label ${lifecycle.className}">${esc(lifecycle.label)}</strong>`:''}</small></span><span class="sector-return-stack"><span class="sector-return-strip">${WINDOWS.map(([key,label])=>returnCell(c,key,label)).join('')}</span><span class="sector-cumulative-strip">${CUMULATIVE.map(([key,label])=>returnCell(c,key,label)).join('')}</span></span><span>${turnover(c.turnover_24h)}</span><span>${n(c.opportunity_score).toFixed(0)}</span></button>`
  }).join('')||'<p class="sector-empty-inline">조건에 맞는 코인이 없습니다.</p>'}</div></section>`;
}
