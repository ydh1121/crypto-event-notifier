import{strategyLab,strategyRows,strategyEquityHistory,strategyCoinMatrix,strategyCoinRows,paperPortfolioHistory,combinedPaper,paperStats}from'../shared/selectors.js';
import{pageHead,loading,empty,exchangeToggle,kpi}from'../shared/components.js';
import{n,money,pct,tone,esc}from'../shared/format.js';
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
  let root=null,unsub=null;
  const ui=()=>store.get().ui;
  const key=r=>String(r?.experiment_id||`${r?.exchange}|${r?.style||r?.label||''}`);

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
  function ensureCoinExperiment(rows){return ensureExperiment(rows,'strategyCoinExperiment')}

  function overviewKpis(rows,data,ex){
    const summary=data.candidate_summary||{};
    return`<section class="strategy-kpis">${kpi('시험 중인 전략',`${rows.length}개`,{sub:ex==='upbit'?'업비트':'빗썸'})}${kpi('후보 통과',`${n(summary.candidate)}개`)}${kpi('검증 중',`${n(summary.warming)}개`)}${kpi('기준 미충족',`${n(summary.rejected)}개`)}</section>`;
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
    const tab=ui().strategyTab||'overview';
    root.innerHTML=`${pageHead('전략 비교','현재 실행 계좌와 분리된 시험 전략들의 성적을 비교합니다.',exchangeToggle(ex,'data-strategy-exchange'))}${scopeBanner('strategy')}<nav class="subnav strategy-subnav"><button data-strategy-tab="overview" class="${tab==='overview'?'active':''}">전략 전체</button><button data-strategy-tab="coins" class="${tab==='coins'?'active':''}">코인별 성과</button><button data-strategy-tab="matrix" class="${tab==='matrix'?'active':''}">코인 × 전략</button><button data-strategy-tab="paper" class="${tab==='paper'?'active':''}">현재 실행 성적</button></nav><section id="strategyBody"></section>`;
    renderTab(rows,criteria,data,ex);
  }

  function renderTab(rows,criteria,data,ex){
    if(ui().strategyTab==='coins')renderCoins(rows);
    else if(ui().strategyTab==='matrix')renderMatrix(rows);
    else if(ui().strategyTab==='paper')renderPaperBenchmark();
    else renderOverview(rows,criteria,data,ex);
  }

  function renderOverview(rows,criteria,data,ex){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const chosen=ensureOverviewSelected(rows),selectedKey=key(chosen);
    box.innerHTML=`${overviewKpis(rows,data,ex)}<section class="strategy-workspace"><div class="strategy-table"><div class="strategy-row columns"><span>전략</span><span>수익률</span><span>최대 하락폭</span><span>PF</span><span>거래</span><span>승률</span><span>검증</span></div>${rows.map((r,i)=>{
      const[cLabel,cStatus]=candidateLabel(r,criteria),pf=n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2);
      return`<button class="strategy-row ${key(r)===selectedKey?'selected':''}" data-strategy-key="${esc(key(r))}"><span><i>${i+1}</i><b>${esc(r.label||r.style)}</b><small>${esc(r.description||'설명 없음')} · 실험 ID ${esc(r.experiment_id||'-')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${pf}</span><span>${n(r.closed_trades)}회</span><span>${n(r.win_rate_pct).toFixed(1)}%</span><span><em class="status-badge ${cStatus}">${esc(cLabel)}</em><small>검증 ${n(r.candidate?.passed_gates)}/${n(r.candidate?.total_gates)}</small></span></button>`;
    }).join('')}</div><aside id="strategyDetail" class="strategy-detail"></aside></section>`;
    renderDetail(chosen,criteria);
  }

  function renderDetail(r,criteria){
    const box=root?.querySelector('#strategyDetail');
    if(!box||!r)return;
    const c=r.candidate||{},[label,status]=candidateLabel(r,criteria),history=strategyEquityHistory(store.get(),r.experiment_id),range=ui().strategyRange||'24h';
    box.innerHTML=`<header><span>선택한 시험 전략</span><h3>${esc(r.label||r.style)}</h3><p>${esc(r.description||'전략 설명 없음')}</p><small class="strategy-experiment-ref">실험 ID · ${esc(r.experiment_id||'-')}</small><em class="status-badge ${status}">${esc(label)}</em></header><div class="strategy-detail-kpis"><span><small>수익률</small><b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b></span><span><small>가상 평가액</small><b>${money(r.total_equity_krw)}</b></span><span><small>최대 하락폭</small><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></span><span><small>번 돈 ÷ 잃은 돈</small><b>${n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2)}</b></span><span><small>완료 거래</small><b>${n(r.closed_trades)}회</b></span><span><small>승률</small><b>${n(r.win_rate_pct).toFixed(1)}%</b></span><span><small>거래당 평균 결과</small><b>${pct(r.expectancy_pct)}</b></span><span><small>수익 종목 비율</small><b>${pct(n(c.profitable_market_share)*100)}</b></span></div><section class="strategy-history-panel"><div class="history-toolbar"><div><h4>전략 자산곡선</h4><p>이 시험 전략의 가상 평가액이 시간에 따라 어떻게 변했는지 봅니다.</p></div>${rangeControl('data-strategy-range',range)}</div><div class="strategy-history-grid">${simpleLineChart('전략 자산곡선',history,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('최대 하락폭 흐름',history,'drawdown_pct',{range,className:'sell',suffix:'%'})}</div></section><details class="gate-panel"><summary>검증 기준 자세히 보기</summary><div><span>완료 거래 ≥ ${n(criteria.min_closed_trades)||30}</span><span>거래시장 ≥ ${n(criteria.min_traded_markets)||5}</span><span>수익시장 ≥ ${n(criteria.min_profitable_market_share)*100||50}%</span><span>손익집중 ≤ ${n(criteria.max_pnl_concentration_share)*100||60}%</span><span>하락폭 ≥ ${n(criteria.max_drawdown_floor_pct)||-12}%</span><span>거래당 평균 결과 &gt; 0</span><span>번 돈 ÷ 잃은 돈 ≥ ${n(criteria.min_profit_factor)||1.1}</span><span>총수익 &gt; 0</span></div><p>자동으로 실행 전략을 바꾸지 않습니다. 충분히 검증된 뒤 별도 결정합니다.</p></details>${r.custom?'<div class="local-management-note"><div><h3>사용자 조합전략</h3><p>생성·일시정지·재개는 로컬 PC에서만 가능합니다.</p></div><span>LOCAL PC ONLY</span></div>':''}`;
  }

  function coinPerformance(rows){
    const chosen=ensureCoinExperiment(rows),matrix=strategyCoinMatrix(store.get(),ui().strategyExchange),q=String(ui().strategyCoinSearch||'').trim().toLowerCase(),items=[];
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
    return{chosen,items};
  }

  function renderCoins(rows){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const{chosen,items}=coinPerformance(rows),chosenKey=key(chosen);
    box.innerHTML=`<section class="strategy-analytics-head"><div><span>선택한 전략의 코인별 결과</span><h3>${esc(chosen.label||chosen.style)}</h3><p>이 표는 위 ‘전략 전체’에서 무엇을 눌렀는지와 무관합니다. 여기서 선택한 전략만 적용됩니다.</p></div><div class="strategy-analytics-controls"><label><span>전략 선택</span><select data-strategy-coin-experiment>${rows.map(r=>`<option value="${esc(key(r))}" ${key(r)===chosenKey?'selected':''}>${esc(r.label||r.style)}</option>`).join('')}</select></label><label><span>정렬</span><select data-strategy-coin-sort><option value="return_desc" ${ui().strategyCoinSort==='return_desc'?'selected':''}>수익률 높은 순</option><option value="return_asc" ${ui().strategyCoinSort==='return_asc'?'selected':''}>수익률 낮은 순</option><option value="trades_desc" ${ui().strategyCoinSort==='trades_desc'?'selected':''}>거래 많은 순</option><option value="win_desc" ${ui().strategyCoinSort==='win_desc'?'selected':''}>승률 높은 순</option><option value="drawdown_asc" ${ui().strategyCoinSort==='drawdown_asc'?'selected':''}>하락폭 큰 순</option></select></label><label class="strategy-search-control"><span>코인 검색</span><input data-strategy-coin-search type="search" value="${esc(ui().strategyCoinSearch||'')}" placeholder="예: BTC"></label></div></section><section class="strategy-coin-table"><div class="strategy-coin-row columns"><span>코인</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>하락폭</span><span>완료 거래</span><span>승률</span><span>상태</span></div>${items.map(r=>`<div class="strategy-coin-row"><span><b>${esc(String(r.market).replace(/^KRW-/,''))}</b><small>${esc(r.market)}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회</span><span>${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('아직 전략별 코인 성과 데이터가 없습니다.')}</section>`;
  }

  function matrixMarkets(){
    let list=strategyCoinMatrix(store.get(),ui().strategyExchange),q=String(ui().strategyCoinSearch||'').trim().toLowerCase();
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
    box.innerHTML=`<section class="strategy-matrix-toolbar"><div><h3>한 코인에서 어떤 전략이 나았나?</h3><p>왼쪽에서 코인을 고르면 모든 시험 전략을 같은 표에서 비교합니다.</p></div><input data-strategy-coin-search type="search" value="${esc(ui().strategyCoinSearch||'')}" placeholder="코인 검색"></section><section class="strategy-matrix-workspace"><aside class="strategy-market-list">${markets.map(x=>`<button data-strategy-market="${esc(x.market)}" class="${x.market===market?'selected':''}"><b>${esc(String(x.market).replace(/^KRW-/,''))}</b><small>${esc(x.market)}</small></button>`).join('')||empty('비교할 코인이 없습니다.')}</aside><div class="strategy-matrix-detail"><header><div><span>선택 코인</span><h3>${esc(String(market||'').replace(/^KRW-/,''))}</h3></div><small>${ui().strategyExchange==='upbit'?'업비트':'빗썸'} · 전략 시험</small></header><div class="strategy-matrix-row columns"><span>전략</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>하락폭</span><span>거래/승률</span><span>상태</span></div>${compare.map(r=>`<div class="strategy-matrix-row"><span><b>${esc(r.label||r.style)}</b><small>실험 ID ${esc(r.experiment_id||'-')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회 · ${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('이 코인의 전략 계좌 데이터가 아직 없습니다.')}</div></section>`;
  }

  function renderPaperBenchmark(){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const state=store.get(),cp=combinedPaper(state),b=paperStats(state,'bithumb'),u=paperStats(state,'upbit'),range=ui().strategyRange||'24h',combined=paperPortfolioHistory(state,'combined'),bh=paperPortfolioHistory(state,'bithumb'),uh=paperPortfolioHistory(state,'upbit'),latest=combined[combined.length-1]||{};
    box.innerHTML=`<section class="strategy-paper-head"><div><span>현재 실행 중인 가상매매 · Adaptive</span><h3>현재 실행 방식의 성적</h3><p>위 시험 전략들과 비교하기 위한 기준선입니다. 서로 다른 계좌이므로 금액이 직접 일치하지 않습니다.</p></div>${rangeControl('data-strategy-range',range)}</section><section class="strategy-paper-kpis"><span><small>전체 평가액</small><b>${money(cp.equity)}</b></span><span><small>전체 증감</small><b class="${tone(cp.pnl)}">${cp.pnl>=0?'+':''}${money(cp.pnl)}</b></span><span><small>현재 하락폭</small><b class="${tone(latest.drawdown_pct)}">${pct(latest.drawdown_pct)}</b></span><span><small>현재 보유</small><b>${n(cp.active)}개</b></span><span><small>빗썸 증감</small><b class="${tone(b.pnl)}">${b.pnl>=0?'+':''}${money(b.pnl)}</b></span><span><small>업비트 증감</small><b class="${tone(u.pnl)}">${u.pnl>=0?'+':''}${money(u.pnl)}</b></span></section><section class="strategy-paper-charts">${simpleLineChart('Adaptive 가상계좌 자산곡선',combined,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('Adaptive 가상계좌 하락폭',combined,'drawdown_pct',{range,className:'sell',suffix:'%'})}${simpleLineChart('빗썸 Adaptive 수익률',bh,'return_pct',{range,className:'regime',suffix:'%'})}${simpleLineChart('업비트 Adaptive 수익률',uh,'return_pct',{range,className:'entry',suffix:'%'})}</section>`;
  }

  const click=e=>{
    const ex=e.target.closest('[data-strategy-exchange]');
    if(ex){store.setUi({strategyExchange:ex.dataset.strategyExchange,strategyCoinMarket:'',strategyOverviewExperiment:'',strategyCoinExperiment:''},{scope:'strategy'});render();return}
    const tab=e.target.closest('[data-strategy-tab]');
    if(tab){store.setUi({strategyTab:tab.dataset.strategyTab},{scope:'strategy'});render();return}
    const row=e.target.closest('[data-strategy-key]');
    if(row){store.setUi({strategyOverviewExperiment:row.dataset.strategyKey},{scope:'strategy-overview'});const data=strategyLab(store.get()),criteria=data.candidate_criteria||{},r=baseRows().find(x=>key(x)===row.dataset.strategyKey);root.querySelectorAll('[data-strategy-key]').forEach(x=>x.classList.toggle('selected',x===row));renderDetail(r,criteria);return}
    const range=e.target.closest('[data-strategy-range]');
    if(range){store.setUi({strategyRange:range.dataset.strategyRange},{scope:'strategy'});render();return}
    const market=e.target.closest('[data-strategy-market]');
    if(market){store.setUi({strategyCoinMarket:market.dataset.strategyMarket},{scope:'strategy'});render()}
  };
  const input=e=>{
    if(e.target.matches('[data-strategy-coin-search]')){store.setUi({strategyCoinSearch:e.target.value},{scope:'strategy'});render()}
  };
  const change=e=>{
    if(e.target.matches('[data-strategy-coin-experiment]')){store.setUi({strategyCoinExperiment:e.target.value},{scope:'strategy-coins'});renderCoins(baseRows());return}
    if(e.target.matches('[data-strategy-coin-sort]')){store.setUi({strategyCoinSort:e.target.value},{scope:'strategy-coins'});renderCoins(baseRows())}
  };

  return{
    mount(r){root=r;root.addEventListener('click',click);root.addEventListener('input',input);root.addEventListener('change',change);unsub=store.subscribe((_,m)=>{if(m.type==='snapshot')render()})},
    render,
    destroy(){unsub?.();root?.removeEventListener('click',click);root?.removeEventListener('input',input);root?.removeEventListener('change',change);root=null}
  };
}
