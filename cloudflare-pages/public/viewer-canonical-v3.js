(()=>{
  if(window.__viewerCanonicalV3Loaded)return;
  window.__viewerCanonicalV3Loaded=true;

  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const n=v=>Number(v||0),money=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`,pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stateRef=()=>{try{return typeof state!=='undefined'?state:null}catch{return null}};
  const snap=()=>stateRef()?.snapshot||null;
  const pub=()=>snap()?.public||{};
  const rows=()=>Array.isArray(pub().leaderboard)?pub().leaderboard:[];
  const ready=()=>Boolean(snap()&&rows().length);
  const privateVisible=()=>Boolean(snap()?.private_visible);
  const manual=()=>privateVisible()?snap()?.private?.manual_holdings:null;
  const formatPrice=v=>{const x=n(v);if(!x)return'-';const d=x>=1000?0:x>=100?1:x>=1?3:x>=.1?5:8;return`${x.toLocaleString('ko-KR',{maximumFractionDigits:d})}원`};
  const NAV=[['home','개요'],['assets','자산'],['coin','리서치'],['results','PAPER']];
  let paperMode='performance',lastExchange='bithumb',installed=false,navFrame=0;

  function loading(text){return `<div class="canonical-state loading"><i></i><b>${esc(text)}</b><p>데이터가 도착하면 자동으로 갱신됩니다.</p></div>`}
  function empty(title,desc){return `<div class="canonical-state empty"><b>${esc(title)}</b><p>${esc(desc)}</p></div>`}
  function exchangeMode(){const x=window.cryptoResearchExchange?.mode||pub().exchange||'bithumb';return ['bithumb','upbit','compare'].includes(x)?x:'bithumb'}
  function exchangeLabel(x){return x==='upbit'?'업비트':'빗썸'}

  function ensureHeader(){
    const top=q('.top-inner'),nav=q('#viewerNav'),actions=q('.top-actions');if(!top||!nav||!actions)return;
    if(nav.parentElement!==top)top.insertBefore(nav,actions);
    const inner=q('.viewer-nav-inner',nav);if(!inner)return;
    const sig=qa('[data-view]',inner).map(b=>`${b.dataset.view}:${b.textContent.trim()}`).join('|'),want=NAV.map(x=>x.join(':')).join('|');
    if(sig!==want)inner.replaceChildren(...NAV.map(([view,label])=>{const b=document.createElement('button');b.type='button';b.dataset.view=view;b.textContent=label;b.onclick=()=>window.switchView?.(view);return b}));
    inner.dataset.canonical='3';
    q('#canonicalSystemBtn')?.remove();
    const fresh=q('#freshnessPill');if(fresh){fresh.title='시스템 상태 보기';fresh.onclick=()=>window.switchView?.('settings')}
    const active=stateRef()?.activeView||'home',mapped=active==='records'?'results':active==='settings'?'':active;
    qa('[data-view]',inner).forEach(b=>b.classList.toggle('active',b.dataset.view===mapped));
  }

  function setHead(view,kicker,title,desc){
    const panel=q(`[data-view-panel="${view}"]`);if(!panel)return;const head=view==='home'?q('.viewer-intro',panel):q('.page-head',panel);if(!head)return;
    const box=q(':scope>div:first-child',head);if(!box)return;
    let k=q('.kicker',box),h=q('h2',box),p=q('p:not(.kicker)',box);if(!k){k=document.createElement('p');k.className='kicker';box.prepend(k)}if(!h){h=document.createElement('h2');box.append(h)}if(!p){p=document.createElement('p');box.append(p)}
    k.textContent=kicker;h.textContent=title;p.textContent=desc;
  }
  function pageCopy(){
    setHead('home','개요','오늘 확인할 것','위험·기회와 자산·시장·PAPER 상태만 먼저 확인합니다.');
    setHead('assets','자산','내 보유자산','실제 보유자산의 평가액·손익·비중을 확인합니다.');
    setHead('coin','리서치','시장과 코인 판단','시장 상태를 보고 관찰 후보를 찾은 뒤 선택 코인의 판단 근거를 확인합니다.');
    setHead('results','PAPER','가상매매 검증','전체 성과를 기준으로 거래기록·전략·거래소 차이를 한 작업공간에서 확인합니다.');
    setHead('settings','시스템','연구 노드와 접근 권한','연구 서버와 계정 상태만 확인합니다.');
  }

  function ensureAssets(){
    const viewer=q('#viewerView');if(!viewer)return null;let panel=q('[data-view-panel="assets"]');
    if(!panel){panel=document.createElement('section');panel.className='viewer-page canonical-assets-page';panel.dataset.viewPanel='assets';q('[data-view-panel="coin"]')?.insertAdjacentElement('beforebegin',panel)}
    if(!q('.page-head',panel))panel.insertAdjacentHTML('afterbegin','<div class="section-head page-head"><div><p class="kicker">자산</p><h2>내 보유자산</h2><p>실제 보유자산을 확인합니다.</p></div></div>');
    let root=q('#canonicalAssetRoot',panel);if(!root){root=document.createElement('section');root.id='canonicalAssetRoot';root.className='canonical-asset-root';panel.append(root)}return panel;
  }
  function holdingRows(){const d=manual(),list=Array.isArray(d?.holdings)?d.holdings.filter(x=>n(x.volume)>0):[];return list.sort((a,b)=>n(b.value_krw)-n(a.value_krw))}
  function renderAssets(){
    const panel=ensureAssets(),root=q('#canonicalAssetRoot',panel);if(!root)return;if(!snap()){root.innerHTML=loading('자산 데이터를 불러오는 중입니다.');return}if(!privateVisible()){root.innerHTML=empty('자산정보를 볼 권한이 없습니다.','현재 계정에는 개인 자산 조회 권한이 없습니다.');return}
    const d=manual(),list=holdingRows();if(!d||!list.length){root.innerHTML=empty('등록된 보유자산이 없습니다.','보유자산이 등록되면 이 화면에 표시됩니다.');return}
    const invested=n(d.invested_krw),value=n(d.value_krw),pnl=n(d.pnl_krw),rate=invested?pnl/invested*100:0;
    root.innerHTML=`<section class="asset-kpis"><div class="asset-main"><span>현재 평가액</span><b>${money(value)}</b><small class="${pnl<0?'negative':pnl>0?'positive':''}">${pnl>=0?'+':''}${money(pnl)} · ${pct(rate)}</small></div><div><span>투입 원금</span><b>${money(invested)}</b></div><div><span>보유 종목</span><b>${list.length}개</b></div></section><section class="asset-split"><article><header><b>자산 배분</b><small>평가액 기준</small></header><div class="asset-bars">${list.map(r=>{const w=value?n(r.value_krw)/value*100:0;return`<div><p><b>${esc(String(r.market||'').replace(/^KRW-/,''))}</b><span>${w.toFixed(1)}%</span><strong>${money(r.value_krw)}</strong></p><i><em style="width:${Math.min(100,Math.max(0,w)).toFixed(1)}%"></em></i></div>`}).join('')}</div></article><article><header><b>보유 종목</b><small>누르면 리서치로 이동</small></header><div class="asset-table"><div class="asset-table-head"><span>종목</span><span>평단</span><span>현재가</span><span>평가액</span><span>손익률</span></div>${list.map(r=>`<button type="button" data-canonical-market="${esc(r.market)}"><span><b>${esc(String(r.market||'').replace(/^KRW-/,''))}</b><small>${n(r.volume).toLocaleString('ko-KR',{maximumFractionDigits:4})}개</small></span><span>${formatPrice(r.avg_price)}</span><span>${formatPrice(r.current_price)}</span><span>${money(r.value_krw)}</span><span class="${n(r.unrealized_pnl_pct)<0?'negative':n(r.unrealized_pnl_pct)>0?'positive':''}">${pct(r.unrealized_pnl_pct)}</span></button>`).join('')}</div></article></section>`;
  }

  function combinedPaper(){
    const ex=pub().exchanges||{};const parts=['bithumb','upbit'].map(k=>ex[k]).filter(Boolean);if(!parts.length){const p=pub();return{start:n(p.aggregate_virtual_capital_krw),equity:n(p.equity_krw),pnl:n(p.pnl_krw),active:n(p.active_positions),markets:n(p.market_count)}}
    return parts.reduce((a,p)=>({start:a.start+n(p.aggregate_virtual_capital_krw),equity:a.equity+n(p.equity_krw),pnl:a.pnl+n(p.pnl_krw),active:a.active+n(p.active_positions),markets:a.markets+n(p.market_count)}),{start:0,equity:0,pnl:0,active:0,markets:0});
  }
  function ensureOverview(){const panel=q('[data-view-panel="home"]');if(!panel)return null;let root=q('#canonicalOverview',panel);if(!root){root=document.createElement('section');root.id='canonicalOverview';root.className='canonical-overview';q('.viewer-intro',panel)?.insertAdjacentElement('afterend',root)}q('.home-grid',panel)?.classList.add('canonical-hidden');q('#v3HomeFocus',panel)?.classList.add('canonical-hidden');return root}
  function renderOverview(){
    const root=ensureOverview();if(!root)return;if(!ready()){root.innerHTML=loading('시장과 PAPER 데이터를 불러오는 중입니다.');return}
    const list=rows(),d=manual(),hold=holdingRows(),worst=[...hold].sort((a,b)=>n(a.unrealized_pnl_pct)-n(b.unrealized_pnl_pct))[0],best=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score))[0],alerts=[];
    if(worst&&n(worst.unrealized_pnl_pct)<=-10)alerts.push({tone:'bad',title:`${String(worst.market).replace(/^KRW-/,'')} ${pct(worst.unrealized_pnl_pct)}`,desc:'실제 보유자산 중 손실률이 가장 큽니다.',view:'assets'});
    if(best&&n(best.opportunity_score)>=65)alerts.push({tone:'info',title:`${best.symbol||best.market} 기회 ${n(best.opportunity_score).toFixed(0)}`,desc:'리서치 우선 확인 후보입니다.',view:'coin',market:best.market});
    const node=pub().research_node||{};if(node.supervisor_running===false||node.online===false)alerts.push({tone:'bad',title:'연구 노드 확인 필요',desc:'시스템 상태를 확인하세요.',view:'settings'});if(!alerts.length)alerts.push({tone:'good',title:'즉시 확인할 경고 없음',desc:'현재 상태에서 우선 대응할 항목이 없습니다.',view:'home'});
    const marketAvg=list.reduce((s,r)=>s+n(r.regime_score),0)/list.length,cp=combinedPaper(),paperRate=cp.start?cp.pnl/cp.start*100:0,assetPnl=n(d?.pnl_krw),assetValue=n(d?.value_krw),assetRate=n(d?.invested_krw)?assetPnl/n(d.invested_krw)*100:0;
    root.innerHTML=`<section class="canonical-priority"><header><b>먼저 확인할 것</b><small>위험·기회만 표시</small></header><div class="canonical-alerts">${alerts.slice(0,3).map(a=>`<button type="button" class="canonical-alert ${a.tone}" data-canonical-view="${a.view}" ${a.market?`data-canonical-market="${esc(a.market)}"`:''}><span></span><div><b>${esc(a.title)}</b><small>${esc(a.desc)}</small></div><em>보기</em></button>`).join('')}</div></section><section class="overview-kpis"><button data-canonical-view="assets"><span>내 자산</span><b>${d?money(assetValue):(privateVisible()?'등록 없음':'권한 없음')}</b><small class="${assetPnl<0?'negative':assetPnl>0?'positive':''}">${d?`${assetPnl>=0?'+':''}${money(assetPnl)} · ${pct(assetRate)}`:'실제 보유자산'}</small></button><button data-canonical-view="coin"><span>시장</span><b>${marketAvg.toFixed(0)}<i>/100</i></b><small>${best?`우선 후보 ${esc(best.symbol||best.market)}`:'관찰 후보 계산 중'}</small></button><button class="paper-total" data-canonical-view="results"><span>전체 PAPER 증감</span><b class="${cp.pnl<0?'negative':cp.pnl>0?'positive':''}">${cp.pnl>=0?'+':''}${money(cp.pnl)}</b><small>${pct(paperRate)} · 빗썸+업비트 합산</small></button></section>`;
  }

  function ensureResearch(){const panel=q('[data-view-panel="coin"]'),head=q('.page-head',panel);if(!panel||!head)return null;let root=q('#canonicalResearchToolbar',panel);if(!root){root=document.createElement('section');root.id='canonicalResearchToolbar';root.className='canonical-research-toolbar';head.insertAdjacentElement('afterend',root);root.addEventListener('input',e=>{if(e.target.id==='canonicalCoinSearch')renderSuggestions(e.target.value)});root.addEventListener('click',e=>{const b=e.target.closest('[data-canonical-market]');if(b)selectMarket(b.dataset.canonicalMarket)})}return root}
  function renderResearch(){
    const root=ensureResearch();if(!root)return;if(!ready()){root.innerHTML=loading('시장 데이터를 불러오는 중입니다.');return}
    const list=rows(),avgR=list.reduce((s,r)=>s+n(r.regime_score),0)/list.length,avgE=list.reduce((s,r)=>s+n(r.entry_score),0)/list.length,candidates=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,6),observed=list.filter(r=>n(r.opportunity_score)>=65).length;
    root.innerHTML=`<section class="research-pulse"><div><span>시장 분위기</span><b>${avgR.toFixed(0)}<small>/100</small></b></div><div><span>평균 진입여건</span><b>${avgE.toFixed(0)}<small>/100</small></b></div><div><span>관찰 후보</span><b>${observed}<small>개</small></b></div></section><section class="research-find"><label><span>코인 찾기</span><input id="canonicalCoinSearch" type="search" placeholder="티커·코인명 검색" autocomplete="off"><div id="canonicalCoinSuggestions" class="canonical-suggestions" hidden></div></label><div class="research-candidates"><span>우선 확인</span>${candidates.map(r=>`<button type="button" data-canonical-market="${esc(r.market)}"><b>${esc(r.symbol||r.market)}</b><small>기회 ${n(r.opportunity_score).toFixed(0)}</small></button>`).join('')}</div></section>`;
    applyResearchHierarchy();
  }
  function renderSuggestions(term){const box=q('#canonicalCoinSuggestions');if(!box)return;const t=String(term||'').trim().toLowerCase();if(!t){box.hidden=true;return}const found=rows().filter(r=>`${r.symbol||''} ${r.name||''} ${r.market||''}`.toLowerCase().includes(t)).slice(0,8);box.innerHTML=found.length?found.map(r=>`<button type="button" data-canonical-market="${esc(r.market)}"><span><b>${esc(r.symbol||r.market)}</b><small>${esc(r.name||r.market)}</small></span><em>기회 ${n(r.opportunity_score).toFixed(0)}</em></button>`).join(''):'<div>검색 결과가 없습니다.</div>';box.hidden=false}
  function selectMarket(market){if(!market)return;const s=stateRef();if(s)s.coinMarket=market;const sel=q('#coinSelect');if(sel){sel.value=market;sel.dispatchEvent(new Event('change',{bubbles:true}))}if(typeof renderCoin==='function')renderCoin();setTimeout(applyResearchHierarchy,80)}
  function applyResearchHierarchy(){
    const panel=q('[data-view-panel="coin"]');if(!panel)return;q('.coin-picker',panel)?.classList.add('canonical-hidden');q('#coinDetailCard',panel)?.classList.add('canonical-hidden');q('.asset-chip-shell',panel)?.classList.add('canonical-hidden');q('#personalToolsRemote',panel)?.classList.add('canonical-hidden');q('#paperResearchExtra',panel)?.classList.add('canonical-hidden');q('#strategyLabMarketCard',panel)?.classList.add('canonical-hidden');q('.context-panel',panel)?.classList.add('canonical-secondary-context');
    const d=q('#assetDecisionRemote',panel),h=q('#assetDetailHeaderRemote',panel),scores=q('#assetScoreGridRemote',panel),diag=q('#assetDiagnosticsRemote',panel);if(d)d.style.order='1';if(h)h.style.order='2';if(scores)scores.style.order='3';if(diag)diag.style.order='4';
    const holding=q('.v2-holding-line',panel);if(holding){const values=qa('b',holding).map(x=>x.textContent.trim());holding.hidden=values.every(v=>v==='-'||v==='입력 안 함'||v==='보유 없음')}
  }

  function ensurePaper(){
    const panel=q('[data-view-panel="results"]'),head=q('.page-head',panel);if(!panel||!head)return null;
    let tabs=q('#canonicalPaperTabs',panel);if(!tabs){tabs=document.createElement('nav');tabs.id='canonicalPaperTabs';tabs.className='paper-tabs';tabs.innerHTML='<button data-paper-mode="performance">전체 성과</button><button data-paper-mode="records">거래기록</button><button data-paper-mode="strategy">전략비교</button><button data-paper-mode="compare">거래소비교</button>';head.insertAdjacentElement('afterend',tabs);tabs.onclick=e=>{const b=e.target.closest('[data-paper-mode]');if(b)setPaperMode(b.dataset.paperMode)}}
    let ctx=q('#canonicalPaperContext',panel);if(!ctx){ctx=document.createElement('div');ctx.id='canonicalPaperContext';ctx.className='paper-context';ctx.innerHTML='<div class="paper-exchange"><span>거래소</span><button data-paper-exchange="bithumb">빗썸</button><button data-paper-exchange="upbit">업비트</button></div><button id="canonicalPaperAll" class="paper-reset">전체 보기</button>';tabs.insertAdjacentElement('afterend',ctx);ctx.onclick=e=>{const ex=e.target.closest('[data-paper-exchange]');if(ex){lastExchange=ex.dataset.paperExchange;window.cryptoResearchExchange?.setMode?.(lastExchange);return}if(e.target.closest('#canonicalPaperAll'))resetPaperFilters()}}
    let summary=q('#canonicalPaperSummary',panel);if(!summary){summary=document.createElement('section');summary.id='canonicalPaperSummary';summary.className='paper-summary';ctx.insertAdjacentElement('afterend',summary)}
    let records=q('#canonicalPaperRecords',panel);if(!records){records=document.createElement('section');records.id='canonicalPaperRecords';records.className='paper-records';summary.insertAdjacentElement('afterend',records)}
    syncRecords();return panel;
  }
  function syncRecords(){const host=q('#canonicalPaperRecords'),source=q('[data-view-panel="records"]');if(!host||!source)return;const root=q('#recordsPort',source);if(root&&root.parentElement!==host)host.append(root)}
  function resetPaperFilters(){const s=stateRef();if(!s)return;s.filter='all';s.search='';const input=q('#searchInput');if(input)input.value='';qa('#filterRow [data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));if(typeof renderMarkets==='function')renderMarkets(true);updatePaperFilters()}
  function updatePaperFilters(){const list=rows(),counts={all:list.length,holding:list.filter(r=>r.has_position).length,completed:list.filter(r=>!r.has_position&&n(r.closed_trades)>0).length,profit:list.filter(r=>n(r.return_pct)>0).length,loss:list.filter(r=>n(r.return_pct)<0).length},labels={all:'전체',holding:'보유 중',completed:'매매 완료',profit:'수익',loss:'손실'};qa('#filterRow [data-filter]').forEach(b=>{const k=b.dataset.filter;b.textContent=`${labels[k]||k} ${counts[k]??''}`.trim()})}
  function paperStats(){const p=pub(),list=rows(),start=n(p.aggregate_virtual_capital_krw),equity=n(p.equity_krw),pnl=n(p.pnl_krw||equity-start),closed=list.reduce((s,r)=>s+n(r.closed_trades),0),wins=list.reduce((s,r)=>s+n(r.closed_trades)*n(r.win_rate_pct)/100,0),win=closed?wins/closed*100:0;return{p,start,equity,pnl,closed,win}}
  function renderPaper(){
    const panel=ensurePaper(),summary=q('#canonicalPaperSummary',panel);if(!panel||!summary)return;if(!ready()){summary.innerHTML=loading('PAPER 성과를 불러오는 중입니다.');return}
    const x=paperStats(),mode=exchangeMode();if(mode!=='compare')lastExchange=mode;const ret=x.start?x.pnl/x.start*100:n(x.p.return_pct);
    summary.innerHTML=`<div class="paper-primary"><span>전체 증감액 · ${exchangeLabel(lastExchange)}</span><b class="${x.pnl<0?'negative':x.pnl>0?'positive':''}">${x.pnl>=0?'+':''}${money(x.pnl)}</b><small>${pct(ret)} · ${n(x.p.market_count)}개 독립 PAPER 계좌</small></div><div><span>현재 평가액</span><b>${money(x.equity)}</b><small>시작 ${money(x.start)}</small></div><div><span>남은 현금</span><b>${money(x.p.cash_krw)}</b></div><div><span>현재 보유</span><b>${n(x.p.active_positions)}개</b></div><div><span>완료 거래</span><b>${x.closed.toLocaleString('ko-KR')}회</b><small>승률 ${x.win.toFixed(1)}%</small></div>`;
    qa('[data-paper-exchange]',panel).forEach(b=>b.classList.toggle('active',b.dataset.paperExchange===lastExchange));updatePaperFilters();applyPaperMode();
  }
  function setPaperMode(mode){paperMode=['performance','records','strategy','compare'].includes(mode)?mode:'performance';try{localStorage.setItem('canonicalPaperMode',paperMode)}catch{};window.switchView?.('results');if(paperMode==='compare')window.cryptoResearchExchange?.setMode?.('compare');else if(exchangeMode()==='compare')window.cryptoResearchExchange?.setMode?.(lastExchange);setTimeout(()=>{syncRecords();applyPaperMode();renderPaper()},60)}
  function applyPaperMode(){
    const panel=q('[data-view-panel="results"]');if(!panel)return;qa('#canonicalPaperTabs [data-paper-mode]',panel).forEach(b=>b.classList.toggle('active',b.dataset.paperMode===paperMode));panel.dataset.paperMode=paperMode;
    const perf=[q('#canonicalPaperSummary',panel),q('#parityResearchLayout',panel),q('.results-card',panel),q('#v3ResultSummary',panel)],records=q('#canonicalPaperRecords',panel),strategy=q('#strategyLabCard',panel),compare=q('#phase3CompareWorkspace',panel),ctx=q('#canonicalPaperContext',panel);
    perf.forEach(el=>{if(el)el.hidden=paperMode!=='performance'});if(records)records.hidden=paperMode!=='records';if(strategy)strategy.hidden=paperMode!=='strategy';if(compare)compare.hidden=paperMode!=='compare';if(ctx)ctx.hidden=paperMode==='compare';
    q('#leaderText',panel)?.classList.add('canonical-hidden');q('#uxStrategyToggle',panel)?.classList.add('canonical-hidden');q('#v3ResultModes',panel)?.classList.add('canonical-hidden');
  }

  function wrapSwitch(){if(typeof window.switchView!=='function'||window.switchView.__canonicalV3)return;const original=window.switchView;const wrapped=function(view){if(view==='records'){paperMode='records';view='results'}original(view);ensureHeader();pageCopy();if(view==='home')renderOverview();if(view==='assets')renderAssets();if(view==='coin'){renderResearch();setTimeout(applyResearchHierarchy,30)}if(view==='results'){ensurePaper();renderPaper()}if(['home','assets','coin','results','settings'].includes(view))requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))};wrapped.__canonicalV3=true;window.switchView=wrapped}

  function bind(){
    document.addEventListener('click',e=>{const jump=e.target.closest?.('[data-canonical-view]');if(jump){const m=jump.dataset.canonicalMarket;if(m)selectMarket(m);window.switchView?.(jump.dataset.canonicalView);return}const market=e.target.closest?.('[data-canonical-market]');if(market&&market.closest('#canonicalAssetRoot')){selectMarket(market.dataset.canonicalMarket);window.switchView?.('coin')}});
    document.addEventListener('phase3exchangechange',e=>{const x=e.detail?.exchange;if(['bithumb','upbit'].includes(x))lastExchange=x;setTimeout(()=>{renderOverview();renderResearch();renderPaper()},80)});
    document.addEventListener('viewer:snapshot',()=>setTimeout(renderAll,0));document.addEventListener('viewer:viewchange',()=>setTimeout(()=>{ensureHeader();applyPaperMode()},0));
    const records=q('[data-view-panel="records"]');if(records)new MutationObserver(()=>syncRecords()).observe(records,{childList:true});
  }
  function renderAll(){ensureHeader();pageCopy();renderOverview();renderAssets();renderResearch();renderPaper();syncRecords();applyResearchHierarchy()}
  function install(){if(installed)return;installed=true;document.documentElement.classList.remove('canonical-v1','canonical-v2','ia-v5','ux-v4');document.documentElement.classList.add('canonical-v3');try{paperMode=localStorage.getItem('canonicalPaperMode')||'performance'}catch{};if(!['performance','records','strategy','compare'].includes(paperMode))paperMode='performance';ensureAssets();ensurePaper();wrapSwitch();bind();renderAll();const s=stateRef();if(s&&s.activeView==='results'&&s.filter!=='all')resetPaperFilters();setInterval(()=>{if(!document.hidden&&stateRef()?.user){cancelAnimationFrame(navFrame);navFrame=requestAnimationFrame(()=>{ensureHeader();renderPaper();syncRecords()})}},12000)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
