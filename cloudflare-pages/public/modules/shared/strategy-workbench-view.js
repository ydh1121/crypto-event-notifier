import {esc} from './format.js';
import {finite, freshness, calculatePlan, relativeSeries} from './strategy-workbench-model.js';

export const number=(v,d=2)=>finite(v)===null?'—':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:d});
export const won=v=>finite(v)===null?'—':`${number(v,Math.abs(Number(v))<10?8:Math.abs(Number(v))<1000?2:0)}원`;
export const percent=v=>finite(v)===null?'—':`${Number(v)>0?'+':''}${number(v,2)}%`;
export const color=v=>finite(v)===null?'':Number(v)>0?'gain':Number(v)<0?'loss':'';
export const time=v=>finite(v)&&Number(v)>0?new Date(Number(v)*1000).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'—';
const metric=(label,value,cls='')=>`<div><dt>${label}</dt><dd class="${cls}">${value}</dd></div>`;
export function accountHtml(a) {
  return `<div class="account-heading"><h2>${esc(a.label)} <span>가상계좌</span></h2><span>${a.reconciliation?.matches===true?'계좌·원장 일치':'계좌·원장 확인 필요'} · 완료 ${number(a.closed_trades,0)}회</span></div>
    <dl class="account-primary">${metric('계좌 평가액',won(a.equity_krw))}${metric('실현손익',won(a.realized_pnl_krw),color(a.realized_pnl_krw))}${metric('보유 평가액',won(a.position_value_krw))}${metric('남은 현금',won(a.cash_krw))}</dl>
    <dl class="account-secondary">${metric('보유수량',number(a.volume,8))}${metric('평단 · 매수 수수료 포함',won(a.avg_price))}${metric('미실현손익',won(a.unrealized_pnl_krw),color(a.unrealized_pnl_krw))}${metric('누적 수익률',percent(a.return_pct),color(a.return_pct))}${metric('승률',a.closed_trades?`${number(a.win_rate_pct,1)}% · ${a.wins}/${a.closed_trades}`:'완료 거래 없음')}${metric('최대 하락폭',percent(a.max_drawdown_pct))}</dl>`;
}
export function planHtml(a) {
  const p=a.plan||{}, entry=p.entries?.[0], exit=p.exits?.[0];
  const action=!p.source_ts?'조건 기록 없음':p.action==='sell'?'청산 조건 충족':p.entry_conditions_met?'매수 조건 충족':'매수 조건 대기';
  return `<div class="section-heading"><h3>현재 계획</h3><span>${esc(action)}</span></div>
    <dl class="plan-prices">${metric(entry?.round>1?'다음 추가매수':'다음 진입',won(entry?.price))}${metric('진입 비중',entry?`${number(entry.weight_pct)}% · ${won(entry.amount_krw)}`:'—')}${metric('익절',exit?`${won(exit.price)} · ${exit.weight_pct}%`:'보유 후 계산')}${metric('손절 기준',won(p.stop_price))}</dl>
    <div class="plan-actions"><button data-action="import-plan" ${!p.available||!a.reconciliation?.matches?'disabled':''}>계획으로 계산</button><small>분할 ${p.completed_entries??0}/${p.rules?.max_buys??'—'}회</small></div>
    <details data-continuity-key="plan-rules"><summary>진입·청산 조건</summary>${p.available?`<dl class="rule-list">${metric('시장 / 진입 / 기회',`${number(p.rules.entry_regime+p.entry_bias)} / ${number(p.rules.entry_score+p.entry_bias)} / ${number(p.rules.opportunity+p.entry_bias)}`)}${metric('최대 보유 비중',`${number(p.rules.max_position_pct)}%`)}${metric('추가매수 간격',`평단 아래 ${number(p.rules.add_drop_pct)}%`)}${metric('시장 약화 청산',`${number(p.weak_market_exit?.after_seconds/60)}분 경과 · 시장 점수 ${number(p.weak_market_exit?.below)} 미만`)}</dl><p>가격과 함께 전략별 진입 조건을 다시 확인합니다. 익절은 현재 규칙의 전량 청산 기준입니다.</p>`:'<p>저장된 전략 조건이 없습니다.</p>'}</details>`;
}
const reasonLabel=r=>({'style hard stop':'손절 기준 도달','style take profit':'익절 기준 도달','regime weakened':'시장 약화','style thresholds satisfied':'진입 조건 충족','meaningful pullback with surviving regime':'조정 후 진입 조건 충족'}[r]||(/style add after ([\d.]+)% drop/.test(r)?`평단 대비 ${r.match(/([\d.]+)%/)[1]}% 하락`:'전략 조건 체결'));
export function journalHtml(page, {loading=false,error=''}={}) {
  if(error)return `<p class="notice" role="status">${esc(error)}</p><button data-action="retry-journal">다시 불러오기</button>`;
  if(!page)return `<p class="placeholder">${loading?'체결 내역 불러오는 중…':'체결 내역을 선택하세요.'}</p>`;
  const start=page.total?page.offset+1:0,end=page.offset+page.trades.length;
  return `<div class="section-heading"><h3>체결 원장 <span>${number(page.total,0)}건</span></h3><span>${start}–${end} / ${number(page.total,0)}</span></div>
    ${page.total?`<div class="table-scroll" data-preserve-scroll><table><thead><tr><th>체결 · 한국시간</th><th>가격 / 수량</th><th>입출금액</th><th>실현손익</th></tr></thead><tbody>${page.trades.map(t=>`<tr><td><b class="${t.side==='buy'?'buy':'sell'}">${t.side==='buy'?'매수':'매도'}</b> <time>${time(t.ts)}</time><small>${esc(reasonLabel(t.reason))}</small></td><td>${won(t.price)}<small>${number(t.volume,8)}개</small></td><td>${t.side==='buy'?'−':'+'}${won(t.krw)}<small>${t.side==='buy'?'수수료 포함 지출':'수수료 차감 수령'}</small></td><td class="${color(t.realized_pnl)}">${t.side==='sell'?won(t.realized_pnl):'—'}<small>${t.side==='sell'?percent(t.return_pct):''}</small></td></tr>`).join('')}</tbody></table></div>`:'<p class="placeholder">이 코인·전략의 체결 기록이 없습니다.</p>'}
    <div class="pagination"><button data-action="previous" ${page.offset===0||loading?'disabled':''}>이전</button><button data-action="next" ${page.next_offset===null||loading?'disabled':''}>다음</button></div>`;
}
export function calculatorHtml(draft,{origin='선택한 가상계좌 기준 · 계산값만 변경됩니다.',closable=true,result=true}={}) {
  const input=(name,value,label)=>`<label>${label}<input data-draft="${name}" data-continuity-key="calc-${name}" type="number" min="0" step="any" value="${esc(value)}"></label>`;
  return `<div class="section-heading"><h3>물타기 · 익절 계산</h3>${closable?'<button class="text-button" data-action="close-calculator" aria-label="계산기 닫기">닫기</button>':''}</div>
    <p class="calculator-origin">${esc(origin)}</p>
    <div class="input-pair">${input('volume',draft.volume,'시작 수량')}${input('average',draft.average,'시작 평단 · 원')}</div>
    <div class="input-pair">${input('fee',draft.fee,'매수·매도 수수료 %')}${input('slippage',draft.slippage,'예상 체결 차이 %')}</div>
    <h4>분할 매수 <small>금액은 수수료 포함</small></h4><div class="stage-list">${draft.buys.map((r,i)=>`<div class="stage-row"><span>${i+1}</span><label>매수가<input data-buy-price="${i}" data-continuity-key="buy-price-${i}" type="number" step="any" min="0" value="${esc(r.price)}"></label><label>투입금 · 원<input data-buy-amount="${i}" data-continuity-key="buy-amount-${i}" type="number" step="any" min="0" value="${esc(r.amount)}"></label><button data-remove-buy="${i}" aria-label="매수 ${i+1}차 삭제">×</button></div>`).join('')}</div>
    <button class="text-button" data-action="add-buy" ${draft.buys.length>=20?'disabled':''}>+ 매수 회차</button>
    <h4>분할 익절 <small>매수 후 총수량 기준</small></h4><div class="stage-list">${draft.sells.map((r,i)=>`<div class="stage-row"><span>${i+1}</span><label>익절가<input data-sell-price="${i}" data-continuity-key="sell-price-${i}" type="number" step="any" min="0" value="${esc(r.price)}"></label><label>수량 비중 %<input data-sell-weight="${i}" data-continuity-key="sell-weight-${i}" type="number" step="any" min="0" max="100" value="${esc(r.weight)}"></label><button data-remove-sell="${i}" aria-label="익절 ${i+1}차 삭제">×</button></div>`).join('')}</div>
    <button class="text-button" data-action="add-sell" ${draft.sells.length>=20?'disabled':''}>+ 익절 회차</button>
    ${draft.buys.some(r=>r.basis==='conditional_recalculation')?'<p class="subtle">2차 이후는 체결 뒤 평단을 다시 계산한 가정입니다. 시장 조건은 다시 확인해야 합니다.</p>':''}${result?'<div id="calculation-result" aria-live="polite"></div>':''}`;
}
export function calculationHtml(draft,identity) {
  const r=calculatePlan(draft,identity);
  if(!r.valid)return `<p role="status" class="notice">${r.errors.map(esc).join('<br>')}</p>`;
  return `<dl class="calculation-primary">${metric('예상 평단',won(r.average))}${metric('예상 실현손익',won(r.realized),color(r.realized))}</dl>
    <dl class="calculation-secondary">${metric('추가 투입',won(r.buyTotal))}${metric('총 수수료',won(r.fees))}${metric('매도 수령액',won(r.net))}${metric('잔여 수량',number(r.remaining,8))}</dl>
    <details data-continuity-key="calculation-stages"><summary>회차별 계산</summary><div class="table-scroll"><table><thead><tr><th>회차</th><th>평단 / 실현손익</th><th>누적 / 잔여 수량</th></tr></thead><tbody>${r.buyStages.map((s,i)=>`<tr><td>매수 ${i+1}</td><td>${won(s.average)}</td><td>${number(s.quantity,8)}</td></tr>`).join('')}${r.sellStages.map((s,i)=>`<tr><td>익절 ${i+1}</td><td>${won(s.realized)}</td><td>${number(s.remaining,8)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
export function priceChart(history,trades,range='7d') {
  const raw=(history||[]).filter(r=>finite(r.price)>0&&finite(r.ts)>0).slice().sort((a,b)=>a.ts-b.ts);
  const last=raw.at(-1)?.ts,windowSeconds=({ '24h':86400,'7d':604800,all:Infinity })[range]||604800;
  const points=raw.filter(r=>r.ts>=last-windowSeconds);
  if(points.length<2)return '<p class="placeholder">가격 기록이 충분하지 않습니다.</p>';
  const t0=points[0].ts,t1=points.at(-1).ts,visible=(trades||[]).filter(t=>t.ts>=t0&&t.ts<=t1);
  const values=[...points.map(p=>p.price),...visible.map(t=>t.price)],low=Math.min(...values),high=Math.max(...values),span=high-low||high*.02||1;
  const x=t=>60+(t-t0)/(t1-t0||1)*730,y=v=>18+(high-v)/span*185;
  return `<figure><svg viewBox="0 0 820 238" role="img" aria-label="가격 흐름과 현재 원장 페이지의 매수·매도 체결"><text x="0" y="22">${number(high,8)}</text><text x="0" y="203">${number(low,8)}</text><line class="gridline" x1="60" y1="204" x2="790" y2="204"/><polyline class="price-line" points="${points.map(p=>`${x(p.ts)},${y(p.price)}`).join(' ')}"/>${visible.map(t=>`<g class="${t.side==='buy'?'buy':'sell'}"><circle cx="${x(t.ts)}" cy="${y(t.price)}" r="5"/><text x="${x(t.ts)}" y="${y(t.price)-10}" text-anchor="middle">${t.side==='buy'?'매수':'매도'}</text><title>${time(t.ts)} · ${won(t.price)} · ${number(t.volume,8)}개</title></g>`).join('')}<text x="60" y="232">${time(t0)}</text><text x="790" y="232" text-anchor="end">${time(t1)}</text></svg><figcaption>표에 표시된 체결 ${visible.length}건 · 저장된 가격 기록</figcaption></figure>`;
}
export function relativeHtml(memory, aligned) {
  if(aligned?.windows?.length) return `<div class="section-heading"><h2>BTC·ETH 대비 움직임</h2><span>${time(aligned.source_ts)} 기준</span></div>
    <p class="subtle">같은 시각의 1시간봉 종가로 비교합니다.</p><div class="table-scroll"><table><thead><tr><th>기간</th><th>코인</th><th>BTC</th><th>ETH</th><th>BTC 대비</th><th>ETH 대비</th></tr></thead><tbody>${aligned.windows.map(r=>`<tr><td>${({ '1h':'1시간','4h':'4시간','1d':'1일','7d':'7일' })[r.horizon]||esc(r.horizon)}</td><td>${percent(r.coin)}</td><td>${percent(r.btc)}</td><td>${percent(r.eth)}</td><td>${finite(r.vs_btc_pp)===null?'—':percent(r.vs_btc_pp)+'p'}</td><td>${finite(r.vs_eth_pp)===null?'—':percent(r.vs_eth_pp)+'p'}</td></tr>`).join('')}</tbody></table></div>`;

  const rows=relativeSeries(memory),last=rows.at(-1);
  if(!last)return '<p class="placeholder">상대 움직임 기록이 없습니다.</p>';
  return `<div class="section-heading"><h2>BTC·ETH 대비 움직임</h2><span>${time(last.ts)} 기준</span></div>
    <dl class="account-primary">${metric('코인 수익률',percent(last.coin),color(last.coin))}${metric('BTC 수익률',percent(last.btc),color(last.btc))}${metric('ETH 수익률',percent(last.eth),color(last.eth))}</dl>
    <p class="subtle">기존 수집기의 수익률 기록입니다. 서로 다른 산출 구간일 수 있어 상대 강도로 단정하지 않습니다.</p>
    <div class="table-scroll"><table><thead><tr><th>시각</th><th>코인</th><th>BTC</th><th>ETH</th></tr></thead><tbody>${rows.slice(-30).reverse().map(r=>`<tr><td>${time(r.ts)}</td><td>${percent(r.coin)}</td><td>${percent(r.btc)}</td><td>${percent(r.eth)}</td></tr>`).join('')}</tbody></table></div>`;
}
export function freshnessHtml(a) {
  const fresh=freshness(a?.source_ts);
  return `<span class="${fresh.stale?'stale':'subtle'}">${fresh.label} · ${time(a?.source_ts)} 기준</span>`;
}

export function sourceHref(value){try{const url=new URL(value);return ["https:","http:"].includes(url.protocol)?esc(url.href):"#";}catch{return "#";}}
