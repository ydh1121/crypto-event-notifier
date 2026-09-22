import {esc} from './format.js';
import {finite} from './strategy-workbench-model.js';
import {won,number,percent,color,sourceHref} from './strategy-workbench-view.js';

const periods=[['15m','15분'],['1h','1시간'],['4h','4시간'],['1d','1일']];
export const eventKey=e=>`${e.event_id}|${e.event_ts}`;
const stamp=v=>finite(v)>0?new Date(v*1000).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'—';
const relative=v=>finite(v)===null?'—':`${v>0?'+':''}${number(v,2)}%p`;

export function eventsHtml(events,selected='') {
  if(!Array.isArray(events))return '<p class="placeholder">이 코인의 이벤트 반응 기록이 아직 전송되지 않았습니다.</p>';
  if(!events.length)return '<p class="placeholder">저장된 코인별 이벤트 반응이 없습니다.</p>';
  const e=events.find(row=>eventKey(row)===selected)||events[0];
  const evidence=periods.flatMap(([h,label])=>['coin','btc','eth'].map(name=>({h,label,name,sample:e.responses?.[h]?.observations?.[name]})));
  return `<div class="section-heading"><h2>이벤트 반응</h2><span>최근 ${events.length}개</span></div>
    <label class="event-choice">이벤트 선택<select id="event-picker" data-continuity-key="event-picker">${events.map(row=>`<option value="${esc(eventKey(row))}" ${row===e?'selected':''}>${esc(row.title)} · ${stamp(row.event_ts)}</option>`).join('')}</select></label>
    <article class="event-detail"><header><h3>${esc(e.title)}</h3><div class="event-meta"><time>${stamp(e.event_ts)} · 한국시간</time><a href="${sourceHref(e.source_url)}" target="_blank" rel="noopener noreferrer">발표 원문 ↗</a></div></header>
    ${e.anchor_changed?'<p class="notice">발표 시각이 수정되었습니다. 아래 반응은 저장 당시의 발표 시각 기준입니다.</p>':''}
    ${e.invalid_observations?'<p class="notice">일부 반응 기록의 가격·시각을 확인해야 합니다.</p>':''}
    <div class="table-scroll"><table class="reaction-table"><thead><tr><th>발표 후</th><th>코인</th><th>BTC</th><th>ETH</th><th>BTC 대비</th><th>ETH 대비</th></tr></thead><tbody>${periods.map(([h,label])=>{const r=e.responses?.[h]||{};return `<tr><td>${label}</td><td class="${color(r.coin)}">${percent(r.coin)}</td><td>${percent(r.btc)}</td><td>${percent(r.eth)}</td><td>${relative(r.vs_btc_pp)}</td><td>${relative(r.vs_eth_pp)}</td></tr>`;}).join('')}</tbody></table></div>
    <p class="subtle">— 해당 시점의 체결 기록 없음</p>
    <details data-continuity-key="event-history-${esc(eventKey(e))}"><summary>과거 같은 이벤트의 반응</summary><p>이전 1년 중 이번 발표 전에 확보된 기록 · 같은 거래소·코인·발표 기관·이벤트 종류</p>
    <div class="table-scroll"><table><thead><tr><th>발표 후</th><th>표본</th><th>평균</th><th>중앙값</th><th>상승</th></tr></thead><tbody>${periods.map(([h,label])=>{const r=e.history?.[h];return `<tr><td>${label}</td><td>${r?`${number(r.samples,0)}회`:'—'}</td><td>${percent(r?.mean_pct)}</td><td>${percent(r?.median_pct)}</td><td>${r?.samples?`${r.positive_samples}/${r.samples}회`:'—'}</td></tr>`;}).join('')}</tbody></table></div></details>
    <details data-continuity-key="event-prices-${esc(eventKey(e))}"><summary>계산에 사용한 실제 가격·시각</summary>
    <div class="table-scroll"><table><thead><tr><th>기간 · 종목</th><th>발표 직전</th><th>발표 후</th></tr></thead><tbody>${evidence.map(({label,name,sample:s})=>`<tr><td>${label} · ${{coin:esc(e.market?.replace('KRW-','')||'코인'),btc:'BTC',eth:'ETH'}[name]}</td><td>${won(s?.baseline_price)}<small>${stamp(s?.baseline_trade_ts)}</small></td><td>${won(s?.target_price)}<small>${stamp(s?.target_trade_ts)}</small></td></tr>`).join('')}</tbody></table></div></details></article>`;
}
