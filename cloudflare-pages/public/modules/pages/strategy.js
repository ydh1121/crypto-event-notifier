import{strategyLab,strategyRows,strategyEquityHistory,strategyCoinMatrix,strategyCoinRows,paperPortfolioHistory,combinedPaper,paperStats}from'../shared/selectors.js';
import{pageHead,loading,empty,exchangeToggle,kpi}from'../shared/components.js';
import{n,money,pct,tone,esc}from'../shared/format.js';
import{rangeControl,simpleLineChart}from'../shared/charts.js';
import{scopeBanner}from'../shared/viewer-context.js';

function candidateLabel(row,criteria){
  const c=row?.candidate||{};
  if(row?.status==='paused'||c.status==='paused')return['일시정지','paused'];
  if(c.status==='candidate')return['후보 통과','candidate'];
  if(c.status==='rejected')return['게이트 미통과','rejected'];
  return[`검증 ${n(c.closed_trades||row.closed_trades)}/${n(criteria?.min_closed_trades)||30}`,'warming'];
}

export function createStrategyPage({store}){
  let root=null,unsub=null,selected='';
  const ui=()=>store.get().ui;
  const key=r=>String(r?.experiment_id||`${r?.exchange}|${r?.style||r?.label||''}`);

  function baseRows(){
    return[...strategyRows(store.get(),ui().strategyExchange)].sort((a,b)=>n(b.return_pct)-n(a.return_pct));
  }

  function ensureSelected(rows){
    if(!selected||!rows.some(r=>key(r)===selected))selected=key(rows[0]);
    return rows.find(r=>key(r)===selected)||rows[0];
  }

  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){
      root.innerHTML=pageHead('전략 연구','Shadow PAPER 실험계좌의 성과와 후보 검증 상태를 비교합니다.')+loading('전략 데이터를 불러오는 중입니다.');
      return;
    }
    const ex=ui().strategyExchange,data=strategyLab(state),criteria=data.candidate_criteria||{},rows=baseRows();
    if(!rows.length){
      root.innerHTML=pageHead('전략 연구','Shadow PAPER 실험계좌의 성과와 후보 검증 상태를 비교합니다.',exchangeToggle(ex,'data-strategy-exchange'))+scopeBanner('strategy')+empty('전략 실험 데이터를 기다리는 중입니다.');
      return;
    }
    ensureSelected(rows);
    const summary=data.candidate_summary||{},tab=ui().strategyTab||'overview';
    root.innerHTML=`${pageHead('전략 연구','실행 PAPER와 분리된 Shadow 실험계좌를 전략별로 비교합니다.',exchangeToggle(ex,'data-strategy-exchange'))}${scopeBanner('strategy')}<nav class="subnav strategy-subnav"><button data-strategy-tab="overview" class="${tab==='overview'?'active':''}">전략 성과</button><button data-strategy-tab="coins" class="${tab==='coins'?'active':''}">코인별 성과</button><button data-strategy-tab="matrix" class="${tab==='matrix'?'active':''}">코인 × 전략</button><button data-strategy-tab="paper" class="${tab==='paper'?'active':''}">Adaptive 기준계좌</button></nav><section class="strategy-kpis">${kpi('Shadow 실험',`${rows.length}개`,{sub:ex==='upbit'?'업비트':'빗썸'})}${kpi('후보 통과',`${n(summary.candidate)}개`)}${kpi('검증 중',`${n(summary.warming)}개`)}${kpi('게이트 미통과',`${n(summary.rejected)}개`)}</section><section id="strategyBody"></section>`;
    renderTab(rows,criteria);
  }

  function renderTab(rows,criteria){
    if(ui().strategyTab==='coins')renderCoins(rows);
    else if(ui().strategyTab==='matrix')renderMatrix(rows);
    else if(ui().strategyTab==='paper')renderPaperBenchmark();
    else renderOverview(rows,criteria);
  }

  function renderOverview(rows,criteria){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const chosen=ensureSelected(rows);
    box.innerHTML=`<section class="strategy-workspace"><div class="strategy-table"><div class="strategy-row columns"><span>전략 / 실험 ID</span><span>수익률</span><span>최대 하락폭</span><span>PF</span><span>거래</span><span>승률</span><span>검증</span></div>${rows.map((r,i)=>{
      const[cLabel,cStatus]=candidateLabel(r,criteria),pf=n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2);
      return`<button class="strategy-row ${key(r)===selected?'selected':''}" data-strategy-key="${esc(key(r))}"><span><i>${i+1}</i><b>${esc(r.label||r.style)}</b><small>${esc(r.experiment_id||'-')} · ${esc(r.description||'설명 없음')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${pf}</span><span>${n(r.closed_trades)}회</span><span>${n(r.win_rate_pct).toFixed(1)}%</span><span><em class="status-badge ${cStatus}">${esc(cLabel)}</em><small>게이트 ${n(r.candidate?.passed_gates)}/${n(r.candidate?.total_gates)}</small></span></button>`;
    }).join('')}</div><aside id="strategyDetail" class="strategy-detail"></aside></section>`;
    renderDetail(chosen,criteria);
  }

  function renderDetail(r,criteria){
    const box=root?.querySelector('#strategyDetail');
    if(!box||!r)return;
    const c=r.candidate||{},[label,status]=candidateLabel(r,criteria),history=strategyEquityHistory(store.get(),r.experiment_id),range=ui().strategyRange||'24h';
    box.innerHTML=`<header><span>선택 Shadow 전략</span><h3>${esc(r.label||r.style)}</h3><p>${esc(r.description||'전략 설명 없음')}</p><small class="strategy-experiment-ref">experiment_id · ${esc(r.experiment_id||'-')}</small><em class="status-badge ${status}">${esc(label)}</em></header><div class="strategy-detail-kpis"><span><small>수익률</small><b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b></span><span><small>Shadow 평가액</small><b>${money(r.total_equity_krw)}</b></span><span><small>최대 하락폭</small><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></span><span><small>Profit Factor</small><b>${n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2)}</b></span><span><small>완료 거래</small><b>${n(r.closed_trades)}회</b></span><span><small>승률</small><b>${n(r.win_rate_pct).toFixed(1)}%</b></span><span><small>기대값</small><b>${pct(r.expectancy_pct)}</b></span><span><small>수익 종목 비율</small><b>${pct(n(c.profitable_market_share)*100)}</b></span></div><section class="strategy-history-panel"><div class="history-toolbar"><div><h4>Shadow 전략 equity curve</h4><p>실행 PAPER와 분리된 실험계좌 평가액을 5분 단위로 누적합니다.</p></div>${rangeControl('data-strategy-range',range)}</div><div class="strategy-history-grid">${simpleLineChart('전략 자산곡선',history,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('포트폴리오 Drawdown',history,'drawdown_pct',{range,className:'sell',suffix:'%'})}</div></section><section class="gate-panel"><h4>후보 승격 Gate</h4><div><span>완료 거래 ≥ ${n(criteria.min_closed_trades)||30}</span><span>거래시장 ≥ ${n(criteria.min_traded_markets)||5}</span><span>수익시장 ≥ ${n(criteria.min_profitable_market_share)*100||50}%</span><span>손익집중 ≤ ${n(criteria.max_pnl_concentration_share)*100||60}%</span><span>하락폭 ≥ ${n(criteria.max_drawdown_floor_pct)||-12}%</span><span>기대값 &gt; 0</span><span>PF ≥ ${n(criteria.min_profit_factor)||1.1}</span><span>총수익 &gt; 0</span></div><p>자동 승격은 하지 않습니다. 이 Gate는 Shadow PAPER 실험 검증용이며 실행 PAPER 전략을 자동으로 변경하지 않습니다.</p></section>${r.custom?'<div class="local-management-note"><div><h3>사용자 조합전략</h3><p>생성·일시정지·재개는 로컬 PC에서만 가능합니다.</p></div><span>LOCAL PC ONLY</span></div>':''}`;
  }

  function coinPerformance(rows){
    const chosen=ensureSelected(rows),matrix=strategyCoinMatrix(store.get(),ui().strategyExchange),q=String(ui().strategyCoinSearch||'').trim().toLowerCase(),items=[];
    for(const item of matrix){
      if(q&&!String(item.market||'').toLowerCase().includes(q))continue;
      const raw=(item.rows||[]).find(v=>String(v?.[0]||'')===chosen.experiment_id);
      if(!raw)continue;
      items.push({market:item.market,return_pct:n(raw[2]),realized_pnl:n(raw[3]),unrealized_pnl:n(raw[4]),max_drawdown_pct:n(raw[5]),closed_trades:n(raw[6]),wins:n(raw[7]),active:Boolean(raw[8])});
    }
    items.sort((a,b)=>Math.abs(n(b.return_pct))-Math.abs(n(a.return_pct)));
    return{chosen,items};
  }

  function renderCoins(rows){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const{chosen,items}=coinPerformance(rows);
    box.innerHTML=`<section class="strategy-analytics-head"><div><span>선택 Shadow 전략</span><h3>${esc(chosen.label||chosen.style)}</h3><p>${esc(chosen.experiment_id||'-')} · 동일 Shadow 실험계좌가 코인별로 어떤 결과를 냈는지 봅니다.</p></div><input data-strategy-coin-search type="search" value="${esc(ui().strategyCoinSearch||'')}" placeholder="코인 검색"></section><section class="strategy-coin-table"><div class="strategy-coin-row columns"><span>코인</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>DD</span><span>완료 거래</span><span>승률</span><span>상태</span></div>${items.map(r=>`<div class="strategy-coin-row"><span><b>${esc(String(r.market).replace(/^KRW-/,''))}</b><small>${esc(r.market)}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회</span><span>${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('아직 전략별 코인 성과 데이터가 없습니다.')}</section>`;
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
    box.innerHTML=`<section class="strategy-matrix-toolbar"><div><h3>코인 × Shadow 전략 비교</h3><p>한 코인을 같은 시점·같은 데이터로 돌린 독립 실험계좌들의 결과입니다.</p></div><input data-strategy-coin-search type="search" value="${esc(ui().strategyCoinSearch||'')}" placeholder="코인 검색"></section><section class="strategy-matrix-workspace"><aside class="strategy-market-list">${markets.map(x=>`<button data-strategy-market="${esc(x.market)}" class="${x.market===market?'selected':''}"><b>${esc(String(x.market).replace(/^KRW-/,''))}</b><small>${esc(x.market)}</small></button>`).join('')||empty('비교할 코인이 없습니다.')}</aside><div class="strategy-matrix-detail"><header><div><span>선택 코인</span><h3>${esc(String(market||'').replace(/^KRW-/,''))}</h3></div><small>${ui().strategyExchange==='upbit'?'업비트':'빗썸'} · Shadow PAPER</small></header><div class="strategy-matrix-row columns"><span>전략 / 실험 ID</span><span>수익률</span><span>실현손익</span><span>미실현</span><span>DD</span><span>거래/승률</span><span>상태</span></div>${compare.map(r=>`<div class="strategy-matrix-row"><span><b>${esc(r.label||r.style)}</b><small>${esc(r.experiment_id||'-')}</small></span><span class="${tone(r.return_pct)}">${pct(r.return_pct)}</span><span class="${tone(r.realized_pnl)}">${r.realized_pnl>=0?'+':''}${money(r.realized_pnl)}</span><span class="${tone(r.unrealized_pnl)}">${r.unrealized_pnl>=0?'+':''}${money(r.unrealized_pnl)}</span><span class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</span><span>${n(r.closed_trades)}회 · ${(r.closed_trades?n(r.wins)/n(r.closed_trades)*100:0).toFixed(1)}%</span><span>${r.active?'보유 중':'대기'}</span></div>`).join('')||empty('이 코인의 전략 계좌 데이터가 아직 없습니다.')}</div></section>`;
  }

  function renderPaperBenchmark(){
    const box=root?.querySelector('#strategyBody');
    if(!box)return;
    const state=store.get(),cp=combinedPaper(state),b=paperStats(state,'bithumb'),u=paperStats(state,'upbit'),range=ui().strategyRange||'24h',combined=paperPortfolioHistory(state,'combined'),bh=paperPortfolioHistory(state,'bithumb'),uh=paperPortfolioHistory(state,'upbit'),latest=combined[combined.length-1]||{};
    box.innerHTML=`<section class="strategy-paper-head"><div><span>실행 PAPER benchmark · Adaptive</span><h3>Adaptive 기준계좌 equity / drawdown</h3><p>Shadow 전략 실험과 비교하기 위한 별도 실행 PAPER 기준선입니다. 같은 계좌가 아니므로 전략 실험 수익과 직접 일치하지 않습니다.</p></div>${rangeControl('data-strategy-range',range)}</section><section class="strategy-paper-kpis"><span><small>전체 평가액</small><b>${money(cp.equity)}</b></span><span><small>전체 증감</small><b class="${tone(cp.pnl)}">${cp.pnl>=0?'+':''}${money(cp.pnl)}</b></span><span><small>현재 Drawdown</small><b class="${tone(latest.drawdown_pct)}">${pct(latest.drawdown_pct)}</b></span><span><small>현재 보유</small><b>${n(cp.active)}개</b></span><span><small>빗썸 증감</small><b class="${tone(b.pnl)}">${b.pnl>=0?'+':''}${money(b.pnl)}</b></span><span><small>업비트 증감</small><b class="${tone(u.pnl)}">${u.pnl>=0?'+':''}${money(u.pnl)}</b></span></section><section class="strategy-paper-charts">${simpleLineChart('Adaptive PAPER 자산곡선',combined,'equity_krw',{range,className:'primary',suffix:'원'})}${simpleLineChart('Adaptive PAPER Drawdown',combined,'drawdown_pct',{range,className:'sell',suffix:'%'})}${simpleLineChart('빗썸 Adaptive 수익률',bh,'return_pct',{range,className:'regime',suffix:'%'})}${simpleLineChart('업비트 Adaptive 수익률',uh,'return_pct',{range,className:'entry',suffix:'%'})}</section>`;
  }

  const click=e=>{
    const ex=e.target.closest('[data-strategy-exchange]');
    if(ex){store.setUi({strategyExchange:ex.dataset.strategyExchange,strategyCoinMarket:''},{scope:'strategy'});selected='';render();return}
    const tab=e.target.closest('[data-strategy-tab]');
    if(tab){store.setUi({strategyTab:tab.dataset.strategyTab},{scope:'strategy'});render();return}
    const row=e.target.closest('[data-strategy-key]');
    if(row){selected=row.dataset.strategyKey;const data=strategyLab(store.get()),criteria=data.candidate_criteria||{},r=baseRows().find(x=>key(x)===selected);root.querySelectorAll('[data-strategy-key]').forEach(x=>x.classList.toggle('selected',x===row));renderDetail(r,criteria);return}
    const range=e.target.closest('[data-strategy-range]');
    if(range){store.setUi({strategyRange:range.dataset.strategyRange},{scope:'strategy'});render();return}
    const market=e.target.closest('[data-strategy-market]');
    if(market){store.setUi({strategyCoinMarket:market.dataset.strategyMarket},{scope:'strategy'});render()}
  };
  const input=e=>{
    if(e.target.matches('[data-strategy-coin-search]')){store.setUi({strategyCoinSearch:e.target.value},{scope:'strategy'});render()}
  };

  return{
    mount(r){root=r;root.addEventListener('click',click);root.addEventListener('input',input);unsub=store.subscribe((_,m)=>{if(m.type==='snapshot')render()})},
    render,
    destroy(){unsub?.();root?.removeEventListener('click',click);root?.removeEventListener('input',input);root=null}
  };
}
