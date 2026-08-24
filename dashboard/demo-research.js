(function(){
  if(window.__demoResearchLoaded)return;
  window.__demoResearchLoaded=true;

  const state={summary:null,selected:'',filter:'',detail:null};
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
  const intentLabel=value=>({buy:'신규 매수',explore:'탐색 매수',idle_explore:'장기대기 탐색',add:'추가 매수',sell:'매도',hold:'보유',wait:'관찰',analysis_error:'분석 오류'})[value]||value||'관찰';
  const sideLabel=value=>value==='buy'?'매수':'매도';
  const time=value=>value?new Date(n(value)*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-';
  const age=value=>{const s=Math.max(0,Date.now()/1000-n(value));if(!value)return'계산 전';if(s<60)return`${Math.round(s)}초 전`;if(s<3600)return`${Math.round(s/60)}분 전`;return`${(s/3600).toFixed(1)}시간 전`};
  const marketFromInput=value=>{const text=String(value||'').trim().toUpperCase();if(!text)return'';return text.startsWith('KRW-')?text:`KRW-${text.replace(/^KRW[-/]/,'')}`};

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
        <div><p class="demo-kicker">PAPER RESEARCH</p><h3>전체 코인 자동매매 연구</h3><p>빗썸 원화마켓의 모든 코인을 각각 독립된 1,000만원으로 가상매매합니다. 실제 주문 없이 진입·추가매수·익절·손절·학습 결과를 비교합니다.</p></div>
        <span id="demoRunPill" class="status-pill neutral">준비 중</span>
      </div>
      <div id="demoSummaryGrid" class="demo-summary-grid"></div>
      <div id="demoBest" class="demo-best"></div>
      <div class="demo-layout">
        <aside class="demo-leaderboard">
          <div class="demo-list-head"><div><b>전체 코인 순위</b><span id="demoListCount">0개</span></div></div>
          <input id="demoSearch" class="demo-search" inputmode="search" placeholder="코인 검색 · BTC, XRP, B3..." autocomplete="off">
          <div id="demoList" class="demo-list"></div>
        </aside>
        <div id="demoDetail" class="demo-detail"><div class="demo-detail-empty">코인을 선택하면 현재 가격부터 진입·추가매수·익절 계획과 실제 가상 체결내역까지 표시합니다.</div></div>
      </div>`;
    const performanceGrid=q('#performanceGrid');performanceGrid?.insertAdjacentElement('beforebegin',root);
    const search=q('#demoSearch',root);
    search?.addEventListener('input',event=>{state.filter=event.target.value.trim().toUpperCase();renderLeaderboard()});
    search?.addEventListener('keydown',event=>{if(event.key!=='Enter')return;event.preventDefault();const market=marketFromInput(event.currentTarget.value);if(market)selectMarket(market)});
    return root;
  }

  function renderHome(){
    const card=ensureHome(),data=state.summary;if(!card)return;
    if(!data){card.innerHTML='<p class="muted">전체 코인 가상매매 상태를 불러오는 중입니다.</p>';return}
    const best=data.best_market||null;
    card.innerHTML=`
      <div class="panel-head"><div><h3>코인별 1,000만원 가상매매</h3><p class="panel-copy">빗썸 모든 원화마켓을 같은 출발선에서 비교합니다.</p></div><span class="status-pill ${data.running?'good':'neutral'}">${data.running?'연구 중':'대기'}</span></div>
      <div class="demo-home-best"><span>현재 수익률 1위</span><b>${best?`${esc(best.symbol)} <span class="${tone(best.return_pct)}">${pct(best.return_pct)}</span>`:'집계 중'}</b></div>
      <div class="demo-home-grid"><div><span>전체 대상</span><b>${n(data.market_count).toLocaleString('ko-KR')}개</b></div><div><span>현재 포지션</span><b>${n(data.active_positions).toLocaleString('ko-KR')}개</b></div><div><span>스캔 진행</span><b>${n(data.scanned_count).toLocaleString('ko-KR')} / ${n(data.scan_total).toLocaleString('ko-KR')}</b></div><div><span>최종 갱신</span><b>${age(data.updated_at)}</b></div></div>
      <p class="demo-home-note">결과 탭에서 코인별 현재가, 실제 가상 진입가, 예상 매수 회차, 동적 익절·손절가, 체결 비중과 알고리즘 개선 기록을 확인할 수 있습니다.</p>`;
  }

  function renderSummary(){
    const data=state.summary,root=ensureResearch();if(!root||!data)return;
    const rows=Array.isArray(data.leaderboard)?data.leaderboard:[],best=data.best_market||rows[0];
    const avg=rows.length?rows.reduce((sum,row)=>sum+n(row.return_pct),0)/rows.length:0;
    const traded=rows.filter(row=>n(row.closed_trades)>0||row.has_position).length;
    const pill=q('#demoRunPill',root);if(pill){pill.textContent=data.running?'가상매매 중':'대기';pill.className=`status-pill ${data.running?'good':'neutral'}`;}
    q('#demoSummaryGrid',root).innerHTML=`
      <div class="demo-stat"><span>코인별 시작금</span><strong>1,000만원</strong><small>코인마다 독립 계좌</small></div>
      <div class="demo-stat"><span>전체 연구 대상</span><strong>${n(data.market_count).toLocaleString('ko-KR')}개</strong><small>순위표에 전부 표시</small></div>
      <div class="demo-stat"><span>전체 평균 수익률</span><strong class="${tone(avg)}">${pct(avg)}</strong><small>현재 전체 계좌 기준</small></div>
      <div class="demo-stat"><span>매매 경험 코인</span><strong>${traded.toLocaleString('ko-KR')}개</strong><small>포지션 또는 종료거래 있음</small></div>`;
    const progress=n(data.scan_total)>0?Math.min(100,n(data.scanned_count)/n(data.scan_total)*100):0;
    q('#demoBest',root).innerHTML=`<div class="demo-best-top"><div><span>현재 수익률 1위</span><strong>${best?esc(best.symbol):'집계 중'}</strong><small>${best?esc(best.name||best.market):''}</small></div><b class="demo-return ${tone(best?.return_pct)}">${best?pct(best.return_pct):'-'}</b></div><div class="demo-progress"><i style="width:${progress.toFixed(1)}%"></i></div><div class="demo-best-meta"><span>전체 스캔 ${n(data.scanned_count).toLocaleString('ko-KR')} / ${n(data.scan_total).toLocaleString('ko-KR')}</span><span>갱신 ${age(data.updated_at)}</span></div>`;
    renderLeaderboard();
  }

  function renderLeaderboard(){
    const root=q('#demoResearch'),list=q('#demoList',root),data=state.summary;if(!list||!data)return;
    let rows=Array.isArray(data.leaderboard)?data.leaderboard:[];
    const fullCount=rows.length;
    if(state.filter)rows=rows.filter(row=>`${row.symbol||''} ${row.market||''} ${row.name||''}`.toUpperCase().includes(state.filter));
    const count=q('#demoListCount',root);if(count)count.textContent=state.filter?`${rows.length} / ${fullCount}개`:`${fullCount}개`;
    if(!state.selected&&rows.length)state.selected=rows[0].market;
    list.innerHTML=rows.map((row,index)=>`
      <button type="button" class="demo-rank-row ${row.market===state.selected?'is-active':''}" data-market="${esc(row.market)}">
        <span class="demo-rank ${index<3?'top':''}">${index+1}</span>
        <span class="demo-rank-main"><b>${esc(row.symbol)}</b><small>${esc(row.name||row.market)} · ${intentLabel(row.trade_intent)}</small></span>
        <span class="demo-rank-price"><b>${price(row.price)}</b><small>${row.has_position?`평단 ${price(row.position_avg_price)}`:'미진입'}</small></span>
        <span class="demo-rank-side"><b class="${tone(row.return_pct)}">${pct(row.return_pct)}</b><small>${n(row.closed_trades)}회 · 승률 ${n(row.win_rate_pct).toFixed(0)}%</small></span>
      </button>`).join('')||'<div class="demo-detail-empty">검색 결과가 없습니다.</div>';
    qa('.demo-rank-row',list).forEach(button=>button.addEventListener('click',()=>selectMarket(button.dataset.market)));
  }

  async function selectMarket(market){state.selected=market;renderLeaderboard();await loadDetail(market)}

  function equitySvg(points){
    if(!Array.isArray(points)||points.length<2)return '<div class="demo-detail-empty">수익 곡선을 수집하는 중입니다.</div>';
    const values=points.map(row=>n(row.return_pct)),min=Math.min(...values),max=Math.max(...values),span=Math.max(.01,max-min);
    const coords=values.map((value,index)=>`${(index/(values.length-1)*100).toFixed(2)},${(92-(value-min)/span*82).toFixed(2)}`).join(' ');
    const zero=max===min?92:92-(0-min)/span*82;
    return `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="가상계좌 수익률 추이"><line x1="0" y1="${Math.max(5,Math.min(95,zero)).toFixed(2)}" x2="100" y2="${Math.max(5,Math.min(95,zero)).toFixed(2)}" stroke="rgba(80,90,110,.15)" stroke-width="1"/><polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function profileChange(feedback){const before=feedback.profile_before||{},after=feedback.profile_after||{};return `<div class="demo-feedback-grid"><span>시장 ${n(before.regime_floor).toFixed(1)} → <b>${n(after.regime_floor).toFixed(1)}</b></span><span>진입 ${n(before.entry_floor).toFixed(1)} → <b>${n(after.entry_floor).toFixed(1)}</b></span><span>기본비중 ${n(before.base_weight_pct).toFixed(1)}% → <b>${n(after.base_weight_pct).toFixed(1)}%</b></span></div>`}

  function planValue(value,fallback='-'){return n(value)>0?price(value):fallback}

  async function loadDetail(market){
    const root=q('#demoResearch'),detail=q('#demoDetail',root);if(!detail||!market)return;
    detail.innerHTML='<div class="demo-detail-empty">코인별 실시간 계획과 매매내역을 불러오는 중입니다.</div>';
    try{
      const response=await fetch(`./demo-runtime/${encodeURIComponent(market)}.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error(`${response.status}`);
      const data=await response.json();state.detail=data;
      const s=data.summary||{},signal=data.signal||{},profile=data.profile||{},position=data.position||{},plan=data.trade_plan||{},fills=Array.isArray(data.fills)?data.fills:[],feedback=Array.isArray(data.feedback)?data.feedback:[],history=Array.isArray(data.equity_history)?data.equity_history:[];
      const latestBuy=fills.find(row=>row.side==='buy');
      const currentPrice=n(plan.current_price||position.current_price||s.price||signal.price);
      const avgPrice=n(position.avg_price||plan.position_avg_price||s.position_avg_price);
      const hasPosition=n(position.volume)>0||s.has_position;
      const targetPrice=n(plan.target_price);
      const stopPrice=n(plan.hard_stop_price);
      const trailPrice=n(plan.trailing_stop_price);
      const nextAdd=n(plan.next_add_price);
      const entryRef=n(plan.expected_entry_price);
      const completed=n(plan.completed_entries||position.buy_count);
      const total=n(plan.expected_total_entries);
      const remaining=n(plan.remaining_entries);
      const targetCopy=hasPosition&&targetPrice?`${price(targetPrice)} · ${pct(plan.target_profit_pct)}`:'포지션 생성 후 계산';
      const nextBuyCopy=hasPosition?(nextAdd?price(nextAdd):remaining<=0?'예상 회차 완료':'점수·가격 대기'):(entryRef?price(entryRef):'조건 충족 시 시장가');
      const trailCopy=trailPrice?price(trailPrice):hasPosition?`+${n(plan.trail_arm_pct).toFixed(1)}%부터 추적`:'미작동';
      const updateTs=n(plan.updated_at||signal.ts||s.signal_ts);
      detail.innerHTML=`
        <div class="demo-detail-head">
          <div><div class="demo-symbol-line"><h4>${esc(s.symbol||market.replace('KRW-',''))}</h4><span>${esc(s.name||market)}</span></div><p>PAPER 프로필 v${n(s.profile_version||profile.version||1)} · 최종 재계산 ${age(updateTs)}</p></div>
          <strong class="demo-return ${tone(s.return_pct)}">${pct(s.return_pct)}</strong>
        </div>

        <section class="demo-live-hero">
          <div class="demo-live-price"><span>현재 가격</span><strong>${price(currentPrice)}</strong><small class="${tone(signal.change_24h_pct)}">24시간 ${pct(signal.change_24h_pct)}</small></div>
          <div class="demo-live-position"><div><span>평균 진입가</span><b>${hasPosition?price(avgPrice):latestBuy?`최근 ${price(latestBuy.price)}`:'미진입'}</b></div><div><span>현재 포지션</span><b>${hasPosition?`${n(position.weight_pct||plan.position_weight_pct).toFixed(1)}%`:'없음'}</b></div><div><span>미실현 손익</span><b class="${tone(position.unrealized_pnl_krw)}">${hasPosition?`${won(position.unrealized_pnl_krw)} · ${pct(position.unrealized_pnl_pct)}`:'-'}</b></div></div>
        </section>

        <section class="demo-plan-panel">
          <div class="demo-plan-head"><div><span>현재 매매 계획</span><b>${intentLabel(signal.trade_intent)}</b></div><span class="demo-live-dot">스캔마다 자동 재계산</span></div>
          <div class="demo-plan-grid">
            <div class="primary"><span>${hasPosition?'다음 추가매수 기준':'예상 진입'}</span><strong>${nextBuyCopy}</strong><small>${hasPosition?`기회점수·호가·${Math.ceil(n(plan.cooldown_remaining_seconds)/60)}분 쿨다운도 함께 확인`:'가격 단독 주문이 아니라 점수와 호가를 같이 확인'}</small></div>
            <div class="primary target"><span>현재 익절 예상가</span><strong>${targetCopy}</strong><small>시장·진입·변동성이 바뀌면 다음 스캔에서 목표도 바뀜</small></div>
            <div><span>예상 매수 회차</span><b>${total?`${Math.round(completed)} / ${Math.round(total)}회`:'계산 중'}</b><small>남은 예상 ${Math.max(0,Math.round(remaining))}회</small></div>
            <div><span>이번 진입 비중</span><b>${n(plan.suggested_weight_pct||signal.suggested_weight_pct).toFixed(1)}%</b><small>코인별 1,000만원 기준</small></div>
            <div><span>추적 보호가</span><b>${trailCopy}</b><small>고점 상승 시 보호가격도 위로 이동</small></div>
            <div class="risk"><span>현재 손절 기준</span><b>${stopPrice?`${price(stopPrice)} · ${n(plan.hard_stop_pct).toFixed(1)}%`:'포지션 생성 후 계산'}</b><small>변동성·시장상태 반영</small></div>
          </div>
          <p class="demo-plan-note">${esc(plan.plan_note||'모든 가격은 최신 분석 때 다시 계산합니다. 실제 주문은 발생하지 않습니다.')}</p>
        </section>

        <div class="demo-score-line"><div><span>기회 점수</span><b>${n(signal.opportunity_score).toFixed(1)}</b></div><div><span>시장</span><b>${n(signal.regime_score).toFixed(1)}</b></div><div><span>진입</span><b>${n(signal.entry_score).toFixed(1)}</b></div><div><span>유동성</span><b>${n(signal.liquidity_score).toFixed(1)}</b></div></div>
        <div class="demo-profile"><div><span>시장 기준</span><b>${n(profile.regime_floor).toFixed(1)}</b></div><div><span>진입 기준</span><b>${n(profile.entry_floor).toFixed(1)}</b></div><div><span>탐색 기준</span><b>${n(profile.exploration_floor).toFixed(1)}</b></div><div><span>기본 비중</span><b>${n(profile.base_weight_pct).toFixed(1)}%</b></div></div>

        <div class="demo-section-title"><h5>가상계좌 수익 곡선</h5><small>최대 하락폭 ${n(s.max_drawdown_pct).toFixed(2)}%</small></div>
        <div class="demo-chart ${tone(s.return_pct)}">${equitySvg(history)}</div>

        <div class="demo-section-title"><h5>매매 내역</h5><small>가격 · 금액 · 비중 · 결과</small></div>
        <div class="demo-trade-head"><span>시점</span><span>구분</span><span>체결가</span><span>금액</span><span>비중</span><span>결과</span><span>근거</span></div>
        <div class="demo-trades">${fills.length?fills.map(row=>`<div class="demo-trade"><span>${time(row.ts)}</span><b class="${row.side}">${sideLabel(row.side)}</b><span>${price(row.price)}</span><span>${won(row.krw)}</span><span>${n(row.weight_pct).toFixed(1)}%</span><span class="${tone(row.return_pct)}">${row.side==='sell'?`${pct(row.return_pct)}<small>${won(row.realized_pnl)}</small>`:'-'}</span><small class="demo-trade-reason" title="${esc(row.reason)}">${esc(row.reason)}</small></div>`).join(''):'<div class="demo-detail-empty">아직 체결된 가상매매가 없습니다.</div>'}</div>

        <div class="demo-section-title"><h5>자동 개선 기록</h5><small>종료된 거래를 다음 매매에 반영</small></div>
        <div>${feedback.length?feedback.map(row=>`<div class="demo-feedback"><b class="${tone(row.outcome_return_pct)}">${pct(row.outcome_return_pct)} · ${esc(row.note)}</b><p>보유 ${Math.max(0,n(row.holding_seconds)/3600).toFixed(1)}시간 · 확정 ${won(row.realized_pnl)}</p>${profileChange(row)}</div>`).join(''):'<div class="demo-detail-empty">거래가 종료되면 이 코인의 진입 기준과 비중 변화가 여기에 누적됩니다.</div>'}</div>`;
    }catch(err){detail.innerHTML='<div class="demo-detail-empty">아직 이 코인의 최신 분석 파일이 없습니다. 전체 스캔이 지나간 뒤 자동으로 생성됩니다.</div>'}
  }

  async function refresh(){
    ensureResearch();ensureHome();
    try{
      const data=await api('/api/demo');state.summary=data;renderHome();renderSummary();
      const rows=Array.isArray(data.leaderboard)?data.leaderboard:[];
      if(!state.selected&&rows.length)state.selected=rows[0].market;
      if(state.selected)await loadDetail(state.selected);
    }catch(err){const card=ensureHome();if(card)card.innerHTML='<p class="muted">가상매매 연구 엔진 연결을 확인하는 중입니다.</p>'}
  }

  function install(){ensureResearch();ensureHome();refresh();setInterval(refresh,8000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
