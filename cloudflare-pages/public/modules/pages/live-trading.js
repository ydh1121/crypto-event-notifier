import{exactHolding}from'../shared/strategy-workbench-model.js';
import{rowsFor,holdings,allCandidateRows,strategyCoinRows,strategyRows,strategyLab,findMarket}from'../shared/selectors.js';
import{pageHead,loading,empty}from'../shared/components.js';
import{n,money,pct,price,tone,esc,decisionLabel}from'../shared/format.js';
import{calculateAveraging}from'../shared/averaging.js';
import{buildHoldingPlanGuidance,buildProfitProtectionGuidance}from'../shared/holding-plan.js';
import{getMarketDetail}from'../services/market-detail.js';

const VALID_EXCHANGES=new Set(['bithumb','upbit']);
const BUY_INTENTS=new Set(['buy','add','explore','idle_explore']);

function exchangeLabel(value){return value==='upbit'?'업비트':'빗썸'}
function symbolOf(row,market=''){return String(row?.symbol||market||'').replace(/^KRW-/,'')}
function marketKey(exchange,market){return `${exchange}|${market}`}
function marketChange(row){const value=Number(row?.change_24h_pct);return Number.isFinite(value)?value:null}
function validationLabel(exp,coinRow,criteria){
  if(exp?.status==='paused')return['일시정지','paused'];
  const count=coinRow?.closed_trades;
  return count===null||count===undefined?['코인별 성과 미수신','warming']:[`이 코인 완료 ${n(count)}회`,'warming'];
}

export function createLiveTradingPage({store,navigate}){
  let root=null,unsub=null,detailSeq=0,detail=null,detailFor='';
  const ui=()=>store.get().ui;
  const exchange=()=>VALID_EXCHANGES.has(ui().liveExchange)?ui().liveExchange:'bithumb';
  const selectedMarket=()=>String(ui().liveMarket||'');

  function exchangeRows(ex=exchange()){return rowsFor(store.get(),ex)}
  function holdingFor(ex,market){
    const list=holdings(store.get());
    return exactHolding(list,ex,market);
  }
  function rankedCandidates(ex=exchange()){
    return allCandidateRows(store.get())
      .filter(row=>row.__exchange===ex)
      .sort((a,b)=>{
        const ai=BUY_INTENTS.has(String(a.trade_intent||'').toLowerCase())?1:0;
        const bi=BUY_INTENTS.has(String(b.trade_intent||'').toLowerCase())?1:0;
        return bi-ai||n(b.opportunity_score)-n(a.opportunity_score)||n(b.entry_score)-n(a.entry_score)||n(b.regime_score)-n(a.regime_score);
      });
  }
  function ensureMarket(){
    const ex=exchange(),rows=exchangeRows(ex);
    let market=selectedMarket();
    if(!rows.some(row=>row.market===market)){
      const held=[...holdings(store.get())]
        .filter(row=>!row.exchange||String(row.exchange).toLowerCase()===ex)
        .sort((a,b)=>n(b.value_krw)-n(a.value_krw));
      market=held.find(row=>rows.some(candidate=>candidate.market===row.market))?.market
        ||rankedCandidates(ex)[0]?.market
        ||rows[0]?.market
        ||'';
      if(market!==ui().liveMarket)store.setUi({liveMarket:market},{scope:'live-market-normalize'});
    }
    return market;
  }
  function selectedRow(){return findMarket(store.get(),exchange(),ensureMarket())}
  function currentPlan(){return detail?.data?.trade_plan||{}}
  function currentStrategy(){return String(detail?.data?.strategy||selectedRow()?.strategy||'adaptive')}
  function detailMatches(){return detailFor===marketKey(exchange(),selectedMarket())}

  function render(){
    if(!root)return;
    const state=store.get();
    if(!state.snapshot){
      root.innerHTML=pageHead('실전매매','코인 선택 → 전략 근거 → 분할 진입·익절 → 계산 순서로 봅니다.')+loading('실전매매 화면을 준비하는 중입니다.');
      return;
    }
    ensureMarket();
    root.innerHTML=`${pageHead('실전매매','현재 코인과 전략 근거를 한 화면에서 보고 진입·익절 계획을 계산합니다.')}
      <section data-live-trading-root class="live-trading-root">
        <section id="liveContext" class="live-context"></section>
        <section class="live-layout">
          <aside class="live-candidates">
            <header><div><h3>상승 관찰 후보</h3><p>기존 시장·PAPER 값으로 1차 스캔합니다. BTC·ETH/이벤트 근거 통합 전에는 자동 추천으로 승격하지 않습니다.</p></div><span>최대 12개</span></header>
            <div id="liveCandidateList" class="live-candidate-list"></div>
          </aside>
          <div class="live-primary">
            <section id="liveStrategySummary" class="live-strategy-summary"></section>
            <section id="liveStrategyPlan" class="live-plan"></section>
            <section id="liveCalculator" class="live-calculator"></section>
          </div>
        </section>
      </section>`;
    renderContext();
    renderCandidates();
    renderStrategySummary();
    renderStrategyPlan();
    renderCalculator();
    loadDetail();
  }

  function renderContext(){
    const box=root?.querySelector('#liveContext');
    if(!box)return;
    const ex=exchange(),market=ensureMarket(),row=findMarket(store.get(),ex,market),holding=holdingFor(ex,market),ticker=symbolOf(row,market);
    const holdingHtml=holding?`<div class="live-holding-brief"><span>실제 보유</span><b>${n(holding.volume).toLocaleString('ko-KR',{maximumFractionDigits:8})}개</b><small>평단 ${price(holding.avg_price)} · 평가 ${money(holding.value_krw)} · <em class="${tone(holding.unrealized_pnl_krw)}">${n(holding.unrealized_pnl_krw)>=0?'+':''}${money(holding.unrealized_pnl_krw)}</em></small></div>`:'<div class="live-holding-brief empty"><span>실제 보유</span><b>미보유</b><small>계산기는 수량·평단을 직접 입력할 수 있습니다.</small></div>';
    const change=marketChange(row);
    box.innerHTML=`
      <div class="live-context-controls">
        <div class="segmented live-exchange" role="group" aria-label="거래소">
          <button data-live-exchange="bithumb" class="${ex==='bithumb'?'active':''}">빗썸</button>
          <button data-live-exchange="upbit" class="${ex==='upbit'?'active':''}">업비트</button>
        </div>
        <label class="live-market-search"><span>코인</span><input data-live-market-search type="search" value="${esc(ticker)}" autocomplete="off" placeholder="티커 검색"><div id="liveMarketSuggestions" class="live-market-suggestions" hidden></div></label>
      </div>
      <div class="live-current-quote"><span>${esc(exchangeLabel(ex))} · ${esc(ticker||market)}</span><b data-live-current-price>${price(row?.price)}</b><small>24h <em class="${change===null?'':tone(change)}">${change===null?'-':pct(change)}</em> · 판단 ${esc(decisionLabel(row)||'-')}</small></div>
      ${holdingHtml}`;
  }

  function renderMarketSuggestions(value=''){
    const box=root?.querySelector('#liveMarketSuggestions');
    if(!box)return;
    const q=String(value||'').trim().toLowerCase(),rows=exchangeRows();
    if(!q){box.hidden=true;box.innerHTML='';return}
    const matches=rows.filter(row=>`${row.symbol||''} ${row.name||''} ${row.market||''}`.toLowerCase().includes(q)).slice(0,12);
    box.innerHTML=matches.map(row=>`<button type="button" data-live-market-choice="${esc(row.market)}"><span><b>${esc(symbolOf(row,row.market))}</b><small>${esc(row.name||row.market)}</small></span><strong>${price(row.price)}</strong></button>`).join('');
    box.hidden=!matches.length;
  }

  function renderCandidates(){
    const box=root?.querySelector('#liveCandidateList');
    if(!box)return;
    const market=ensureMarket(),rows=rankedCandidates().slice(0,12);
    box.innerHTML=rows.length?rows.map(row=>{
      const active=row.market===market,intent=String(row.trade_intent||'').toLowerCase(),signal=BUY_INTENTS.has(intent)?'매수 조건 관찰':decisionLabel(row)||'관찰';
      return`<button type="button" data-live-candidate="${esc(row.market)}" data-live-candidate-exchange="${esc(row.__exchange)}" class="live-candidate-row ${active?'selected':''}">
        <span><b>${esc(symbolOf(row,row.market))}</b><small>${esc(signal)} · 기회 ${n(row.opportunity_score).toFixed(0)} · 타이밍 ${n(row.entry_score).toFixed(0)}</small></span>
        <strong><b>${price(row.price)}</b><small class="${tone(row.return_pct)}">PAPER ${pct(row.return_pct)}</small></strong>
      </button>`;
    }).join(''):empty('현재 스캔할 코인이 없습니다.');
  }

  function strategyEvidence(){
    const ex=exchange(),market=ensureMarket(),coinRows=[...strategyCoinRows(store.get(),ex,market)].sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    const experiments=new Map(strategyRows(store.get(),ex).map(row=>[String(row.experiment_id||''),row]));
    const criteria=strategyLab(store.get()).candidate_criteria||{};
    return coinRows.map(row=>({row,exp:experiments.get(String(row.experiment_id||''))||{},criteria}));
  }

  function renderStrategySummary(){
    const box=root?.querySelector('#liveStrategySummary');
    if(!box)return;
    const evidence=strategyEvidence(),candidate=evidence.filter(item=>(item.exp?.candidate||{}).status==='candidate'&&n(item.row.closed_trades)>0);
    let title='검증 부족',note='코인별 우세 전략을 확정할 projection이 아직 없습니다. 아래 실제 시험 성과를 비교하세요.';
    if(candidate.length===1){
      title=`${candidate[0].row.label||candidate[0].row.style||'전략'} · 우세 후보`;
      note='전략 자체는 후보 Gate를 통과했고 이 코인에도 거래 표본이 있습니다. 코인별 우세 확정값은 아직 별도 projection이 없습니다.';
    }else if(candidate.length>1){
      title=`후보 ${candidate.length}개 · 비교 필요`;
      note='복수 전략이 후보 Gate를 통과했습니다. 수익률만으로 한 전략을 임의 선택하지 않습니다.';
    }
    box.innerHTML=`<header><div><span>현재 우세 전략</span><h3>${esc(title)}</h3><p>${esc(note)}</p></div><button type="button" data-live-open-legacy="strategy">전략 근거 전체 보기</button></header>`;
  }

  function renderStrategyPlan(){
    const box=root?.querySelector('#liveStrategyPlan');
    if(!box)return;
    const row=selectedRow(),plan=detailMatches()?currentPlan():{},planReady=detailMatches()&&Object.keys(plan).length>0,guide=buildHoldingPlanGuidance({row,plan}),evidence=strategyEvidence(),adaptiveName=currentStrategy();
    const adaptive=`<div class="live-plan-row live-plan-current">
      <span><b>현재 실행 · ${esc(adaptiveName)}</b><small>실행 PAPER 계획</small></span>
      <span><small>진입</small><b>${planReady?price(guide.nextPrice):'계획 대기'}</b><em>${planReady&&guide.suggestedWeightPct?guide.suggestedWeightPct.toFixed(2)+'%':'비중 미제공'}</em></span>
      <span><small>익절</small><b>${planReady?price(guide.targetPrice):'계획 대기'}</b><em>분할 비중 미제공</em></span>
      <span><small>중단</small><b>${planReady?price(guide.stopPrice):'-'}</b><em>${planReady&&guide.remainingEntries?'남은 분할 '+guide.remainingEntries+'회':'-'}</em></span>
      <span><small>상태</small><b>${esc(guide.status)}</b><em>실거래 주문 아님</em></span>
    </div>`;
    const experimental=evidence.map(({row:r,exp,criteria})=>{
      const[label,status]=validationLabel(exp,r,criteria),win=n(r.closed_trades)?n(r.wins)/n(r.closed_trades)*100:0;
      return`<div class="live-plan-row">
        <span><b>${esc(r.label||r.style||r.experiment_id)}</b><small>코인 시험 성과 · ${n(r.closed_trades)}회 · 승률 ${win.toFixed(1)}%</small></span>
        <span><small>진입</small><b>projection 대기</b><em>전략별 타점 미제공</em></span>
        <span><small>익절</small><b>projection 대기</b><em>전략별 비중 미제공</em></span>
        <span><small>이 코인 수익률</small><b class="${tone(r.return_pct)}">${pct(r.return_pct)}</b><em>DD ${pct(r.max_drawdown_pct)}</em></span>
        <span><small>검증</small><b class="status-badge ${status}">${esc(label)}</b><em>추천 순위 아님</em></span>
      </div>`;
    }).join('');
    box.innerHTML=`<header><div><h3>전략별 진입·익절 계획</h3><p>현재 Snapshot이 제공하는 실제 계획만 표시합니다. 전략별 분할 타점·비중이 없는 경우 값을 만들지 않습니다.</p></div><span>${esc(symbolOf(row,selectedMarket()))}</span></header>
      <div class="live-plan-table">
        <div class="live-plan-row columns"><span>전략</span><span>진입 / 비중</span><span>익절 / 비중</span><span>성과 / 위험</span><span>검증</span></div>
        ${adaptive}${experimental||'<div class="live-plan-empty">이 코인의 전략 실험 성과가 아직 없습니다.</div>'}
      </div>`;
  }

  async function loadDetail({preserve=false}={}){
    const ex=exchange(),market=ensureMarket(),key=marketKey(ex,market),id=++detailSeq;
    if(!preserve){detail=null;detailFor='';renderStrategyPlan();}
    try{
      const next=await getMarketDetail(ex,market);
      if(id!==detailSeq||key!==marketKey(exchange(),selectedMarket()))return;
      detail=next;detailFor=key;renderStrategyPlan();renderCalculatorReference();
    }catch{
      if(id===detailSeq&&!preserve){detail=null;detailFor=key;renderStrategyPlan();renderCalculatorReference()}
    }
  }

  function calculatorMode(){return ui().liveCalculator==='profit'?'profit':'average'}
  function renderCalculator(){
    const box=root?.querySelector('#liveCalculator');
    if(!box)return;
    const market=ensureMarket(),holding=holdingFor(exchange(),market),mode=calculatorMode(),qty=n(holding?.volume),avg=n(holding?.avg_price);
    box.innerHTML=`<header class="live-calculator-head"><div><h3>계산기</h3><p id="liveCalculatorReference"></p></div><div class="segmented"><button type="button" data-live-calculator="average" class="${mode==='average'?'active':''}">물타기</button><button type="button" data-live-calculator="profit" class="${mode==='profit'?'active':''}">익절</button></div></header>
      <div id="liveCalculatorBody"></div>`;
    const body=box.querySelector('#liveCalculatorBody');
    if(mode==='profit')body.innerHTML=profitCalculatorHtml(qty,avg);
    else body.innerHTML=averageCalculatorHtml(qty,avg);
    renderCalculatorReference();recalcCalculator();
  }

  function renderCalculatorReference(){
    const box=root?.querySelector('#liveCalculatorReference');
    if(!box)return;
    const holding=holdingFor(exchange(),ensureMarket()),plan=detailMatches()?currentPlan():{},guide=buildHoldingPlanGuidance({row:selectedRow(),plan}),profit=buildProfitProtectionGuidance({holding,plan});
    box.textContent=calculatorMode()==='profit'
      ?`PAPER 목표 ${price(profit.targetPrice)} · 고점보호 ${price(profit.trailingStopPrice)} · 계산값은 수수료 제외`
      :`PAPER 다음 진입 ${price(guide.nextPrice)} · 중단선 ${price(guide.stopPrice)} · 실제 주문은 실행하지 않음`;
  }

  function averageCalculatorHtml(qty,avg){
    return`<div class="live-calc-base"><label>기준 수량<input data-live-base-qty type="number" min="0" step="any" value="${qty||''}"></label><label>현재 평균단가<input data-live-base-avg type="number" min="0" step="any" value="${avg||''}"></label><button type="button" data-live-use-holding>보유값 다시 불러오기</button></div>
      <div class="live-calc-table" data-live-average-rows>
        <div class="live-calc-row columns"><span>회차</span><span>매수가</span><span>투입금</span><span>매수 수량</span><span>예상 평단</span><span></span></div>
        ${[1,2,3].map(i=>averageRowHtml(i)).join('')}
      </div>
      <div class="live-calc-actions"><button type="button" data-live-add-average>분할 추가</button></div>
      <div id="liveCalcResult" class="live-calc-result"></div>`;
  }
  function averageRowHtml(round){
    return`<div class="live-calc-row" data-live-average-row><span>${round}차</span><label><span>매수가</span><input data-live-average-price type="number" min="0" step="any" placeholder="가격"></label><label><span>투입금</span><input data-live-average-amount type="number" min="0" step="1000" placeholder="원"></label><span data-live-average-volume>-</span><span data-live-average-result>-</span><button type="button" data-live-remove-row aria-label="${round}차 삭제">삭제</button></div>`;
  }
  function profitCalculatorHtml(qty,avg){
    return`<div class="live-calc-base"><label>기준 수량<input data-live-base-qty type="number" min="0" step="any" value="${qty||''}"></label><label>현재 평균단가<input data-live-base-avg type="number" min="0" step="any" value="${avg||''}"></label><button type="button" data-live-use-holding>보유값 다시 불러오기</button></div>
      <div class="live-calc-table" data-live-profit-rows>
        <div class="live-profit-row columns"><span>회차</span><span>익절가</span><span>비중</span><span>예상 매도수량</span><span>예상 손익</span><span></span></div>
        ${[1,2,3].map(i=>profitRowHtml(i)).join('')}
      </div>
      <div class="live-calc-actions"><button type="button" data-live-add-profit>분할 추가</button></div>
      <div id="liveCalcResult" class="live-calc-result"></div>`;
  }
  function profitRowHtml(round){
    return`<div class="live-profit-row" data-live-profit-row><span>${round}차</span><label><span>익절가</span><input data-live-profit-price type="number" min="0" step="any" placeholder="가격"></label><label><span>비중</span><input data-live-profit-pct type="number" min="0" max="100" step="1" placeholder="%"></label><span data-live-profit-volume>-</span><span data-live-profit-pnl>-</span><button type="button" data-live-remove-row aria-label="${round}차 삭제">삭제</button></div>`;
  }

  function renumberRows(selector){
    root?.querySelectorAll(selector).forEach((row,index)=>{
      const first=row.querySelector(':scope>span');if(first)first.textContent=`${index+1}차`;
      row.querySelector('[data-live-remove-row]')?.setAttribute('aria-label',`${index+1}차 삭제`);
    });
  }
  function recalcCalculator(){
    const result=root?.querySelector('#liveCalcResult');if(!result)return;
    const qty=Math.max(0,n(root.querySelector('[data-live-base-qty]')?.value)),avg=Math.max(0,n(root.querySelector('[data-live-base-avg]')?.value));
    if(calculatorMode()==='average'){
      const rows=[...root.querySelectorAll('[data-live-average-row]')].map(row=>({price:n(row.querySelector('[data-live-average-price]')?.value),amount_krw:n(row.querySelector('[data-live-average-amount]')?.value)}));
      const calc=calculateAveraging({volume:qty,avgPrice:avg,rows});
      [...root.querySelectorAll('[data-live-average-row]')].forEach((row,index)=>{
        const stage=calc.stages[index]||{},volume=row.querySelector('[data-live-average-volume]'),average=row.querySelector('[data-live-average-result]');
        if(volume)volume.textContent=stage.valid?n(stage.buy_volume).toLocaleString('ko-KR',{maximumFractionDigits:8}):'-';
        if(average)average.textContent=stage.valid?price(stage.avg_price):'-';
      });
      const valid=calc.stages.filter(stage=>stage.valid);
      result.innerHTML=`<span><small>최종 수량</small><b>${n(calc.final_volume).toLocaleString('ko-KR',{maximumFractionDigits:8})}</b></span><span><small>최종 평단</small><b>${price(calc.final_avg_price)}</b></span><span><small>추가 투입</small><b>${money(valid.reduce((sum,stage)=>sum+n(stage.amount_krw),0))}</b></span>`;
      return;
    }
    let remaining=qty,totalPnl=0,totalProceeds=0,sold=0;
    const rows=[...root.querySelectorAll('[data-live-profit-row]')];
    for(const row of rows){
      const target=Math.max(0,n(row.querySelector('[data-live-profit-price]')?.value)),share=Math.max(0,Math.min(100,n(row.querySelector('[data-live-profit-pct]')?.value)));
      const requested=qty*share/100,sellQty=target>0?Math.min(remaining,requested):0,pnlValue=target>0?(target-avg)*sellQty:0;
      remaining=Math.max(0,remaining-sellQty);sold+=sellQty;totalPnl+=pnlValue;totalProceeds+=target*sellQty;
      const volume=row.querySelector('[data-live-profit-volume]'),pnlBox=row.querySelector('[data-live-profit-pnl]');
      if(volume)volume.textContent=sellQty?sellQty.toLocaleString('ko-KR',{maximumFractionDigits:8}):'-';
      if(pnlBox){pnlBox.textContent=sellQty?`${pnlValue>=0?'+':''}${money(pnlValue)}`:'-';pnlBox.className=tone(pnlValue)}
    }
    const soldPct=qty?sold/qty*100:0;
    result.innerHTML=`<span><small>예상 매도 비중</small><b>${soldPct.toFixed(1)}%</b></span><span><small>예상 실현손익</small><b class="${tone(totalPnl)}">${totalPnl>=0?'+':''}${money(totalPnl)}</b></span><span><small>잔여 수량</small><b>${remaining.toLocaleString('ko-KR',{maximumFractionDigits:8})}</b></span><span><small>예상 수령액</small><b>${money(totalProceeds)}</b></span>`;
  }

  function selectMarket(ex,market){
    if(!VALID_EXCHANGES.has(ex)||!rowsFor(store.get(),ex).some(row=>row.market===market))return;
    store.setUi({liveExchange:ex,liveMarket:market},{scope:'live-selection'});
    detailSeq++;detail=null;detailFor='';
    renderContext();renderCandidates();renderStrategySummary();renderStrategyPlan();renderCalculator();loadDetail();
  }
  function refreshData(){
    if(!root?.querySelector('[data-live-trading-root]')){render();return}
    ensureMarket();renderContext();renderCandidates();renderStrategySummary();renderStrategyPlan();renderCalculatorReference();
    loadDetail({preserve:true});
  }

  const click=event=>{
    const exButton=event.target.closest('[data-live-exchange]');
    if(exButton){const ex=exButton.dataset.liveExchange;store.setUi({liveExchange:ex,liveMarket:''},{scope:'live-exchange'});const market=ensureMarket();selectMarket(ex,market);return}
    const choice=event.target.closest('[data-live-market-choice]');
    if(choice){selectMarket(exchange(),choice.dataset.liveMarketChoice);return}
    const candidate=event.target.closest('[data-live-candidate]');
    if(candidate){selectMarket(candidate.dataset.liveCandidateExchange||exchange(),candidate.dataset.liveCandidate);return}
    const legacy=event.target.closest('[data-live-open-legacy]');
    if(legacy){navigate?.(legacy.dataset.liveOpenLegacy);return}
    const mode=event.target.closest('[data-live-calculator]');
    if(mode){store.setUi({liveCalculator:mode.dataset.liveCalculator},{scope:'live-calculator'});renderCalculator();return}
    if(event.target.closest('[data-live-use-holding]')){renderCalculator();return}
    if(event.target.closest('[data-live-add-average]')){
      const rows=root.querySelectorAll('[data-live-average-row]');if(rows.length>=8)return;
      root.querySelector('[data-live-average-rows]')?.insertAdjacentHTML('beforeend',averageRowHtml(rows.length+1));recalcCalculator();return;
    }
    if(event.target.closest('[data-live-add-profit]')){
      const rows=root.querySelectorAll('[data-live-profit-row]');if(rows.length>=8)return;
      root.querySelector('[data-live-profit-rows]')?.insertAdjacentHTML('beforeend',profitRowHtml(rows.length+1));recalcCalculator();return;
    }
    const remove=event.target.closest('[data-live-remove-row]');
    if(remove){
      const row=remove.closest('[data-live-average-row],[data-live-profit-row]'),parent=row?.parentElement;
      if(row&&parent?.querySelectorAll('[data-live-average-row],[data-live-profit-row]').length>1)row.remove();
      renumberRows('[data-live-average-row]');renumberRows('[data-live-profit-row]');recalcCalculator();
    }
  };
  const input=event=>{
    if(event.target.matches('[data-live-market-search]')){renderMarketSuggestions(event.target.value);return}
    if(event.target.matches('[data-live-base-qty],[data-live-base-avg],[data-live-average-price],[data-live-average-amount],[data-live-profit-price],[data-live-profit-pct]'))recalcCalculator();
  };
  const change=event=>{
    if(!event.target.matches('[data-live-market-search]'))return;
    const q=String(event.target.value||'').trim().toLowerCase(),row=exchangeRows().find(item=>symbolOf(item,item.market).toLowerCase()===q||String(item.market||'').toLowerCase()===q||String(item.name||'').toLowerCase()===q);
    if(row)selectMarket(exchange(),row.market);
  };

  return{
    mount(target){
      root=target;root.addEventListener('click',click);root.addEventListener('input',input);root.addEventListener('change',change);
      unsub=store.subscribe((_,meta)=>{if(meta.type==='snapshot'||meta.type==='snapshot-live')refreshData()});
    },
    render,
    destroy(){
      detailSeq++;unsub?.();
      root?.removeEventListener('click',click);root?.removeEventListener('input',input);root?.removeEventListener('change',change);root=null;
    }
  };
}
