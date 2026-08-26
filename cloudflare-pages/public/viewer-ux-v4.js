(()=>{
  if(window.__viewerUxV4Loaded)return;
  window.__viewerUxV4Loaded=true;

  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const n=v=>Number(v||0);
  const STORE='cryptoViewerUxV4';
  let settings={strategyExpanded:false,componentsExpanded:false};
  try{settings={...settings,...JSON.parse(localStorage.getItem(STORE)||'{}')}}catch{}
  const save=()=>{try{localStorage.setItem(STORE,JSON.stringify(settings))}catch{}};
  const stateRef=()=>typeof state!=='undefined'?state:null;
  const rows=()=>Array.isArray(stateRef()?.snapshot?.public?.leaderboard)?state.snapshot.public.leaderboard:[];
  const currentMarket=()=>stateRef()?.coinMarket||q('#coinSelect')?.value||'';
  const symbol=row=>String(row?.symbol||row?.market||'').replace(/^KRW-/,'');

  function selectMarket(market){
    if(!market)return;
    const select=q('#coinSelect');
    if(select){select.value=market;select.dispatchEvent(new Event('change',{bubbles:true}))}
    const s=stateRef();if(s)s.coinMarket=market;
    if(typeof switchView==='function')switchView('coin');
    setTimeout(refreshCoinFinder,50);
  }

  function ensureCoinFinder(){
    const panel=q('[data-view-panel="coin"]'),head=q('.page-head',panel);if(!panel||!head)return;
    let root=q('#uxCoinFinder',panel);
    if(!root){
      root=document.createElement('div');root.id='uxCoinFinder';root.className='ux-coin-finder';
      root.innerHTML='<label><span>코인 찾기</span><input id="uxCoinSearch" list="uxCoinOptions" type="search" placeholder="티커·코인명 검색 (예: BTC)" autocomplete="off"></label><datalist id="uxCoinOptions"></datalist><div id="uxCoinQuickRail" class="ux-coin-quick"></div>';
      head.insertAdjacentElement('afterend',root);
      const input=q('#uxCoinSearch',root);
      const commit=()=>{
        const value=String(input.value||'').trim().toLowerCase();if(!value)return;
        const list=rows();
        const match=list.find(r=>symbol(r).toLowerCase()===value||String(r.market||'').toLowerCase()===value||String(r.name||'').toLowerCase()===value)||list.find(r=>`${symbol(r)} ${r.name||''} ${r.market||''}`.toLowerCase().includes(value));
        if(match){input.value=symbol(match);selectMarket(match.market)}
      };
      input.addEventListener('change',commit);
      input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();commit()}});
      q('#uxCoinQuickRail',root).addEventListener('click',event=>{const button=event.target.closest('[data-ux-market]');if(button)selectMarket(button.dataset.uxMarket)});
    }
    refreshCoinFinder();
  }

  function quickRows(){
    const list=rows(),current=currentMarket(),byMarket=new Map(list.map(r=>[r.market,r]));
    const picks=[];const add=row=>{if(row&&!picks.some(x=>x.market===row.market))picks.push(row)};
    add(byMarket.get(current));add(byMarket.get('KRW-BTC'));add(byMarket.get('KRW-ETH'));
    list.filter(r=>r.has_position).sort((a,b)=>n(b.position_value_krw)-n(a.position_value_krw)).slice(0,4).forEach(add);
    [...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,12).forEach(add);
    return picks.slice(0,10);
  }

  function refreshCoinFinder(){
    const root=q('#uxCoinFinder');if(!root)return;const list=rows();
    const datalist=q('#uxCoinOptions',root);if(datalist){const sig=list.map(r=>`${r.market}:${r.symbol}:${r.name}`).join('|');if(datalist.dataset.sig!==sig){datalist.dataset.sig=sig;datalist.innerHTML=list.map(r=>`<option value="${symbol(r).replace(/"/g,'&quot;')}">${String(r.name||r.market).replace(/</g,'&lt;')}</option>`).join('')}}
    const input=q('#uxCoinSearch',root),current=list.find(r=>r.market===currentMarket());if(input&&document.activeElement!==input&&current)input.value=symbol(current);
    const quick=q('#uxCoinQuickRail',root);if(quick){quick.innerHTML=quickRows().map(r=>`<button type="button" data-ux-market="${r.market}" class="${r.market===currentMarket()?'active':''}"><b>${symbol(r)}</b><span>${r.has_position?'보유':`기회 ${n(r.opportunity_score).toFixed(0)}`}</span></button>`).join('')}
  }

  function pruneLegacyCoinRail(){
    const rail=q('#assetChipRailRemote');if(!rail||rail.dataset.uxPruned==='1')return;
    rail.dataset.uxPruned='1';rail.replaceChildren();
  }

  function ensureStrategyToggle(){
    const card=q('#strategyLabCard'),panel=q('[data-view-panel="results"]');if(!card||!panel)return;
    let button=q('#uxStrategyToggle',panel);
    if(!button){button=document.createElement('button');button.id='uxStrategyToggle';button.className='ux-strategy-toggle';card.insertAdjacentElement('beforebegin',button);button.addEventListener('click',()=>{settings.strategyExpanded=!settings.strategyExpanded;save();applyStrategyState()})}
    applyStrategyState();
  }
  function applyStrategyState(){const card=q('#strategyLabCard'),button=q('#uxStrategyToggle');if(!card||!button)return;const hidden=card.classList.contains('hidden');button.hidden=hidden;card.classList.toggle('ux-collapsed',!settings.strategyExpanded);button.innerHTML=settings.strategyExpanded?'<span>전략 연구실</span><b>접기 ↑</b>':'<span>전략 연구실 요약</span><b>6개 전략 자세히 보기 ↓</b>'}

  function ensureSettingsToggle(){
    const section=q('#v3ResearchSettings'),components=q('.v3-components',section);if(!section||!components)return;
    let button=q('#uxComponentsToggle',section);
    if(!button){button=document.createElement('button');button.id='uxComponentsToggle';button.className='ux-components-toggle';components.insertAdjacentElement('beforebegin',button);button.addEventListener('click',()=>{settings.componentsExpanded=!settings.componentsExpanded;save();applySettingsState()})}
    applySettingsState();
  }
  function applySettingsState(){const section=q('#v3ResearchSettings'),button=q('#uxComponentsToggle');if(!section||!button)return;section.classList.toggle('ux-components-expanded',settings.componentsExpanded);const count=qa('.v3-components article',section).length;button.innerHTML=settings.componentsExpanded?`구성요소 ${count}개 접기 ↑`:`연구 구성요소 ${count}개 보기 ↓`}

  function ensureResultsHint(){
    const card=q('.results-card'),controls=q('.market-controls',card);if(!card||!controls)return;
    let hint=q('#uxResultsHint',card);if(!hint){hint=document.createElement('div');hint.id='uxResultsHint';hint.className='ux-results-hint';controls.insertAdjacentElement('afterend',hint)}
    const s=window.__viewerPerformance?.stats||{},shown=n(s.marketRowsRendered),total=n(s.marketRowsTotal);
    hint.textContent=total?`현재 ${shown.toLocaleString('ko-KR')} / ${total.toLocaleString('ko-KR')}개 표시 · 검색은 전체 종목 대상`:'검색·필터로 원하는 코인을 바로 찾을 수 있습니다.';
  }

  function refresh(){
    document.documentElement.classList.add('ux-v4');
    const view=stateRef()?.activeView;
    if(view==='coin'){ensureCoinFinder();pruneLegacyCoinRail()}
    if(view==='results'){ensureStrategyToggle();ensureResultsHint()}
    if(view==='settings')ensureSettingsToggle();
  }

  document.addEventListener('viewer:viewchange',()=>requestAnimationFrame(refresh));
  document.addEventListener('viewer:snapshot',()=>requestAnimationFrame(refresh));
  document.addEventListener('viewer:marketrowsupdated',()=>requestAnimationFrame(ensureResultsHint));
  document.addEventListener('phase3exchangechange',()=>setTimeout(()=>{refreshCoinFinder();refresh()},80));
  document.addEventListener('click',event=>{if(event.target.closest?.('[data-open-market],.asset-chip[data-market],[data-v3-coin]'))setTimeout(refreshCoinFinder,100)},true);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(refresh,50)});

  function install(){refresh();setTimeout(refresh,300)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
