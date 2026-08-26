(()=>{
  if(window.__viewerIaV5Loaded)return;
  window.__viewerIaV5Loaded=true;

  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const n=v=>Number(v||0);
  let lastView='';
  let coinSuggestTimer=0;

  const stateRef=()=>{try{return typeof state!=='undefined'?state:null}catch{return null}};
  const publicRef=()=>stateRef()?.snapshot?.public||{};
  const rows=()=>Array.isArray(publicRef().leaderboard)?publicRef().leaderboard:[];
  const exchangeMode=()=>window.cryptoResearchExchange?.mode||'bithumb';
  const exchangeData=name=>publicRef().exchanges?.[name]||null;
  const symbol=row=>String(row?.symbol||row?.market||'').replace(/^KRW-/,'');
  const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const NAV={
    home:'대시보드',
    coin:'시장분석',
    results:'성과분석',
    records:'거래기록',
    settings:'시스템',
  };
  const PAGE_COPY={
    home:{kicker:'대시보드',title:'내 자산과 PAPER 연구 상태',desc:'실제 보유자산과 연구용 가상계좌를 구분해서 한눈에 확인합니다.'},
    coin:{kicker:'시장분석',title:'코인을 찾아 현재 판단 확인',desc:'원하는 코인을 검색하고 가격·보유상태·진입 판단을 확인합니다.'},
    results:{kicker:'성과분석',title:'PAPER 성과와 전략 검증',desc:'코인별 가상계좌 성과를 먼저 보고, 필요할 때 전략별 결과를 비교합니다.'},
    records:{kicker:'거래기록',title:'체결과 학습 기록',desc:'가상 체결과 학습 변화가 언제 어떻게 발생했는지 시간순으로 확인합니다.'},
    settings:{kicker:'시스템',title:'연구 노드와 접근 권한',desc:'연구 서버 상태와 계정 권한을 확인합니다. 외부 웹에서는 매매를 제어하지 않습니다.'},
  };

  function applyNavLabels(){
    qa('#viewerNav button[data-view]').forEach(button=>{
      const label=NAV[button.dataset.view];
      if(label&&button.textContent!==label)button.textContent=label;
    });
  }

  function pageHead(view){
    const panel=q(`[data-view-panel="${view}"]`);if(!panel)return null;
    return view==='home'?q('.viewer-intro',panel):q('.page-head',panel);
  }

  function applyPageCopy(){
    Object.entries(PAGE_COPY).forEach(([view,copy])=>{
      const head=pageHead(view);if(!head)return;
      const kicker=q('.kicker',head),title=q('h2',head),desc=q('p:not(.kicker)',head);
      if(kicker&&kicker.textContent!==copy.kicker)kicker.textContent=copy.kicker;
      if(title&&title.textContent!==copy.title)title.textContent=copy.title;
      if(desc&&desc.textContent!==copy.desc)desc.textContent=copy.desc;
    });
  }

  function dashboardHeading(id,title,desc){
    let node=q(`#${id}`);if(!node){node=document.createElement('div');node.id=id;node.className='ia-section-heading'}
    let copy=q(':scope>.ia-section-copy',node);
    if(!copy){copy=document.createElement('div');copy.className='ia-section-copy';copy.innerHTML='<h3></h3><p></p>';node.prepend(copy)}
    const h=q('h3',copy),p=q('p',copy);if(h)h.textContent=title;if(p)p.textContent=desc;
    return node;
  }

  function arrangeDashboard(){
    const panel=q('[data-view-panel="home"]'),hold=q('#holdingsCard',panel),capital=q('.capital-card',panel);if(!panel||!capital)return;
    const assetHead=dashboardHeading('iaAssetHeading','내 자산','내가 실제로 보유한 자산입니다. PAPER 연구계정과 별도로 표시합니다.');
    const paperHead=dashboardHeading('iaPaperHeading','PAPER 연구','거래소별 독립 가상계좌의 현재 성과와 시장 판단입니다.');
    const intro=q('.viewer-intro',panel);
    if(hold){intro?.insertAdjacentElement('afterend',assetHead);assetHead.insertAdjacentElement('afterend',hold);assetHead.hidden=hold.classList.contains('hidden')}
    if(hold)hold.insertAdjacentElement('afterend',paperHead);else intro?.insertAdjacentElement('afterend',paperHead);
    paperHead.insertAdjacentElement('afterend',capital);
    const focus=q('#v3HomeFocus',panel);if(focus&&focus.previousElementSibling!==capital)capital.insertAdjacentElement('afterend',focus);
    q('.home-grid',panel)?.classList.add('ia-hide-legacy-home');
  }

  function contextHost(view){
    const anchor=view==='home'?q('#iaPaperHeading'):pageHead(view);if(!anchor)return null;
    let host=q(':scope>.ia-head-tools',anchor);
    if(!host){host=document.createElement('div');host.className='ia-head-tools';anchor.appendChild(host)}
    return host;
  }

  function renderContext(view){
    const host=contextHost(view);if(!host)return;
    const mode=exchangeMode();
    const b=exchangeData('bithumb'),u=exchangeData('upbit');
    const bc=n(b?.market_count)||n(b?.leaderboard?.length),uc=n(u?.market_count)||n(u?.leaderboard?.length);
    host.innerHTML=`<div class="ia-exchange-filter"><span>${view==='home'?'PAPER 데이터':'데이터 기준'}</span><div><button type="button" data-ia-exchange="bithumb" class="${mode==='bithumb'?'active':''}">빗썸${bc?` <small>${bc}</small>`:''}</button><button type="button" data-ia-exchange="upbit" class="${mode==='upbit'?'active':''}">업비트${uc?` <small>${uc}</small>`:''}</button>${view==='results'?`<button type="button" data-ia-exchange="compare" class="compare ${mode==='compare'?'active':''}">거래소 비교</button>`:''}</div></div>`;
  }

  function renderAllContexts(){['home','coin','results','records'].forEach(renderContext)}

  function selectCoin(market){
    if(!market)return;
    const s=stateRef();if(s)s.coinMarket=market;
    const select=q('#coinSelect');if(select){select.value=market;select.dispatchEvent(new Event('change',{bubbles:true}))}
    if(typeof switchView==='function')switchView('coin');
  }

  function ensureCoinSuggestions(){
    const root=q('#uxCoinFinder'),input=q('#uxCoinSearch',root);if(!root||!input)return;
    input.removeAttribute('list');q('#uxCoinOptions',root)?.remove();
    let pop=q('#iaCoinSuggestions',root);if(!pop){
      pop=document.createElement('div');pop.id='iaCoinSuggestions';pop.className='ia-coin-suggestions';pop.hidden=true;root.querySelector('label')?.appendChild(pop);
      input.addEventListener('input',()=>{clearTimeout(coinSuggestTimer);coinSuggestTimer=setTimeout(()=>renderCoinSuggestions(input.value),35)});
      input.addEventListener('focus',()=>{if(String(input.value||'').trim())renderCoinSuggestions(input.value)});
      input.addEventListener('blur',()=>setTimeout(()=>{pop.hidden=true},120));
      pop.addEventListener('mousedown',event=>{
        const button=event.target.closest('[data-ia-market]');if(!button)return;
        event.preventDefault();input.value=button.dataset.symbol||'';pop.hidden=true;selectCoin(button.dataset.iaMarket);
      });
    }
  }

  function renderCoinSuggestions(raw){
    const pop=q('#iaCoinSuggestions'),input=q('#uxCoinSearch');if(!pop||!input)return;
    const term=String(raw||'').trim().toLowerCase();if(!term){pop.hidden=true;return}
    const matches=rows().filter(row=>`${symbol(row)} ${row.name||''} ${row.market||''}`.toLowerCase().includes(term)).slice(0,8);
    if(!matches.length){pop.innerHTML='<div class="ia-no-result">검색 결과가 없습니다.</div>';pop.hidden=false;return}
    pop.innerHTML=matches.map(row=>`<button type="button" data-ia-market="${safe(row.market)}" data-symbol="${safe(symbol(row))}"><span><b>${safe(symbol(row))}</b><small>${safe(row.name||row.market)}</small></span><em>${row.has_position?'보유 중':`기회 ${n(row.opportunity_score).toFixed(0)}`}</em></button>`).join('');
    pop.hidden=false;
  }

  function arrangeCoin(){
    ensureCoinSuggestions();
    const quick=q('#uxCoinQuickRail');if(quick){qa('button',quick).forEach((button,index)=>button.classList.toggle('ia-extra-quick',index>=6))}
  }

  function arrangeResults(){
    const panel=q('[data-view-panel="results"]');if(!panel)return;
    const layout=q('#parityResearchLayout',panel),card=q('#strategyLabCard',panel),toggle=q('#uxStrategyToggle',panel);
    if(layout&&toggle&&toggle.previousElementSibling!==layout)layout.insertAdjacentElement('afterend',toggle);
    if(toggle&&card&&card.previousElementSibling!==toggle)toggle.insertAdjacentElement('afterend',card);
    panel.classList.toggle('ia-compare-active',exchangeMode()==='compare');
  }

  function simplifySettings(){
    const node=q('#v3ResearchSettings');if(!node)return;
    const head=q('.v3-section-head h3',node),copy=q('.v3-section-head p:not(.kicker)',node);
    if(head)head.textContent='연구 노드 상태';if(copy)copy.textContent='필요한 상태만 먼저 확인하고, 상세 구성요소는 펼쳐서 봅니다.';
  }

  function resetPageScroll(view){
    if(!view||view===lastView)return;
    lastView=view;
    requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}));
  }

  function refresh(){
    document.documentElement.classList.add('ia-v5');
    applyNavLabels();applyPageCopy();arrangeDashboard();renderAllContexts();
    const view=stateRef()?.activeView||'';
    if(view==='coin')arrangeCoin();
    if(view==='results')arrangeResults();
    if(view==='settings')simplifySettings();
  }

  document.addEventListener('click',event=>{
    const ex=event.target.closest?.('[data-ia-exchange]');if(ex){
      const next=ex.dataset.iaExchange;if(!next||!window.cryptoResearchExchange?.setMode)return;
      window.cryptoResearchExchange.setMode(next);setTimeout(()=>{refresh();if(next==='compare'&&typeof switchView==='function')switchView('results')},80);return;
    }
  });
  document.addEventListener('viewer:viewchange',event=>{resetPageScroll(event.detail?.view||stateRef()?.activeView);setTimeout(refresh,0)});
  document.addEventListener('viewer:snapshot',()=>setTimeout(refresh,0));
  document.addEventListener('phase3exchangechange',()=>setTimeout(refresh,80));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(refresh,40)});

  function install(){lastView=stateRef()?.activeView||'';refresh();setTimeout(refresh,250);setTimeout(refresh,900)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
