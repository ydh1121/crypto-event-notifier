import {esc} from './format.js';
import {number,won,percent,color,time,calculatorHtml,calculationHtml,freshnessHtml} from './strategy-workbench-view.js';
import {finite} from './strategy-workbench-model.js';
import {holdingChanged,importAvailable,buyAllocations} from './holdings-workbench-model.js';

const exchangeLabel=ex=>({bithumb:'빗썸',upbit:'업비트'}[ex]||'거래소 미지정');
const quote=(value,currency)=>currency==='KRW'?won(value):finite(value)===null?'—':`${number(value,8)} ${esc(currency||'')}`;
const metric=(label,value,cls='')=>`<div><dt>${label}</dt><dd class="${cls}">${value}</dd></div>`;
export function holdingsShell() {
  return `<link rel="stylesheet" href="/modules/styles/strategy-workbench.css?v=3"><link rel="stylesheet" href="/modules/styles/holdings-workbench.css">
    <main><header class="workbench-header"><h1>실전 계획</h1><span>실제 보유자산</span></header><div id="holdings-summary"></div>
    <div class="holdings-layout"><aside aria-label="보유자산"><div id="holdings-list"></div></aside><section id="holding-detail"></section></div></main>`;
}
export function holdingsSummaryHtml(data) {
  if(!data)return '<p class="placeholder">보유자산 불러오는 중…</p>';
  if(data.status!=='read')return `<p class="notice" role="status">${({configuration_required:'보유자산 DB 경로를 확인하세요.',db_missing:'보유자산 DB를 찾지 못했습니다.',table_missing:'보유정보 테이블을 찾지 못했습니다.',schema_mismatch:'보유정보 형식을 확인하세요.',read_failed:'보유자산을 읽지 못했습니다. 다음 갱신 때 다시 확인합니다.'})[data.status]||'보유자산을 확인하지 못했습니다.'}</p>`;
  return `<dl class="holdings-total">${metric(data.valuation_complete?'보유 평가액':'확인된 평가액',won(data.valuation_complete?data.value_krw:data.known_value_krw))}${metric('평가손익',won(data.pnl_krw),color(data.pnl_krw))}${metric('보유 종목',`${data.holding_count}개`)}</dl>${!data.valuation_complete||data.valuation_stale?`<p class="subtle">${!data.valuation_complete?`원화 평가 ${data.priced_count}/${data.holding_count}개 · 미확인 자산은 합계에서 제외`:'일부 가격 갱신 지연'}</p>`:''}`;
}
export function holdingsListHtml(data,selected) {
  if(data?.status!=='read')return '';
  const rows=data.holdings.filter(h=>!h.closed);
  if(!rows.length)return '<p class="placeholder">등록된 보유자산이 없습니다.</p>';
  return `<div class="holdings-list">${rows.map(h=>`<button data-holding="${esc(h.key)}" aria-pressed="${h.key===selected}"><span><b>${esc(h.symbol)}</b><small>${exchangeLabel(h.exchange)} · ${esc(h.quote_currency||'통화 미확인')}</small></span><span><b>${quote(h.value_quote,h.quote_currency)}</b><small class="${color(h.unrealized_pnl_pct)}">${percent(h.unrealized_pnl_pct)}</small></span></button>`).join('')}</div>${data.closed_count?`<p class="subtle">매도 완료 ${data.closed_count}개</p>`:''}`;
}
export function holdingHeaderHtml(h) {
  return `<header class="coin-heading"><div><span>${exchangeLabel(h.exchange)} · ${esc(h.quote_currency||'통화 미확인')}</span><h2>${esc(h.symbol)}</h2></div><div class="coin-price"><b>${quote(h.current_price,h.quote_currency)}</b>${freshnessHtml({source_ts:h.price_ts})}</div></header>
    <dl class="holding-position">${metric('보유수량',number(h.volume,8))}${metric('내 평단',quote(h.avg_price,h.quote_currency))}${metric('평가손익',quote(h.unrealized_pnl_quote,h.quote_currency),color(h.unrealized_pnl_quote))}</dl>`;
}
export function holdingStrategiesHtml(accounts,selected,{loading=false,error=''}={}) {
  if(error)return `<p class="notice">${esc(error)}</p><button data-action="retry-strategies">다시 불러오기</button>`;
  if(!accounts.length)return `<p class="subtle">${loading?'코인별 전략 기록을 불러오는 중…':'이 코인의 전략 기록이 없습니다.'}</p>`;
  const a=accounts.find(a=>a.experiment_id===selected),p=a?.plan;
  return `<div class="section-heading"><h3>이 코인의 가상매매 성과</h3><span>누적수익 순</span></div><div class="strategy-tabs" role="tablist" aria-label="보유 코인의 전략">${accounts.map(a=>`<button role="tab" data-strategy="${esc(a.experiment_id)}" aria-selected="${a.experiment_id===selected}"><b>${esc(a.label)}</b><span>${percent(a.return_pct)} · 완료 ${number(a.closed_trades,0)}회</span></button>`).join('')}</div>
    ${a?`<div class="holding-strategy-evidence"><span>승률 ${a.closed_trades?`${number(a.win_rate_pct,1)}% (${a.wins}/${a.closed_trades})`:'—'} · 최대 하락 ${percent(a.max_drawdown_pct)} · ${a.reconciliation?.matches?'원장 일치':'원장 확인 필요'}</span><button class="text-button" data-action="paper-ledger">체결 원장 보기</button></div>
    <dl class="holding-strategy-prices">${metric('가상계좌 다음 진입',won(p?.entries?.[0]?.price))}${metric('가상계좌 진입 비중',p?.entries?.length?`${number(p.entries[0].weight_pct)}%`:'—')}${metric('전략 익절 기준',finite(p?.rules?.take_profit_pct)!==null?`평단 ${percent(p.rules.take_profit_pct)}`:'—')}</dl>`:''}`;
}
export function holdingCalculatorHtml(h,draft,account) {
  if(!h.planning_available)return `<p class="notice">${!h.valid?'저장된 수량·평단을 확인하세요.':!h.exchange?'보유 거래소를 확인해야 전략을 연결할 수 있습니다.':'이 보유분은 원화 계산 대상이 아닙니다.'}</p>`;
  const changed=holdingChanged(draft,h);
  return `<div class="holding-draft-state">${changed?'<p class="notice">보유정보가 갱신됐습니다. 계산에는 이전 시작값이 남아 있습니다.</p>':''}<button class="text-button" data-action="reload-holding">최신 수량·평단 불러오기</button></div>
    <div class="holding-plan-import"><label>분할 매수 총예산 · 원<input type="number" min="0" step="1" data-draft="budget" data-continuity-key="holding-budget" value="${esc(draft.budget)}"></label><button data-action="import-holding-plan" ${!importAvailable(account,h)||changed?'disabled':''}>전략 가격 불러오기</button></div>
    <p class="subtle">매수는 가상계좌 계획가, 익절은 내 예상 평단 기준입니다. 불러온 뒤 회차·가격·비중을 조정하세요.</p>
    <p id="holding-plan-error" role="status" class="notice"></p>
    <div class="holding-plan-grid"><section>${calculatorHtml(draft,{origin:'기존 평단은 저장값 · 수수료는 새 매수·익절에 적용 · 주문 전송 없음',closable:false,result:false})}</section><aside class="holding-calc-output"><h3>계산 결과</h3><div id="calculation-result" aria-live="polite">${calculationHtml(draft,{exchange:h.exchange,market:h.market})}</div><p id="holding-allocation" class="subtle">${allocationHtml(draft)}</p></aside></div>`;
}
export function allocationHtml(draft) {
  const weights=buyAllocations(draft);
  return weights.length?`추가 투입금 배분 · ${weights.map((w,i)=>`${i+1}차 ${number(w,1)}%`).join(' / ')}`:'';
}
