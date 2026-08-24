(function(){
  if(window.__demoResearchLoaded)return;
  window.__demoResearchLoaded=true;

  const state={summary:null,selected:'',filter:''};
  const q=(selector,root=document)=>root.querySelector(selector);
  const qa=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const won=value=>`${Math.round(Number(value||0)).toLocaleString('ko-KR')}원`;
  const percent=(value,d=2)=>`${Number(value||0)>=0?'+':''}${Number(value||0).toFixed(d)}%`;
  const tone=value=>Number(value||0)>0?'positive':Number(value||0)<0?'negative':'';
  const intentLabel=value=>({buy:'매수',explore:'탐색 매수',idle_explore:'장기대기 탐색',add:'추가 매수',sell:'매도',hold:'보유',wait:'관찰',analysis_error:'분석 오류'})[value]||value||'관찰';
  const sideLabel=value=>value==='buy'?'매수':'매도';
  const time=value=>value?new Date(Number(value)*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-';
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
      <div class="demo-head"><div><h3>전체 코인 자동매매 연구</h3><p>빗썸 원화마켓마다 독립된 1,000만원 가상계좌로 매매합니다. 결과가 좋은 코인을 위로 올리고, 종료된 거래의 피드백으로 해당 코인의 PAPER 프로필만 제한적으로 조정합니다.</p></div><span id="demoRunPill" class="status-pill neutral">준비 중</span></div>
      <div id="demoSummaryGrid" class="demo-summary-grid"></div>
      <div id="demoBest" class="demo-best"></div>
      <div class="demo-layout">
        <div class="demo-leaderboard"><input id="demoSearch" class="demo-search" inputmode="search" placeholder="코인 검색 · BTC, XRP, B3..." autocomplete="off"><div id="demoList" class="demo-list"></div><p class="demo-home-note">순위표 밖의 코인도 티커를 입력하고 Enter를 누르면 직접 조회할 수 있습니다.</p></div>
        <div id="demoDetail" class="demo-detail"><div class="demo-detail-empty">왼쪽에서 코인을 선택하면 매매 시점, 비중, 손익, 학습 결과를 표시합니다.</div></div>
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
    card.innerHTML=`<div class="panel-head"><div><h3>코인별 1,000만원 가상매매</h3><p class="panel-copy">빗썸 각 코인을 별도 1,000만원 계좌로 비교합니다.</p></div><span class="status-pill ${data.running?'good':'neutral'}">${data.running?'연구 중':'대기'}</span></div><div class="demo-home-best"><span>현재 수익률 1위</span><b>${best?`${esc(best.symbol)} <span class="${tone(best.return_pct)}">${percent(best.return_pct)}</span>`:'집계 중'}</b></div><div class="auto-demo-row"><span>연구 대상</span><b>${Number(data.market_count||0).toLocaleString('ko-KR')}개 코인</b></div><div class="auto-demo-row"><span>현재 스캔</span><b>${Number(data.scanned_count||0).toLocaleString('ko-KR')} / ${Number(data.scan_total||0).toLocaleString('ko-KR')}</b></div><div class="auto-demo-row"><span>포지션 보유</span><b>${Number(data.active_positions||0).toLocaleString('ko-KR')}개</b></div><p class="demo-home-note">실제 주문은 없습니다. 결과 탭에서 코인별 체결 시점, 주문 비중, 손익과 자동 조정된 PAPER 프로필을 확인할 수 있습니다.</p>`;
  }

  function renderSummary(){
    const data=state.summary,root=ensureResearch();if(!root||!data)return;
    const leaderboard=Array.isArray(data.leaderboard)?data.leaderboard:[],best=data.best_market||leaderboard[0];
    const avg=leaderboard.length?leaderboard.reduce((sum,row)=>sum+Number(row.return_pct||0),0)/leaderboard.length:0;
    q('#demoRunPill',root).textContent=data.running?'가상매매 중':'대기';q('#demoRunPill',root).className=`status-pill ${data.running?'good':'neutral'}`;
    q('#demoSummaryGrid',root).innerHTML=`<div class="demo-stat"><span>코인별 시작금</span><strong>1,000만원</strong><small>서로 독립된 계좌</small></div><div class="demo-stat"><span>전체 대상</span><strong>${Number(data.market_count||0).toLocaleString('ko-KR')}개</strong><small>빗썸 원화마켓</small></div><div class="demo-stat"><span>상위표 평균</span><strong class="${tone(avg)}">${percent(avg)}</strong><small>현재 표시된 상위 코인 기준</small></div><div class="demo-stat"><span>보유 중</span><strong>${Number(data.active_positions||0).toLocaleString('ko-KR')}개</strong><small>실제 주문 없음</small></div>`;
    const progress=Number(data.scan_total||0)>0?Math.min(100,Number(data.scanned_count||0)/Number(data.scan_total)*100):0;
    q('#demoBest',root).innerHTML=`<div class="demo-best-top"><div><span class="muted">현재 수익률 1위</span><strong>${best?esc(best.symbol):'집계 중'}</strong></div><b class="demo-return ${tone(best?.return_pct)}">${best?percent(best.return_pct):'-'}</b></div><div class="demo-progress"><i style="width:${progress.toFixed(1)}%"></i></div>`;
    renderLeaderboard();
  }

  function renderLeaderboard(){
    const root=q('#demoResearch'),list=q('#demoList',root),data=state.summary;if(!list||!data)return;
    let rows=Array.isArray(data.leaderboard)?data.leaderboard:[];
    if(state.filter)rows=rows.filter(row=>`${row.symbol||''} ${row.market||''} ${row.name||''}`.toUpperCase().includes(state.filter));
    if(!state.selected&&rows.length)state.selected=rows[0].market;
    list.innerHTML=rows.map((row,index)=>`<button type="button" class="demo-rank-row ${row.market===state.selected?'is-active':''}" data-market="${esc(row.market)}"><span class="demo-rank">${index+1}</span><span class="demo-rank-main"><b>${esc(row.symbol)}</b><small>${esc(row.name||row.market)} · ${intentLabel(row.trade_intent)}</small></span><span class="demo-rank-side"><b class="${tone(row.return_pct)}">${percent(row.return_pct)}</b><small>${Number(row.closed_trades||0)}회 · 승률 ${Number(row.win_rate_pct||0).toFixed(0)}%</small></span></button>`).join('')||'<div class="demo-detail-empty">상위표에는 없습니다. 티커 입력 후 Enter로 직접 조회할 수 있습니다.</div>';
    qa('.demo-rank-row',list).forEach(button=>button.addEventListener('click',()=>selectMarket(button.dataset.market)));
  }

  async function selectMarket(market){state.selected=market;renderLeaderboard();await loadDetail(market)}

  function equitySvg(points){
    if(!Array.isArray(points)||points.length<2)return '<div class="demo-detail-empty">수익 곡선을 수집하는 중입니다.</div>';
    const values=points.map(row=>Number(row.return_pct||0)),min=Math.min(...values),max=Math.max(...values),span=Math.max(.01,max-min);
    const coords=values.map((value,index)=>`${(index/(values.length-1)*100).toFixed(2)},${(92-(value-min)/span*82).toFixed(2)}`).join(' ');
    return `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="가상계좌 수익률 추이"><line x1="0" y1="92" x2="100" y2="92" stroke="rgba(80,90,110,.14)" stroke-width="1"/><polyline points="${coords}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }
  function profileChange(feedback){const before=feedback.profile_before||{},after=feedback.profile_after||{};return `<div class="demo-feedback-grid"><span>시장 ${Number(before.regime_floor||0).toFixed(1)} → <b>${Number(after.regime_floor||0).toFixed(1)}</b></span><span>진입 ${Number(before.entry_floor||0).toFixed(1)} → <b>${Number(after.entry_floor||0).toFixed(1)}</b></span><span>기본비중 ${Number(before.base_weight_pct||0).toFixed(1)}% → <b>${Number(after.base_weight_pct||0).toFixed(1)}%</b></span></div>`}

  async function loadDetail(market){
    const root=q('#demoResearch'),detail=q('#demoDetail',root);if(!detail||!market)return;detail.innerHTML='<div class="demo-detail-empty">코인별 결과를 불러오는 중입니다.</div>';
    try{
      const response=await fetch(`./demo-runtime/${encodeURIComponent(market)}.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw new Error(`${response.status}`);
      const data=await response.json(),s=data.summary||{},signal=data.signal||{},profile=data.profile||{},fills=Array.isArray(data.fills)?data.fills:[],feedback=Array.isArray(data.feedback)?data.feedback:[],history=Array.isArray(data.equity_history)?data.equity_history:[];
      detail.innerHTML=`<div class="demo-detail-head"><div><h4>${esc(s.symbol||market.replace('KRW-',''))}</h4><p>${esc(s.name||market)} · PAPER 프로필 v${Number(s.profile_version||profile.version||1)}</p></div><strong class="demo-return ${tone(s.return_pct)}">${percent(s.return_pct)}</strong></div><div class="demo-score-line"><div><span>기회 점수</span><b>${Number(signal.opportunity_score||0).toFixed(1)}</b></div><div><span>시장</span><b>${Number(signal.regime_score||0).toFixed(1)}</b></div><div><span>진입</span><b>${Number(signal.entry_score||0).toFixed(1)}</b></div></div><div class="demo-profile"><div><span>현재 판단</span><b>${intentLabel(signal.trade_intent)}</b></div><div><span>권장 비중</span><b>${Number(signal.suggested_weight_pct||0).toFixed(1)}%</b></div><div><span>누적 거래</span><b>${Number(s.closed_trades||0)}회</b></div><div><span>최대 하락폭</span><b>${Number(s.max_drawdown_pct||0).toFixed(2)}%</b></div></div><div class="demo-profile"><div><span>시장 기준</span><b>${Number(profile.regime_floor||0).toFixed(1)}</b></div><div><span>진입 기준</span><b>${Number(profile.entry_floor||0).toFixed(1)}</b></div><div><span>탐색 기준</span><b>${Number(profile.exploration_floor||0).toFixed(1)}</b></div><div><span>기본 비중</span><b>${Number(profile.base_weight_pct||0).toFixed(1)}%</b></div></div><div class="demo-chart ${tone(s.return_pct)}">${equitySvg(history)}</div><div class="demo-section-title"><h5>매매 내역</h5><small>시점 · 비중 · 결과</small></div><div class="demo-trades">${fills.length?fills.slice(0,30).map(row=>`<div class="demo-trade"><span>${time(row.ts)}</span><b class="${row.side}">${sideLabel(row.side)}</b><span>${won(row.krw)}<br><small>${Number(row.weight_pct||0).toFixed(1)}%</small></span><span class="${tone(row.return_pct)}">${row.side==='sell'?percent(row.return_pct):won(row.price)}</span><small class="demo-trade-reason" title="${esc(row.reason)}">${esc(row.reason)}</small></div>`).join(''):'<div class="demo-detail-empty">아직 체결된 가상매매가 없습니다.</div>'}</div><div class="demo-section-title"><h5>자동 개선 기록</h5><small>종료된 거래의 피드백</small></div><div>${feedback.length?feedback.slice(0,10).map(row=>`<div class="demo-feedback"><b class="${tone(row.outcome_return_pct)}">${percent(row.outcome_return_pct)} · ${esc(row.note)}</b><p>보유 ${Math.max(0,Number(row.holding_seconds||0)/3600).toFixed(1)}시간 · 확정 ${won(row.realized_pnl)}</p>${profileChange(row)}</div>`).join(''):'<div class="demo-detail-empty">거래가 종료되면 이 코인의 PAPER 기준과 비중 조정 기록이 여기에 쌓입니다.</div>'}</div>`;
    }catch(err){detail.innerHTML='<div class="demo-detail-empty">아직 이 코인의 첫 분석 파일이 없습니다. 전체 스캔이 진행된 뒤 다시 확인하세요.</div>'}
  }

  async function refresh(){
    ensureResearch();ensureHome();
    try{const data=await api('/api/demo');state.summary=data;renderHome();renderSummary();const rows=Array.isArray(data.leaderboard)?data.leaderboard:[];if(!state.selected&&rows.length)state.selected=rows[0].market;if(state.selected)await loadDetail(state.selected)}
    catch(err){const card=ensureHome();if(card)card.innerHTML='<p class="muted">가상매매 엔진이 최신 런타임으로 올라오기를 기다리고 있습니다.</p>'}
  }

  ensureResearch();ensureHome();refresh();setInterval(refresh,15000);
})();
