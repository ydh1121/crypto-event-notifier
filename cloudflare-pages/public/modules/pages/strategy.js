import{strategyLab,strategyRows,strategyEquityHistory,strategyTradeRows,strategyCoinMatrix,strategyCoinRows,paperPortfolioHistory,combinedPaper,paperStats}from'../shared/selectors.js';
import{pageHead,loading,empty,exchangeToggle}from'../shared/components.js';
import{n,money,pct,tone,esc,normalizeCapital}from'../shared/format.js';
import{rangeControl,simpleLineChart}from'../shared/charts.js';
import{scopeBanner}from'../shared/viewer-context.js?v=46';

function candidateLabel(row,criteria){
  const c=row?.candidate||{};
  if(row?.status==='paused'||c.status==='paused')return['일시정지','paused'];
  if(c.status==='candidate')return['후보 통과','candidate'];
  if(c.status==='rejected')return['기준 미충족','rejected'];
  return[`검증 ${n(c.closed_trades||row.closed_trades)}/${n(criteria?.min_closed_trades)||30}`,'warming'];
}

function tradeTime(value){
  const raw=n(value);
  if(!raw)return'-';
  const date=new Date(raw<1e12?raw*1000:raw);
  if(Number.isNaN(date.getTime()))return'-';
  return date.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
}
function tradeSide(value){const side=String(value||'').toLowerCase();return side==='buy'||side==='long'?'매수':side==='sell'||side==='short'?'매도':value||'-'}
function tradePrice(value){const v=n(value);return v?v.toLocaleString('ko-KR',{maximumFractionDigits:v>=100?0:8}):'-'}
function tradeQty(value){const v=n(value);return v?v.toLocaleString('ko-KR',{maximumFractionDigits:8}):'-'}

export function createStrategyPage({store}){
  let root=null,unsub=null,breakdownSearch='',matrixSearch='',overviewDetailTab='summary';
  const ui=()=>store.get().ui;
  const key=r=>String(r?.experiment_id||`${r?.exchange}|${r?.style||r?.label||''}`);
  const currentTab=()=>{const tab=ui().strategyTab||'overview';return tab==='coins'?'overview':tab};
  const readerMode=()=>document.documentElement.dataset.readerMode==='detail'?'detail':'simple';

  function baseRows(){return[...strategyRows(store.get(),ui().strategyExchange)].sort((a,b)=>n(b.return_pct)-n(a.return_pct))}
  function ensureExperiment(rows,field){
    let value=String(ui()[field]||'');
    if(!rows.some(r=>key(r)===value)){
      value=key(rows[0]);
      if(value!==ui()[field])store.setUi({[field]:value},{scope:`strategy-${field}`});
    }
    return rows.find(r=>key(r)===value)||rows[0];
  }
  function ensureOverviewSelected(rows){return ensureExperiment(rows,'strategyOverviewExperiment')}
  function normalizedDetailTab(){
    if(readerMode()==='simple'&&overviewDetailTab!=='summary')overviewDetailTab='summary';
    return overviewDetailTab;
  }

  function overviewKpis(rows,criteria,ex){
    const states=rows.map(row=>candidateLabel(row,criteria)[1]);
    const candidate=states.filter(x=>x==='candidate').length;
    const warming=states.filter(x=>x==='warming').length;
    const stopped=states.filter(x=>x==='rejected'||x==='paused').length;
    return`<section class="strategy-overview-summary"><b>${ex==='upbit'?'업비트':'빗썸'} 시험 방법 ${rows.length}개</b><span>후보 통과 ${candidate}</span><span>검증 중 ${warming}</span><span>미충족 · 중지 ${stopped}</span></section><p class="strategy-sort-note">수익률 높은 순으로 정렬했습니다. 추천 순위가 아니라 비교를 위한 순서입니다.</p>`;
  }

  function detailTabsHtml(){
    const tab=normalizedDetailTab();
    const item=(value,label)=>`<button type="button" data-strategy-v5-tab="${value}" class="${tab===value?'active':''}" aria-selected="${tab===value?'true':'false'}">${label}</button>`;
    return`<nav class="strategy-v5-detail-tabs" aria-label="선택한 매매방법 보기">${item('summary','요약')}${item('coins','코인별 성과')}${item('trades','가상매매 내역')}${item('evidence','검증 흐름')}<button type="button" class="strategy-v5-back" data-strategy-v5-back>전략 목록</button></nav>`;
  }

  function strategyRailRowsHtml(rows,criteria,selectedKey){
    return rows.map(r=>{
      const[cLabel]=candidateLabel(r,criteria),selected=key(r)===selectedKey;
      return`<button class="strategy-row strategy-v5-strategy-item ${selected?'selected':''}" data-strategy-key="${esc(key(r))}" aria-pressed="${selected?'true':'false'}" aria-current="${selected?'true':'false'}"><span class="strategy-v5-item-copy"><b>${esc(r.label||r.style)}</b><small>${esc(r.description||'설명 없음')}</small></span><span class="strategy-v5-item-facts"><span><small>수익률</small><b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b></span><span><small>최대 하락</small><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></span><em>${esc(cLabel)}</em></span></button>`;
    }).join('');
  }

  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){root.innerHTML=pageHead('전략','여러 가상 매매방법의 성적과 실제 체결 근거를 비교합니다.')+loading('시험 결과를 불러오는 중입니다.');return}
    const ex=ui().strategyExchange,data=strategyLab(state),criteria=data.candidate_criteria||{},rows=baseRows();
    if(!rows.length){root.innerHTML=pageHead('전략','여러 가상 매매방법의 성적과 실제 체결 근거를 비교합니다.',exchangeToggle(ex,'data-strategy-exchange'))+scopeBanner('strategy')+empty('시험 결과를 기다리는 중입니다.');return}
    const tab=currentTab();
    root.innerHTML=`${pageHead('전략','성과 → 코인별 결과 → 실제 가상 체결 → 검증 흐름 순서로 확인합니다.',exchangeToggle(ex,'data-strategy-exchange'))}<p class="strategy-context-line">각 방법은 별도 가상계좌로 시험합니다. 현재 실행 중인 모의투자 결과와는 분리되어 있습니다.</p><nav class="subnav strategy-subnav"><button data-strategy-tab="overview" class="${tab==='overview'?'active':''}">매매방법별 비교</button><button data-strategy-tab="matrix" class="${tab==='matrix'?'active':''}">코인별로 비교</button><button data-strategy-tab="paper" class="${tab==='paper'?'active':''}">현재 실행 성적</button></nav><section id="strategyBody"></section>`;
    renderTab(rows,criteria,ex);
  }

  function renderTab(rows,criteria,ex){
    const tab=currentTab();
    if(tab==='matrix')renderMatrix();
    else if(tab==='paper')renderPaperBenchmark();
    else renderOverview(rows,criteria,ex);
  }

  function renderOverview(rows,criteria,ex){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const chosen=ensureOverviewSelected(rows),selectedKey=key(chosen);
    box.innerHTML=`${overviewKpis(rows,criteria,ex)}<section class="strategy-workspace" data-strategy-workspace-v5="ready"><div class="strategy-table"><div class="strategy-v5-rail-head"><span><b>시험 중인 매매방법</b><small>방법을 고르면 오른쪽 근거가 같은 자리에서 바뀝니다.</small></span><em>수익률 순</em></div>${strategyRailRowsHtml(rows,criteria,selectedKey)}</div><section class="strategy-v5-detail-shell" aria-label="선택한 매매방법 상세">${detailTabsHtml()}<div class="strategy-v5-detail-panels"><aside id="strategyDetail" class="strategy-detail strategy-v5-panel" data-strategy-v5-panel="summary"></aside><section id="strategyBreakdown" class="strategy-v5-panel" data-strategy-v5-panel="coins"></section><section id="strategyTrades" class="strategy-v5-panel strategy-trades" data-strategy-v5-panel="trades"></section><section id="strategyEvidence" class="strategy-v5-panel" data-strategy-v5-panel="evidence"></section></div></section></section>`;
    renderOverviewDetails(chosen,criteria);
  }

  function setSelectedRailItem(selectedKey){
    root?.querySelectorAll('[data-strategy-key]').forEach(row=>{
      const selected=row.dataset.strategyKey===selectedKey;
      row.classList.toggle('selected',selected);
      row.setAttribute('aria-pressed',selected?'true':'false');
      row.setAttribute('aria-current',selected?'true':'false');
    });
  }

  function applyOverviewDetailTab(){
    const shell=root?.querySelector('.strategy-v5-detail-shell');
    if(!shell)return;
    const tab=normalizedDetailTab();
    shell.querySelectorAll('[data-strategy-v5-tab]').forEach(button=>{
      const active=button.dataset.strategyV5Tab===tab;
      button.classList.toggle('active',active);
      button.setAttribute('aria-selected',active?'true':'false');
    });
    shell.querySelectorAll('[data-strategy-v5-panel]').forEach(panel=>{panel.hidden=panel.dataset.strategyV5Panel!==tab});
  }

  function renderOverviewDetails(chosen,criteria){
    renderSummary(chosen,criteria);
    renderBreakdown(chosen);
    renderTrades(chosen);
    renderEvidence(chosen,criteria);
    applyOverviewDetailTab();
  }

  function renderSummary(r,criteria){
    const box=root?.querySelector('#strategyDetail');
    if(!box||!r)return;
    const c=r.candidate||{},[label,status]=candidateLabel(r,criteria),normalized=normalizeCapital(r.initial_capital_krw,r.total_equity_krw,10000000,r.return_pct);
    box.innerHTML=`<header><span>지금 선택한 매매방법</span><h3>${esc(r.label||r.style)}</h3><p>${esc(r.description||'설명 없음')}</p><em class="status-badge ${status}">${esc(label)}</em></header><div class="strategy-detail-kpis"><span><small>전체 수익률</small><b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b></span><span><small>1,000만원 기준 평가액</small><b>${money(normalized.equity)}</b></span><span><small>최대 하락폭</small><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></span><span><small>번 돈 ÷ 잃은 돈</small><b>${n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2)}</b></span><span><small>완료 거래</small><b>${n(r.closed_trades)}회</b></span><span><small>승률</small><b>${n(r.win_rate_pct).toFixed(1)}%</b></span><span><small>거래당 평균 결과</small><b>${pct(r.expectancy_pct)}</b></span><span><small>수익 코인 비율</small><b>${pct(n(c.profitable_market_share)*100)}</b></span></div><p class="strategy-detail-next">성과가 왜 나왔는지는 ‘가상매매 내역’에서 체결 단위로 확인하고, 통계적 흐름은 ‘검증 흐름’에서 확인합니다.</p>`;
  }

  function breakdownItems(chosen){
    const matrix=strategyCoinMatrix(store.get(),ui().strategyExchange),q=breakdownSearch.trim().toLowerCase(),items=[];
    for(const item of matrix){
      if(q&&!String(item.market||'').toLowerCase().includes(q))continue;
      const raw=(item.rows||[]).find(v=>String(v?.[0]||'')===chosen.experiment_id);
      if(!raw)continue;
      items.push({market:item.market,return_pct:n(raw[2]),realized_pnl:n(raw[3]),unrealized_pnl:n(raw[4]),max_drawdown_pct:n(raw[5]),closed_trades:n(raw[6]),wins:n(raw[7]),active:Boolean(raw[8])});
    }
    const sorters={return_desc:(a,b)=>n(b.return_pct)-n(a.return_pct),return_asc:(a,b)=>n(a.return_pct)-n(b.return_pct),trades_desc:(a,b)=>n(b.closed_trades)-n(a.closed_trades),win_desc:(a,b)=>(b.closed_trades?n(b.wins)/n(b.closed_trades):0)-(a.closed_trades?n(a.wins)/n(a.closed_trades):0),drawdown_asc:(a,b)=>n(a.max_drawdown_pct)-n(b.max_drawdown_pct)};
    items.sort(sorters[ui().strategyCoinSort]||sorters.return_desc);
    return items;
  }

  function breakdownRowsHtml(items){return items.map(r=>`<div class="strategy-coin-row"><span><b>${esc(String(r.market).replace(/^KRW-/,''))}</b><small>${esc(r.market)}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회</span><span>${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('조건에 맞는 코인 성과가 없습니다.')}
  function breakdownStatsHtml(items){const profitable=items.filter(x=>n(x.return_pct)>0).length,loss=items.filter(x=>n(x.return_pct)<0).length,active=items.filter(x=>x.active).length,trades=items.reduce((sum,x)=>sum+n(x.closed_trades),0);return`<span><small>성과가 있는 코인</small><b>${items.length}개</b></span><span><small>수익 코인</small><b>${profitable}개</b></span><span><small>손실 코인</small><b>${loss}개</b></span><span><small>완료 거래</small><b>${trades}회</b></span><span><small>현재 가상 보유</small><b>${active}개</b></span>`}

  function renderBreakdown(chosen){
    const box=root?.querySelector('#strategyBreakdown');
    if(!box||!chosen)return;
    const items=breakdownItems(chosen),sort=ui().strategyCoinSort||'return_desc';
    box.innerHTML=`<section class="strategy-breakdown" data-strategy-coin-experiment="${esc(key(chosen))}"><header class="strategy-breakdown-head"><div><span>선택한 매매방법의 코인별 성과</span><h3>${esc(chosen.label||chosen.style)}</h3><p>어느 코인에서 성과와 손실이 발생했는지 먼저 분해합니다.</p></div><div class="strategy-breakdown-controls"><label><span>정렬</span><select data-strategy-coin-sort><option value="return_desc" ${sort==='return_desc'?'selected':''}>수익률 높은 순</option><option value="return_asc" ${sort==='return_asc'?'selected':''}>손실 큰 순</option><option value="trades_desc" ${sort==='trades_desc'?'selected':''}>거래 많은 순</option><option value="win_desc" ${sort==='win_desc'?'selected':''}>승률 높은 순</option><option value="drawdown_asc" ${sort==='drawdown_asc'?'selected':''}>하락폭 큰 순</option></select></label><label><span>코인 검색</span><input data-strategy-breakdown-search type="search" value="${esc(breakdownSearch)}" placeholder="예: BTC"></label></div></header><div id="strategyBreakdownStats" class="strategy-breakdown-stats">${breakdownStatsHtml(items)}</div><div class="strategy-coin-table strategy-breakdown-table"><div class="strategy-coin-row columns"><span>코인</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>하락폭</span><span>완료 거래</span><span>승률</span><span>상태</span></div><div id="strategyBreakdownRows">${breakdownRowsHtml(items)}</div></div></section>`;
  }
  function refreshBreakdown(chosen){const rowsBox=root?.querySelector('#strategyBreakdownRows'),statsBox=root?.querySelector('#strategyBreakdownStats');if(!chosen||!rowsBox||!statsBox)return;const items=breakdownItems(chosen);rowsBox.innerHTML=breakdownRowsHtml(items);statsBox.innerHTML=breakdownStatsHtml(items)}

  function renderTrades(r){
    const box=root?.querySelector('#strategyTrades');
    if(!box||!r)return;
    const rows=strategyTradeRows(store.get(),r.experiment_id);
    const body=rows.length?`<div class="strategy-trade-table"><div class="strategy-trade-row columns"><span>시간</span><span>코인</span><span>구분</span><span>체결가</span><span>수량</span><span>실현손익</span></div>${rows.map(row=>`<div class="strategy-trade-row"><span>${esc(tradeTime(row.ts))}</span><span><b>${esc(String(row.market||'-').replace(/^KRW-/,''))}</b></span><span>${esc(tradeSide(row.side))}</span><span>${esc(tradePrice(row.price))}</span><span>${esc(tradeQty(row.qty))}</span><span class="${tone(row.pnl_krw)}">${n(row.pnl_krw)>=0?'+':''}${money(row.pnl_krw)}</span></div>`).join('')}</div>`:`<div class="strategy-trade-empty"><b>이 전략의 체결 원장이 아직 Snapshot에 제공되지 않습니다.</b><p>집계 수익률이나 코인별 통계로 가상의 거래를 만들어 표시하지 않습니다. 생산부가 <code>strategy_lab.strategy_trades</code>에 experiment_id별 체결을 제공하면 이 탭에 자동으로 표시됩니다.</p></div>`;
    box.innerHTML=`<section class="strategy-trades"><header class="strategy-breakdown-head"><div><span>선택 전략의 가상매매 근거</span><h3>${esc(r.label||r.style)} · 가상매매 내역</h3><p>전체 모의투자 기록이 아니라 이 실험 ID가 실제로 만든 체결만 보여줍니다.</p></div><small>시험 번호 ${esc(r.experiment_id||'-')}</small></header>${body}</section>`;
  }

  function renderEvidence(r,criteria){
    const box=root?.querySelector('#strategyEvidence');
    if(!box||!r)return;
    const history=strategyEquityHistory(store.get(),r.experiment_id),range=ui().strategyRange||'24h';
    box.innerHTML=`<section class="strategy-evidence"><div class="history-toolbar"><div><h3>${esc(r.label||r.style)} 검증 흐름</h3><p>자산 변화와 하락폭, 후보 판정 기준을 확인합니다.</p></div>${rangeControl('data-strategy-range',range)}</div><div class="strategy-history-grid">${simpleLineChart('전략 자산곡선',history,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('최대 하락폭 흐름',history,'drawdown_pct',{range,className:'sell',suffix:'%'})}</div><details class="gate-panel"><summary>검증 기준 자세히 보기</summary><div><span>완료 거래 ≥ ${n(criteria.min_closed_trades)||30}</span><span>거래시장 ≥ ${n(criteria.min_traded_markets)||5}</span><span>수익시장 ≥ ${n(criteria.min_profitable_market_share)*100||50}%</span><span>손익집중 ≤ ${n(criteria.max_pnl_concentration_share)*100||60}%</span><span>하락폭 ≥ ${n(criteria.max_drawdown_floor_pct)||-12}%</span><span>거래당 평균 결과 &gt; 0</span><span>번 돈 ÷ 잃은 돈 ≥ ${n(criteria.min_profit_factor)||1.1}</span><span>총수익 &gt; 0</span></div><p>자동으로 실행 방법을 바꾸지 않습니다. 충분히 검증된 뒤 별도 결정합니다.</p></details></section>`;
  }

  function matrixMarkets(){let list=strategyCoinMatrix(store.get(),ui().strategyExchange),q=matrixSearch.trim().toLowerCase();if(q)list=list.filter(x=>String(x.market||'').toLowerCase().includes(q));return list}
  function ensureMatrixMarket(list){let market=ui().strategyCoinMarket;if(!list.some(x=>x.market===market))market=list[0]?.market||'';if(market!==ui().strategyCoinMarket)store.setUi({strategyCoinMarket:market},{scope:'strategy'});return market}
  function renderMatrix(){
    const box=root?.querySelector('#strategyBody');if(!box)return;
    const markets=matrixMarkets(),market=ensureMatrixMarket(markets),compare=strategyCoinRows(store.get(),ui().strategyExchange,market).sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    box.innerHTML=`<section class="strategy-matrix-toolbar"><div><h3>코인별 매매방법 비교</h3><p>코인을 먼저 고른 뒤 시험 중인 방법을 같은 표에서 비교합니다.</p></div><input data-strategy-matrix-search type="search" value="${esc(matrixSearch)}" placeholder="코인 검색"></section><section class="strategy-matrix-workspace"><aside class="strategy-market-list">${markets.map(x=>`<button data-strategy-market="${esc(x.market)}" class="${x.market===market?'selected':''}"><b>${esc(String(x.market).replace(/^KRW-/,''))}</b><small>${esc(x.market)}</small></button>`).join('')||empty('비교할 코인이 없습니다.')}</aside><div class="strategy-matrix-detail"><header><div><span>선택 코인</span><h3>${esc(String(market||'').replace(/^KRW-/,''))}</h3></div><small>${ui().strategyExchange==='upbit'?'업비트':'빗썸'} · 시험 결과</small></header><div class="strategy-matrix-row columns"><span>매매방법</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>하락폭</span><span>거래/승률</span><span>상태</span></div>${compare.map(r=>`<div class="strategy-matrix-row"><span><b>${esc(r.label||r.style)}</b><small>시험 번호 ${esc(r.experiment_id||'-')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회 · ${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('이 코인의 시험 결과가 아직 없습니다.')}</div></section>`;
  }

  function renderPaperBenchmark(){
    const box=root?.querySelector('#strategyBody');if(!box)return;
    const state=store.get(),cp=combinedPaper(state),normalized=normalizeCapital(cp.start,cp.equity,10000000,cp.start?cp.pnl/cp.start*100:0),b=paperStats(state,'bithumb'),u=paperStats(state,'upbit'),range=ui().strategyRange||'24h',combined=paperPortfolioHistory(state,'combined'),bh=paperPortfolioHistory(state,'bithumb'),uh=paperPortfolioHistory(state,'upbit'),latest=combined[combined.length-1]||{};
    box.innerHTML=`<section class="strategy-paper-head"><div><span>현재 실행 중인 모의투자</span><h3>현재 실행 방식의 성적</h3><p>시험 전략과 별개로 실제 PAPER 실행 기준선만 보여줍니다.</p></div>${rangeControl('data-strategy-range',range)}</section><section class="strategy-paper-kpis"><span><small>1,000만원 기준 평가액</small><b>${money(normalized.equity)}</b></span><span><small>1,000만원 기준 증감</small><b class="${tone(normalized.pnl)}">${normalized.pnl>=0?'+':''}${money(normalized.pnl)}</b></span><span><small>현재 하락폭</small><b class="${tone(latest.drawdown_pct)}">${pct(latest.drawdown_pct)}</b></span><span><small>현재 보유</small><b>${n(cp.active)}개</b></span><span><small>빗썸 수익률</small><b class="${tone(b.returnPct)}">${pct(b.returnPct)}</b></span><span><small>업비트 수익률</small><b class="${tone(u.returnPct)}">${pct(u.returnPct)}</b></span></section><section class="strategy-paper-charts">${simpleLineChart('통합 가상계좌 자산곡선',combined,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('통합 가상계좌 하락폭',combined,'drawdown_pct',{range,className:'sell',suffix:'%'})}${simpleLineChart('빗썸 가상계좌 수익률',bh,'return_pct',{range,className:'regime',suffix:'%'})}${simpleLineChart('업비트 가상계좌 수익률',uh,'return_pct',{range,className:'entry',suffix:'%'})}</section>`;
  }

  const click=e=>{
    const ex=e.target.closest('[data-strategy-exchange]');
    if(ex){store.setUi({strategyExchange:ex.dataset.strategyExchange,strategyCoinMarket:'',strategyOverviewExperiment:'',strategyCoinExperiment:''},{scope:'strategy'});breakdownSearch='';matrixSearch='';overviewDetailTab='summary';render();return}
    const tab=e.target.closest('[data-strategy-tab]');
    if(tab){store.setUi({strategyTab:tab.dataset.strategyTab},{scope:'strategy'});render();return}
    const detailTab=e.target.closest('[data-strategy-v5-tab]');
    if(detailTab){
      const value=String(detailTab.dataset.strategyV5Tab||'');
      if(!['summary','coins','trades','evidence'].includes(value))return;
      overviewDetailTab=value;
      if(value!=='summary'&&readerMode()==='simple'){
        const detailMode=document.querySelector('[data-reader-mode="detail"]');
        if(detailMode instanceof HTMLElement){detailMode.click();return}
      }
      applyOverviewDetailTab();
      return;
    }
    const back=e.target.closest('[data-strategy-v5-back]');
    if(back){root?.querySelector('.strategy-table')?.scrollIntoView({block:'start',behavior:'auto'});return}
    const row=e.target.closest('[data-strategy-key]');
    if(row){
      store.setUi({strategyOverviewExperiment:row.dataset.strategyKey,strategyCoinExperiment:row.dataset.strategyKey},{scope:'strategy-overview'});
      const chosen=ensureOverviewSelected(baseRows()),data=strategyLab(store.get()),criteria=data.candidate_criteria||{};
      setSelectedRailItem(key(chosen));
      renderOverviewDetails(chosen,criteria);
      return;
    }
    const range=e.target.closest('[data-strategy-range]');
    if(range){store.setUi({strategyRange:range.dataset.strategyRange},{scope:'strategy'});if(currentTab()==='paper')renderPaperBenchmark();else{const chosen=ensureOverviewSelected(baseRows()),data=strategyLab(store.get()),criteria=data.candidate_criteria||{};renderEvidence(chosen,criteria);applyOverviewDetailTab()}return}
    const market=e.target.closest('[data-strategy-market]');
    if(market){store.setUi({strategyCoinMarket:market.dataset.strategyMarket},{scope:'strategy'});renderMatrix()}
  };
  const input=e=>{
    if(e.target.matches('[data-strategy-breakdown-search]')){breakdownSearch=e.target.value;refreshBreakdown(ensureOverviewSelected(baseRows()));return}
    if(e.target.matches('[data-strategy-matrix-search]')){matrixSearch=e.target.value;renderMatrix()}
  };
  const change=e=>{if(e.target.matches('[data-strategy-coin-sort]')){store.setUi({strategyCoinSort:e.target.value},{scope:'strategy-breakdown'});refreshBreakdown(ensureOverviewSelected(baseRows()))}};

  return{
    mount(r){root=r;root.addEventListener('click',click);root.addEventListener('input',input);root.addEventListener('change',change);unsub=store.subscribe((_,m)=>{if(m.type==='snapshot')render()})},
    render,
    destroy(){unsub?.();root?.removeEventListener('click',click);root?.removeEventListener('input',input);root?.removeEventListener('change',change);root=null}
  };
}
