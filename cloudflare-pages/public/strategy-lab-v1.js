(()=>{
  if(window.__strategyLabViewerV1Loaded)return;
  window.__strategyLabViewerV1Loaded=true;

  const q=(s,r=document)=>r.querySelector(s);
  const n=v=>Number(v||0);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot',"'":'&#39;'}[c]));
  const pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const won=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
  const price=v=>{const x=n(v);if(!x)return'-';const d=x>=1000?0:x>=100?1:x>=1?3:x>=.1?5:8;return`${x.toLocaleString('ko-KR',{maximumFractionDigits:d})}원`};
  const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  const STORE='strategyLabViewerV1';
  let exchange='bithumb';
  let viewerExchange='bithumb';
  let lastSignature='';
  let marketRequest=0;
  let marketTimer=0;

  try{
    const saved=JSON.parse(localStorage.getItem(STORE)||'{}');
    if(['bithumb','upbit'].includes(saved.exchange))exchange=saved.exchange;
  }catch{}

  function save(){try{localStorage.setItem(STORE,JSON.stringify({exchange}))}catch{}}
  function lab(){return typeof state!=='undefined'?state.snapshot?.public?.strategy_lab||{}:{}}
  function root(){return q('#strategyLabCard')}
  function exchangeLabel(x){return x==='upbit'?'업비트':'빗썸'}
  function currentMarket(){return typeof state!=='undefined'?(state.coinMarket||q('#coinSelect')?.value||''):(q('#coinSelect')?.value||'')}
  function currentViewerExchange(){const x=typeof state!=='undefined'?state.snapshot?.public?.exchange:'';return ['bithumb','upbit'].includes(x)?x:viewerExchange}
  function isCustom(row){return String(row?.style||'').startsWith('custom_')}
  function candidateMeta(row,criteria={}){
    const c=row?.candidate||{};
    if(row?.status==='paused'||c.status==='paused')return{label:'일시정지',className:'paused',detail:'검증 중지'};
    if(c.status==='candidate')return{label:'후보 통과',className:'candidate',detail:`게이트 ${n(c.passed_gates).toFixed(0)}/${n(c.total_gates).toFixed(0)}`};
    if(c.status==='rejected')return{label:'게이트 미통과',className:'rejected',detail:`게이트 ${n(c.passed_gates).toFixed(0)}/${n(c.total_gates).toFixed(0)}`};
    const need=n(criteria.min_closed_trades)||30;
    return{label:`검증 ${n(c.closed_trades||row?.closed_trades).toFixed(0)}/${need}`,className:'warming',detail:`종목 ${n(c.traded_markets).toFixed(0)}/${n(criteria.min_traded_markets)||5}`};
  }

  function render(force=false){
    const el=root();if(!el)return;
    const data=lab(),all=Array.isArray(data.experiments)?data.experiments:[],criteria=data.candidate_criteria||{};
    if(!all.length){el.classList.add('hidden');return}
    const rows=all.filter(r=>r.exchange===exchange).sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    if(!rows.length){el.classList.add('hidden');return}
    const signature=`${exchange}|${n(data.updated_at)}|${rows.map(r=>`${r.style}:${n(r.return_pct)}:${n(r.closed_trades)}:${n(r.active_positions)}:${r.status}:${r.candidate?.status||''}:${n(r.candidate?.passed_gates)}`).join('|')}`;
    if(!force&&signature===lastSignature)return;
    lastSignature=signature;
    el.classList.remove('hidden');
    const running=rows.filter(r=>r.status==='running');
    const ranked=(running.length?running:rows).slice().sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    const leader=ranked[0];
    const candidates=rows.filter(r=>r.candidate?.status==='candidate').length;
    const custom=rows.filter(isCustom).length;
    el.innerHTML=`<div class="strategy-lab-head"><div><p class="kicker">STRATEGY LAB · PHASE 4</p><h3>같은 시장 데이터로 전략별 PAPER 결과를 비교합니다.</h3><p>기본 6개 전략${custom?`과 사용자 조합 ${custom}개`:''}가 같은 시장 기억을 재사용합니다. 수익률만 보지 않고 표본·종목 분산·낙폭·기대값·손익 집중도 게이트를 함께 봅니다.</p></div><div class="strategy-lab-switch"><button type="button" data-lab-exchange="bithumb" class="${exchange==='bithumb'?'active':''}">빗썸</button><button type="button" data-lab-exchange="upbit" class="${exchange==='upbit'?'active':''}">업비트</button></div></div><div class="strategy-lab-summary"><div><span>현재 수익률 1위</span><b>${esc(leader?.label||leader?.style||'-')}</b><small class="${tone(leader?.return_pct)}">${leader?pct(leader.return_pct):'-'} 누적</small></div><div><span>비교 전략</span><b>${rows.length}개</b><small>기본 6 · 사용자 ${custom}</small></div><div><span>후보 게이트 통과</span><b>${candidates}개</b><small>자동 승격은 하지 않음</small></div><div><span>최소 검증 표본</span><b>${n(criteria.min_closed_trades)||30}회</b><small>${n(criteria.min_traded_markets)||5}종목 이상 분산</small></div></div><div class="strategy-lab-grid">${rows.map(r=>{const trades=n(r.closed_trades),rank=ranked.findIndex(x=>x.experiment_id===r.experiment_id)+1,c=r.candidate||{},cm=candidateMeta(r,criteria);return`<article class="strategy-lab-style ${rank===1?'leader':''} ${isCustom(r)?'custom':''}"><div class="strategy-lab-style-head"><span><i>${rank>0?rank:'–'}</i><b>${esc(r.label||r.style)}</b></span><strong class="${tone(r.return_pct)}">${pct(r.return_pct)}</strong></div><p>${esc(r.description||'')}</p><div class="strategy-lab-metrics"><div><span>최대 낙폭</span><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></div><div><span>승률</span><b>${n(r.win_rate_pct).toFixed(1)}%</b></div><div><span>기대값</span><b class="${tone(r.expectancy_pct)}">${pct(r.expectancy_pct)}</b></div><div><span>완료 거래</span><b>${trades.toLocaleString('ko-KR')}</b></div><div><span>거래 종목</span><b>${n(c.traded_markets).toFixed(0)}</b></div><div><span>Profit Factor</span><b>${n(r.profit_factor)>=999?'∞':n(r.profit_factor).toFixed(2)}</b></div></div><div class="strategy-lab-gate-mini"><span>수익 종목 ${n(c.profitable_market_share)*100?`${(n(c.profitable_market_share)*100).toFixed(0)}%`:'-'}</span><span>손익 집중 ${n(c.pnl_concentration_share)*100?`${(n(c.pnl_concentration_share)*100).toFixed(0)}%`:'-'}</span><span>${esc(cm.detail)}</span></div><footer><span>${isCustom(r)?'사용자 조합':exchangeLabel(exchange)}</span><span class="${cm.className}">${esc(cm.label)}</span></footer></article>`}).join('')}</div><p class="strategy-lab-candidate-note">후보 통과는 PAPER 연구상 검증 게이트를 통과했다는 뜻이며 실제 주문 전략으로 자동 승격되지 않습니다.</p>`;
  }

  function ensureMarketCard(){
    const panel=q('[data-view-panel="coin"]');if(!panel)return null;
    let el=q('#strategyLabMarketCard',panel);if(el)return el;
    el=document.createElement('section');el.id='strategyLabMarketCard';el.className='strategy-lab-market-card';
    const port=q('#assetLocalPort',panel),tools=q('#personalToolsRemote',panel),detail=q('#coinDetailCard',panel);
    if(tools)tools.insertAdjacentElement('beforebegin',el);else if(port)port.appendChild(el);else if(detail)detail.insertAdjacentElement('afterend',el);else panel.appendChild(el);
    return el;
  }

  function renderMarket(data,market,ex){
    const el=ensureMarketCard();if(!el)return;
    const rows=Array.isArray(data?.experiments)?data.experiments.slice():[];
    if(!rows.length){el.innerHTML='<div class="strategy-lab-market-empty">이 코인의 Strategy Lab 상세가 다음 상세 전송 순환에서 표시됩니다.</div>';return}
    rows.sort((a,b)=>n(b.return_pct)-n(a.return_pct));
    const active=rows.filter(r=>r.status==='running');
    const custom=rows.filter(isCustom).length;
    el.innerHTML=`<div class="strategy-lab-market-head"><div><p class="kicker">COIN STRATEGY COMPARISON</p><h3>${esc(String(market).replace(/^KRW-/,''))} · 전략별 독립 1,000만원 계좌</h3><p>${exchangeLabel(ex)}의 같은 코인·같은 시장 데이터를 기본 6개${custom?` + 사용자 ${custom}개`:''} 전략이 어떻게 다르게 처리했는지 봅니다.</p></div><span>${active.length}/${rows.length} 실행 중</span></div><div class="strategy-lab-market-grid">${rows.map((r,i)=>{const t=r.latest_trade||null;return`<article class="strategy-lab-market-row ${i===0?'leader':''} ${isCustom(r)?'custom':''}"><div class="strategy-lab-market-title"><span><i>${i+1}</i><b>${esc(r.label||r.style)}</b>${isCustom(r)?'<em>사용자</em>':''}</span><strong class="${tone(r.return_pct)}">${pct(r.return_pct)}</strong></div><div class="strategy-lab-market-kpis"><div><span>평가액</span><b>${won(r.equity_krw)}</b></div><div><span>보유금액</span><b>${won(r.position_value_krw)}</b></div><div><span>평단</span><b>${price(r.avg_price)}</b></div><div><span>매수회차</span><b>${n(r.buy_count).toFixed(0)}회</b></div><div><span>최대 DD</span><b class="${tone(r.max_drawdown_pct)}">${pct(r.max_drawdown_pct)}</b></div><div><span>완료 / 승률</span><b>${n(r.closed_trades).toFixed(0)} / ${n(r.win_rate_pct).toFixed(1)}%</b></div></div><footer><span>${r.status==='paused'?'일시정지':`학습 가중 ${n(r.weight_multiplier||1).toFixed(3)}배`}</span><span>${t?`최근 ${t.side==='buy'?'매수':'매도'} ${price(t.price)}`:'체결 대기'}</span></footer></article>`}).join('')}</div><p class="strategy-lab-market-note">이 영역은 조회 전용입니다. 전략 생성·일시정지는 24시간 PC의 로컬 설정 화면에서만 가능합니다.</p>`;
  }

  async function loadMarketDetail(force=false){
    if(typeof state==='undefined'||!state.user||state.activeView!=='coin')return;
    const market=currentMarket(),ex=currentViewerExchange();if(!market||!['bithumb','upbit'].includes(ex))return;
    const request=++marketRequest;const el=ensureMarketCard();if(el&&force)el.innerHTML='<div class="strategy-lab-market-empty">전략별 코인 성과를 불러오는 중입니다.</div>';
    try{
      const response=await fetch(`/api/market-detail?exchange=${encodeURIComponent(ex)}&strategy=adaptive&market=${encodeURIComponent(market)}`,{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)throw new Error(String(response.status));
      const body=await response.json();if(request!==marketRequest)return;
      const detail=body.detail?.data||body.detail||{};
      renderMarket(detail.strategy_lab||{},market,ex);
    }catch(_err){if(request!==marketRequest)return;if(el)el.innerHTML='<div class="strategy-lab-market-empty">Strategy Lab 상세가 아직 도착하지 않았습니다. 다음 상세 전송 후 자동으로 다시 확인합니다.</div>'}
  }

  document.addEventListener('click',event=>{
    const btn=event.target.closest?.('[data-lab-exchange]');if(!btn)return;
    const next=btn.dataset.labExchange;if(!['bithumb','upbit'].includes(next)||next===exchange)return;
    exchange=next;save();render(true);
  });
  document.addEventListener('phase3exchangechange',event=>{
    const next=event.detail?.exchange;if(['bithumb','upbit'].includes(next)){viewerExchange=next;exchange=next;save();render(true);setTimeout(()=>loadMarketDetail(true),120)}
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden){render(true);loadMarketDetail(false)}});
  document.addEventListener('change',event=>{if(event.target?.id==='coinSelect')setTimeout(()=>loadMarketDetail(true),80)});
  document.addEventListener('click',event=>{if(event.target.closest?.('[data-v3-coin],.asset-chip[data-market],[data-open-market]'))setTimeout(()=>loadMarketDetail(true),180)},true);

  function install(){
    const initial=typeof state!=='undefined'?state.snapshot?.public?.exchange:'';if(['bithumb','upbit'].includes(initial)){viewerExchange=initial;exchange=initial}
    render(true);ensureMarketCard();
    setInterval(()=>{if(!document.hidden&&typeof state!=='undefined'&&state.user)render(false)},15000);
    marketTimer=setInterval(()=>{if(!document.hidden)loadMarketDetail(false)},30000);
    setTimeout(()=>loadMarketDetail(true),400);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
