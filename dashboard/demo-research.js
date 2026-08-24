(function(){
  if(window.__demoResearchLoaded)return;
  window.__demoResearchLoaded=true;

  const state={
    summary:null,selected:'',filter:'',status:'all',sort:'return_desc',detail:null,
    freezeUntil:0,lastSummarySignature:'',lastDetailSignature:'',pollTimer:0,
  };
  const q=(selector,root=document)=>root.querySelector(selector);
  const qa=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const n=value=>Number(value||0);
  const won=value=>`${Math.round(n(value)).toLocaleString('ko-KR')}원`;
  const pct=(value,d=2)=>`${n(value)>=0?'+':''}${n(value).toFixed(d)}%`;
  const tone=value=>n(value)>0?'positive':n(value)<0?'negative':'';
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const price=value=>{
    const v=n(value);if(!v)return '-';
    const digits=v>=1000?0:v>=100?1:v>=1?3:v>=.1?5:8;
    return `${v.toLocaleString('ko-KR',{maximumFractionDigits:digits})}원`;
  };
  const time=value=>value?new Date(n(value)*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-';
  const age=value=>{const s=Math.max(0,Date.now()/1000-n(value));if(!value)return'계산 전';if(s<60)return`${Math.round(s)}초 전`;if(s<3600)return`${Math.round(s/60)}분 전`;return`${(s/3600).toFixed(1)}시간 전`};
  const marketFromInput=value=>{const text=String(value||'').trim().toUpperCase();if(!text)return'';return text.startsWith('KRW-')?text:`KRW-${text.replace(/^KRW[-/]/,'')}`};
  const intentLabel=value=>({buy:'신규 매수',explore:'탐색 매수',idle_explore:'장기대기 탐색',add:'추가 매수',sell:'매도',hold:'보유',wait:'관찰',analysis_error:'분석 오류'})[value]||value||'관찰';
  const sideLabel=value=>value==='buy'?'매수':'매도';
  const stateClass=row=>row?.state_class||(row?.has_position?'holding':n(row?.closed_trades)>0?'completed_waiting':'untraded');
  const stateLabel=row=>row?.state_label||({holding:'보유 중',completed_waiting:'매매 완료 · 대기',untraded:'미진입'})[stateClass(row)]||'대기';

  function markInteraction(ms=10000){state.freezeUntil=Math.max(state.freezeUntil,Date.now()+ms)}

  function ensureHome(){
    const overview=q('[data-view-panel="overview"]');if(!overview)return null;
    let card=q('#autoDemoCard');
    if(!card){card=document.createElement('section');card.id='autoDemoCard';card.className='panel auto-demo-card demo-home-card';const holdings=q('#myHoldingsOverview');(holdings||overview.querySelector('.kpi-grid'))?.insertAdjacentElement('afterend',card)}
    return card;
  }

  function ensureResearch(){
    const panel=q('[data-view-panel="performance"]');if(!panel)return null;
    let root=q('#demoResearch');if(root)return root;
    root=document.createElement('section');root.id='demoResearch';root.className='panel demo-research';
    root.innerHTML=`
      <div class="demo-head">
        <div><p class="demo-kicker">PAPER RESEARCH</p><h3>전체 코인 자동매매 연구</h3><p>빗썸 원화마켓 전체를 코인별 독립 1,000만원 계좌로 비교합니다. 실제 주문은 없습니다.</p></div>
        <div class="demo-head-actions"><span id="demoRunPill" class="status-pill neutral">준비 중</span><button id="demoRefresh" type="button" class="button secondary compact">지금 갱신</button></div>
      </div>
      <div id="demoSummaryGrid" class="demo-summary-grid"></div>
      <div id="demoBest" class="demo-best"></div>
      <div class="demo-layout">
        <aside class="demo-leaderboard">
          <div class="demo-list-head"><div><b>전체 코인</b><span id="demoListCount">0개</span></div><small id="demoRefreshHint">자동 갱신</small></div>
          <div class="demo-list-controls">
            <input id="demoSearch" class="demo-search" inputmode="search" placeholder="코인 검색 · BTC, XRP, B3..." autocomplete="off">
            <select id="demoSort" class="demo-sort" aria-label="정렬 기준">
              <option value="return_desc">수익률 높은순</option>
              <option value="position_desc">보유금액 높은순</option>
              <option value="unrealized_desc">미실현손익 높은순</option>
              <option value="trades_desc">거래횟수 많은순</option>
              <option value="win_desc">승률 높은순</option>
              <option value="drawdown_asc">최대낙폭 작은순</option>
              <option value="opportunity_desc">기회점수 높은순</option>
              <option value="price_desc">현재가 높은순</option>
            </select>
          </div>
          <div id="demoStatusFilters" class="demo-filter-chips" aria-label="상태 필터">
            <button type="button" class="is-active" data-filter="all">전체</button>
            <button type="button" data-filter="holding">보유 중</button>
            <button type="button" data-filter="completed_waiting">매매 완료 · 대기</button>
            <button type="button" data-filter="untraded">미진입</button>
            <button type="button" data-filter="profit">수익</button>
            <button type="button" data-filter="loss">손실</button>
          </div>
          <div id="demoList" class="demo-list"></div>
        </aside>
        <div id="demoDetail" class="demo-detail"><div class="demo-detail-empty">코인을 선택하면 현재가, 평단, 보유금액, 매매계획과 누적 시장 움직임을 확인할 수 있습니다.</div></div>
      </div>`;
    const performanceGrid=q('#performanceGrid');performanceGrid?.insertAdjacentElement('beforebegin',root);
    q('#demoSearch',root)?.addEventListener('input',event=>{state.filter=event.target.value.trim().toUpperCase();markInteraction();renderLeaderboard()});
    q('#demoSearch',root)?.addEventListener('keydown',event=>{if(event.key!=='Enter')return;event.preventDefault();const market=marketFromInput(event.currentTarget.value);if(market)selectMarket(market)});
    q('#demoSort',root)?.addEventListener('change',event=>{state.sort=event.target.value;markInteraction();renderLeaderboard()});
    qa('#demoStatusFilters button',root).forEach(button=>button.addEventListener('click',()=>{
      state.status=button.dataset.filter||'all';markInteraction();qa('#demoStatusFilters button',root).forEach(item=>item.classList.toggle('is-active',item===button));renderLeaderboard();
    }));
    q('#demoRefresh',root)?.addEventListener('click',()=>{state.freezeUntil=0;refresh({force:true})});
    root.addEventListener('pointerdown',()=>markInteraction(),{passive:true});
    root.addEventListener('touchstart',()=>markInteraction(),{passive:true});
    q('#demoList',root)?.addEventListener('scroll',()=>markInteraction(7000),{passive:true});
    return root;
  }

  function rowsFromSummary(){return Array.isArray(state.summary?.leaderboard)?state.summary.leaderboard:[]}

  function filteredRows(){
    let rows=[...rowsFromSummary()];
    if(state.filter)rows=rows.filter(row=>`${row.symbol||''} ${row.market||''} ${row.name||''}`.toUpperCase().includes(state.filter));
    if(state.status==='holding')rows=rows.filter(row=>stateClass(row)==='holding');
    else if(state.status==='completed_waiting')rows=rows.filter(row=>stateClass(row)==='completed_waiting');
    else if(state.status==='untraded')rows=rows.filter(row=>stateClass(row)==='untraded');
    else if(state.status==='profit')rows=rows.filter(row=>n(row.return_pct)>0);
    else if(state.status==='loss')rows=rows.filter(row=>n(row.return_pct)<0);
    const comparators={
      return_desc:(a,b)=>n(b.return_pct)-n(a.return_pct),
      position_desc:(a,b)=>n(b.position_value_krw)-n(a.position_value_krw),
      unrealized_desc:(a,b)=>n(b.unrealized_pnl_krw)-n(a.unrealized_pnl_krw),
      trades_desc:(a,b)=>n(b.closed_trades)-n(a.closed_trades)||n(b.return_pct)-n(a.return_pct),
      win_desc:(a,b)=>n(b.win_rate_pct)-n(a.win_rate_pct)||n(b.closed_trades)-n(a.closed_trades),
      drawdown_asc:(a,b)=>Math.abs(n(a.max_drawdown_pct))-Math.abs(n(b.max_drawdown_pct)),
      opportunity_desc:(a,b)=>n(b.opportunity_score)-n(a.opportunity_score),
      price_desc:(a,b)=>n(b.price)-n(a.price),
    };
    rows.sort(comparators[state.sort]||comparators.return_desc);
    return rows;
  }

  function renderHome(){
    const card=ensureHome(),data=state.summary;if(!card)return;
    if(!data){card.innerHTML='<p class="muted">전체 코인 가상매매 상태를 불러오는 중입니다.</p>';return}
    const rows=rowsFromSummary(),best=data.best_market||rows[0];
    const completedWaiting=rows.filter(row=>stateClass(row)==='completed_waiting').length;
    card.innerHTML=`
      <div class="panel-head"><div><h3>코인별 1,000만원 가상매매</h3><p class="panel-copy">빗썸 모든 원화마켓을 같은 출발선에서 비교합니다.</p></div><span class="status-pill ${data.running?'good':'neutral'}">${data.running?'연구 중':'대기'}</span></div>
      <div class="demo-home-best"><span>현재 수익률 1위</span><b>${best?`${esc(best.symbol)} <span class="${tone(best.return_pct)}">${pct(best.return_pct)}</span>`:'집계 중'}</b></div>
      <div class="demo-home-grid"><div><span>전체 대상</span><b>${n(data.market_count).toLocaleString('ko-KR')}개</b></div><div><span>보유 중</span><b>${n(data.active_positions).toLocaleString('ko-KR')}개</b></div><div><span>매매 완료 · 대기</span><b>${completedWaiting.toLocaleString('ko-KR')}개</b></div><div><span>최종 갱신</span><b>${age(data.updated_at)}</b></div></div>
      <p class="demo-home-note">결과 탭에서 정렬·필터, 코인별 평단/보유금액, 동적 익절·손절과 시장 움직임 누적 기록을 확인할 수 있습니다.</p>`;
  }

  function renderSummary(){
    const data=state.summary,root=ensureResearch();if(!root||!data)return;
    const rows=rowsFromSummary(),best=data.best_market||rows[0];
    const avg=rows.length?rows.reduce((sum,row)=>sum+n(row.return_pct),0)/rows.length:0;
    const holding=rows.filter(row=>stateClass(row)==='holding').length;
    const completedWaiting=rows.filter(row=>stateClass(row)==='completed_waiting').length;
    const untraded=rows.filter(row=>stateClass(row)==='untraded').length;
    const pill=q('#demoRunPill',root);if(pill){pill.textContent=data.running?'가상매매 중':'대기';pill.className=`status-pill ${data.running?'good':'neutral'}`;}
    q('#demoSummaryGrid',root).innerHTML=`
      <div class="demo-stat"><span>전체 연구 대상</span><strong>${n(data.market_count).toLocaleString('ko-KR')}개</strong><small>코인별 독립 1,000만원</small></div>
      <div class="demo-stat"><span>보유 중</span><strong>${holding.toLocaleString('ko-KR')}개</strong><small>현재 포지션 있음</small></div>
      <div class="demo-stat"><span>매매 완료 · 대기</span><strong>${completedWaiting.toLocaleString('ko-KR')}개</strong><small>청산 후 다음 기회 대기</small></div>
      <div class="demo-stat"><span>아직 미진입</span><strong>${untraded.toLocaleString('ko-KR')}개</strong><small>탐색/조건 확인 중</small></div>
      <div class="demo-stat"><span>전체 평균 수익률</span><strong class="${tone(avg)}">${pct(avg)}</strong><small>전체 가상계좌 기준</small></div>`;
    const progress=n(data.scan_total)>0?Math.min(100,n(data.scanned_count)/n(data.scan_total)*100):0;
    q('#demoBest',root).innerHTML=`<div class="demo-best-top"><div><span>현재 수익률 1위</span><strong>${best?esc(best.symbol):'집계 중'}</strong><small>${best?esc(best.name||best.market):''}</small></div><b class="demo-return ${tone(best?.return_pct)}">${best?pct(best.return_pct):'-'}</b></div><div class="demo-progress"><i style="width:${progress.toFixed(1)}%"></i></div><div class="demo-best-meta"><span>전체 스캔 ${n(data.scanned_count).toLocaleString('ko-KR')} / ${n(data.scan_total).toLocaleString('ko-KR')}</span><span>갱신 ${age(data.updated_at)}</span></div>`;
    const hint=q('#demoRefreshHint',root);if(hint)hint.textContent=`자동 갱신 · ${age(data.updated_at)}`;
    renderLeaderboard();
  }

  function renderLeaderboard(){
    const root=q('#demoResearch'),list=q('#demoList',root),data=state.summary;if(!list||!data)return;
    const oldScroll=list.scrollTop;
    const rows=filteredRows(),fullCount=rowsFromSummary().length;
    const count=q('#demoListCount',root);if(count)count.textContent=(state.filter||state.status!=='all')?`${rows.length} / ${fullCount}개`:`${fullCount}개`;
    if(!state.selected&&rows.length)state.selected=rows[0].market;
    list.innerHTML=rows.map((row,index)=>{
      const cls=stateClass(row),label=stateLabel(row),has=row.has_position;
      return `<button type="button" class="demo-rank-row ${row.market===state.selected?'is-active':''}" data-market="${esc(row.market)}">
        <span class="demo-rank ${index<3?'top':''}">${index+1}</span>
        <span class="demo-rank-main"><span class="demo-rank-name"><b>${esc(row.symbol)}</b><i class="state-${cls}">${esc(label)}</i></span><small>${esc(row.name||row.market)} · ${intentLabel(row.trade_intent)}</small></span>
        <span class="demo-rank-price"><b>${price(row.price)}</b><small>${has?`평단 ${price(row.position_avg_price)}`:'평단 -'}</small></span>
        <span class="demo-rank-holding"><b>${has?won(row.position_value_krw):'-'}</b><small>${has?'보유금액':'보유 없음'}</small></span>
        <span class="demo-rank-side"><b class="${tone(row.return_pct)}">${pct(row.return_pct)}</b><small>${n(row.closed_trades)}회 · 승률 ${n(row.win_rate_pct).toFixed(0)}%</small></span>
      </button>`;
    }).join('')||'<div class="demo-detail-empty">조건에 맞는 코인이 없습니다.</div>';
    qa('.demo-rank-row',list).forEach(button=>button.addEventListener('click',()=>selectMarket(button.dataset.market)));
    requestAnimationFrame(()=>{list.scrollTop=oldScroll});
  }

  async function selectMarket(market){state.selected=market;markInteraction(7000);renderLeaderboard();await loadDetail(market,{force:true})}

  function lineSvg(points,valueKey,{zero=false}={}){
    const valid=(Array.isArray(points)?points:[]).map(row=>n(row[valueKey])).filter(Number.isFinite);
    if(valid.length<2)return '<div class="demo-detail-empty">기록을 수집하는 중입니다.</div>';
    const min=Math.min(...valid),max=Math.max(...valid),span=Math.max(1e-9,max-min);
    const coords=valid.map((value,index)=>`${(index/(valid.length-1)*100).toFixed(2)},${(92-(value-min)/span*82).toFixed(2)}`).join(' ');
    let zeroLine='';
    if(zero&&min<=0&&max>=0){const y=92-(0-min)/span*82;zeroLine=`<line x1="0" y1="${y.toFixed(2)}" x2="100" y2="${y.toFixed(2)}" stroke="rgba(80,90,110,.15)" stroke-width="1"/>`;}
    return `<svg viewBox="0 0 100 100" preserveAspectRatio="none">${zeroLine}<polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function profileChange(feedback){const before=feedback.profile_before||{},after=feedback.profile_after||{};return `<div class="demo-feedback-grid"><span>시장 ${n(before.regime_floor).toFixed(1)} → <b>${n(after.regime_floor).toFixed(1)}</b></span><span>진입 ${n(before.entry_floor).toFixed(1)} → <b>${n(after.entry_floor).toFixed(1)}</b></span><span>기본비중 ${n(before.base_weight_pct).toFixed(1)}% → <b>${n(after.base_weight_pct).toFixed(1)}%</b></span></div>`}

  function detailSignature(data){
    const s=data?.summary||{},plan=data?.trade_plan||{},fills=data?.fills||[],feedback=data?.feedback||[],memory=data?.market_memory||[];
    return [s.market,s.signal_ts,s.return_pct,plan.updated_at,fills.length,feedback.length,memory.length,memory.at?.(-1)?.signal_ts||''].join('|');
  }

  async function loadDetail(market,{force=false}={}){
    const root=q('#demoResearch'),detail=q('#demoDetail',root);if(!detail||!market)return;
    try{
      const response=await fetch(`./demo-runtime/${encodeURIComponent(market)}.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error(`${response.status}`);
      const data=await response.json();const signature=detailSignature(data);
      if(!force&&signature===state.lastDetailSignature)return;
      state.lastDetailSignature=signature;state.detail=data;
      const s=data.summary||{},signal=data.signal||{},profile=data.profile||{},position=data.position||{},plan=data.trade_plan||{},fills=Array.isArray(data.fills)?data.fills:[],feedback=Array.isArray(data.feedback)?data.feedback:[],history=Array.isArray(data.equity_history)?data.equity_history:[],memory=Array.isArray(data.market_memory)?data.market_memory:[];
      const latestBuy=fills.find(row=>row.side==='buy');
      const latestMemory=memory[memory.length-1]||{};
      const currentPrice=n(plan.current_price||position.current_price||s.price||signal.price);
      const avgPrice=n(position.avg_price||plan.position_avg_price||s.position_avg_price);
      const hasPosition=n(position.volume)>0||s.has_position;
      const targetPrice=n(plan.target_price),stopPrice=n(plan.hard_stop_price),trailPrice=n(plan.trailing_stop_price),nextAdd=n(plan.next_add_price),entryRef=n(plan.expected_entry_price);
      const completed=n(plan.completed_entries||position.buy_count),total=n(plan.expected_total_entries),remaining=n(plan.remaining_entries);
      const targetCopy=hasPosition&&targetPrice?`${price(targetPrice)} · ${pct(plan.target_profit_pct)}`:'포지션 생성 후 계산';
      const nextBuyCopy=hasPosition?(nextAdd?price(nextAdd):remaining<=0?'예상 회차 완료':'점수·가격 대기'):(entryRef?price(entryRef):'조건 충족 시 시장가');
      const trailCopy=trailPrice?price(trailPrice):hasPosition?`+${n(plan.trail_arm_pct).toFixed(1)}%부터 추적`:'미작동';
      const updateTs=n(plan.updated_at||signal.ts||s.signal_ts);
      const cls=data.state_class||stateClass(s),label=data.state_label||stateLabel(s);
      detail.innerHTML=`
        <div class="demo-detail-head">
          <div><div class="demo-symbol-line"><h4>${esc(s.symbol||market.replace('KRW-',''))}</h4><span>${esc(s.name||market)}</span><i class="state-${cls}">${esc(label)}</i></div><p>PAPER 프로필 v${n(s.profile_version||profile.version||1)} · 최종 계산 ${age(updateTs)}</p></div>
          <strong class="demo-return ${tone(s.return_pct)}">${pct(s.return_pct)}</strong>
        </div>

        <section class="demo-live-hero">
          <div class="demo-live-price"><span>현재 가격</span><strong>${price(currentPrice)}</strong><small class="${tone(signal.change_24h_pct)}">24시간 ${pct(signal.change_24h_pct)}</small></div>
          <div class="demo-live-position">
            <div class="key"><span>평균 진입가</span><b>${hasPosition?price(avgPrice):latestBuy?`최근 ${price(latestBuy.price)}`:'미진입'}</b></div>
            <div class="key"><span>현재 보유금액</span><b>${hasPosition?won(position.value_krw):'0원'}</b><small>${hasPosition?`계좌의 ${n(position.weight_pct||plan.position_weight_pct).toFixed(1)}%`:'포지션 없음'}</small></div>
            <div class="key"><span>미실현 손익</span><b class="${tone(position.unrealized_pnl_krw)}">${hasPosition?won(position.unrealized_pnl_krw):'-'}</b><small class="${tone(position.unrealized_pnl_pct)}">${hasPosition?pct(position.unrealized_pnl_pct):''}</small></div>
          </div>
        </section>

        <section class="demo-plan-panel">
          <div class="demo-plan-head"><div><span>현재 매매 계획</span><b>${intentLabel(signal.trade_intent)}</b></div><span class="demo-live-dot">스캔마다 자동 재계산</span></div>
          <div class="demo-plan-grid">
            <div class="primary"><span>${hasPosition?'다음 추가매수 기준':'예상 진입'}</span><strong>${nextBuyCopy}</strong><small>${hasPosition?`기회점수·호가·${Math.ceil(n(plan.cooldown_remaining_seconds)/60)}분 쿨다운 확인`:'가격 단독이 아니라 시장·호가·점수 동시 확인'}</small></div>
            <div class="primary target"><span>현재 익절 예상가</span><strong>${targetCopy}</strong><small>시장·진입·변동성 변화에 따라 다음 스캔에서 조정</small></div>
            <div><span>예상 매수 회차</span><b>${total?`${Math.round(completed)} / ${Math.round(total)}회`:'계산 중'}</b><small>남은 예상 ${Math.max(0,Math.round(remaining))}회</small></div>
            <div><span>이번 진입 비중</span><b>${n(plan.suggested_weight_pct||signal.suggested_weight_pct).toFixed(1)}%</b><small>코인별 1,000만원 기준</small></div>
            <div><span>추적 보호가</span><b>${trailCopy}</b><small>고점 상승 시 보호가격도 위로 이동</small></div>
            <div class="risk"><span>현재 손절 기준</span><b>${stopPrice?`${price(stopPrice)} · ${n(plan.hard_stop_pct).toFixed(1)}%`:'포지션 생성 후 계산'}</b><small>변동성·시장상태 반영</small></div>
          </div>
        </section>

        <div class="demo-score-line"><div><span>기회 점수</span><b>${n(signal.opportunity_score).toFixed(1)}</b></div><div><span>시장</span><b>${n(signal.regime_score).toFixed(1)}</b></div><div><span>진입</span><b>${n(signal.entry_score).toFixed(1)}</b></div><div><span>유동성</span><b>${n(signal.liquidity_score).toFixed(1)}</b></div></div>

        <div class="demo-section-title memory-title"><div><h5>시장 움직임 누적 기록</h5><small>향후 AI 분석용 시장 메모리</small></div><b>${n(data.market_memory_count||memory.length).toLocaleString('ko-KR')}개 스냅샷</b></div>
        <div class="demo-memory-chart">${lineSvg(memory,'price')}</div>
        <div class="demo-memory-traits">
          <div><span>최근 스캔 가격변화</span><b class="${tone(latestMemory.price_delta_pct)}">${pct(latestMemory.price_delta_pct||0,3)}</b></div>
          <div><span>최근 구간 수익률</span><b class="${tone(latestMemory.asset_return_pct)}">${pct(latestMemory.asset_return_pct||signal.asset_return_pct,2)}</b></div>
          <div><span>변동성</span><b>${n(latestMemory.volatility_pct||signal.volatility_pct).toFixed(2)}%</b></div>
          <div><span>고점 대비 눌림</span><b>${n(latestMemory.pullback_pct||signal.pullback_pct).toFixed(2)}%</b></div>
          <div><span>호가 균형</span><b>${n(latestMemory.orderbook_imbalance||signal.orderbook_imbalance).toFixed(3)}</b></div>
          <div><span>기회점수 변화</span><b class="${tone(latestMemory.opportunity_delta)}">${n(latestMemory.opportunity_delta).toFixed(2)}</b></div>
        </div>
        <p class="demo-memory-note">가격뿐 아니라 시장·진입·기회점수, 변동성, 눌림폭, 호가 불균형 등 당시 특징을 DB에 스캔별로 누적합니다. 이후 코인별 패턴과 성공/실패 조건을 AI가 비교하기 쉬운 구조입니다.</p>

        <div class="demo-section-title"><h5>가상계좌 수익 곡선</h5><small>최대 하락폭 ${n(s.max_drawdown_pct).toFixed(2)}%</small></div>
        <div class="demo-chart ${tone(s.return_pct)}">${lineSvg(history,'return_pct',{zero:true})}</div>

        <div class="demo-section-title"><h5>매매 내역</h5><small>가격 · 금액 · 비중 · 결과</small></div>
        <div class="demo-trade-head"><span>시점</span><span>구분</span><span>체결가</span><span>금액</span><span>비중</span><span>결과</span><span>근거</span></div>
        <div class="demo-trades">${fills.length?fills.map(row=>`<div class="demo-trade"><span>${time(row.ts)}</span><b class="${row.side}">${sideLabel(row.side)}</b><span>${price(row.price)}</span><span>${won(row.krw)}</span><span>${n(row.weight_pct).toFixed(1)}%</span><span class="${tone(row.return_pct)}">${row.side==='sell'?`${pct(row.return_pct)}<small>${won(row.realized_pnl)}</small>`:'-'}</span><small class="demo-trade-reason" title="${esc(row.reason)}">${esc(row.reason)}</small></div>`).join(''):'<div class="demo-detail-empty">아직 체결된 가상매매가 없습니다.</div>'}</div>

        <div class="demo-section-title"><h5>자동 개선 기록</h5><small>종료된 거래를 다음 매매에 반영</small></div>
        <div>${feedback.length?feedback.map(row=>`<div class="demo-feedback"><b class="${tone(row.outcome_return_pct)}">${pct(row.outcome_return_pct)} · ${esc(row.note)}</b><p>보유 ${Math.max(0,n(row.holding_seconds)/3600).toFixed(1)}시간 · 확정 ${won(row.realized_pnl)}</p>${profileChange(row)}</div>`).join(''):'<div class="demo-detail-empty">거래가 종료되면 이 코인의 기준과 비중 변화가 여기에 누적됩니다.</div>'}</div>`;
    }catch(err){if(force)detail.innerHTML='<div class="demo-detail-empty">아직 이 코인의 최신 분석 파일이 없습니다. 전체 스캔 이후 자동 생성됩니다.</div>'}
  }

  function summarySignature(data){return [data?.updated_at,data?.scan_number,data?.scanned_count,data?.active_positions,data?.leaderboard?.length].join('|')}

  async function refresh({force=false}={}){
    ensureResearch();ensureHome();
    if(!force&&(Date.now()<state.freezeUntil||document.hidden))return;
    try{
      const data=await api('/api/demo');
      const signature=summarySignature(data);state.summary=data;
      renderHome();
      if(force||signature!==state.lastSummarySignature){state.lastSummarySignature=signature;renderSummary();}
      const rows=rowsFromSummary();
      if(!state.selected&&rows.length)state.selected=rows[0].market;
      if(state.selected)await loadDetail(state.selected,{force});
    }catch(err){const card=ensureHome();if(card)card.innerHTML='<p class="muted">가상매매 연구 엔진 연결을 확인하는 중입니다.</p>'}
  }

  function install(){
    ensureResearch();ensureHome();refresh({force:true});
    state.pollTimer=window.setInterval(()=>refresh({force:false}),15000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh({force:false})});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
