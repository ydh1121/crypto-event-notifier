import{strategyLab,strategyRows,strategyEquityHistory,strategyCoinMatrix,strategyCoinRows,paperPortfolioHistory,combinedPaper,paperStats}from'../shared/selectors.js';
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

export function createStrategyPage({store}){
  let root=null,unsub=null,breakdownSearch='',matrixSearch='';
  const ui=()=>store.get().ui;
  const key=r=>String(r?.experiment_id||`${r?.exchange}|${r?.style||r?.label||''}`);
  const currentTab=()=>{const tab=ui().strategyTab||'overview';return tab==='coins'?'overview':tab};

  function baseRows(){
    return[...strategyRows(store.get(),ui().strategyExchange)].sort((a,b)=>n(b.return_pct)-n(a.return_pct));
  }

  function ensureExperiment(rows,field){
    let value=String(ui()[field]||'');
    if(!rows.some(r=>key(r)===value)){
      value=key(rows[0]);
      if(value!==ui()[field])store.setUi({[field]:value},{scope:`strategy-${field}`});
    }
    return rows.find(r=>key(r)===value)||rows[0];
  }
  function ensureOverviewSelected(rows){return ensureExperiment(rows,'strategyOverviewExperiment')}

  function overviewKpis(rows,criteria,ex){
    const states=rows.map(row=>candidateLabel(row,criteria)[1]);
    const candidate=states.filter(x=>x==='candidate').length;
    const warming=states.filter(x=>x==='warming').length;
    const stopped=states.filter(x=>x==='rejected'||x==='paused').length;
    return`<section class="strategy-overview-summary"><b>${ex==='upbit'?'업비트':'빗썸'} 시험 전략 ${rows.length}개</b><span>후보 통과 ${candidate}</span><span>검증 중 ${warming}</span><span>미충족 · 중지 ${stopped}</span></section><p class="strategy-sort-note">현재 정렬: 수익률 높은 순 · 추천 순위가 아니라 비교를 위한 정렬입니다.</p>`;
  }

  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){
      root.innerHTML=pageHead('전략 비교','여러 가상 전략의 성적을 비교합니다.')+loading('전략 데이터를 불러오는 중입니다.');
      return;
    }
    const ex=ui().strategyExchange,data=strategyLab(state),criteria=data.candidate_criteria||{},rows=baseRows();
    if(!rows.length){
      root.innerHTML=pageHead('전략 비교','여러 가상 전략의 성적을 비교합니다.',exchangeToggle(ex,'data-strategy-exchange'))+scopeBanner('strategy')+empty('전략 시험 데이터를 기다리는 중입니다.');
      return;
    }
    const tab=currentTab();
    root.innerHTML=`${pageHead('전략 비교','전략을 고르면 그 전략의 전체 코인 성적까지 한 흐름으로 확인합니다.',exchangeToggle(ex,'data-strategy-exchange'))}<p class="strategy-context-line">각 전략은 별도의 가상계좌로 시험합니다. 현재 실행 가상매매와는 별도 결과입니다.</p><nav class="subnav strategy-subnav"><button data-strategy-tab="overview" class="${tab==='overview'?'active':''}">전략별 비교</button><button data-strategy-tab="matrix" class="${tab==='matrix'?'active':''}">코인에서 전략 비교</button><button data-strategy-tab="paper" class="${tab==='paper'?'active':''}">현재 실행 성적</button></nav><section id="strategyBody"></section>`;
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
    box.innerHTML=`${overviewKpis(rows,criteria,ex)}<section class="strategy-workspace"><div class="strategy-table"><div class="strategy-row columns"><span>전략</span><span>수익률</span><span>최대 하락</span><span>손익비</span><span>거래</span><span>승률</span><span>검증</span></div>${rows.map(r=>{
      const[cLabel,cStatus]=candidateLabel(r,criteria),pf=n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2);
      return`<button class="strategy-row ${key(r)===selectedKey?'selected':''}" data-strategy-key="${esc(key(r))}" aria-pressed="${key(r)===selectedKey?'true':'false'}"><span><b>${esc(r.label||r.style)}</b><small>${esc(r.description||'설명 없음')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${pf}</span><span>${n(r.closed_trades)}회</span><span>${n(r.win_rate_pct).toFixed(1)}%</span><span><em class="status-badge ${cStatus}">${esc(cLabel)}</em><small>검증 ${n(r.candidate?.passed_gates)}/${n(r.candidate?.total_gates)}</small></span></button>`;
    }).join('')}</div><aside id="strategyDetail" class="strategy-detail"></aside></section><section id="strategyBreakdown"></section><section id="strategyEvidence"></section>`;
    renderSummary(chosen,criteria);
    renderBreakdown(chosen);
    renderEvidence(chosen,criteria);
  }

  function renderSummary(r,criteria){
    const box=root?.querySelector('#strategyDetail');
    if(!box||!r)return;
    const c=r.candidate||{},[label,status]=candidateLabel(r,criteria),normalized=normalizeCapital(r.initial_capital_krw,r.total_equity_krw,10000000,r.return_pct);
    box.innerHTML=`<header><span>지금 선택한 전략</span><h3>${esc(r.label||r.style)}</h3><p>${esc(r.description||'전략 설명 없음')}</p><em class="status-badge ${status}">${esc(label)}</em></header><div class="strategy-detail-kpis"><span><small>전체 수익률</small><b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b></span><span><small>1,000만원 기준 평가액</small><b>${money(normalized.equity)}</b></span><span><small>최대 하락폭</small><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></span><span><small>번 돈 ÷ 잃은 돈</small><b>${n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2)}</b></span><span><small>완료 거래</small><b>${n(r.closed_trades)}회</b></span><span><small>승률</small><b>${n(r.win_rate_pct).toFixed(1)}%</b></span><span><small>거래당 평균 결과</small><b>${pct(r.expectancy_pct)}</b></span><span><small>수익 종목 비율</small><b>${pct(n(c.profitable_market_share)*100)}</b></span></div><p class="strategy-detail-next">1,000만원을 같은 수익률로 운용했다고 가정한 환산값입니다. 아래에서 이 전략이 각 코인에서 얼마나 벌고 잃었는지 확인할 수 있습니다.</p>`;
  }

  function breakdownItems(chosen){
    const matrix=strategyCoinMatrix(store.get(),ui().strategyExchange),q=breakdownSearch.trim().toLowerCase(),items=[];
    for(const item of matrix){
      if(q&&!String(item.market||'').toLowerCase().includes(q))continue;
      const raw=(item.rows||[]).find(v=>String(v?.[0]||'')===chosen.experiment_id);
      if(!raw)continue;
      items.push({market:item.market,return_pct:n(raw[2]),realized_pnl:n(raw[3]),unrealized_pnl:n(raw[4]),max_drawdown_pct:n(raw[5]),closed_trades:n(raw[6]),wins:n(raw[7]),active:Boolean(raw[8])});
    }
    const sorters={
      return_desc:(a,b)=>n(b.return_pct)-n(a.return_pct),
      return_asc:(a,b)=>n(a.return_pct)-n(b.return_pct),
      trades_desc:(a,b)=>n(b.closed_trades)-n(a.closed_trades),
      win_desc:(a,b)=>(b.closed_trades?n(b.wins)/n(b.closed_trades):0)-(a.closed_trades?n(a.wins)/n(a.closed_trades):0),
      drawdown_asc:(a,b)=>n(a.max_drawdown_pct)-n(b.max_drawdown_pct)
    };
    items.sort(sorters[ui().strategyCoinSort]||sorters.return_desc);
    return items;
  }

  function breakdownRowsHtml(items){
    return items.map(r=>`<div class="strategy-coin-row"><span><b>${esc(String(r.market).replace(/^KRW-/,''))}</b><small>${esc(r.market)}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회</span><span>${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('조건에 맞는 코인 성과가 없습니다.');
  }

  function breakdownStatsHtml(items){
    const profitable=items.filter(x=>n(x.return_pct)>0).length,loss=items.filter(x=>n(x.return_pct)<0).length,active=items.filter(x=>x.active).length,trades=items.reduce((sum,x)=>sum+n(x.closed_trades),0);
    return`<span><small>성과가 있는 코인</small><b>${items.length}개</b></span><span><small>수익 코인</small><b>${profitable}개</b></span><span><small>손실 코인</small><b>${loss}개</b></span><span><small>완료 거래</small><b>${trades}회</b></span><span><small>현재 가상 보유</small><b>${active}개</b></span>`;
  }

  function renderBreakdown(chosen){
    const box=root?.querySelector('#strategyBreakdown');
    if(!box||!chosen)return;
    const items=breakdownItems(chosen),sort=ui().strategyCoinSort||'return_desc';
    box.innerHTML=`<section class="strategy-breakdown" data-strategy-coin-experiment="${esc(key(chosen))}"><header class="strategy-breakdown-head"><div><span>선택 전략 전체 코인별 성과</span><h3>${esc(chosen.label||chosen.style)}</h3><p>전략을 선택하면 이 영역도 같은 전략으로 즉시 바뀝니다. 별도 전략 선택은 필요하지 않습니다.</p></div><div class="strategy-breakdown-controls"><label><span>정렬</span><select data-strategy-coin-sort><option value="return_desc" ${sort==='return_desc'?'selected':''}>수익률 높은 순</option><option value="return_asc" ${sort==='return_asc'?'selected':''}>손실 큰 순</option><option value="trades_desc" ${sort==='trades_desc'?'selected':''}>거래 많은 순</option><option value="win_desc" ${sort==='win_desc'?'selected':''}>승률 높은 순</option><option value="drawdown_asc" ${sort==='drawdown_asc'?'selected':''}>하락폭 큰 순</option></select></label><label><span>코인 검색</span><input data-strategy-breakdown-search type="search" value="${esc(breakdownSearch)}" placeholder="예: BTC"></label></div></header><div id="strategyBreakdownStats" class="strategy-breakdown-stats">${breakdownStatsHtml(items)}</div><div class="strategy-coin-table strategy-breakdown-table"><div class="strategy-coin-row columns"><span>코인</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>하락폭</span><span>완료 거래</span><span>승률</span><span>상태</span></div><div id="strategyBreakdownRows">${breakdownRowsHtml(items)}</div></div></section>`;
  }

  function refreshBreakdown(chosen){
    const rowsBox=root?.querySelector('#strategyBreakdownRows'),statsBox=root?.querySelector('#strategyBreakdownStats');
    if(!chosen||!rowsBox||!statsBox)return;
    const items=breakdownItems(chosen);
    rowsBox.innerHTML=breakdownRowsHtml(items);
    statsBox.innerHTML=breakdownStatsHtml(items);
  }

  function renderEvidence(r,criteria){
    const box=root?.querySelector('#strategyEvidence');
    if(!box||!r)return;
    const history=strategyEquityHistory(store.get(),r.experiment_id),range=ui().strategyRange||'24h';
    box.innerHTML=`<section class="strategy-evidence"><div class="history-toolbar"><div><h3>${esc(r.label||r.style)} 성적 흐름</h3><p>전체 코인 내역을 본 뒤 필요할 때 자산곡선과 검증 기준을 확인합니다.</p></div>${rangeControl('data-strategy-range',range)}</div><div class="strategy-history-grid">${simpleLineChart('전략 자산곡선',history,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('최대 하락폭 흐름',history,'drawdown_pct',{range,className:'sell',suffix:'%'})}</div><details class="gate-panel"><summary>검증 기준 자세히 보기</summary><div><span>완료 거래 ≥ ${n(criteria.min_closed_trades)||30}</span><span>거래시장 ≥ ${n(criteria.min_traded_markets)||5}</span><span>수익시장 ≥ ${n(criteria.min_profitable_market_share)*100||50}%</span><span>손익집중 ≤ ${n(criteria.max_pnl_concentration_share)*100||60}%</span><span>하락폭 ≥ ${n(criteria.max_drawdown_floor_pct)||-12}%</span><span>거래당 평균 결과 &gt; 0</span><span>번 돈 ÷ 잃은 돈 ≥ ${n(criteria.min_profit_factor)||1.1}</span><span>총수익 &gt; 0</span></div><p>자동으로 실행 전략을 바꾸지 않습니다. 충분히 검증된 뒤 별도 결정합니다.</p></details></section>`;
  }

  function matrixMarkets(){
    let list=strategyCoinMatrix(store.get(),ui().strategyExchange),q=matrixSearch.trim().toLowerCase();
    if(q)list=list.filter(x=>String(x.market||'').toLowerCase().includes(q));
    return list;
  }

  function ensureMatrixMarket(list){
    let market=ui().strategyCoinMarket;
    if(!list.some(x=>x.market===market))market=list[0]?.market||'';
    if(market!==ui().strategyCoinMarket)store.setUi({strategyCoinMarket:market},{scope:'strategy'});
    return market;
  }

  function renderMatrix(){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const markets=matrixMarkets(),market=ensureMatrixMarket(markets),compare=strategyCoinRows(store.get(),ui().strategyExchange,market).sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    box.innerHTML=`<section class="strategy-matrix-toolbar"><div><h3>코인 × 전략 비교</h3><p>코인을 먼저 고른 뒤 모든 시험 전략을 같은 표에서 비교합니다. 위 전략 선택과는 별개 작업입니다.</p></div><input data-strategy-matrix-search type="search" value="${esc(matrixSearch)}" placeholder="코인 검색"></section><section class="strategy-matrix-workspace"><aside class="strategy-market-list">${markets.map(x=>`<button data-strategy-market="${esc(x.market)}" class="${x.market===market?'selected':''}"><b>${esc(String(x.market).replace(/^KRW-/,''))}</b><small>${esc(x.market)}</small></button>`).join('')||empty('비교할 코인이 없습니다.')}</aside><div class="strategy-matrix-detail"><header><div><span>선택 코인</span><h3>${esc(String(market||'').replace(/^KRW-/,''))}</h3></div><small>${ui().strategyExchange==='upbit'?'업비트':'빗썸'} · 전략 시험</small></header><div class="strategy-matrix-row columns"><span>전략</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>하락폭</span><span>거래/승률</span><span>상태</span></div>${compare.map(r=>`<div class="strategy-matrix-row"><span><b>${esc(r.label||r.style)}</b><small>실험 ID ${esc(r.experiment_id||'-')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회 · ${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('이 코인의 전략 계좌 데이터가 아직 없습니다.')}</div></section>`;
  }

  function renderPaperBenchmark(){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const state=store.get(),cp=combinedPaper(state),normalized=normalizeCapital(cp.start,cp.equity,10000000,cp.start?cp.pnl/cp.start*100:0),b=paperStats(state,'bithumb'),u=paperStats(state,'upbit'),range=ui().strategyRange||'24h',combined=paperPortfolioHistory(state,'combined'),bh=paperPortfolioHistory(state,'bithumb'),uh=paperPortfolioHistory(state,'upbit'),latest=combined[combined.length-1]||{};
    box.innerHTML=`<section class="strategy-paper-head"><div><span>현재 실행 중인 가상매매 · Adaptive</span><h3>현재 실행 방식의 성적</h3><p>시험 전략을 선택해도 이 화면은 바뀌지 않습니다. 현재 실행 가상매매 기준선만 보여줍니다.</p></div>${rangeControl('data-strategy-range',range)}</section><section class="strategy-paper-kpis"><span><small>1,000만원 기준 평가액</small><b>${money(normalized.equity)}</b></span><span><small>1,000만원 기준 증감</small><b class="${tone(normalized.pnl)}">${normalized.pnl>=0?'+':''}${money(normalized.pnl)}</b></span><span><small>현재 하락폭</small><b class="${tone(latest.drawdown_pct)}">${pct(latest.drawdown_pct)}</b></span><span><small>현재 보유</small><b>${n(cp.active)}개</b></span><span><small>빗썸 수익률</small><b class="${tone(b.returnPct)}">${pct(b.returnPct)}</b></span><span><small>업비트 수익률</small><b class="${tone(u.returnPct)}">${pct(u.returnPct)}</b></span></section><section class="strategy-paper-charts">${simpleLineChart('Adaptive 가상계좌 자산곡선',combined,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('Adaptive 가상계좌 하락폭',combined,'drawdown_pct',{range,className:'sell',suffix:'%'})}${simpleLineChart('빗썸 Adaptive 수익률',bh,'return_pct',{range,className:'regime',suffix:'%'})}${simpleLineChart('업비트 Adaptive 수익률',uh,'return_pct',{range,className:'entry',suffix:'%'})}</section>`;
  }

  const click=e=>{
    const ex=e.target.closest('[data-strategy-exchange]');
    if(ex){store.setUi({strategyExchange:ex.dataset.strategyExchange,strategyCoinMarket:'',strategyOverviewExperiment:'',strategyCoinExperiment:''},{scope:'strategy'});breakdownSearch='';matrixSearch='';render();return}
    const tab=e.target.closest('[data-strategy-tab]');
    if(tab){store.setUi({strategyTab:tab.dataset.strategyTab},{scope:'strategy'});render();return}
    const row=e.target.closest('[data-strategy-key]');
    if(row){store.setUi({strategyOverviewExperiment:row.dataset.strategyKey,strategyCoinExperiment:row.dataset.strategyKey},{scope:'strategy-overview'});const data=strategyLab(store.get()),criteria=data.candidate_criteria||{};renderOverview(baseRows(),criteria,ui().strategyExchange);return}
    const range=e.target.closest('[data-strategy-range]');
    if(range){store.setUi({strategyRange:range.dataset.strategyRange},{scope:'strategy'});if(currentTab()==='paper')renderPaperBenchmark();else{const chosen=ensureOverviewSelected(baseRows()),data=strategyLab(store.get()),criteria=data.candidate_criteria||{};renderEvidence(chosen,criteria)}return}
    const market=e.target.closest('[data-strategy-market]');
    if(market){store.setUi({strategyCoinMarket:market.dataset.strategyMarket},{scope:'strategy'});renderMatrix()}
  };

  const input=e=>{
    if(e.target.matches('[data-strategy-breakdown-search]')){breakdownSearch=e.target.value;refreshBreakdown(ensureOverviewSelected(baseRows()));return}
    if(e.target.matches('[data-strategy-matrix-search]')){matrixSearch=e.target.value;renderMatrix()}
  };

  const change=e=>{
    if(e.target.matches('[data-strategy-coin-sort]')){store.setUi({strategyCoinSort:e.target.value},{scope:'strategy-breakdown'});refreshBreakdown(ensureOverviewSelected(baseRows()))}
  };

  return{
    mount(r){root=r;root.addEventListener('click',click);root.addEventListener('input',input);root.addEventListener('change',change);unsub=store.subscribe((_,m)=>{if(m.type==='snapshot')render()})},
    render,
    destroy(){unsub?.();root?.removeEventListener('click',click);root?.removeEventListener('input',input);root?.removeEventListener('change',change);root=null}
  };
}
