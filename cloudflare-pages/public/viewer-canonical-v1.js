(()=>{
  if(window.__viewerCanonicalV1Loaded)return;
  window.__viewerCanonicalV1Loaded=true;

  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const n=v=>Number(v||0),pct=v=>`${n(v)>=0?'+':''}${n(v).toFixed(2)}%`,money=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
  const stateRef=()=>{try{return typeof state!=='undefined'?state:null}catch{return null}};
  const pub=()=>stateRef()?.snapshot?.public||{};
  const rows=()=>Array.isArray(pub().leaderboard)?pub().leaderboard:[];
  const privateData=()=>stateRef()?.snapshot?.private_visible?stateRef()?.snapshot?.private:null;
  let lastNormalExchange='bithumb';
  let paperMode='performance';

  function navMarkup(){return '<button type="button" data-view="home">개요</button><button type="button" data-view="assets">자산</button><button type="button" data-view="coin">리서치</button><button type="button" data-view="results">PAPER</button>'}

  function ensureNavigation(){
    const inner=q('#viewerNav .viewer-nav-inner');if(!inner)return;
    if(inner.dataset.canonical!=='1'){
      inner.dataset.canonical='1';inner.innerHTML=navMarkup();
      inner.addEventListener('click',event=>{const b=event.target.closest('[data-view]');if(b&&typeof switchView==='function')switchView(b.dataset.view)});
    }
    const actions=q('.top-actions');if(actions&&!q('#canonicalSystemBtn',actions)){
      const button=document.createElement('button');button.id='canonicalSystemBtn';button.type='button';button.className='canonical-system-button';button.textContent='시스템';
      button.onclick=()=>{if(typeof switchView==='function')switchView('settings')};actions.insertBefore(button,q('#logoutBtn',actions)||null);
    }
  }

  function ensureAssetsPanel(){
    const viewer=q('#viewerView');if(!viewer)return;
    let panel=q('[data-view-panel="assets"]');
    if(!panel){panel=document.createElement('section');panel.className='viewer-page canonical-assets-page';panel.dataset.viewPanel='assets';panel.innerHTML='<div class="section-head page-head"><div><p class="kicker">자산</p><h2>내 보유자산</h2><p>실제 보유자산의 평가액·손익·비중을 확인합니다. PAPER 가상계좌와 분리해서 봅니다.</p></div></div><div id="canonicalAssetsEmpty" class="canonical-empty" hidden><b>등록된 보유자산이 없습니다.</b><p>보유자산이 등록되면 이 화면에 평가액·손익·종목별 비중이 표시됩니다.</p></div>';
      const coin=q('[data-view-panel="coin"]');coin?.insertAdjacentElement('beforebegin',panel);
    }
    const holdings=q('#holdingsCard');if(holdings&&holdings.parentElement!==panel)panel.appendChild(holdings);
    return panel;
  }

  function movePaperCapital(){
    const panel=q('[data-view-panel="results"]'),capital=q('.capital-card');if(!panel||!capital)return;
    capital.classList.add('canonical-paper-capital');
    const head=q('.page-head',panel);if(head&&capital.previousElementSibling!==head)head.insertAdjacentElement('afterend',capital);
  }

  function ensureOverview(){
    const panel=q('[data-view-panel="home"]');if(!panel)return null;
    let root=q('#canonicalOverview',panel);if(!root){root=document.createElement('section');root.id='canonicalOverview';root.className='canonical-overview';q('.viewer-intro',panel)?.insertAdjacentElement('afterend',root)}
    q('#v3HomeFocus',panel)?.classList.add('canonical-hidden');q('.home-grid',panel)?.classList.add('canonical-hidden');
    return root;
  }

  function overviewData(){
    const p=pub(),list=rows(),pd=privateData()?.manual_holdings;
    const holdings=Array.isArray(pd?.holdings)?pd.holdings.filter(x=>n(x.volume)>0):[];
    const worst=[...holdings].sort((a,b)=>n(a.unrealized_pnl_pct)-n(b.unrealized_pnl_pct))[0];
    const bestOpp=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score))[0];
    const node=p.research_node||{};
    const alerts=[];
    if(worst&&n(worst.unrealized_pnl_pct)<=-10)alerts.push({tone:'bad',title:`${String(worst.market||'').replace(/^KRW-/,'')} 손실 ${pct(worst.unrealized_pnl_pct)}`,desc:'실제 보유자산 중 손실률이 가장 큽니다.',view:'assets'});
    if(bestOpp&&n(bestOpp.opportunity_score)>=65)alerts.push({tone:'info',title:`${bestOpp.symbol||bestOpp.market} 기회점수 ${n(bestOpp.opportunity_score).toFixed(0)}`,desc:'리서치 우선 확인 후보입니다.',view:'coin'});
    if(node.supervisor_running===false||node.online===false)alerts.push({tone:'bad',title:'연구 노드 확인 필요',desc:'시스템 상태를 확인하세요.',view:'settings'});
    if(!alerts.length)alerts.push({tone:'good',title:'즉시 확인할 경고 없음',desc:'자산·리서치·PAPER 요약을 확인하면 됩니다.',view:'home'});
    return {p,pd,holdings,worst,bestOpp,alerts};
  }

  function renderOverview(){
    const root=ensureOverview();if(!root)return;const d=overviewData(),p=d.p,pd=d.pd;
    const assetValue=n(pd?.value_krw),assetPnl=n(pd?.pnl_krw),paperReturn=n(p.return_pct),marketAvg=rows().length?rows().reduce((s,r)=>s+n(r.regime_score),0)/rows().length:0;
    root.innerHTML=`<div class="canonical-priority"><div class="canonical-section-title"><span>먼저 확인할 것</span><small>주의가 필요한 항목만 위로 올립니다.</small></div><div class="canonical-alerts">${d.alerts.slice(0,3).map(a=>`<button type="button" class="canonical-alert ${a.tone}" data-canonical-view="${a.view}"><span></span><div><b>${a.title}</b><small>${a.desc}</small></div><em>보기</em></button>`).join('')}</div></div><div class="canonical-overview-grid"><button type="button" data-canonical-view="assets"><span>내 자산</span><b>${pd?money(assetValue):'등록 없음'}</b><small class="${assetPnl<0?'negative':assetPnl>0?'positive':''}">${pd?`${assetPnl>=0?'+':''}${money(assetPnl)}`:'실제 보유자산'}</small></button><button type="button" data-canonical-view="coin"><span>시장</span><b>${marketAvg.toFixed(0)}<i>/100</i></b><small>${d.bestOpp?`우선 후보 ${d.bestOpp.symbol||d.bestOpp.market}`:'리서치 데이터 확인 중'}</small></button><button type="button" data-canonical-view="results"><span>PAPER</span><b class="${paperReturn<0?'negative':paperReturn>0?'positive':''}">${pct(paperReturn)}</b><small>${n(p.active_positions)}개 보유 · ${n(p.market_count)}개 추적</small></button></div>`;
  }

  function ensureResearchToolbar(){
    const panel=q('[data-view-panel="coin"]'),head=q('.page-head',panel);if(!panel||!head)return;
    let root=q('#canonicalResearchToolbar',panel);if(!root){
      root=document.createElement('section');root.id='canonicalResearchToolbar';root.className='canonical-research-toolbar';head.insertAdjacentElement('afterend',root);
      root.addEventListener('input',event=>{if(event.target.id==='canonicalCoinSearch')renderResearchSuggestions(event.target.value)});
      root.addEventListener('click',event=>{const b=event.target.closest('[data-canonical-market]');if(b)selectMarket(b.dataset.canonicalMarket)});
    }
    renderResearchToolbar();
  }

  function selectMarket(market){
    if(!market)return;const s=stateRef();if(s)s.coinMarket=market;const select=q('#coinSelect');if(select){select.value=market;select.dispatchEvent(new Event('change',{bubbles:true}))}if(typeof renderCoin==='function')renderCoin();
  }

  function renderResearchToolbar(){
    const root=q('#canonicalResearchToolbar');if(!root)return;const list=rows(),avgReg=list.length?list.reduce((s,r)=>s+n(r.regime_score),0)/list.length:0,avgEntry=list.length?list.reduce((s,r)=>s+n(r.entry_score),0)/list.length:0,candidates=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,6);
    root.innerHTML=`<div class="canonical-market-pulse"><div><span>시장 분위기</span><b>${avgReg.toFixed(0)}<small>/100</small></b></div><div><span>평균 진입여건</span><b>${avgEntry.toFixed(0)}<small>/100</small></b></div><div><span>관찰 후보</span><b>${list.filter(r=>n(r.opportunity_score)>=65).length}<small>개</small></b></div></div><div class="canonical-research-find"><label><span>코인 찾기</span><input id="canonicalCoinSearch" type="search" placeholder="티커·코인명 검색" autocomplete="off"><div id="canonicalCoinSuggestions" class="canonical-suggestions" hidden></div></label><div class="canonical-candidates"><span>우선 확인</span>${candidates.map(r=>`<button type="button" data-canonical-market="${r.market}"><b>${r.symbol||String(r.market).replace(/^KRW-/,'')}</b><small>${n(r.opportunity_score).toFixed(0)}</small></button>`).join('')}</div></div>`;
    q('.asset-chip-shell',panelOrDocument())?.classList.add('canonical-hidden');
  }

  function panelOrDocument(){return q('[data-view-panel="coin"]')||document}

  function renderResearchSuggestions(term){
    const box=q('#canonicalCoinSuggestions');if(!box)return;const s=String(term||'').trim().toLowerCase();if(!s){box.hidden=true;return}
    const matches=rows().filter(r=>`${r.symbol||''} ${r.name||''} ${r.market||''}`.toLowerCase().includes(s)).slice(0,8);
    box.innerHTML=matches.length?matches.map(r=>`<button type="button" data-canonical-market="${r.market}"><span><b>${r.symbol||r.market}</b><small>${r.name||r.market}</small></span><em>${r.has_position?'보유':`기회 ${n(r.opportunity_score).toFixed(0)}`}</em></button>`).join(''):'<div>검색 결과가 없습니다.</div>';box.hidden=false;
  }

  function ensurePaperTabs(panel){
    if(!panel)return;let nav=q('.canonical-paper-tabs',panel);if(nav)return;
    nav=document.createElement('nav');nav.className='canonical-paper-tabs';nav.setAttribute('aria-label','PAPER 보기');nav.innerHTML='<button type="button" data-paper-mode="performance">성과</button><button type="button" data-paper-mode="records">거래기록</button><button type="button" data-paper-mode="strategy">전략비교</button><button type="button" data-paper-mode="compare">거래소비교</button>';
    q('.page-head',panel)?.insertAdjacentElement('afterend',nav);nav.addEventListener('click',event=>{const b=event.target.closest('[data-paper-mode]');if(b)setPaperMode(b.dataset.paperMode)});
  }

  function setPaperMode(mode){
    paperMode=['performance','records','strategy','compare'].includes(mode)?mode:'performance';
    if(paperMode==='records'){if(typeof switchView==='function')switchView('records');return}
    if(typeof switchView==='function')switchView('results');
    if(paperMode==='compare'){window.cryptoResearchExchange?.setMode?.('compare')}
    else if(window.cryptoResearchExchange?.mode==='compare'){window.cryptoResearchExchange?.setMode?.(lastNormalExchange)}
    applyPaperMode();
  }

  function applyPaperMode(){
    const results=q('[data-view-panel="results"]'),records=q('[data-view-panel="records"]');ensurePaperTabs(results);ensurePaperTabs(records);
    qa('.canonical-paper-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.paperMode===paperMode));
    if(results){results.dataset.paperMode=paperMode;const layout=q('#parityResearchLayout',results)||q('.results-card',results),summary=q('#v3ResultSummary',results),strategy=q('#strategyLabCard',results),toggle=q('#uxStrategyToggle',results),compare=q('#phase3CompareWorkspace',results),capital=q('.canonical-paper-capital',results);[layout,summary,capital].forEach(el=>{if(el)el.hidden=paperMode!=='performance'});if(strategy)strategy.hidden=paperMode!=='strategy';if(toggle)toggle.hidden=true;if(compare)compare.hidden=paperMode!=='compare'}
  }

  function ensureSystemUtility(){
    const pill=q('#freshnessPill');if(pill)pill.title='클릭하면 시스템 상태를 확인합니다.';
  }

  function updateAssetsState(){const panel=ensureAssetsPanel(),hold=q('#holdingsCard',panel),empty=q('#canonicalAssetsEmpty',panel);if(!panel||!empty)return;empty.hidden=Boolean(hold&&!hold.classList.contains('hidden'))}

  function mapActiveNav(){const v=stateRef()?.activeView||'home',mapped=v==='assets'?'assets':v==='records'?'results':v==='settings'?'':v;qa('#viewerNav [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===mapped));q('#canonicalSystemBtn')?.classList.toggle('active',v==='settings')}

  function wrapSwitchView(){
    if(typeof window.switchView!=='function'||window.switchView.__canonical)return;const original=window.switchView;
    const wrapped=function(view){original(view);if(view==='records')paperMode='records';if(view==='results'&&paperMode==='records')paperMode='performance';mapActiveNav();if(['home','assets','coin','results','records','settings'].includes(view))requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}));if(view==='home')renderOverview();if(view==='assets')updateAssetsState();if(view==='coin')ensureResearchToolbar();if(view==='results'||view==='records')applyPaperMode()};wrapped.__canonical=true;window.switchView=wrapped;
  }

  function bindGlobal(){
    document.addEventListener('click',event=>{const jump=event.target.closest?.('[data-canonical-view]');if(jump&&typeof switchView==='function')switchView(jump.dataset.canonicalView);if(event.target.closest?.('#freshnessPill')){if(typeof switchView==='function')switchView('settings')}});
    document.addEventListener('phase3exchangechange',event=>{const ex=event.detail?.exchange;if(ex&&ex!=='compare')lastNormalExchange=ex;setTimeout(()=>{renderOverview();renderResearchToolbar();applyPaperMode()},60)});
    document.addEventListener('viewer:snapshot',()=>setTimeout(()=>{renderOverview();renderResearchToolbar();updateAssetsState()},0));
    document.addEventListener('viewer:viewchange',()=>setTimeout(()=>{mapActiveNav();applyPaperMode()},0));
  }

  function install(){
    document.documentElement.classList.remove('ia-v5','ux-v4');document.documentElement.classList.add('canonical-v1');
    ensureNavigation();ensureAssetsPanel();movePaperCapital();ensureOverview();ensureResearchToolbar();ensurePaperTabs(q('[data-view-panel="results"]'));ensurePaperTabs(q('[data-view-panel="records"]'));ensureSystemUtility();wrapSwitchView();bindGlobal();
    const home=q('[data-view-panel="home"] .viewer-intro');if(home)home.innerHTML='<div><p class="kicker">개요</p><h2>오늘 확인할 것</h2><p>주의가 필요한 항목과 자산·시장·PAPER 상태만 빠르게 확인합니다.</p></div>';
    const research=q('[data-view-panel="coin"] .page-head>div:first-child');if(research)research.innerHTML='<p class="kicker">리서치</p><h2>시장 상태와 코인 판단</h2><p>시장 상황을 먼저 보고, 관심 코인을 찾아 현재 판단을 확인합니다.</p>';
    const paper=q('[data-view-panel="results"] .page-head>div:first-child');if(paper)paper.innerHTML='<p class="kicker">PAPER</p><h2>가상매매 검증</h2><p>성과를 먼저 보고, 거래기록·전략·거래소 비교는 필요한 경우에만 전환합니다.</p>';
    q('#phase3ExchangeBar')?.classList.add('canonical-hidden');renderOverview();renderResearchToolbar();updateAssetsState();applyPaperMode();mapActiveNav();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();