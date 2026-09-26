import {esc} from './format.js';
import {finite} from './strategy-workbench-model.js';
import {won,number,percent,color,sourceHref} from './strategy-workbench-view.js';

const periods=[['15m','15분'],['1h','1시간'],['4h','4시간'],['1d','1일']];
export const eventKey=e=>[e.event_id,e.event_ts,e.source_id||'',e.event_type||''].map(v=>encodeURIComponent(String(v))).join('|');
const stamp=v=>finite(v)>0?new Date(v*1000).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'—';
const relative=v=>finite(v)===null?'—':`${v>0?'+':''}${number(v,2)}%p`;
const pendingLabels={before_horizon:'대기 중',missing_baseline:'기준가 미확보',missing_target:'이후 가격 미확보',awaiting_capture:'계산 대기',invalid_response:'확인 필요'};
const reaction=(e,h,name)=>finite(e.responses?.[h]?.[name])!==null?percent(e.responses[h][name]):pendingLabels[e.price_progress?.[name]?.[h]?.status]||'—';
const priceCell=p=>`${won(p?.price)}<small>${stamp(p?.trade_ts)}${p?.origin==='archive'?' · 보존':''}</small>`;

export function eventsHtml(events,selected='',horizon='1h') {
  if(!Array.isArray(events))return '<p class="placeholder">이 코인의 이벤트 반응 기록이 아직 전송되지 않았습니다.</p>';
  if(!events.length)return '<p class="placeholder">저장된 이벤트 가격·반응이 없습니다.</p>';
  const e=events.find(row=>eventKey(row)===selected)||events[0];
  const period=periods.some(([h])=>h===horizon)?horizon:'1h';
  const evidence=periods.flatMap(([h,label])=>['coin','btc','eth'].map(name=>{
    const sample=e.responses?.[h]?.observations?.[name],p=e.price_progress?.[name]?.[h];
    return {label,name,baseline:p?.baseline||(sample?{price:sample.baseline_price,trade_ts:sample.baseline_trade_ts}:null),target:p?.target||(sample?{price:sample.target_price,trade_ts:sample.target_trade_ts}:null)};
  }));
  return `<div class="section-heading event-toolbar"><h2>뉴스·지표 반응</h2><div class="range-picker" role="group" aria-label="발표 후 시간">${periods.map(([h,label])=>`<button data-event-horizon="${h}" data-continuity-key="event-horizon-${h}" aria-pressed="${h===period}">${label}</button>`).join('')}</div></div>
    <div class="table-scroll event-index" data-preserve-scroll><table><caption class="subtle">최근 ${events.length}개 · ${periods.find(([h])=>h===period)[1]} 반응</caption><thead><tr><th>발표</th><th>${esc(e.market?.replace('KRW-','')||'코인')}</th><th>BTC 대비</th><th>ETH 대비</th><th>과거 표본</th></tr></thead><tbody>${events.map(row=>{
      const r=row.responses?.[period]||{},key=esc(eventKey(row));
      return `<tr><th scope="row"><button data-event="${key}" data-continuity-key="event-row-${key}" aria-pressed="${row===e}" title="${esc(row.title)}"><span>${esc(row.title)}</span><time>${stamp(row.event_ts)}</time></button></th><td class="${color(r.coin)}" title="${esc(reaction(row,period,'coin'))}">${finite(r.coin)===null?'—':percent(r.coin)}</td><td class="${color(r.vs_btc_pp)}">${relative(r.vs_btc_pp)}</td><td class="${color(r.vs_eth_pp)}">${relative(r.vs_eth_pp)}</td><td>${row.history?.[period]?`${number(row.history[period].samples,0)}회`:'—'}</td></tr>`;
    }).join('')}</tbody></table></div>
    <article class="event-detail"><header><h3>${esc(e.title)}</h3><div class="event-meta"><time>${stamp(e.event_ts)} · 한국시간</time><a href="${sourceHref(e.source_url)}" target="_blank" rel="noopener noreferrer">발표 원문 ↗</a></div></header>
    ${e.anchor_changed?'<p class="notice">발표 시각이 수정되었습니다. 아래 반응은 저장 당시의 발표 시각 기준입니다.</p>':''}
    ${e.anchor_conflict?'<p class="notice">발표 시각·출처가 다른 반응 기록이 있습니다.</p>':''}
    ${e.invalid_observations?'<p class="notice">일부 반응 기록의 가격·시각을 확인해야 합니다.</p>':''}
    <div class="table-scroll"><table class="reaction-table"><thead><tr><th>발표 후</th><th>${esc(e.market?.replace('KRW-','')||'코인')}</th><th>BTC</th><th>ETH</th><th>BTC 대비</th><th>ETH 대비</th></tr></thead><tbody>${periods.map(([h,label])=>{const r=e.responses?.[h]||{};return `<tr><td>${label}</td><td class="${color(r.coin)}">${reaction(e,h,'coin')}</td><td>${reaction(e,h,'btc')}</td><td>${reaction(e,h,'eth')}</td><td>${relative(r.vs_btc_pp)}</td><td>${relative(r.vs_eth_pp)}</td></tr>`;}).join('')}</tbody></table></div>
    <p class="subtle">수익률은 저장된 반응 기준 · — 비교 기록 없음</p>
    <details data-continuity-key="event-history-${esc(eventKey(e))}"><summary>과거 같은 이벤트의 반응</summary><p>이전 1년 중 이번 발표 전에 확보된 기록 · 같은 거래소·코인·발표 기관·이벤트 종류</p>
    <div class="table-scroll"><table><thead><tr><th>발표 후</th><th>표본</th><th>평균</th><th>중앙값</th><th>상승</th></tr></thead><tbody>${periods.map(([h,label])=>{const r=e.history?.[h];return `<tr><td>${label}</td><td>${r?`${number(r.samples,0)}회`:'—'}</td><td>${percent(r?.mean_pct)}</td><td>${percent(r?.median_pct)}</td><td>${r?.samples?`${r.positive_samples}/${r.samples}회`:'—'}</td></tr>`;}).join('')}</tbody></table></div></details>
    <details data-continuity-key="event-prices-${esc(eventKey(e))}"><summary>실제 가격·시각</summary>
    <div class="table-scroll"><table><thead><tr><th>기간 · 종목</th><th>발표 직전</th><th>발표 후</th></tr></thead><tbody>${evidence.map(({label,name,baseline,target})=>`<tr><td>${label} · ${{coin:esc(e.market?.replace('KRW-','')||'코인'),btc:'BTC',eth:'ETH'}[name]}</td><td>${priceCell(baseline)}</td><td>${priceCell(target)}</td></tr>`).join('')}</tbody></table></div></details></article>`;
}
