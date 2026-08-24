(()=>{
  if(window.__cloudflareLocalParityLoaded)return;
  window.__cloudflareLocalParityLoaded=true;

  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const n=value=>Number(value||0);
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const won=value=>`${Math.round(n(value)).toLocaleString('ko-KR')}원`;
  const pct=(value,d=2)=>`${n(value)>=0?'+':''}${n(value).toFixed(d)}%`;
  const price=value=>{const v=n(value);if(!v)return'-';const digits=v>=1000?0:v>=100?1:v>=1?3:v>=.1?5:8;return `${v.toLocaleString('ko-KR',{maximumFractionDigits:digits})}원`};
  const tone=value=>n(value)>0?'parity-positive':n(value)<0?'parity-negative':'';
  const dt=value=>value?new Date(n(value)*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'-';
  const age=value=>{const sec=Math.max(0,Date.now()/1000-n(value));if(!value)return'갱신 대기';if(sec<60)return`${Math.round(sec)}초 전`;if(sec<3600)return`${Math.round(sec/60)}분 전`;return`${(sec/3600).toFixed(1)}시간 전`};
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));

  let selectedMarket='';
  let selectedSeq=0;
  let selectedInFlight='';
  let navController=null;
  let refreshTimer=0;

  function labelPages(){
    const labels={home:'개요',coin:'자산',results:'성과',records:'활동',settings:'설정'};
    $$('#viewerNav button[data-view]').forEach(button=>{button.textContent=labels[button.dataset.view]||button.textContent});
    const copy={
      home:['현재 상태','가상매매 연구 개요'],
      coin:['ASSET WORKSPACE','자산 분석'],
      results:['FORWARD TEST','PAPER 성과'],
      records:['JOURNAL','활동 기록'],
      settings:['SETTINGS','조회 설정'],
    };
    Object.entries(copy).forEach(([view,[kicker,title]])=>{
      const panel=$(`[data-view-panel="${view}"]`);if(!panel)return;
      const head=panel.querySelector(view==='home'?'.viewer-intro':'.page-head');if(!head)return;
      const k=head.querySelector('.kicker'),h=head.querySelector('h2');if(k)k.textContent=kicker;if(h)h.textContent=title;
    });
    const resultCopy=$('[data-view-panel="results"] .page-head p:not(.kicker)');
    if(resultCopy)resultCopy.textContent='빗썸 원화마켓 전체를 코인별 독립 가상계좌로 비교하고, 선택한 코인의 매매 계획과 누적 연구 데이터를 함께 봅니다.';
  }

  function ensureNavIndicator(root){
    let indicator=root.querySelector(':scope > .viewer-liquid-indicator');
    if(!indicator){indicator=document.createElement('span');indicator.className='viewer-liquid-indicator';indicator.setAttribute('aria-hidden','true');indicator.innerHTML='<span class="viewer-liquid-skin"></span>';root.prepend(indicator)}
    return indicator;
  }

  function installLiquidNav(){
    const root=$('.viewer-nav-inner');if(!root)return;
    if(navController){navController.update(true);return}
    let indicator=ensureNavIndicator(root);
    let state={x:0,w:0,ready:false};
    const active=()=>root.querySelector('button.active')||root.querySelector('button[data-view]');
    const update=(instant=false)=>{
      const item=active();if(!item)return;
      indicator=ensureNavIndicator(root);
      const x=item.offsetLeft,y=item.offsetTop,w=item.offsetWidth,h=item.offsetHeight;
      if(!w||!h)return;
      const distance=Math.max(Math.abs(x-state.x),Math.abs(w-state.w));
      const duration=Math.round(clamp(255+distance*.10,255,380));
      indicator.style.transition=(instant||!state.ready)?'none':`transform ${duration}ms cubic-bezier(0.34,1.56,0.64,1),width ${duration}ms cubic-bezier(0.34,1.56,0.64,1),height ${duration}ms cubic-bezier(0.34,1.56,0.64,1)`;
      indicator.style.width=`${w}px`;indicator.style.height=`${h}px`;indicator.style.transform=`translate3d(${x}px,${y}px,0)`;
      state={x,w,ready:true};root.classList.add('parity-nav-ready');
      $$('button[data-view]',root).forEach(button=>button.setAttribute('aria-selected',button===item?'true':'false'));
    };
    const observer=new MutationObserver(records=>{if(records.some(record=>record.type==='attributes'&&record.attributeName==='class'))requestAnimationFrame(()=>update(false))});
    observer.observe(root,{subtree:true,attributes:true,attributeFilter:['class']});
    root.addEventListener('click',()=>requestAnimationFrame(()=>update(false)));
    let resizeTimer=0;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>update(true),90)},{passive:true});
    navController={update};requestAnimationFrame(()=>update(true));
  }

  function ensureResearchLayout(){
    const panel=$('[data-view-panel="results"]');if(!panel)return null;
    let layout=$('#parityResearchLayout',panel);
    if(layout)return layout;
    const card=$('.results-card',panel);if(!card)return null;
    layout=document.createElement('section');layout.id='parityResearchLayout';layout.className='parity-research-layout';
    const detail=document.createElement('section');detail.id='parityResultDetail';detail.className='parity-result-detail';detail.innerHTML='<div class="parity-detail-empty">왼쪽에서 코인을 선택하면 로컬 대시보드와 같은 방식으로 상세 연구 내용을 표시합니다.</div>';
    card.parentNode.insertBefore(layout,card);layout.append(card,detail);card.classList.add('parity-leaderboard');
    installResultInteractions();
    return layout;
  }

  function chartPoints(values,width=620,height=150,pad=9,fixed=false){
    if(values.length<2)return'';
    let min=fixed?0:Math.min(...values),max=fixed?100:Math.max(...values);if(max===min){max+=1;min-=1}
    return values.map((value,index)=>{const x=pad+(width-pad*2)*(index/(values.length-1));const y=pad+(height-pad*2)*(1-(value-min)/(max-min));return`${x.toFixed(1)},${y.toFixed(1)}`}).join(' ');
  }

  function chart(title,rows,key,{fixed=false,secondary=false,formatValue=value=>String(value)}={}){
    const values=rows.map(row=>n(row?.[key])).filter(Number.isFinite);
    if(values.length<2)return `<div class="parity-chart"><div class="parity-chart-meta"><b>${esc(title)}</b><span>데이터 축적 중</span></div></div>`;
    const last=values[values.length-1];
    return `<div class="parity-chart"><div class="parity-chart-meta"><b>${esc(title)}</b><span>${esc(formatValue(last))}</span></div><svg viewBox="0 0 620 150" preserveAspectRatio="none"><line class="parity-chart-gridline" x1="0" y1="75" x2="620" y2="75"></line><polyline class="parity-chart-line ${secondary?'secondary':''}" points="${chartPoints(values,620,150,9,fixed)}"></polyline></svg></div>`;
  }

  function renderFills(rows){
    if(!rows.length)return'<div class="parity-detail-empty">아직 가상매매 체결이 없습니다.</div>';
    return rows.slice(0,8).map(row=>`<div class="parity-fill-row"><b>${row.side==='buy'?'매수':'매도'}</b><span>${price(row.price)}</span><span class="${tone(row.realized_pnl)}">${row.side==='sell'?`${n(row.realized_pnl)>=0?'+':''}${won(row.realized_pnl)}`:won(row.krw)}</span><small>${dt(row.ts)}</small></div>`).join('');
  }

  function renderLearning(rows){
    if(!rows.length)return'<div class="parity-detail-empty">완료 거래 학습 기록이 아직 없습니다.</div>';
    return rows.slice(0,6).map(row=>{const before=row.profile_before||{},after=row.profile_after||{};return `<div class="parity-learning"><b class="${tone(row.outcome_return_pct)}">${pct(row.outcome_return_pct)}</b><p>시장 기준 ${n(before.regime_floor).toFixed(1)} → ${n(after.regime_floor).toFixed(1)} · 매수 기준 ${n(before.entry_floor).toFixed(1)} → ${n(after.entry_floor).toFixed(1)}<br>${esc(row.note||'완료 거래를 반영해 학습 기준을 조정했습니다.')}</p></div>`}).join('');
  }

  function renderResearchDetail(detail,market){
    const root=$('#parityResultDetail');if(!root)return;
    if(!detail){root.innerHTML='<div class="parity-detail-empty">이 코인의 상세 연구 데이터가 아직 Cloudflare 순회에 도착하지 않았습니다.</div>';return}
    const data=detail.data||{},summary=data.summary||{},account=data.account||{},plan=data.trade_plan||{},signal=data.signal||{},memory=Array.isArray(data.market_memory)?data.market_memory:[],equity=Array.isArray(data.equity_history)?data.equity_history:[],fills=Array.isArray(data.fills)?data.fills:[],feedback=Array.isArray(data.feedback)?data.feedback:[];
    const next=n(plan.next_add_price)||n(plan.expected_entry_price);
    const nextLabel=n(plan.next_add_price)?'다음 추가매수':'예상 진입가';
    const symbol=summary.symbol||market.replace(/^KRW-/,'');
    const positionValue=n(summary.position_value_krw),cash=n(summary.cash_krw),avg=n(summary.position_avg_price)||n(account.avg_price);
    root.dataset.market=market;
    root.innerHTML=`
      <div class="parity-detail-head"><div><div class="parity-detail-title"><h3>${esc(symbol)}</h3><i class="parity-state">${esc(data.state_label||'연구 중')}</i><span>${esc(summary.name||market)}</span></div><span class="parity-detail-age">${esc(market)} · ${age(detail.source_ts||detail.received_at)}</span></div></div>
      <div class="parity-live-hero"><div class="parity-live-price"><span>현재가</span><strong>${price(summary.price||signal.price)}</strong><small class="${tone(summary.return_pct)}">가상계좌 ${pct(summary.return_pct)}</small></div><div class="parity-live-position"><div><span>가상계좌 평가액</span><b>${won(summary.equity_krw)}</b><small>독립 PAPER 계좌</small></div><div><span>남은 현금</span><b>${won(cash)}</b><small>대기 자금</small></div><div><span>현재 보유금액</span><b>${won(positionValue)}</b><small>${summary.has_position?'포지션 보유 중':'현재 미보유'}</small></div><div><span>평균 매수가</span><b>${avg?price(avg):'-'}</b></div><div><span>미실현 손익</span><b class="${tone(summary.unrealized_pnl_krw)}">${n(summary.unrealized_pnl_krw)>=0?'+':''}${won(summary.unrealized_pnl_krw)}</b></div><div><span>완료 거래</span><b>${n(summary.closed_trades).toLocaleString('ko-KR')}회</b><small>승률 ${n(summary.win_rate_pct).toFixed(1)}%</small></div></div></div>
      <div class="parity-plan-panel"><div class="parity-plan-head"><div><span>다음 매매 계획</span><b>${esc(signal.trade_intent||'관찰')}</b></div><span>${age(detail.source_ts||detail.received_at)}</span></div><div class="parity-plan-grid"><div class="primary"><span>${nextLabel}</span><strong>${price(next)}</strong><small>현재 조건에서 다음으로 검토하는 가격</small></div><div class="primary target"><span>목표가</span><strong>${price(plan.target_price)}</strong><small>현재 동적 청산 계획</small></div><div class="risk"><span>손절 기준</span><b>${price(plan.hard_stop_price)}</b></div><div><span>트레일링 기준</span><b>${n(plan.trailing_stop_price)?price(plan.trailing_stop_price):'아직 미활성'}</b></div><div><span>분할 진행</span><b>${Number(plan.completed_entries||0)} / ${Number(plan.expected_total_entries||0)}</b></div><div><span>남은 분할</span><b>${Number(plan.remaining_entries||0)}회</b></div></div></div>
      <div class="parity-score-line"><div><span>전체 시장 분위기</span><b>${n(summary.regime_score||signal.regime_score).toFixed(1)}</b></div><div><span>매수 타이밍</span><b>${n(summary.entry_score||signal.entry_score).toFixed(1)}</b></div><div><span>기회점수</span><b>${n(summary.opportunity_score||signal.opportunity_score).toFixed(1)}</b></div><div><span>제안 비중</span><b>${n(summary.suggested_weight_pct||signal.suggested_weight_pct).toFixed(2)}%</b></div></div>
      <div class="parity-section-title"><h4>누적 연구 흐름</h4><small>최근 저장 구간</small></div><div class="parity-chart-grid">${chart('가상계좌 자산곡선',equity,'equity_krw',{formatValue:won})}${chart('기회점수',memory,'opportunity_score',{fixed:true,secondary:true,formatValue:value=>`${value.toFixed(1)} / 100`})}</div>
      <div class="parity-detail-columns"><div class="parity-detail-box"><h4>최근 가상매매 체결</h4>${renderFills(fills)}</div><div class="parity-detail-box"><h4>최근 학습 변화</h4>${renderLearning(feedback)}</div></div>`;
  }

  async function loadResultDetail(market,{foreground=false}={}){
    if(!market||selectedInFlight===market)return;
    const root=$('#parityResultDetail');if(!root)return;
    const seq=++selectedSeq;selectedInFlight=market;
    if(foreground&&root.dataset.market!==market)root.innerHTML='<div class="parity-detail-empty">선택한 코인의 상세 연구 데이터를 불러오는 중입니다.</div>';
    try{
      const response=await fetch(`/api/market-detail?exchange=bithumb&strategy=adaptive&market=${encodeURIComponent(market)}`,{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)throw new Error(`요청 실패 ${response.status}`);
      const body=await response.json();if(seq!==selectedSeq||selectedMarket!==market)return;renderResearchDetail(body.detail||null,market);
    }catch(error){if(seq!==selectedSeq)return;if(foreground)root.innerHTML=`<div class="parity-detail-empty">${esc(error?.message||'상세 데이터를 불러오지 못했습니다.')}</div>`;else console.warn('parity detail refresh failed',error)}
    finally{if(selectedInFlight===market)selectedInFlight=''}
  }

  function applySelectedRow(){
    $$('#marketList [data-open-market]').forEach(row=>row.classList.toggle('is-active',row.dataset.openMarket===selectedMarket));
  }

  function selectResultMarket(market,{foreground=true}={}){
    if(!market)return;selectedMarket=market;applySelectedRow();loadResultDetail(market,{foreground});
  }

  function reconcileRows(){
    const rows=$$('#marketList [data-open-market]');if(!rows.length)return;
    if(!selectedMarket||!rows.some(row=>row.dataset.openMarket===selectedMarket))selectResultMarket(rows[0].dataset.openMarket,{foreground:true});else applySelectedRow();
  }

  function installResultInteractions(){
    const list=$('#marketList');if(!list||list.dataset.parityBound==='1')return;list.dataset.parityBound='1';
    list.addEventListener('click',event=>{const row=event.target.closest?.('[data-open-market]');if(!row)return;event.preventDefault();event.stopPropagation();event.stopImmediatePropagation();selectResultMarket(row.dataset.openMarket,{foreground:true})},true);
    const observer=new MutationObserver(()=>requestAnimationFrame(reconcileRows));observer.observe(list,{childList:true,subtree:true});
    list.addEventListener('scroll',applySelectedRow,{passive:true});reconcileRows();
  }

  function installViewHooks(){
    document.addEventListener('click',event=>{const button=event.target.closest?.('#viewerNav button[data-view]');if(!button)return;setTimeout(()=>{installLiquidNav();if(button.dataset.view==='results'){ensureResearchLayout();reconcileRows()}},40)});
    refreshTimer=setInterval(()=>{if($('[data-view-panel="results"]')?.classList.contains('active')&&selectedMarket)loadResultDetail(selectedMarket,{foreground:false})},30000);
  }

  function install(){labelPages();installLiquidNav();ensureResearchLayout();installViewHooks();setTimeout(reconcileRows,250)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
