import {esc} from './format.js';
import {won,number,percent,time,color} from './strategy-workbench-view.js';

const count=v=>v===null||v===undefined?'—':`${number(v,0)}회`;
export function manualComparisonHtml(c,label='선택 전략') {
  if(!c?.start)return '<p class="subtle">체결을 기록하면 같은 기간의 가상매매와 비교합니다.</p>';
  const sides=[c.manual,c.paper];
  const rows=[
    ['매수 금액',v=>won(v.invested_krw)],
    ['매도 수령액',v=>won(v.proceeds_krw)],
    ['실현손익',v=>`<strong class="${color(v.realized_pnl_krw)}">${won(v.realized_pnl_krw)}</strong>`],
    ['매매 수익률',v=>`<strong class="${color(v.return_pct)}">${percent(v.return_pct)}</strong>`],
    ['승리 / 완료',v=>v.closed?`${v.wins} / ${v.closed}회`:'완료 0회'],
    ['보유 중 · 비교 제외',v=>count(v.open)],
    ['최저 거래 수익률',v=>percent(v.worst_return_pct)],
  ];
  const witnesses=[...['manual','paper'].flatMap(side=>(c[`${side}_witnesses`]||[]).map(w=>({...w,side})))].sort((a,b)=>b.entry_ts-a.entry_ts);
  const unavailable=c.status==='paper_incomplete'?'가상매매 원장을 모두 읽지 못했습니다.':c.status!=='ok'?'가상계좌와 체결 원장을 확인해야 비교할 수 있습니다.':'';
  return `<div class="section-heading"><h3>같은 기간 전략 비교</h3><button class="text-button" data-action="paper-ledger">가상 체결 원장</button></div>
    <p class="subtle">${time(c.start)} ~ ${time(c.end)} · 한국시간 · 완료 매매 기준</p>
    ${unavailable?`<p class="notice" role="status">${unavailable}</p>`:''}
    <div class="table-scroll" data-preserve-scroll data-continuity-key="manual-comparison"><table><thead><tr><th>항목</th><th>내 실거래</th><th>${esc(label)} · 가상</th></tr></thead><tbody>${rows.map(([title,format],i)=>`<tr data-render-key="comparison-${i}"><th scope="row">${title}</th>${sides.map(v=>`<td>${v?format(v):'—'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    <details data-continuity-key="manual-comparison-trades"><summary>비교에 쓴 매매 · 실거래 ${count((c.manual?.closed||0)+(c.manual?.open||0))} / 가상 ${c.paper?count(c.paper.closed+c.paper.open):'—'}</summary>
      <p class="subtle">각각 최근 ${c.witnesses_limit||20}회 표시 · 기간 전에 시작한 가상 매매 ${count(c.paper_carried_positions)} 제외</p>
      ${witnesses.length?`<div class="table-scroll" data-preserve-scroll data-continuity-key="manual-witnesses"><table><thead><tr><th>구분 · 첫 매수</th><th>전량 매도</th><th>매수 금액</th><th>매도 수령액</th><th>실현손익</th></tr></thead><tbody>${witnesses.map(w=>`<tr data-render-key="${w.side}-${esc(w.entry_trade_id??w.entry_ts)}"><th scope="row">${w.side==='manual'?'내 실거래':'가상매매'}<small>${time(w.entry_ts)}</small></th><td>${w.exit_ts?time(w.exit_ts):'보유 중 · 제외'}</td><td>${won(w.invested_krw)}</td><td>${won(w.proceeds_krw)}</td><td>${w.exit_ts?won(w.realized_pnl_krw):'—'}</td></tr>`).join('')}</tbody></table></div>`:'<p class="subtle">이 기간에 새로 시작한 매매가 없습니다.</p>'}
    </details>
    <details data-continuity-key="manual-comparison-method"><summary>금액·비용 기준</summary><p>내 첫 체결부터 마지막 체결까지, 처음 매수해 전량 매도한 매매를 비교합니다. 기간 전에 시작했거나 아직 보유 중인 매매는 완료 성과에서 제외합니다.</p><p>매수 금액은 수수료를 포함한 지급액, 매도 수령액은 수수료를 뺀 금액입니다. 실거래에는 입력한 실제 수수료를, 가상매매에는 원장에 반영된 비용을 사용합니다. 완료 실거래 수수료 합계 ${won(c.manual?.fees_krw)}.</p><p>매매 수익률 = 실현손익 합계 ÷ 매수 금액 합계. 거래별 수익률의 단순 평균이나 계좌 전체 수익률과 다릅니다. 최저 거래 수익률은 보유 중 최대 하락폭을 뜻하지 않습니다.</p></details>`;
}
