import {esc} from './format.js';
import {number,won,percent,color,time} from './strategy-workbench-view.js';

const count=v=>v===null||v===undefined?'—':`${number(v,0)}회`;
const span=(start,end)=>`${start?time(start):'첫 기록'} ~ ${time(end)}`;
export function strategyPeriodHtml(review,selection={}, {loading=false,error=''}={}) {
  const toolbar=`<div class="section-heading period-toolbar"><h3>기간별 전략 비교</h3><div class="range-picker" aria-label="전략 비교 기간">${[['7d','7일'],['30d','30일'],['90d','90일'],['all','전체']].map(([key,label])=>`<button data-period-range="${key}" data-continuity-key="period-range-${key}" aria-pressed="${selection.period===key}">${label}</button>`).join('')}</div></div>`;
  if(error)return `${toolbar}<p class="notice" role="status">${esc(error)}</p><button data-period-retry>다시 불러오기</button>`;
  if(!review)return `${toolbar}<p class="placeholder" role="status">기간별 매매를 불러오는 중…</p>`;
  if(review.status!=='ok')return `${toolbar}<p class="placeholder">${review.status==='read_error'?'매매 기록을 읽지 못했습니다.':'이 코인의 전략 계좌가 없습니다.'}</p><button data-period-retry>다시 불러오기</button>`;
  const selected=review.strategies.find(r=>r.experiment_id===review.selected_experiment);
  const current=selected?.current;
  const rows=review.strategies.map(r=>{
    const c=r.current,p=r.previous;
    return `<tr><th scope="row"><button data-period-experiment="${esc(r.experiment_id)}" data-continuity-key="period-strategy-${esc(r.experiment_id)}" aria-pressed="${r===selected}">${esc(r.label)}</button></th>${r.status==='ok'?`<td>${count(c.closed)} / ${count(c.open)}</td><td class="${color(c.realized_pnl_krw)}">${won(c.realized_pnl_krw)}</td><td class="${color(c.return_pct)}">${percent(c.return_pct)}</td><td>${c.closed?`${c.wins} / ${c.closed}`:'—'}</td><td>${percent(c.worst_return_pct)}</td><td>${p?percent(p.return_pct):'—'}<small>${p?`완료 ${count(p.closed)} · 미청산 ${count(p.open)}`:'기간 구분 없음'}</small></td>`:'<td colspan="6">계좌·원장 확인 필요</td>'}</tr>`;
  }).join('');
  return `${toolbar}<p class="subtle" role="status">${span(review.start,review.end)} · 한국시간${loading?' · 갱신 중':''}</p>
    <div class="table-scroll period-summary" data-preserve-scroll data-continuity-key="period-summary"><table><thead><tr><th>전략</th><th>완료 / 보유 중</th><th>실현손익</th><th>매매 수익률</th><th>승리 / 완료</th><th>최저 거래 수익률</th><th>직전 기간 수익률</th></tr></thead><tbody>${rows}</tbody></table></div>
    <section class="period-evidence"><div class="section-heading"><h3>${esc(selected?.label||'')} · 매매 내역</h3>${selected?`<button class="text-button" data-period-journal="${esc(selected.experiment_id)}">계좌·전체 원장</button>`:''}</div>
    ${current?`<dl class="account-secondary">${[['완료 매매 매수 금액',won(current.invested_krw)],['완료 매매 매도 수령액',won(current.proceeds_krw)],['보유 중 매수 금액',won(current.open_invested_krw)]].map(([label,value])=>`<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl><p class="subtle">기간 내 첫 진입 ${count(review.witnesses_total)}${review.witnesses_total>review.witnesses_limit?` · 최근 ${review.witnesses_limit}회 표시`:''} · 이전 기간 진입 ${count(current.carried_positions)} 제외</p>`:''}
    ${review.witnesses.length?`<div class="table-scroll" data-preserve-scroll data-continuity-key="period-witnesses"><table><thead><tr><th>첫 매수 · 가격</th><th>청산 · 가격</th><th>매수 금액</th><th>매도 수령액</th><th>실현손익</th><th>수익률</th></tr></thead><tbody>${review.witnesses.map(w=>`<tr><td>${won(w.entry_price)}<small>${time(w.entry_ts)} · ${w.buy_count}회 매수</small></td><td>${w.exit_ts?won(w.exit_price):'보유 중'}<small>${time(w.exit_ts)}</small></td><td>${won(w.invested_krw)}</td><td>${won(w.proceeds_krw)}</td><td class="${color(w.realized_pnl_krw)}">${won(w.realized_pnl_krw)}</td><td>${percent(w.return_pct)}</td></tr>`).join('')}</tbody></table></div>`:`<p class="placeholder">${selected?.status==='ok'?'이 기간에 새로 진입한 매매가 없습니다.':'계좌와 원장을 확인해야 성과를 계산할 수 있습니다.'}</p>`}
    </section><details data-continuity-key="period-method"><summary>집계 기준</summary><p>선택한 거래소·코인의 각 전략을 같은 기간으로 비교합니다. 기간 안에 처음 매수한 포지션만 포함하며, 완료와 보유 중을 구분합니다. 첫 매수 가격은 물타기를 포함한 평단과 다릅니다.</p><p>매수 금액과 매도 수령액은 비용이 반영된 원장 금액입니다. 매매 수익률은 완료 매매의 손익 합계 ÷ 매수 금액 합계이며, 계좌 전체 수익률과 다릅니다. 최저 거래 수익률은 완료 거래 중 최저값이며 보유 중 최대 하락폭을 뜻하지 않습니다.</p><p>${review.previous_end?`직전 기간: ${span(review.previous_start,review.previous_end)} 직전까지. 그 이후 매수·매도를 제외한 당시 결과입니다.`:'전체 기간은 직전 기간과 비교하지 않습니다.'}</p><p>완료 횟수와 보유 중 금액을 함께 보세요. 과거 수익률만으로 현재 전략 우위나 앞으로의 수익을 판정하지 않습니다.</p></details>`;
}
