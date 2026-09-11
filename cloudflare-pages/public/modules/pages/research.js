import{rowsFor,findHolding,findMarket,marketSummary,fullPublic}from'../shared/selectors.js';
import{pageHead,loading,empty,exchangeToggle}from'../shared/components.js';
import{n,money,pct,price,tone,esc,decisionLabel,stateLabel,dt}from'../shared/format.js';
import{DECISION_FILTERS,decisionCounts,decisionMatches,decisionEmptyMessage}from'../shared/decision.js';
import{rangeControl,priceFillChart,scoreHistoryChart,simpleLineChart}from'../shared/charts.js';
import{getMarketDetail}from'../services/market-detail.js';

const LISTING_STATUS={complete:'완료',tracking_postlisting:'상장 후 추적',no_foreign_market_found:'해외 선행 없음',venue_verification_waiting:'거래소 검증 대기',foreign_source_waiting:'해외 데이터 대기',waiting_for_domestic_open:'국내 개시 대기',waiting_for_domestic_open_price:'상장가 대기',rejected_notice:'공지 제외',rejected_identity:'식별 제외'};
function listingPct(value){return value===undefined||value===null?'-':pct(value)}
function listingMetric(label,value){return`<span><small>${esc(label)}</small><b class="${value===undefined||value===null?'':tone(value)}">${listingPct(value)}</b></span>`}
function renderListingSource(source){const pre=source.prelisting_returns||{},post=source.postlisting_returns||{};return`<div class="listing-source-row"><div class="listing-source-head"><span><b>${esc(String(source.exchange||'').toUpperCase())}</b><small>${esc(source.market||'')} · ${esc(source.quote_asset||'')}</small></span><span><b>v${n(source.feature_version)}</b><small>${source.p5m_source_interval_seconds===60?'5분 반응 · 1분봉':'요약 feature'}</small></span></div><div class="listing-metrics">${listingMetric('상장 프리미엄',source.domestic_listing_premium_pct)}${listingMetric('T-1일',pre.t1d)}${listingMetric('T-1시간',pre.t1h)}${listingMetric('+5분',post.p5m)}${listingMetric('+1시간',post.p1h)}${listingMetric('+24시간',post.p24h)}${listingMetric('+7일',post.p7d)}</div></div>`}
function renderListingHistory(history){const data=history&&typeof history==='object'?history:{},cases=Array.isArray(data.cases)?data.cases:[],counts=data.status_counts&&typeof data.status_counts==='object'?data.status_counts:{};if(!cases.length)return`<section class="listing-history-panel"><div class="listing-history-head"><div><h3>상장 이력 연구</h3><p>국내 상장 전후의 검증된 해외 CEX 반응을 compact feature로 비교합니다.</p></div><span>원본 캔들 로컬 보관</span></div>${empty('상장 이력 feature가 아직 없습니다.','리서치 수집기가 사례를 검증하면 이 영역에 요약값만 표시됩니다.')}</section>`;return`<section class="listing-history-panel"><div class="listing-history-head"><div><h3>상장 이력 연구</h3><p>국내 상장 전후의 검증된 해외 CEX 반응입니다. 원본 OHLCV는 Viewer로 전송하지 않습니다.</p></div><span>${data.raw_candles_included===false?'COMPACT · NO RAW CANDLES':'COMPACT'}</span></div><div class="listing-history-summary"><span><small>사례</small><b>${n(data.case_count)}</b></span><span><small>완료</small><b>${n(counts.complete)}</b></span><span><small>검증 source</small><b>${n(data.source_count)}</b></span><span><small>feature</small><b>${n(data.feature_count)}</b></span></div><div class="listing-case-grid">${cases.slice(0,12).map(row=>{const sources=Array.isArray(row.sources)?row.sources:[];return`<article class="listing-case-card"><header><div><span>${esc(String(row.exchange||'').toUpperCase())}</span><h4>${esc(row.market||row.symbol||'-')}</h4><small>${row.domestic_open_at?dt(row.domestic_open_at):'개시 시각 미확인'} · ${row.domestic_open_price?price(row.domestic_open_price):'상장가 미확인'}</small></div><strong>${esc(LISTING_STATUS[row.status]||row.status||'대기')}</strong></header>${sources.length?sources.map(renderListingSource).join(''):'<p class="listing-no-source">검증된 해외 선행 CEX source가 없습니다.</p>'}</article>`}).join('')}</div></section>`}
function finiteValue(value){if(value===null||value===undefined||value==='')return null;const parsed=Number(value);return Number.isFinite(parsed)?parsed:null}
function quoteChangePct(row,detail=null){
  const direct=finiteValue(row?.change_24h_pct);if(direct!==null)return direct;
  const data=detail?.data||{},signal=data.signal||{},fromSignal=finiteValue(signal.change_24h_pct);if(fromSignal!==null)return fromSignal;
  const memory=Array.isArray(data.market_memory)?data.market_memory:[],latest=memory[memory.length-1]||{},fromMemory=finiteValue(latest.change_24h_pct);return fromMemory;
}
function quoteChangeAmount(row,detail=null){const current=finiteValue(row?.price),change=quoteChangePct(row,detail);if(current===null||current<=0||change===null)return null;const base=1+change/100;if(base<=0)return null;return current-current/base}
function signedPct(value){return value===null?'—':`${value>0?'+':''}${value.toFixed(2)}%`}
function signedPrice(value){if(value===null)return'등락 데이터 대기';return`${value>0?'+':value<0?'−':''}${price(Math.abs(value))}`}
function quoteTone(value){return value===null?'muted':tone(value)}

export function createResearchPage({store}){
  let root=null,unsub=null,seq=0,lastDetail=null,lastDetailKey='',detailTab='summary';
  const ui=()=>store.get().ui;
  const rows=()=>rowsFor(store.get(),ui().researchExchange);
  function matches(row){const q=String(ui().researchSearch||'').trim().toLowerCase();if(q&&!`${row.symbol||''} ${row.name||''} ${row.market||''}`.toLowerCase().includes(q))return false;return decisionMatches(row,ui().researchFilter)}
  function filteredRows(){return rows().filter(matches).sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score))}
  function ensureSelected(list=filteredRows()){let market=ui().researchMarket;if(!list.some(r=>r.market===market))market=list[0]?.market||'';if(market!==ui().researchMarket)store.setUi({researchMarket:market},{scope:'research-select'});return market}
  function filterButton(key,counts){const info=DECISION_FILTERS[key];return`<button data-research-filter="${key}" title="${esc(info.hint)}" class="${ui().researchFilter===key?'active':''}">${esc(info.label)} <span>${counts[key]||0}</span></button>`}
  function currentKey(){return`${ui().researchExchange}|${ui().researchMarket}`}
  function cachedDetail(){return lastDetailKey===currentKey()?lastDetail:null}
  function currentRow(){return findMarket(store.get(),ui().researchExchange,ui().researchMarket)}

  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){root.innerHTML=pageHead('코인','현재가와 등락을 먼저 확인하고, 판단과 근거를 이어서 봅니다.')+loading('시장 데이터를 불러오는 중입니다.');return}
    const ex=ui().researchExchange,summary=marketSummary(state,ex),list=filteredRows(),counts=summary.decisionCounts||decisionCounts(rows());
    ensureSelected(list);
    root.innerHTML=`${pageHead('코인','현재가 · 등락 · 판단을 한 화면에서 확인합니다.',exchangeToggle(ex,'data-research-exchange'))}<section class="research-workspace decision-first-workspace"><aside class="research-master decision-first-master"><div id="researchPulse" class="decision-first-market-pulse"></div><input class="search" data-research-search type="search" value="${esc(ui().researchSearch)}" placeholder="티커·코인명 검색"><div id="researchFilters" class="chip-row research-filter">${['all','buy','wait','watch','risk','holding'].map(k=>filterButton(k,counts)).join('')}</div><div class="market-list-columns" aria-hidden="true"><span>코인</span><span>현재가</span><span>24h</span></div><div id="researchList" class="master-list market-quote-list"></div></aside><section id="researchDetail" class="research-detail decision-first-detail"></section></section><details class="decision-first-extra-research"><summary>추가 연구 · 상장 이력</summary><div id="researchSecondary"></div></details>`;
    renderMasterSummary();
    renderList(list);
    renderSecondaryResearch();
    renderDetail({refreshDetail:true});
  }

  function renderMasterSummary(){
    const box=root?.querySelector('#researchPulse');if(!box)return;
    const summary=marketSummary(store.get(),ui().researchExchange);
    box.innerHTML=`<span><small>시장</small><b>${summary.avgRegime.toFixed(0)}</b></span><span><small>매수 후보</small><b>${summary.buyCandidates}</b></span><span><small>기회 65+</small><b>${summary.opportunityCandidates}</b></span>`;
  }

  function updateFilterState(){
    const summary=marketSummary(store.get(),ui().researchExchange),counts=summary.decisionCounts||decisionCounts(rows());
    root?.querySelectorAll('[data-research-filter]').forEach(button=>{
      const key=button.dataset.researchFilter,info=DECISION_FILTERS[key];
      button.classList.toggle('active',ui().researchFilter===key);
      button.innerHTML=`${esc(info.label)} <span>${counts[key]||0}</span>`;
    });
  }

  function renderSecondaryResearch(){const box=root?.querySelector('#researchSecondary');if(box&&root?.querySelector('.decision-first-extra-research')?.open)box.innerHTML=renderListingHistory(fullPublic(store.get()).listing_history)}

  function renderList(list=filteredRows()){
    const box=root?.querySelector('#researchList');if(!box)return;const selected=ui().researchMarket;
    if(list.length){box.innerHTML=list.slice(0,160).map(r=>{const change=quoteChangePct(r),changeClass=quoteTone(change);return`<button data-research-market="${esc(r.market)}" class="master-row market-quote-row ${r.market===selected?'selected':''}"><span class="market-asset-cell"><b>${esc(r.symbol||r.market)}</b><small>${esc(r.name||stateLabel(r))} · ${esc(decisionLabel(r))}</small></span><span class="market-price-cell"><b>${price(r.price)}</b><small>기회 ${n(r.opportunity_score).toFixed(0)}</small></span><strong class="market-change-cell ${changeClass}">${signedPct(change)}</strong></button>`}).join('');return}
    if(String(ui().researchSearch||'').trim()){box.innerHTML=empty('검색 결과가 없습니다.','검색어를 지우거나 다른 코인을 입력하세요.');return}
    const[title,desc]=decisionEmptyMessage(ui().researchFilter,ui().researchExchange==='upbit'?'업비트':'빗썸');box.innerHTML=empty(title,desc)
  }

  function selectListRow(market){root?.querySelectorAll('[data-research-market]').forEach(button=>button.classList.toggle('selected',button.dataset.researchMarket===market))}
  function tabButton(key,label){return`<button type="button" data-research-detail-tab="${key}" class="${detailTab===key?'active':''}" aria-pressed="${detailTab===key?'true':'false'}">${label}</button>`}

  function summaryHtml(row,holding){
    const holdingHtml=holding?`<section class="decision-first-summary-row" data-research-holding-row><div><span>내 실제 보유</span><small>실제 자산 기준</small></div><div><b data-research-live="holding-value">${money(holding.value_krw)}</b><small data-research-live="holding-pnl" class="${tone(holding.unrealized_pnl_krw)}">${holding.unrealized_pnl_krw>=0?'+':''}${money(holding.unrealized_pnl_krw)} · ${pct(holding.unrealized_pnl_pct)}</small></div><div><small>평균 매수가</small><b data-research-live="holding-avg">${price(holding.avg_price)}</b></div></section>`:'';
    return`<div class="decision-first-summary-stack">${holdingHtml}<section class="decision-first-summary-row"><div><span>PAPER 참고</span><small>실제 주문이 아닌 독립 가상계좌</small></div><div><b data-research-live="paper-return" class="${tone(row.return_pct)}">${pct(row.return_pct)}</b><small>PAPER 수익률</small></div><div><small>완료 거래</small><b data-research-live="paper-trades">${n(row.closed_trades)}회 · ${n(row.win_rate_pct).toFixed(1)}%</b></div></section></div>`;
  }

  function valPct(v){return v===undefined||v===null?'-':pct(v)}
  function planHtml(detail){
    if(!detail)return loading('매매 계획을 불러오는 중입니다.');
    const data=detail.data||{},plan=data.trade_plan||{},signal=data.signal||{},diag=signal.diagnostics||{},memory=Array.isArray(data.market_memory)?data.market_memory:[],latest=memory[memory.length-1]||{};
    return`<section class="decision-first-plan"><header><div><span>다음 행동을 볼 때</span><h3>가격 기준 4개만 먼저 확인</h3></div><small>현재 전략 계산값</small></header><div class="decision-first-plan-grid"><span><small>다음 진입/추가매수</small><b>${price(n(plan.next_add_price)||n(plan.expected_entry_price))}</b></span><span><small>목표가</small><b>${price(plan.target_price)}</b></span><span><small>손절 기준</small><b>${price(plan.hard_stop_price)}</b></span><span><small>분할 진행</small><b>${n(plan.completed_entries)} / ${n(plan.expected_total_entries)}</b></span></div><div class="decision-first-context"><span><small>현재 되돌림</small><b>${pct(diag.pullback_pct)}</b></span><span><small>최근 변동성</small><b>${n(diag.volatility_pct).toFixed(2)}%</b></span><span><small>BTC 흐름</small><b class="${tone(latest.btc_return_pct??diag.btc_return_pct)}">${valPct(latest.btc_return_pct??diag.btc_return_pct)}</b></span><span><small>코인 vs BTC·ETH</small><b class="${tone(latest.asset_vs_majors_pct)}">${valPct(latest.asset_vs_majors_pct)}</b></span></div></section>`;
  }

  function historyHtml(detail){
    if(!detail)return loading('가격과 판단 이력을 불러오는 중입니다.');
    const data=detail.data||{},fills=Array.isArray(data.fills)?data.fills:[],feedback=Array.isArray(data.feedback)?data.feedback:[],eq=Array.isArray(data.equity_history)?data.equity_history:[],memory=Array.isArray(data.market_memory)?data.market_memory:[],range=ui().researchRange||'24h';
    return`<section class="decision-first-history"><div class="history-toolbar"><div><span>가장 먼저</span><h3>가격과 체결 흐름</h3><p>판단 점수와 가상계좌 곡선은 상세 모드에서 추가로 봅니다.</p></div>${rangeControl('data-research-range',range)}</div><div class="history-stack">${priceFillChart(memory,fills,{range})}<div class="decision-first-secondary-chart">${scoreHistoryChart(memory,{range})}</div><div class="decision-first-secondary-chart">${simpleLineChart('가상계좌 자산곡선',eq,'equity_krw',{range,className:'primary',suffix:'원'})}</div></div><div class="detail-columns decision-first-history-records"><section><header><h3>최근 가상체결</h3></header>${fills.length?fills.slice(0,8).map(f=>`<div class="event-row"><b>${f.side==='buy'?'매수':'매도'}</b><span>${price(f.price)}</span><strong class="${tone(f.realized_pnl)}">${f.side==='sell'?`${n(f.realized_pnl)>=0?'+':''}${money(f.realized_pnl)}`:money(f.krw)}</strong><small>${dt(f.ts)}</small></div>`).join(''):'<p class="muted">체결 없음</p>'}</section><section class="decision-first-detail-only"><header><h3>최근 학습 변화</h3></header>${feedback.length?feedback.slice(0,6).map(f=>`<div class="learning-item"><b class="${tone(f.outcome_return_pct)}">${pct(f.outcome_return_pct)}</b><span>${esc(f.note||'학습 기준 조정')}</span><small>${dt(f.ts)}</small></div>`).join(''):'<p class="muted">학습 기록 없음</p>'}</section></div></section>`;
  }

  function renderDetailBody(row=currentRow(),holding=row?findHolding(store.get(),row.market):null,detail=cachedDetail()){
    const body=root?.querySelector('#researchDetailBody');if(!body||!row)return;
    root?.querySelectorAll('[data-research-detail-tab]').forEach(button=>{const active=button.dataset.researchDetailTab===detailTab;button.classList.toggle('active',active);button.setAttribute('aria-pressed',active?'true':'false')});
    if(detailTab==='plan'){body.innerHTML=planHtml(detail);return}
    if(detailTab==='history'){body.innerHTML=historyHtml(detail);return}
    body.innerHTML=summaryHtml(row,holding);
  }

  function patchText(selector,text,className){const node=root?.querySelector(selector);if(!node)return;if(node.textContent!==text)node.textContent=text;if(className!==undefined)node.className=className}
  function patchQuoteLive(row=currentRow(),detail=cachedDetail()){
    if(!row)return;
    const change=quoteChangePct(row,detail),amount=quoteChangeAmount(row,detail),klass=`market-change-value ${quoteTone(change)}`;
    patchText('[data-research-live="price"]',price(row.price));
    patchText('[data-research-live="market-change"]',signedPct(change),klass);
    patchText('[data-research-live="market-change-amount"]',`${signedPrice(amount)} · 24h`);
  }
  function patchDetailLive(){
    const box=root?.querySelector('#researchDetail'),row=currentRow();if(!box||!row)return false;
    const holding=findHolding(store.get(),row.market),holdingFlag=holding?'1':'0';
    if(box.dataset.market!==row.market||box.dataset.exchange!==ui().researchExchange||box.dataset.holding!==holdingFlag)return false;
    patchText('[data-research-live="decision"]',decisionLabel(row));
    patchText('[data-research-live="state"]',row.state_label||'현재 시장과 진입 조건을 함께 반영한 판단입니다.');
    patchText('[data-research-live="entry"]',n(row.entry_score).toFixed(0));
    patchText('[data-research-live="opportunity"]',n(row.opportunity_score).toFixed(0));
    patchText('[data-research-live="regime"]',n(row.regime_score).toFixed(0));
    patchQuoteLive(row,cachedDetail());
    if(detailTab==='summary'){
      patchText('[data-research-live="paper-return"]',pct(row.return_pct),tone(row.return_pct));
      patchText('[data-research-live="paper-trades"]',`${n(row.closed_trades)}회 · ${n(row.win_rate_pct).toFixed(1)}%`);
      if(holding){
        patchText('[data-research-live="holding-value"]',money(holding.value_krw));
        patchText('[data-research-live="holding-pnl"]',`${holding.unrealized_pnl_krw>=0?'+':''}${money(holding.unrealized_pnl_krw)} · ${pct(holding.unrealized_pnl_pct)}`,tone(holding.unrealized_pnl_krw));
        patchText('[data-research-live="holding-avg"]',price(holding.avg_price));
      }
    }
    return true;
  }

  async function renderDetail({refreshDetail=true}={}){
    const box=root?.querySelector('#researchDetail');if(!box)return;
    const ex=ui().researchExchange,market=ui().researchMarket,row=findMarket(store.get(),ex,market);
    if(!row){seq++;lastDetail=null;lastDetailKey='';box.innerHTML=empty('현재 조건에서 선택할 코인이 없습니다.','왼쪽 검색 또는 판단 필터를 변경하세요.');box.dataset.market='';box.dataset.exchange=ex;box.dataset.holding='0';return}
    const holding=findHolding(store.get(),market),key=`${ex}|${market}`,cached=lastDetailKey===key?lastDetail:null,change=quoteChangePct(row,cached),amount=quoteChangeAmount(row,cached);
    box.dataset.market=market;box.dataset.exchange=ex;box.dataset.holding=holding?'1':'0';
    box.innerHTML=`<article class="decision-first-hero market-quote-hero"><div class="price-stack market-quote-primary"><div class="market-quote-identity"><b>${esc(row.symbol||market)}</b><span>${esc(row.name||market)} · ${ex==='upbit'?'업비트':'빗썸'}</span></div><b class="market-current-price" data-research-live="price">${price(row.price)}</b><div class="market-change-line"><strong data-research-live="market-change" class="market-change-value ${quoteTone(change)}">${signedPct(change)}</strong><span data-research-live="market-change-amount">${signedPrice(amount)} · 24h</span></div></div><div class="decision-first-conclusion"><span>현재 판단</span><h3 data-research-live="decision">${esc(decisionLabel(row))}</h3><p data-research-live="state">${esc(row.state_label||'현재 시장과 진입 조건을 함께 반영한 판단입니다.')}</p></div><div class="decision-first-vitals"><span><small>진입</small><b data-research-live="entry">${n(row.entry_score).toFixed(0)}</b></span><span><small>기회</small><b data-research-live="opportunity">${n(row.opportunity_score).toFixed(0)}</b></span><span><small>시장</small><b data-research-live="regime">${n(row.regime_score).toFixed(0)}</b></span></div></article><nav class="decision-first-tabs" aria-label="코인 상세 보기">${tabButton('summary','요약')}${tabButton('plan','매매 계획')}${tabButton('history','이력')}</nav><section id="researchDetailBody" class="decision-first-body"></section>`;
    renderDetailBody(row,holding,cached);
    if(cached&&!refreshDetail)return;
    const requestId=++seq;
    try{
      const detail=await getMarketDetail(ex,market);
      if(requestId!==seq||ui().researchMarket!==market||ui().researchExchange!==ex)return;
      lastDetail=detail;lastDetailKey=key;patchQuoteLive(row,detail);renderDetailBody(row,holding,detail);
    }catch(err){
      if(requestId===seq&&(detailTab==='plan'||detailTab==='history')){
        const body=root?.querySelector('#researchDetailBody');if(body)body.innerHTML=empty('상세 연구 데이터를 불러오지 못했습니다.',err.message)
      }
    }
  }

  function refreshSnapshot(){
    if(!root?.querySelector('.decision-first-workspace')){render();return}
    const previousMarket=ui().researchMarket;
    renderMasterSummary();updateFilterState();
    const list=filteredRows();ensureSelected(list);renderList(list);
    if(root?.querySelector('.decision-first-extra-research')?.open)renderSecondaryResearch();
    if(previousMarket!==ui().researchMarket||!patchDetailLive())renderDetail({refreshDetail:previousMarket!==ui().researchMarket});
  }

  const click=e=>{
    const ex=e.target.closest('[data-research-exchange]');
    if(ex){lastDetail=null;lastDetailKey='';store.setUi({researchExchange:ex.dataset.researchExchange,researchMarket:''},{scope:'research'});render();return}
    const f=e.target.closest('[data-research-filter]');
    if(f){const previous=ui().researchMarket;store.setUi({researchFilter:f.dataset.researchFilter},{scope:'research'});updateFilterState();const list=filteredRows();ensureSelected(list);renderList(list);if(previous!==ui().researchMarket)renderDetail({refreshDetail:true});else patchDetailLive();return}
    const row=e.target.closest('[data-research-market]');
    if(row){const market=row.dataset.researchMarket;if(market===ui().researchMarket)return;store.setUi({researchMarket:market},{scope:'research'});selectListRow(market);renderDetail({refreshDetail:true});return}
    const tab=e.target.closest('[data-research-detail-tab]');
    if(tab){detailTab=tab.dataset.researchDetailTab||'summary';renderDetailBody();return}
    const range=e.target.closest('[data-research-range]');
    if(range&&cachedDetail()){store.setUi({researchRange:range.dataset.researchRange},{scope:'research-range'});renderDetailBody();return}
    const extra=e.target.closest('.decision-first-extra-research>summary');
    if(extra)requestAnimationFrame(()=>{if(root?.querySelector('.decision-first-extra-research')?.open)renderSecondaryResearch()});
  };

  const input=e=>{
    if(e.target.matches('[data-research-search]')){const previous=ui().researchMarket;store.setUi({researchSearch:e.target.value},{scope:'research-search'});const list=filteredRows();ensureSelected(list);renderList(list);if(previous!==ui().researchMarket)renderDetail({refreshDetail:true})}
  };

  return{
    mount(r){root=r;root.addEventListener('click',click);root.addEventListener('input',input);unsub=store.subscribe((_,m)=>{if(m.type==='snapshot')refreshSnapshot()})},
    render,
    destroy(){seq++;lastDetail=null;lastDetailKey='';unsub?.();root?.removeEventListener('click',click);root?.removeEventListener('input',input);root=null}
  };
}
