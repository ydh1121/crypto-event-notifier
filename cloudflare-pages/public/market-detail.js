(()=>{
  if(window.__marketDetailViewerLoaded)return;
  window.__marketDetailViewerLoaded=true;

  const esc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const n=v=>Number(v||0);
  const won=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
  const pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const price=v=>{const x=n(v);if(!x)return'-';return `${x.toLocaleString('ko-KR',{maximumFractionDigits:x<1?8:x<100?4:2})}원`};
  const dt=ts=>n(ts)?new Date(n(ts)*1000).toLocaleString('ko-KR'):'-';
  const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  let lastMarket='';
  let requestSeq=0;
  let timer=0;

  function ensureShell(){
    let shell=document.getElementById('marketResearchDetail');
    if(shell)return shell;
    const anchor=document.getElementById('coinDetailCard');
    if(!anchor)return null;
    shell=document.createElement('section');
    shell.id='marketResearchDetail';
    shell.className='research-detail-shell';
    shell.innerHTML='<article class="research-detail-card"><div class="detail-empty">코인별 상세 연구 데이터를 불러오는 중입니다.</div></article>';
    anchor.insertAdjacentElement('afterend',shell);
    return shell;
  }

  function currentMarket(){return document.getElementById('coinSelect')?.value||''}
  function coinViewActive(){return document.querySelector('[data-view-panel="coin"]')?.classList.contains('active')}
  function ageText(ts){
    const sec=Math.max(0,Math.floor(Date.now()/1000-n(ts)));
    if(!ts)return'상세 데이터 대기';
    if(sec<60)return`${sec}초 전 갱신`;
    if(sec<3600)return`${Math.floor(sec/60)}분 전 갱신`;
    return`${Math.floor(sec/3600)}시간 전 갱신`;
  }

  function points(values,width=600,height=140,pad=8){
    const nums=values.map(n).filter(Number.isFinite);if(nums.length<2)return'';
    let min=Math.min(...nums),max=Math.max(...nums);if(max===min){max+=1;min-=1}
    return nums.map((value,index)=>{
      const x=pad+(width-pad*2)*(index/(nums.length-1));
      const y=pad+(height-pad*2)*(1-(value-min)/(max-min));
      return`${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  function equityChart(rows){
    const values=rows.map(row=>n(row.equity_krw));
    if(values.length<2)return'<div class="detail-empty">자산곡선 데이터가 아직 부족합니다.</div>';
    const last=values[values.length-1];
    return`<div class="mini-chart"><div class="mini-chart-head"><b>가상계좌 자산곡선</b><span>${won(last)}</span></div><svg viewBox="0 0 600 140" preserveAspectRatio="none"><line class="grid" x1="0" y1="70" x2="600" y2="70"></line><polyline class="equity" points="${points(values)}"></polyline></svg></div>`;
  }

  function scoreChart(rows){
    if(rows.length<2)return'<div class="detail-empty">판단 점수 이력이 아직 부족합니다.</div>';
    const regime=rows.map(row=>n(row.regime_score)),entry=rows.map(row=>n(row.entry_score)),opp=rows.map(row=>n(row.opportunity_score));
    const fixed=values=>values.map((value,index)=>`${8+(600-16)*(index/(Math.max(1,values.length-1)))},${8+(140-16)*(1-Math.max(0,Math.min(100,value))/100)}`).join(' ');
    return`<div class="mini-chart"><div class="mini-chart-head"><b>시장·매수 판단 점수</b><span>최근 ${rows.length}개 기록</span></div><svg viewBox="0 0 600 140" preserveAspectRatio="none"><line class="grid" x1="0" y1="70" x2="600" y2="70"></line><polyline class="regime" points="${fixed(regime)}"></polyline><polyline class="entry" points="${fixed(entry)}"></polyline><polyline class="opportunity" points="${fixed(opp)}"></polyline></svg><div class="chart-legend-mini"><span class="l-regime"><i></i>전체 시장 분위기</span><span class="l-entry"><i></i>매수 타이밍</span><span class="l-opportunity"><i></i>기회점수</span></div></div>`;
  }

  function planGrid(plan){
    const entries=`${Number(plan.completed_entries||0)} / ${Number(plan.expected_total_entries||0)}`;
    const next=n(plan.next_add_price)||n(plan.expected_entry_price);
    const nextLabel=n(plan.next_add_price)?'다음 추가매수 기준':'현재 예상 진입가';
    return`<div class="trade-plan-grid"><div><span>${nextLabel}</span><b>${price(next)}</b></div><div><span>목표가</span><b>${price(plan.target_price)}</b></div><div><span>손절 기준</span><b>${price(plan.hard_stop_price)}</b></div><div><span>트레일링 기준</span><b>${n(plan.trailing_stop_price)?price(plan.trailing_stop_price):'아직 미활성'}</b></div><div><span>분할 진행</span><b>${entries}</b></div><div><span>남은 분할</span><b>${Number(plan.remaining_entries||0)}회</b></div><div><span>이번 제안 비중</span><b>${n(plan.suggested_weight_pct).toFixed(2)}%</b></div><div><span>현재 수익률</span><b class="${tone(plan.unrealized_return_pct)}">${pct(plan.unrealized_return_pct)}</b></div></div>`;
  }

  function diagnostics(signal){
    const d=signal?.diagnostics||{};
    return`<div class="diagnostic-grid"><div><span>현재 되돌림</span><b>${pct(d.pullback_pct)}</b></div><div><span>최근 변동성</span><b>${n(d.volatility_pct).toFixed(2)}%</b></div><div><span>호가 균형</span><b>${n(d.orderbook_imbalance).toFixed(3)}</b></div><div><span>BTC 흐름</span><b class="${tone(d.btc_return_pct)}">${pct(d.btc_return_pct)}</b></div></div>`;
  }

  function fillsList(rows){
    if(!rows.length)return'<div class="detail-empty">아직 가상매매 체결이 없습니다.</div>';
    return`<div class="detail-list">${rows.slice(0,12).map(row=>`<div class="detail-row"><b>${row.side==='buy'?'매수':'매도'}</b><span>${price(row.price)}</span><span class="${tone(row.realized_pnl)}">${row.side==='sell'?`${n(row.realized_pnl)>=0?'+':''}${won(row.realized_pnl)}`:won(row.krw)}</span><small>${dt(row.ts)}</small></div>`).join('')}</div>`;
  }

  function feedbackList(rows){
    if(!rows.length)return'<div class="detail-empty">완료 거래 학습 기록이 아직 없습니다.</div>';
    return`<div class="detail-list">${rows.slice(0,8).map(row=>{
      const before=row.profile_before||{},after=row.profile_after||{};
      return`<div class="learning-row"><div><b class="${tone(row.outcome_return_pct)}">${pct(row.outcome_return_pct)}</b><span>${dt(row.ts)}</span></div><small>시장 기준 ${n(before.regime_floor).toFixed(1)} → ${n(after.regime_floor).toFixed(1)} · 매수 기준 ${n(before.entry_floor).toFixed(1)} → ${n(after.entry_floor).toFixed(1)} · ${esc(row.note||'학습 기준 조정')}</small></div>`;
    }).join('')}</div>`;
  }

  function render(detail){
    const shell=ensureShell();if(!shell)return;
    if(!detail){shell.innerHTML='<article class="research-detail-card"><div class="detail-empty">이 코인의 상세 데이터가 아직 Cloudflare 순회에 도착하지 않았습니다. 기본 가상계좌 정보는 위에서 계속 실시간으로 갱신됩니다.</div></article>';return}
    const data=detail.data||{},plan=data.trade_plan||{},signal=data.signal||{},fills=Array.isArray(data.fills)?data.fills:[],feedback=Array.isArray(data.feedback)?data.feedback:[],equity=Array.isArray(data.equity_history)?data.equity_history:[],memory=Array.isArray(data.market_memory)?data.market_memory:[];
    shell.innerHTML=`
      <article class="research-detail-card"><div class="research-detail-head"><div><p class="kicker">TRADE PLAN</p><h3>다음 매매 계획</h3></div><span class="detail-age">${esc(ageText(detail.source_ts||detail.received_at))}</span></div>${planGrid(plan)}${diagnostics(signal)}</article>
      <div class="detail-chart-grid">${equityChart(equity)}${scoreChart(memory)}</div>
      <div class="detail-columns"><article class="research-detail-card"><div class="research-detail-head"><div><p class="kicker">FILLS</p><h3>최근 가상매매 체결</h3></div><span class="detail-age">최대 12건 표시</span></div>${fillsList(fills)}</article><article class="research-detail-card"><div class="research-detail-head"><div><p class="kicker">LEARNING</p><h3>최근 학습 변화</h3></div><span class="detail-age">완료 거래 기준</span></div>${feedbackList(feedback)}</article></div>`;
  }

  async function load(force=false){
    if(document.hidden||!coinViewActive())return;
    const market=currentMarket();if(!market)return;
    if(!force&&market===lastMarket&&document.getElementById('marketResearchDetail')?.dataset.loaded==='1')return;
    lastMarket=market;const seq=++requestSeq;const shell=ensureShell();if(shell){shell.dataset.loaded='0';shell.innerHTML='<article class="research-detail-card"><div class="detail-empty">상세 연구 데이터를 불러오는 중입니다.</div></article>'}
    try{
      const response=await fetch(`/api/market-detail?exchange=bithumb&strategy=adaptive&market=${encodeURIComponent(market)}`,{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)throw new Error(`요청 실패 ${response.status}`);
      const body=await response.json();if(seq!==requestSeq)return;render(body.detail||null);const current=ensureShell();if(current)current.dataset.loaded='1';
    }catch(err){if(seq!==requestSeq)return;const current=ensureShell();if(current)current.innerHTML=`<article class="research-detail-card"><div class="detail-error">${esc(err?.message||'상세 데이터를 불러오지 못했습니다.')}</div></article>`}
  }

  function install(){
    ensureShell();
    document.getElementById('coinSelect')?.addEventListener('change',()=>setTimeout(()=>load(true),20));
    document.addEventListener('click',event=>{
      if(event.target.closest?.('[data-open-market]')||event.target.closest?.('[data-view="coin"]'))setTimeout(()=>load(true),80);
    });
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(()=>load(true),50)});
    timer=setInterval(()=>load(true),30000);
    setTimeout(()=>load(true),150);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
