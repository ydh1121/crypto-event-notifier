(()=>{
  if(window.__viewerCanonicalV2Loaded)return;
  window.__viewerCanonicalV2Loaded=true;

  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const n=v=>Number(v||0),money=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`,pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stateRef=()=>{try{return typeof state!=='undefined'?state:null}catch{return null}};
  const snap=()=>stateRef()?.snapshot||null;
  const pub=()=>snap()?.public||{};
  const rows=()=>Array.isArray(pub().leaderboard)?pub().leaderboard:[];
  const dataReady=()=>Boolean(snap()&&rows().length);
  const privateVisible=()=>Boolean(snap()?.private_visible);
  const manual=()=>privateVisible()?snap()?.private?.manual_holdings:null;
  const currentExchange=()=>{const x=window.cryptoResearchExchange?.mode||pub().exchange||'bithumb';return ['bithumb','upbit','compare'].includes(x)?x:'bithumb'};
  let paperMode='performance',lastExchange='bithumb',navFrame=0,assetFrame=0;

  const NAV=[['home','개요'],['assets','자산'],['coin','리서치'],['results','PAPER']];
  const PAGE_COPY={
    home:['개요','오늘 확인할 것','주의가 필요한 항목과 자산·시장·PAPER 상태만 빠르게 확인합니다.'],
    assets:['자산','내 보유자산','실제 보유자산의 평가액·손익·비중을 확인합니다. PAPER 가상계좌와 분리해서 봅니다.'],
    coin:['리서치','시장과 코인 판단','시장 상태를 먼저 보고, 관찰할 코인을 찾은 뒤 현재 판단과 근거를 확인합니다.'],
    results:['PAPER','가상매매 검증','전체 성과를 먼저 보고, 거래기록·전략·거래소 비교는 필요한 경우에만 전환합니다.'],
    records:['PAPER · 거래기록','체결·학습 이력','가상 체결과 학습 변화를 시간순으로 확인합니다.'],
    settings:['시스템','연구 노드와 접근 권한','연구 서버 상태와 계정 권한만 확인합니다. 외부 웹에서는 매매를 제어하지 않습니다.'],
  };

  function navSignature(){return qa('#viewerNav [data-view]').map(b=>`${b.dataset.view}:${b.textContent.trim()}`).join('|')}
  function ensureNavigation(){
    const inner=q('#viewerNav .viewer-nav-inner');if(!inner)return;
    const wanted=NAV.map(x=>x.join(':')).join('|');
    if(navSignature()!==wanted){
      inner.replaceChildren(...NAV.map(([view,label])=>{const b=document.createElement('button');b.type='button';b.dataset.view=view;b.textContent=label;b.setAttribute('aria-label',label);b.onclick=()=>window.switchView?.(view);return b}));
    }
    inner.dataset.canonical='2';
    const v=stateRef()?.activeView||'home',mapped=v==='records'?'results':v==='settings'?'':v;
    qa('#viewerNav [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===mapped));
  }

  function ensureSystemUtility(){
    const actions=q('.top-actions');if(!actions)return;
    let b=q('#canonicalSystemBtn',actions);if(!b){b=document.createElement('button');b.id='canonicalSystemBtn';b.type='button';b.className='canonical-system-button';b.textContent='시스템';b.onclick=()=>window.switchView?.('settings');actions.insertBefore(b,q('#logoutBtn',actions)||null)}
    b.classList.toggle('active',stateRef()?.activeView==='settings');
    const pill=q('#freshnessPill');if(pill){pill.title='시스템 상태 보기';pill.onclick=()=>window.switchView?.('settings')}
  }

  function ensureUserChip(){
    const intro=q('[data-view-panel="home"] .viewer-intro');if(!intro)return;
    let chip=q('.user-chip',intro);if(!chip){chip=document.createElement('div');chip.className='user-chip';chip.innerHTML='<span id="userName">-</span><small id="userRole">-</small>';intro.appendChild(chip)}
    const s=stateRef();q('#userName')&&(q('#userName').textContent=s?.user?.display_name||s?.user?.email||'-');q('#userRole')&&(q('#userRole').textContent=s?.user?.role==='owner'?'관리자':'조회 사용자');
  }

  function setHead(view){
    const panel=q(`[data-view-panel="${view}"]`);if(!panel)return;
    const head=view==='home'?q('.viewer-intro',panel):q('.page-head',panel);if(!head)return;
    let box=view==='home'?q(':scope>div:first-child',head):q(':scope>div:first-child',head);if(!box)return;
    const [k,t,d]=PAGE_COPY[view]||[];if(!k)return;
    let kicker=q('.kicker',box),title=q('h2',box),desc=q('p:not(.kicker)',box);
    if(!kicker){kicker=document.createElement('p');kicker.className='kicker';box.prepend(kicker)}
    if(!title){title=document.createElement('h2');box.appendChild(title)}
    if(!desc){desc=document.createElement('p');box.appendChild(desc)}
    kicker.textContent=k;title.textContent=t;desc.textContent=d;
  }
  function applyPageCopy(){Object.keys(PAGE_COPY).forEach(setHead);ensureUserChip()}

  function ensureAssetsPanel(){
    const viewer=q('#viewerView');if(!viewer)return null;
    let panel=q('[data-view-panel="assets"]');if(!panel){panel=document.createElement('section');panel.className='viewer-page canonical-assets-page';panel.dataset.viewPanel='assets';const coin=q('[data-view-panel="coin"]');coin?.insertAdjacentElement('beforebegin',panel)}
    if(!q('.page-head',panel))panel.insertAdjacentHTML('afterbegin','<div class="section-head page-head"><div><p class="kicker">자산</p><h2>내 보유자산</h2><p>실제 보유자산의 평가액·손익·비중을 확인합니다.</p></div></div>');
    let root=q('#canonicalAssetRoot',panel);if(!root){root=document.createElement('section');root.id='canonicalAssetRoot';root.className='canonical-asset-root';panel.appendChild(root)}
    return panel;
  }

  function holdingRows(){const d=manual(),list=Array.isArray(d?.holdings)?d.holdings.filter(x=>n(x.volume)>0):[];return list.sort((a,b)=>n(b.value_krw)-n(a.value_krw))}
  function renderAssets(){
    const panel=ensureAssetsPanel(),root=q('#canonicalAssetRoot',panel);if(!root)return;
    if(!snap()){root.innerHTML=loadingBlock('자산 데이터를 불러오는 중입니다.');return}
    if(!privateVisible()){root.innerHTML=emptyBlock('자산정보를 볼 권한이 없습니다.','이 계정에는 개인 자산 조회 권한이 없습니다.');return}
    const d=manual(),list=holdingRows();if(!d||!list.length){root.innerHTML=emptyBlock('등록된 보유자산이 없습니다.','보유자산이 등록되면 평가액·손익·종목별 비중이 표시됩니다.');return}
    const invested=n(d.invested_krw),value=n(d.value_krw),pnl=n(d.pnl_krw),rate=invested?pnl/invested*100:0;
    root.innerHTML=`<section class="asset-summary-primary"><div class="asset-value"><span>현재 평가액</span><b>${money(value)}</b><small class="${pnl<0?'negative':pnl>0?'positive':''}">${pnl>=0?'+':''}${money(pnl)} · ${pct(rate)}</small></div><div><span>투입 원금</span><b>${money(invested)}</b></div><div><span>보유 종목</span><b>${list.length}개</b></div></section><section class="asset-allocation-section"><div class="canonical-section-title"><span>자산 배분</span><small>현재 평가액 기준</small></div><div class="asset-allocation-list">${list.map(r=>{const w=value>0?n(r.value_krw)/value*100:0;return`<div class="asset-allocation-row"><div><b>${esc(String(r.market||'').replace(/^KRW-/,''))}</b><span>${w.toFixed(1)}%</span><strong>${money(r.value_krw)}</strong></div><i><em style="width:${Math.max(0,Math.min(100,w)).toFixed(1)}%"></em></i></div>`}).join('')}</div></section><section class="asset-table-section"><div class="canonical-section-title"><span>보유 종목</span><small>종목을 누르면 리서치로 이동합니다.</small></div><div class="asset-table"><div class="asset-table-head"><span>종목</span><span>평단</span><span>현재가</span><span>평가액</span><span>손익률</span></div>${list.map(r=>`<button type="button" data-canonical-market="${esc(r.market)}"><span><b>${esc(String(r.market||'').replace(/^KRW-/,''))}</b><small>${n(r.volume).toLocaleString('ko-KR',{maximumFractionDigits:4})}개</small></span><span>${formatPrice(r.avg_price)}</span><span>${formatPrice(r.current_price)}</span><span>${money(r.value_krw)}</span><span class="${n(r.unrealized_pnl_pct)<0?'negative':n(r.unrealized_pnl_pct)>0?'positive':''}">${pct(r.unrealized_pnl_pct)}</span></button>`).join('')}</div></section>`;
  }

  function loadingBlock(text){return `<div class="canonical-state loading"><i></i><b>${esc(text)}</b><p>잠시만 기다려 주세요.</p></div>`}
  function emptyBlock(title,desc){return `<div class="canonical-state empty"><b>${esc(title)}</b><p>${esc(desc)}</p></div>`}
  function formatPrice(v){const x=n(v);if(!x)return'-';const d=x>=1000?0:x>=100?1:x>=1?3:x>=.1?5:8;return`${x.toLocaleString('ko-KR',{maximumFractionDigits:d})}원`}

  function ensureOverview(){const panel=q('[data-view-panel="home"]');if(!panel)return null;let root=q('#canonicalOverview',panel);if(!root){root=document.createElement('section');root.id='canonicalOverview';root.className='canonical-overview';q('.viewer-intro',panel)?.insertAdjacentElement('afterend',root)}q('.home-grid',panel)?.classList.add('canonical-hidden');q('#v3HomeFocus',panel)?.classList.add('canonical-hidden');return root}
  function renderOverview(){
    const root=ensureOverview();if(!root)return;if(!dataReady()){root.innerHTML=loadingBlock('시장과 PAPER 데이터를 불러오는 중입니다.');return}
    const p=pub(),list=rows(),d=manual(),hold=holdingRows(),worst=[...hold].sort((a,b)=>n(a.unrealized_pnl_pct)-n(b.unrealized_pnl_pct))[0],best=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score))[0],alerts=[];
    if(worst&&n(worst.unrealized_pnl_pct)<=-10)alerts.push({tone:'bad',title:`${String(worst.market).replace(/^KRW-/,'')} 손실 ${pct(worst.unrealized_pnl_pct)}`,desc:'실제 보유자산 중 손실률이 가장 큽니다.',view:'assets'});
    if(best&&n(best.opportunity_score)>=65)alerts.push({tone:'info',title:`${best.symbol||best.market} 기회점수 ${n(best.opportunity_score).toFixed(0)}`,desc:'리서치 우선 확인 후보입니다.',view:'coin',market:best.market});
    const node=p.research_node||{};if(node.supervisor_running===false||node.online===false)alerts.push({tone:'bad',title:'연구 노드 확인 필요',desc:'시스템 상태를 확인하세요.',view:'settings'});
    if(!alerts.length)alerts.push({tone:'good',title:'즉시 확인할 경고 없음',desc:'자산·리서치·PAPER 요약을 확인하면 됩니다.',view:'home'});
    const marketAvg=list.reduce((s,r)=>s+n(r.regime_score),0)/Math.max(1,list.length),closed=list.reduce((s,r)=>s+n(r.closed_trades),0),assetPnl=n(d?.pnl_krw),assetValue=n(d?.value_krw),assetRate=n(d?.invested_krw)?assetPnl/n(d.invested_krw)*100:0;
    root.innerHTML=`<section class="canonical-priority"><div class="canonical-section-title"><span>먼저 확인할 것</span><small>주의·기회 항목만 표시합니다.</small></div><div class="canonical-alerts">${alerts.slice(0,3).map(a=>`<button type="button" class="canonical-alert ${a.tone}" data-canonical-view="${a.view}" ${a.market?`data-canonical-market="${esc(a.market)}"`:''}><span></span><div><b>${esc(a.title)}</b><small>${esc(a.desc)}</small></div><em>보기</em></button>`).join('')}</div></section><section class="canonical-overview-grid"><button type="button" data-canonical-view="assets"><span>내 자산</span><b>${d?money(assetValue):(privateVisible()?'등록 없음':'권한 없음')}</b><small class="${assetPnl<0?'negative':assetPnl>0?'positive':''}">${d?`${assetPnl>=0?'+':''}${money(assetPnl)} · ${pct(assetRate)}`:'실제 보유자산'}</small></button><button type="button" data-canonical-view="coin"><span>시장</span><b>${marketAvg.toFixed(0)}<i>/100</i></b><small>${best?`우선 후보 ${esc(best.symbol||best.market)}`:'후보 계산 중'}</small></button><button type="button" data-canonical-view="results"><span>PAPER</span><b class="${n(p.return_pct)<0?'negative':n(p.return_pct)>0?'positive':''}">${pct(p.return_pct)}</b><small>완료 거래 ${closed.toLocaleString('ko-KR')}회 · 보유 ${n(p.active_positions)}개</small></button></section>`;
  }

  function ensureResearch(){
    const panel=q('[data-view-panel="coin"]'),head=q('.page-head',panel);if(!panel||!head)return null;
    let root=q('#canonicalResearchToolbar',panel);if(!root){root=document.createElement('section');root.id='canonicalResearchToolbar';root.className='canonical-research-toolbar';head.insertAdjacentElement('afterend',root);root.addEventListener('input',e=>{if(e.target.id==='canonicalCoinSearch')renderSuggestions(e.target.value)});root.addEventListener('click',e=>{const b=e.target.closest('[data-canonical-market]');if(b)selectMarket(b.dataset.canonicalMarket)})}
    return root;
  }
  function renderResearch(){
    const root=ensureResearch();if(!root)return;if(!dataReady()){root.innerHTML=loadingBlock('시장 데이터를 불러오는 중입니다.');return}
    const list=rows(),avgR=list.reduce((s,r)=>s+n(r.regime_score),0)/list.length,avgE=list.reduce((s,r)=>s+n(r.entry_score),0)/list.length,candidates=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,6);
    root.innerHTML=`<div class="canonical-market-pulse"><div><span>시장 분위기</span><b>${avgR.toFixed(0)}<small>/100</small></b></div><div><span>평균 진입여건</span><b>${avgE.toFixed(0)}<small>/100</small></b></div><div><span>관찰 후보</span><b>${list.filter(r=>n(r.opportunity_score)>=65).length}<small>개</small></b></div></div><div class="canonical-research-find"><label><span>코인 찾기</span><input id="canonicalCoinSearch" type="search" placeholder="티커·코인명 검색" autocomplete="off"><div id="canonicalCoinSuggestions" class="canonical-suggestions" hidden></div></label><div class="canonical-candidates"><span>우선 확인</span>${candidates.map(r=>`<button type="button" data-canonical-market="${esc(r.market)}"><b>${esc(r.symbol||String(r.market).replace(/^KRW-/,''))}</b><small>기회 ${n(r.opportunity_score).toFixed(0)}</small></button>`).join('')}</div></div>`;
    cleanResearchDetail();
  }
  function renderSuggestions(term){const box=q('#canonicalCoinSuggestions');if(!box)return;const s=String(term||'').trim().toLowerCase();if(!s){box.hidden=true;return}const matches=rows().filter(r=>`${r.symbol||''} ${r.name||''} ${r.market||''}`.toLowerCase().includes(s)).slice(0,8);box.innerHTML=matches.length?matches.map(r=>`<button type="button" data-canonical-market="${esc(r.market)}"><span><b>${esc(r.symbol||r.market)}</b><small>${esc(r.name||r.market)}</small></span><em>${r.has_position?'보유':`기회 ${n(r.opportunity_score).toFixed(0)}`}</em></button>`).join(''):'<div class="canonical-no-result">검색 결과가 없습니다.</div>';box.hidden=false}
  function selectMarket(market){if(!market)return;const s=stateRef();if(s)s.coinMarket=market;const select=q('#coinSelect');if(select){select.value=market;select.dispatchEvent(new Event('change',{bubbles:true}))}window.switchView?.('coin');setTimeout(cleanResearchDetail,120)}
  function cleanResearchDetail(){const port=q('#assetLocalPort');if(!port)return;q('#paperResearchExtra',port)?.classList.add('canonical-hidden');q('#personalToolsRemote',port)?.classList.add('canonical-hidden');q('#strategyLabMarketCard')?.classList.add('canonical-hidden');const line=q('.v2-holding-line',port),avg=q('.v4-average-value',port);if(line)line.hidden=Boolean(avg&&/입력 안 함/.test(avg.textContent||''))}

  function ensurePaperTabs(panel){if(!panel)return null;let nav=q('.canonical-paper-tabs',panel);if(!nav){nav=document.createElement('nav');nav.className='canonical-paper-tabs';nav.setAttribute('aria-label','PAPER 보기');nav.innerHTML='<button type="button" data-paper-mode="performance">성과</button><button type="button" data-paper-mode="records">거래기록</button><button type="button" data-paper-mode="strategy">전략비교</button><button type="button" data-paper-mode="compare">거래소비교</button>';q('.page-head',panel)?.insertAdjacentElement('afterend',nav);nav.onclick=e=>{const b=e.target.closest('[data-paper-mode]');if(b)setPaperMode(b.dataset.paperMode)}}return nav}
  function ensurePaperExchange(panel){if(!panel)return null;let root=q('.canonical-paper-exchange',panel);if(!root){root=document.createElement('div');root.className='canonical-paper-exchange';root.innerHTML='<span>거래소</span><div><button type="button" data-paper-exchange="bithumb">빗썸</button><button type="button" data-paper-exchange="upbit">업비트</button></div>';q('.canonical-paper-tabs',panel)?.insertAdjacentElement('afterend',root);root.onclick=e=>{const b=e.target.closest('[data-paper-exchange]');if(b)window.cryptoResearchExchange?.setMode?.(b.dataset.paperExchange)}}const ex=currentExchange();qa('[data-paper-exchange]',root).forEach(b=>b.classList.toggle('active',b.dataset.paperExchange===ex));root.hidden=paperMode==='compare';return root}
  function paperStats(){const list=rows(),p=pub(),closed=list.reduce((s,r)=>s+n(r.closed_trades),0),weightedWins=list.reduce((s,r)=>s+n(r.closed_trades)*n(r.win_rate_pct)/100,0),win=closed?weightedWins/closed*100:0,dd=list.length?Math.min(...list.map(r=>n(r.max_drawdown_pct))):0;return{ret:n(p.return_pct),closed,win,dd,active:n(p.active_positions),markets:n(p.market_count)||list.length}}
  function ensurePaperSummary(panel){if(!panel)return null;let root=q('#canonicalPaperSummary',panel);if(!root){root=document.createElement('section');root.id='canonicalPaperSummary';root.className='canonical-paper-summary';q('.canonical-paper-exchange',panel)?.insertAdjacentElement('afterend',root)}return root}
  function renderPaperSummary(){const panel=q('[data-view-panel="results"]');ensurePaperTabs(panel);ensurePaperExchange(panel);const root=ensurePaperSummary(panel);if(!root)return;if(!dataReady()){root.innerHTML=loadingBlock('PAPER 성과를 불러오는 중입니다.');return}const s=paperStats();root.innerHTML=`<div class="paper-primary"><span>전체 수익률</span><b class="${s.ret<0?'negative':s.ret>0?'positive':''}">${pct(s.ret)}</b><small>${s.markets}개 독립 PAPER 계좌</small></div><div><span>최대 낙폭</span><b class="${s.dd<0?'negative':''}">${pct(s.dd)}</b></div><div><span>완료 거래</span><b>${s.closed.toLocaleString('ko-KR')}회</b></div><div><span>승률</span><b>${s.closed?s.win.toFixed(1)+'%':'표본 대기'}</b></div><div><span>현재 보유</span><b>${s.active}개</b></div>`}
  function setPaperMode(mode){paperMode=['performance','records','strategy','compare'].includes(mode)?mode:'performance';if(paperMode==='records'){window.switchView?.('records');return}window.switchView?.('results');if(paperMode==='compare')window.cryptoResearchExchange?.setMode?.('compare');else if(currentExchange()==='compare')window.cryptoResearchExchange?.setMode?.(lastExchange);applyPaperMode()}
  function applyPaperMode(){
    const results=q('[data-view-panel="results"]'),records=q('[data-view-panel="records"]');ensurePaperTabs(results);ensurePaperTabs(records);qa('.canonical-paper-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.paperMode===paperMode));if(records&&stateRef()?.activeView==='records')return;
    if(!results)return;renderPaperSummary();ensurePaperExchange(results);results.dataset.paperMode=paperMode;
    const perf=[q('#canonicalPaperSummary',results),q('#parityResearchLayout',results)||q('.results-card',results),q('#v3ResultSummary',results)],strategy=q('#strategyLabCard',results),compare=q('#phase3CompareWorkspace',results),capital=q('.capital-card',results);
    perf.forEach(el=>{if(el)el.hidden=paperMode!=='performance'});if(capital)capital.hidden=true;if(strategy)strategy.hidden=paperMode!=='strategy';if(compare)compare.hidden=paperMode!=='compare';q('.canonical-paper-exchange',results)&&(q('.canonical-paper-exchange',results).hidden=paperMode==='compare');
    if(paperMode==='strategy')window.strategyLabV2?.render?.(true);
  }

  function wrapRenderMarkets(){if(typeof window.renderMarkets!=='function'||window.renderMarkets.__canonicalV2)return;const original=window.renderMarkets;const wrapped=function(force=false){const box=q('#marketList');if(!dataReady()){if(box)box.innerHTML=loadingBlock('PAPER 코인 결과를 불러오는 중입니다.');return}return original(force)};wrapped.__canonicalV2=true;window.renderMarkets=wrapped}
  function wrapSwitchView(){if(typeof window.switchView!=='function'||window.switchView.__canonicalV2)return;const original=window.switchView;const wrapped=function(view){original(view);if(view==='records')paperMode='records';if(view==='results'&&paperMode==='records')paperMode='performance';ensureNavigation();ensureSystemUtility();applyPageCopy();if(['home','assets','coin','results','records','settings'].includes(view))requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}));if(view==='home')renderOverview();if(view==='assets')renderAssets();if(view==='coin'){renderResearch();setTimeout(cleanResearchDetail,100)}if(view==='results'||view==='records')applyPaperMode()};wrapped.__canonicalV2=true;window.switchView=wrapped}

  function bind(){
    document.addEventListener('click',e=>{const jump=e.target.closest?.('[data-canonical-view]');if(jump){const market=jump.dataset.canonicalMarket;if(market)selectMarket(market);else window.switchView?.(jump.dataset.canonicalView);return}const market=e.target.closest?.('[data-canonical-market]');if(market&&!market.closest('#canonicalResearchToolbar'))selectMarket(market.dataset.canonicalMarket)});
    document.addEventListener('phase3exchangechange',e=>{const ex=e.detail?.exchange;if(['bithumb','upbit'].includes(ex))lastExchange=ex;setTimeout(()=>{renderOverview();renderResearch();renderPaperSummary();ensurePaperExchange(q('[data-view-panel="results"]'));applyPaperMode()},60)});
    document.addEventListener('viewer:snapshot',()=>setTimeout(sync,0));
    document.addEventListener('viewer:viewchange',()=>setTimeout(()=>{ensureNavigation();ensureSystemUtility();applyPaperMode()},0));
    const nav=q('#viewerNav .viewer-nav-inner');if(nav)new MutationObserver(()=>{if(navFrame)return;navFrame=requestAnimationFrame(()=>{navFrame=0;ensureNavigation()})}).observe(nav,{childList:true,subtree:true,characterData:true});
    const port=q('#assetLocalPort');if(port)new MutationObserver(()=>{if(assetFrame)return;assetFrame=requestAnimationFrame(()=>{assetFrame=0;cleanResearchDetail()})}).observe(port,{childList:true,subtree:true});
  }
  function sync(){ensureNavigation();ensureSystemUtility();ensureUserChip();applyPageCopy();ensureAssetsPanel();renderOverview();renderAssets();renderResearch();renderPaperSummary();applyPaperMode();cleanResearchDetail()}
  function install(){document.documentElement.classList.remove('ia-v5','ux-v4','canonical-v1');document.documentElement.classList.add('canonical-v2');wrapRenderMarkets();wrapSwitchView();ensureNavigation();ensureSystemUtility();ensureUserChip();applyPageCopy();ensureAssetsPanel();ensureOverview();ensureResearch();ensurePaperTabs(q('[data-view-panel="results"]'));ensurePaperTabs(q('[data-view-panel="records"]'));bind();sync();setTimeout(sync,250);setTimeout(sync,900)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();