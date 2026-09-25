import {esc} from './format.js';
import {number,won,percent,color,time,calculatorHtml,calculationHtml,freshnessHtml} from './strategy-workbench-view.js';
import {finite} from './strategy-workbench-model.js';
import {holdingChanged,importAvailable,buyAllocations,holdingTarget} from './holdings-workbench-model.js';

const exchangeLabel=ex=>({bithumb:'빗썸',upbit:'업비트'}[ex]||'거래소 미지정');
const quote=(value,currency)=>currency==='KRW'?won(value):finite(value)===null?'—':`${number(value,8)} ${esc(currency||'')}`;
const metric=(label,value,cls='')=>`<div><dt>${label}</dt><dd class="${cls}">${value}</dd></div>`;
export function holdingsShell() {
  return `<link rel="stylesheet" href="/modules/styles/strategy-workbench.css?v=3"><link rel="stylesheet" href="/modules/styles/holdings-workbench.css">
    <main><header class="workbench-header"><h1>실전 계획</h1><div id="holding-price-refresh"></div></header><div id="holdings-summary"></div>
    <div class="holdings-layout"><aside aria-label="보유자산"><div id="holdings-list"></div></aside><section id="holding-detail"></section></div></main>`;
}
export function priceRefreshHtml(data,{available=false,busy=false,error=''}={}) {
  if(!available)return '<span>실제 보유자산</span>';
  const state=data?.public_quotes,reason=state?.failures?.[0]?.reason;
  const failure=({timeout:'가격 조회 시간 초과',tls_error:'거래소 보안 연결 실패',connection:'거래소 연결 실패',rate_limit:'조회 요청 제한',http_error:'일부 마켓 조회 실패',incomplete:'일부 가격 미확보',invalid_response:'시세 응답 확인 필요'})[reason]||'일부 가격 조회 실패';
  const status=error||({loading:'가격 조회 중…',partial:`${failure} · 확보된 시세 유지`,complete:state?.requested?'거래소 가격 반영':'조회할 거래소가 지정되지 않았습니다.'})[state?.status]||'';
  return `<button data-action="refresh-prices" ${busy?'disabled':''}>${busy?'가격 조회 중…':'현재가 새로고침'}</button><span class="subtle" role="status">${esc(status)}</span>`;
}
export function holdingsSummaryHtml(data) {
  if(!data)return '<p class="placeholder">보유자산 불러오는 중…</p>';
  if(data.status!=='read')return `<p class="notice" role="status">${({configuration_required:'보유자산 DB 경로를 확인하세요.',db_missing:'보유자산 DB를 찾지 못했습니다.',table_missing:'보유정보 테이블을 찾지 못했습니다.',schema_mismatch:'보유정보 형식을 확인하세요.',read_failed:'보유자산을 읽지 못했습니다. 다음 갱신 때 다시 확인합니다.'})[data.status]||'보유자산을 확인하지 못했습니다.'}</p>`;
  return `<dl class="holdings-total">${metric(data.valuation_complete?'보유 평가액':'확인된 평가액',won(data.valuation_complete?data.value_krw:data.known_value_krw))}${metric('평가손익',won(data.pnl_krw),color(data.pnl_krw))}${metric('보유 종목',`${data.holding_count}개`)}</dl>${!data.valuation_complete||data.valuation_stale?`<p class="subtle">${!data.valuation_complete?`원화 평가 ${data.priced_count}/${data.holding_count}개 · 미확인 자산은 합계에서 제외`:'일부 가격 갱신 지연'}</p>`:''}`;
}
export function holdingsListHtml(data,selected) {
  if(data?.status!=='read')return '';
  const rows=data.holdings.filter(h=>!h.closed);
  const closed=data.planning_enabled?data.holdings.filter(h=>h.closed&&h.recording_available):[];
  const archive=closed.length?`<details data-continuity-key="closed-holdings"><summary>매도 완료 ${data.closed_count}개</summary><div class="holdings-list">${closed.map(h=>`<button data-holding="${esc(h.key)}" aria-pressed="${h.key===selected}"><span><b>${esc(h.symbol)}</b><small>${exchangeLabel(h.exchange)} · 기록 보기</small></span></button>`).join('')}</div></details>`:data.closed_count?`<p class="subtle">매도 완료 ${data.closed_count}개</p>`:'';
  return (rows.length?`<div class="holdings-list">${rows.map(h=>`<button data-holding="${esc(h.key)}" aria-pressed="${h.key===selected}"><span><b>${esc(h.symbol)}</b><small>${exchangeLabel(h.exchange)} · ${esc(h.quote_currency||'통화 미확인')}</small></span><span><b>${h.quote_currency==='KRW'?quote(h.value_quote,'KRW'):won(h.value_krw)}</b><small class="${color(h.unrealized_pnl_pct)}">${percent(h.unrealized_pnl_pct)}${h.quote_currency==='BTC'?' · BTC 기준':''}</small></span></button>`).join('')}</div>`:'<p class="placeholder">등록된 보유자산이 없습니다.</p>')+archive;
}
export function holdingHeaderHtml(h) {
  const btc=h.quote_currency==='BTC',direct=h.valuation_basis==='krw_market';
  const price=btc?won(h.current_price_krw):quote(h.current_price,h.quote_currency);
  const basis=direct?`${exchangeLabel(h.exchange)} 원화마켓 평가가`:'BTC마켓 원화 환산가';
  return `<header class="coin-heading"><div><span>${exchangeLabel(h.exchange)} · ${esc(h.quote_currency||'통화 미확인')}</span><h2>${esc(h.symbol)}</h2></div><div class="coin-price"><b>${price}</b>${btc?`<small>${basis}</small>`:''}${freshnessHtml({source_ts:btc?h.valuation_ts:h.price_ts})}</div></header>
    <dl class="holding-position">${metric('보유수량',number(h.volume,8))}${metric('내 평단',quote(h.avg_price,h.quote_currency))}${metric('평가손익',quote(h.unrealized_pnl_quote,h.quote_currency),color(h.unrealized_pnl_quote))}</dl>${btc?`<p class="holding-conversion">원화 평가액 <b>${won(h.value_krw)}</b> · BTC마켓 ${quote(h.current_price,'BTC')} (${time(h.price_ts)}${h.price_stale?' · 갱신 지연':''}) · BTC ${won(h.quote_to_krw)} (${time(h.conversion_ts)})${h.valuation_stale?' · 평가 시세 갱신 지연':''}</p>`:''}`;
}
export function holdingStrategiesHtml(accounts,selected,{loading=false,error='',holding=null}={}) {
  if(error)return `<p class="notice">${esc(error)}</p><button data-action="retry-strategies">다시 불러오기</button>`;
  if(!accounts.length)return `<p class="subtle">${loading?'코인별 전략 기록을 불러오는 중…':'이 코인의 전략 기록이 없습니다.'}</p>`;
  const a=accounts.find(a=>a.experiment_id===selected),p=a?.plan,target=holdingTarget(holding,a);
  const distance=target?.distance;
  const targetNote=finite(distance)===null?'':`<p class="subtle">현재가는 이 기준보다 ${number(Math.abs(distance))}% ${distance>=0?'위':'아래'}</p>`;
  return `<div class="section-heading"><h3>이 코인의 가상매매 성과</h3><span>누적수익 순</span></div><div class="strategy-tabs" role="tablist" aria-label="보유 코인의 전략">${accounts.map(a=>`<button role="tab" data-strategy="${esc(a.experiment_id)}" aria-selected="${a.experiment_id===selected}"><b>${esc(a.label)}</b><span>${percent(a.return_pct)} · 완료 ${number(a.closed_trades,0)}회</span></button>`).join('')}</div>
    ${a?`<div class="holding-strategy-evidence"><span>승률 ${a.closed_trades?`${number(a.win_rate_pct,1)}% (${a.wins}/${a.closed_trades})`:'—'} · 최대 하락 ${percent(a.max_drawdown_pct)} · ${a.reconciliation?.matches?'원장 일치':'원장 확인 필요'}</span><button class="text-button" data-action="paper-ledger">체결 원장 보기</button></div>
    <dl class="holding-strategy-prices">${metric('가상계좌 다음 진입',p?.entries?.length?won(p.entries[0].price):p?.available?'진입 대기':'—')}${metric('가상계좌 진입 비중',p?.entries?.length?`${number(p.entries[0].weight_pct)}%`:'—')}${metric('내 보유 평단 적용 익절가',target?`${won(target.price)}<small>평단 ${percent(target.pct)} · 계산 기준</small>`:'—','holding-target')}</dl>${targetNote}`:''}`;
}
export function holdingCalculatorHtml(h,draft,account) {
  if(!h.planning_available)return `<p class="notice">${!h.valid?'저장된 수량·평단을 확인하세요.':!h.exchange?'보유 거래소를 확인해야 전략을 연결할 수 있습니다.':'이 보유분은 원화 계산 대상이 아닙니다.'}</p>`;
  const changed=holdingChanged(draft,h);
  return `<div class="holding-draft-state">${changed?'<p class="notice">보유정보가 갱신됐습니다. 계산에는 이전 시작값이 남아 있습니다.</p>':''}<button class="text-button" data-action="reload-holding">최신 수량·평단 불러오기</button></div>
    <div class="holding-plan-import"><label>분할 매수 총예산 · 원<input type="number" min="0" step="1" data-draft="budget" data-continuity-key="holding-budget" value="${esc(draft.budget)}"></label><button data-action="import-holding-buy" ${!importAvailable(account,h)||changed||!account?.plan?.entries?.length?'disabled':''}>매수가 불러오기</button><button data-action="import-holding-sell" ${!importAvailable(account,h)||changed||!(finite(account?.plan?.rules?.take_profit_pct)>0)?'disabled':''}>익절가 불러오기</button></div>
    <p class="subtle">익절은 입력한 매수 후 예상 평단 기준 · 불러온 뒤 가격·비중 조정</p>
    <p id="holding-plan-error" role="status" class="notice"></p>
    <div class="holding-plan-grid"><section>${calculatorHtml(draft,{origin:'기존 평단은 저장값 · 수수료는 새 매수·익절에 적용 · 주문 전송 없음',closable:false,result:false})}</section><aside class="holding-calc-output"><h3>계산 결과</h3><div id="calculation-result" aria-live="polite">${holdingCalculationHtml(h,draft)}</div><p id="holding-allocation" class="subtle">${allocationHtml(draft)}</p></aside></div>`;
}
export function holdingCalculationHtml(h,draft) {
  return calculationHtml(draft,{exchange:h.exchange,market:h.market},{emptySellAsMissing:true});
}
export function allocationHtml(draft) {
  const weights=buyAllocations(draft);
  return weights.length?`추가 투입금 배분 · ${weights.map((w,i)=>`${i+1}차 ${number(w,1)}%`).join(' / ')}`:'';
}
