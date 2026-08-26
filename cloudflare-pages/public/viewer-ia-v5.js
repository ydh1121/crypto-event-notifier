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
  const avg=(list,key)=>list.length?list.reduce((sum,row)=>sum+n(row?.[key]),0)/list.length:0;

  const NAV={home:'자산',coin:'리서치',results:'PAPER',records:'기록',settings:'시스템'};
  const PAGE_COPY={
    home:{kicker:'자산',title:'내 보유자산',desc:'실제 보유자산의 평가액·손익·종목별 비중을 확인합니다.'},
    coin:{kicker:'리서치',title:'지금 볼 코인과 현재 판단',desc:'시장 상황을 먼저 보고, 관심 코인을 찾아 진입 판단과 보유 상태를 확인합니다.'},
    results:{kicker:'PAPER',title:'가상매매 성과 검증',desc:'가상계좌 성과와 코인별 결과를 확인하고, 필요할 때 전략 결과를 비교합니다.'},
    records:{kicker:'기록',title:'체결·학습 이력',desc:'가상 체결과 학습 변화가 언제 어떻게 발생했는지 시간순으로 확인합니다.'},
    settings:{kicker:'시스템',title:'연구 노드와 접근 권한',desc:'연구 서버 상태와 계정 권한만 확인합니다. 외부 웹에서는 매매를 제어하지 않습니다.'},
  };

  function applyNavLabels(){
    qa('#viewerNav button[data-view]').forEach(button=>{
      const label=NAV[button.dataset.view];
      if(!label)return;
      if(button.textContent!==label)button.textContent=label;
      button.setAttribute('aria-label',label);
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

  function contextHost(view){
    const head=pageHead(view);if(!head)return null;
    let host=q(':scope>.ia-head-tools',head);
    if(!host){host=document.createElement('div');host.className='ia-head-tools';head.appendChild(host)}
    return host;
  }

  function renderExchangeFilter(view){
    const host=contextHost(view);if(!host)return;
    if(!['coin','results','records'].includes(view)){host.replaceChildren();return}
    const mode=exchangeMode();
    const b=exchangeData('bithumb'),u=exchangeData('upbit');
    const bc=n(b?.market_count)||n(b?.leaderboard?.length),uc=n(u?.market_count)||n(u?.leaderboard?.length);
    const label=view==='records'?'기록 거래소':'거래소';
    host.innerHTML=`<div class="ia-exchange-filter"><span>${label}</span><div><button type="button" data-ia-exchange="bithumb" class="${mode==='bithumb'?'active':''}">빗썸${bc?` <small>${bc}</small>`:''}</button><button type="button" data-ia-exchange="upbit" class="${mode==='upbit'?'active':''}">업비트${uc?` <small>${uc}</small>`:''}</button>${view==='results'?`<button type="button" data-ia-exchange="compare" class="compare ${mode==='compare'?'active':''}">비교</button>`:''}</div></div>`;
  }

  function ensureAssetsEmpty(panel,hold){
    let empty=q('#iaAssetsEmpty',panel);
    const visible=hold&&!hold.classList.contains('hidden');
    if(visible){empty?.remove();return}
    if(!empty){
      empty=document.createElement('section');empty.id='iaAssetsEmpty';empty.className='ia-empty-state';
      empty.innerHTML='<div><b>표시할 보유자산이 없습니다.</b><p>보유자산이 등록되면 평가액·손익·종목별 비중을 이 화면에서 확인합니다.</p></div><button type="button" data-ia-go-research>리서치 보기</button>';
      pageHead('home')?.insertAdjacentElement('afterend',empty);
    }
  }

  function arrangeAssets(){
    const panel=q('[data-view-panel="home"]'),hold=q('#holdingsCard',panel);if(!panel)return;
    q('.capital-card',panel)?.classList.add('ia-move-to-paper');
    q('#v3HomeFocus',panel)?.classList.add('ia-hide-from-assets');
    q('.home-grid',panel)?.classList.add('ia-hide-from-assets');
    if(hold){
      pageHead('home')?.insertAdjacentElement('afterend',hold);
      hold.classList.add('ia-assets-primary');
    }
    ensureAssetsEmpty(panel,hold);
  }

  function researchSummaryMarkup(){
    const list=rows();if(!list.length)return'<div class="ia-research-loading">시장 데이터를 기다리는 중입니다.</div>';
    const regime=avg(list,'regime_score'),entry=avg(list,'entry_score'),holding=list.filter(row=>row.has_position).length;
    const picks=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,4);
    return `<div class="ia-research-stats"><div><span>시장 분위기</span><b>${regime.toFixed(0)}<small>/100</small></b></div><div><span>평균 진입여건</span><b>${entry.toFixed(0)}<small>/100</small></b></div><div><span>현재 보유</span><b>${holding}<small>개</small></b></div></div><div class="ia-research-picks"><span>지금 볼 코인</span><div>${picks.map(row=>`<button type="button" data-ia-market="${safe(row.market)}"><b>${safe(symbol(row))}</b><small>기회 ${n(row.opportunity_score).toFixed(0)}</small></button>`).join('')}</div></div>`;
  }

  function ensureResearchSummary(){
    const panel=q('[data-view-panel="coin"]'),head=pageHead('coin');if(!panel||!head)return;
    let box=q('#iaResearchSummary',panel);if(!box){box=document.createElement('section');box.id='iaResearchSummary';box.className='ia-research-summary';head.insertAdjacentElement('afterend',box)}
    box.innerHTML=researchSummaryMarkup();
  }

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
      pop.addEventListener('mousedown',event=>{const button=event.target.closest('[data-ia-market]');if(!button)return;event.preventDefault();input.value=button.dataset.symbol||'';pop.hidden=true;selectCoin(button.dataset.iaMarket)});
    }
  }

  function renderCoinSuggestions(raw){
    const pop=q('#iaCoinSuggestions');if(!pop)return;
    const term=String(raw||'').trim().toLowerCase();if(!term){pop.hidden=true;return}
    const matches=rows().filter(row=>`${symbol(row)} ${row.name||''} ${row.market||''}`.toLowerCase().includes(term)).slice(0,8);
    if(!matches.length){pop.innerHTML='<div class="ia-no-result">검색 결과가 없습니다.</div>';pop.hidden=false;return}
    pop.innerHTML=matches.map(row=>`<button type="button" data-ia-market="${safe(row.market)}" data-symbol="${safe(symbol(row))}"><span><b>${safe(symbol(row))}</b><small>${safe(row.name||row.market)}</small></span><em>${row.has_position?'보유 중':`기회 ${n(row.opportunity_score).toFixed(0)}`}</em></button>`).join('');
    pop.hidden=false;
  }

  function arrangeResearch(){
    ensureResearchSummary();ensureCoinSuggestions();
    const quick=q('#uxCoinQuickRail');if(quick)qa('button',quick).forEach((button,index)=>button.classList.toggle('ia-extra-quick',index>=5));
  }

  function arrangePaper(){
    const panel=q('[data-view-panel="results"]'),capital=q('.capital-card');if(!panel||!capital)return;
    const head=pageHead('results');
    if(capital.parentElement!==panel)head?.insertAdjacentElement('afterend',capital);
    capital.classList.remove('ia-move-to-paper');capital.classList.add('ia-paper-summary');
    const title=q('.capital-main>span',capital);if(title)title.textContent='PAPER 가상계좌 요약';
    q('#v3ResultSummary',panel)?.classList.add('ia-hide-result-summary');
    const layout=q('#parityResearchLayout',panel),card=q('#strategyLabCard',panel),toggle=q('#uxStrategyToggle',panel);
    if(layout&&toggle&&toggle.previousElementSibling!==layout)layout.insertAdjacentElement('afterend',toggle);
    if(toggle&&card&&card.previousElementSibling!==toggle)toggle.insertAdjacentElement('afterend',card);
    panel.classList.toggle('ia-compare-active',exchangeMode()==='compare');
  }

  function simplifySystem(){
    const node=q('#v3ResearchSettings');if(!node)return;
    const head=q('.v3-section-head h3',node),copy=q('.v3-section-head p:not(.kicker)',node);
    if(head)head.textContent='연구 노드 상태';if(copy)copy.textContent='핵심 상태를 먼저 보고, 상세 구성요소는 필요할 때 펼쳐서 확인합니다.';
  }

  function resetPageScroll(view){
    if(!view||view===lastView)return;
    lastView=view;
    requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}));
  }

  function refresh(){
    document.documentElement.classList.add('ia-v5');
    applyNavLabels();applyPageCopy();arrangeAssets();
    ['coin','results','records','settings','home'].forEach(renderExchangeFilter);
    const view=stateRef()?.activeView||'';
    if(view==='coin')arrangeResearch();
    if(view==='results')arrangePaper();
    if(view==='settings')simplifySystem();
  }

  document.addEventListener('click',event=>{
    const ex=event.target.closest?.('[data-ia-exchange]');if(ex){
      const next=ex.dataset.iaExchange;if(!next||!window.cryptoResearchExchange?.setMode)return;
      window.cryptoResearchExchange.setMode(next);setTimeout(()=>{refresh();if(next==='compare'&&typeof switchView==='function')switchView('results')},80);return;
    }
    const market=event.target.closest?.('[data-ia-market]');if(market){selectCoin(market.dataset.iaMarket);return}
    if(event.target.closest?.('[data-ia-go-research]')&&typeof switchView==='function')switchView('coin');
  });
  document.addEventListener('viewer:viewchange',event=>{resetPageScroll(event.detail?.view||stateRef()?.activeView);setTimeout(refresh,0)});
  document.addEventListener('viewer:snapshot',()=>setTimeout(refresh,0));
  document.addEventListener('phase3exchangechange',()=>setTimeout(refresh,80));
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)setTimeout(refresh,40)});

  function install(){lastView=stateRef()?.activeView||'';refresh();setTimeout(refresh,250);setTimeout(refresh,900)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
