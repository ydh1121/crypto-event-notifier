(()=>{
  if(window.__viewerCanonicalV4Loaded)return;
  window.__viewerCanonicalV4Loaded=true;

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
  const price=v=>{const x=n(v);if(!x)return'-';const d=x>=1000?0:x>=100?1:x>=1?3:x>=.1?5:8;return`${x.toLocaleString('ko-KR',{maximumFractionDigits:d})}원`};
  const NAV=[['home','대시보드'],['coin','리서치'],['results','PAPER'],['assets','자산']];
  const PAPER_MODES=['summary','markets','strategy','records','compare'];
  let paperMode='summary',lastExchange='bithumb',installed=false;

  const loading=t=>`<div class="v4-state"><i></i><b>${esc(t)}</b><span>데이터가 도착하면 자동으로 갱신됩니다.</span></div>`;
  const empty=(t,d)=>`<div class="v4-state is-empty"><b>${esc(t)}</b><span>${esc(d)}</span></div>`;
  const exchangeMode=()=>{const x=window.cryptoResearchExchange?.mode||pub().exchange||'bithumb';return ['bithumb','upbit','compare'].includes(x)?x:'bithumb'};
  const exLabel=x=>x==='upbit'?'업비트':'빗썸';
  const exchangeData=x=>pub().exchanges?.[x]||null;

  function ensureHeader(){
    const top=q('.top-inner'),nav=q('#viewerNav'),actions=q('.top-actions');if(!top||!nav||!actions)return;
    if(nav.parentElement!==top)top.insertBefore(nav,actions);
    const inner=q('.viewer-nav-inner',nav);if(!inner)return;
    const want=NAV.map(x=>x.join(':')).join('|'),have=qa('[data-view]',inner).map(b=>`${b.dataset.view}:${b.textContent.trim()}`).join('|');
    if(want!==have){inner.replaceChildren(...NAV.map(([view,label])=>{const b=document.createElement('button');b.type='button';b.dataset.view=view;b.textContent=label;b.onclick=()=>window.switchView?.(view);return b}))}
    inner.dataset.canonical='4';
    const active=stateRef()?.activeView||'home',mapped=active==='records'?'results':active==='settings'?'':active;
    qa('[data-view]',inner).forEach(b=>b.classList.toggle('active',b.dataset.view===mapped));
    const fresh=q('#freshnessPill');if(fresh){fresh.title='시스템 상태';fresh.onclick=()=>window.switchView?.('settings')}
  }

  function setHead(view,title,desc){
    const panel=q(`[data-view-panel="${view}"]`);if(!panel)return;const head=view==='home'?q('.viewer-intro',panel):q('.page-head',panel);if(!head)return;
    const box=q(':scope>div:first-child',head);if(!box)return;
    q('.kicker',box)?.remove();let h=q('h2',box),p=q('p',box);if(!h){h=document.createElement('h2');box.append(h)}if(!p){p=document.createElement('p');box.append(p)}h.textContent=title;p.textContent=desc;
  }
  function pageCopy(){
    setHead('home','오늘의 상태','실제 자산, 시장, PAPER 연구에서 지금 확인할 것만 한 화면에 모았습니다.');
    setHead('coin','코인 리서치','시장 상태에서 후보를 찾고, 선택한 코인의 현재 판단과 근거를 한 화면에서 봅니다.');
    setHead('results','PAPER 연구','전체 연구 성과부터 코인별 결과, 전략, 기록, 거래소 차이까지 한 작업공간에서 확인합니다.');
    setHead('assets','내 자산','실제 보유자산의 평가액, 손익, 비중과 종목별 상태만 확인합니다.');
    setHead('settings','시스템','연구 노드와 접근 권한을 확인합니다.');
  }

  function holdings(){const d=manual();return Array.isArray(d?.holdings)?d.holdings.filter(x=>n(x.volume)>0).sort((a,b)=>n(b.value_krw)-n(a.value_krw)):[]}
  function combinedPaper(){
    const parts=['bithumb','upbit'].map(exchangeData).filter(Boolean);
    if(!parts.length){const p=pub();return{start:n(p.aggregate_virtual_capital_krw),equity:n(p.equity_krw),pnl:n(p.pnl_krw),cash:n(p.cash_krw),active:n(p.active_positions),markets:n(p.market_count)}}
    return parts.reduce((a,p)=>({start:a.start+n(p.aggregate_virtual_capital_krw),equity:a.equity+n(p.equity_krw),pnl:a.pnl+n(p.pnl_krw),cash:a.cash+n(p.cash_krw),active:a.active+n(p.active_positions),markets:a.markets+n(p.market_count)}),{start:0,equity:0,pnl:0,cash:0,active:0,markets:0});
  }
  function totalClosed(d){return (d?.leaderboard||[]).reduce((s,r)=>s+n(r.closed_trades),0)}
  function weightedWin(d){const list=d?.leaderboard||[],closed=totalClosed(d);if(!closed)return 0;return list.reduce((s,r)=>s+n(r.closed_trades)*n(r.win_rate_pct)/100,0)/closed*100}

  function ensureDashboard(){const panel=q('[data-view-panel="home"]');if(!panel)return null;let root=q('#v4Dashboard',panel);if(!root){root=document.createElement('section');root.id='v4Dashboard';root.className='v4-dashboard';q('.viewer-intro',panel)?.insertAdjacentElement('afterend',root)}q('.capital-card',panel)?.classList.add('v4-hidden');q('#holdingsCard',panel)?.classList.add('v4-hidden');q('.home-grid',panel)?.classList.add('v4-hidden');return root}
  function renderDashboard(){
    const root=ensureDashboard();if(!root)return;if(!ready()){root.innerHTML=loading('대시보드 데이터를 불러오는 중입니다.');return}
    const list=rows(),d=manual(),hs=holdings(),cp=combinedPaper(),assetValue=n(d?.value_krw),assetPnl=n(d?.pnl_krw),assetRate=n(d?.invested_krw)?assetPnl/n(d.invested_krw)*100:0,paperRate=cp.start?cp.pnl/cp.start*100:0;
    const marketAvg=list.reduce((s,r)=>s+n(r.regime_score),0)/Math.max(1,list.length),candidates=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,5),worst=[...hs].sort((a,b)=>n(a.unrealized_pnl_pct)-n(b.unrealized_pnl_pct))[0];
    const alerts=[];if(worst&&n(worst.unrealized_pnl_pct)<=-10)alerts.push(`<button data-jump="assets"><b>${esc(String(worst.market).replace(/^KRW-/,''))} ${pct(worst.unrealized_pnl_pct)}</b><span>실제 보유자산 손실률이 큽니다.</span></button>`);if(candidates[0]&&n(candidates[0].opportunity_score)>=65)alerts.push(`<button data-jump="coin" data-market="${esc(candidates[0].market)}"><b>${esc(candidates[0].symbol||candidates[0].market)} 기회 ${n(candidates[0].opportunity_score).toFixed(0)}</b><span>리서치 우선 확인 후보입니다.</span></button>`);if(!alerts.length)alerts.push('<div class="is-ok"><b>즉시 확인할 경고 없음</b><span>현재 데이터 기준으로 긴급하게 확인할 항목이 없습니다.</span></div>');
    const bx=exchangeData('bithumb'),ux=exchangeData('upbit');
    root.innerHTML=`<section class="v4-alert-zone"><header><h3>먼저 확인할 것</h3><span>경고와 기회만 표시</span></header>${alerts.join('')}</section><section class="v4-kpi-row"><button data-jump="assets"><span>실제 자산</span><b>${d?money(assetValue):(privateVisible()?'등록 없음':'권한 없음')}</b><small class="${assetPnl<0?'negative':assetPnl>0?'positive':''}">${d?`${assetPnl>=0?'+':''}${money(assetPnl)} · ${pct(assetRate)}`:'개인 자산'}</small></button><button data-jump="coin"><span>시장 상태</span><b>${marketAvg.toFixed(0)}<i>/100</i></b><small>관찰 후보 ${list.filter(r=>n(r.opportunity_score)>=65).length}개</small></button><button data-jump="results" data-paper="summary"><span>전체 PAPER 증감</span><b class="${cp.pnl<0?'negative':cp.pnl>0?'positive':''}">${cp.pnl>=0?'+':''}${money(cp.pnl)}</b><small>${pct(paperRate)} · 빗썸+업비트</small></button><button data-jump="results" data-paper="markets"><span>PAPER 보유</span><b>${cp.active.toLocaleString('ko-KR')}개</b><small>${cp.markets.toLocaleString('ko-KR')}개 독립 계좌</small></button></section><section class="v4-dashboard-split"><article><header><h3>지금 볼 코인</h3><button data-jump="coin">리서치 열기</button></header><div class="v4-candidate-list">${candidates.map((r,i)=>`<button data-jump="coin" data-market="${esc(r.market)}"><i>${i+1}</i><span><b>${esc(r.symbol||r.market)}</b><small>${esc(r.name||'')}</small></span><strong>${n(r.opportunity_score).toFixed(0)}</strong></button>`).join('')}</div></article><article><header><h3>PAPER 거래소별 상태</h3><button data-jump="results" data-paper="summary">전체 보기</button></header><div class="v4-exchange-cards">${[['bithumb',bx],['upbit',ux]].map(([k,x])=>x?`<div><span>${exLabel(k)}</span><b class="${n(x.pnl_krw)<0?'negative':n(x.pnl_krw)>0?'positive':''}">${n(x.pnl_krw)>=0?'+':''}${money(x.pnl_krw)}</b><small>${pct(x.return_pct)} · 보유 ${n(x.active_positions)}개</small></div>`:`<div><span>${exLabel(k)}</span><b>-</b><small>데이터 대기</small></div>`).join('')}</div></article></section>`;
  }

  function ensureAssets(){const viewer=q('#viewerView');if(!viewer)return null;let panel=q('[data-view-panel="assets"]');if(!panel){panel=document.createElement('section');panel.className='viewer-page';panel.dataset.viewPanel='assets';q('[data-view-panel="settings"]')?.insertAdjacentElement('beforebegin',panel)}if(!q('.page-head',panel))panel.insertAdjacentHTML('afterbegin','<div class="section-head page-head"><div><h2>내 자산</h2><p>실제 보유자산을 확인합니다.</p></div></div>');let root=q('#v4AssetRoot',panel);if(!root){root=document.createElement('section');root.id='v4AssetRoot';root.className='v4-asset-root';panel.append(root)}return panel}
  function renderAssets(){
    const panel=ensureAssets(),root=q('#v4AssetRoot',panel);if(!root)return;if(!snap()){root.innerHTML=loading('자산 데이터를 불러오는 중입니다.');return}if(!privateVisible()){root.innerHTML=empty('자산정보를 볼 권한이 없습니다.','현재 계정에는 개인 자산 조회 권한이 없습니다.');return}
    const d=manual(),list=holdings();if(!d||!list.length){root.innerHTML=empty('등록된 보유자산이 없습니다.','실제 보유자산이 등록되면 이 화면에 표시됩니다.');return}
    const invested=n(d.invested_krw),value=n(d.value_krw),pnl=n(d.pnl_krw),rate=invested?pnl/invested*100:0;
    root.innerHTML=`<section class="v4-asset-summary"><div class="primary"><span>현재 평가액</span><b>${money(value)}</b><small class="${pnl<0?'negative':pnl>0?'positive':''}">${pnl>=0?'+':''}${money(pnl)} · ${pct(rate)}</small></div><div><span>투입 원금</span><b>${money(invested)}</b></div><div><span>보유 종목</span><b>${list.length}개</b></div></section><section class="v4-asset-layout"><article><header><h3>자산 배분</h3><span>평가액 기준</span></header><div class="v4-allocation">${list.map(r=>{const w=value?n(r.value_krw)/value*100:0;return`<div><p><b>${esc(String(r.market||'').replace(/^KRW-/,''))}</b><span>${w.toFixed(1)}%</span><strong>${money(r.value_krw)}</strong></p><i><em style="width:${Math.max(0,Math.min(100,w)).toFixed(1)}%"></em></i></div>`}).join('')}</div></article><article><header><h3>보유 종목</h3><span>실제 자산</span></header><div class="v4-asset-table"><div class="head"><span>종목</span><span>평단</span><span>현재가</span><span>평가액</span><span>손익률</span></div>${list.map(r=>`<div class="row"><span><b>${esc(String(r.market||'').replace(/^KRW-/,''))}</b><small>${n(r.volume).toLocaleString('ko-KR',{maximumFractionDigits:4})}개</small></span><span>${price(r.avg_price)}</span><span>${price(r.current_price)}</span><span>${money(r.value_krw)}</span><span class="${n(r.unrealized_pnl_pct)<0?'negative':n(r.unrealized_pnl_pct)>0?'positive':''}">${pct(r.unrealized_pnl_pct)}</span></div>`).join('')}</div></article></section>`;
  }

  function ensureResearch(){
    const panel=q('[data-view-panel="coin"]'),head=q('.page-head',panel);if(!panel||!head)return null;
    let shell=q('#v4ResearchShell',panel);if(!shell){shell=document.createElement('section');shell.id='v4ResearchShell';shell.className='v4-research-shell';shell.innerHTML='<aside id="v4ResearchSide"></aside><main id="v4ResearchMain"></main>';head.insertAdjacentElement('afterend',shell)}
    const side=q('#v4ResearchSide',shell),main=q('#v4ResearchMain',shell),workspace=q('.asset-workspace',panel);if(workspace&&workspace.parentElement!==main)main.append(workspace);
    q('.coin-picker',panel)?.classList.add('v4-hidden');q('#coinDetailCard',panel)?.classList.add('v4-hidden');q('.asset-chip-shell',panel)?.classList.add('v4-hidden');q('#personalToolsRemote',panel)?.classList.add('v4-hidden');q('#paperResearchExtra',panel)?.classList.add('v4-hidden');q('#strategyLabMarketCard',panel)?.classList.add('v4-hidden');
    return shell;
  }
  function renderResearch(){
    const shell=ensureResearch();if(!shell)return;const side=q('#v4ResearchSide',shell),main=q('#v4ResearchMain',shell);if(!ready()){side.innerHTML=loading('시장 데이터 불러오는 중');return}
    const list=rows(),avgR=list.reduce((s,r)=>s+n(r.regime_score),0)/list.length,avgE=list.reduce((s,r)=>s+n(r.entry_score),0)/list.length,candidates=[...list].sort((a,b)=>n(b.opportunity_score)-n(a.opportunity_score)).slice(0,8),current=list.find(r=>r.market===stateRef()?.coinMarket)||candidates[0]||list[0],mode=exchangeMode()==='upbit'?'upbit':'bithumb';
    side.innerHTML=`<section class="v4-side-section"><label>거래소</label><div class="v4-segment"><button data-research-ex="bithumb" class="${mode==='bithumb'?'active':''}">빗썸</button><button data-research-ex="upbit" class="${mode==='upbit'?'active':''}">업비트</button></div></section><section class="v4-side-metrics"><div><span>시장</span><b>${avgR.toFixed(0)}</b></div><div><span>진입</span><b>${avgE.toFixed(0)}</b></div><div><span>후보</span><b>${list.filter(r=>n(r.opportunity_score)>=65).length}</b></div></section><section class="v4-side-section"><label>코인 검색</label><input id="v4CoinSearch" type="search" placeholder="티커 또는 코인명"><div id="v4SearchResults" class="v4-search-results"></div></section><section class="v4-side-section"><label>우선 확인</label><div class="v4-watchlist">${candidates.map(r=>`<button data-market="${esc(r.market)}" class="${current?.market===r.market?'active':''}"><span><b>${esc(r.symbol||r.market)}</b><small>${esc(r.name||'')}</small></span><strong>${n(r.opportunity_score).toFixed(0)}</strong></button>`).join('')}</div></section>`;
    if(current){let preview=q('#v4ResearchPaperPreview',main);if(!preview){preview=document.createElement('section');preview.id='v4ResearchPaperPreview';preview.className='v4-paper-preview';main.append(preview)}preview.innerHTML=`<header><div><span>PAPER 참고</span><b>${esc(current.symbol||current.market)} 가상매매 상태</b></div><button data-paper-market="${esc(current.market)}">PAPER에서 보기</button></header><div><span>가상계좌</span><b>${money(current.equity_krw)}</b></div><div><span>수익률</span><b class="${n(current.return_pct)<0?'negative':n(current.return_pct)>0?'positive':''}">${pct(current.return_pct)}</b></div><div><span>완료 거래</span><b>${n(current.closed_trades)}회</b></div><div><span>승률</span><b>${n(current.win_rate_pct).toFixed(1)}%</b></div>`}
    applyResearchHierarchy();
  }
  function applyResearchHierarchy(){const panel=q('[data-view-panel="coin"]');if(!panel)return;const d=q('#assetDecisionRemote',panel),h=q('#assetDetailHeaderRemote',panel),scores=q('#assetScoreGridRemote',panel),diag=q('#assetDiagnosticsRemote',panel);if(d)d.style.order='1';if(h)h.style.order='2';if(scores)scores.style.order='3';if(diag)diag.style.order='4';q('.context-panel',panel)?.classList.add('v4-secondary')}
  function chooseMarket(market){if(!market)return;const s=stateRef();if(s)s.coinMarket=market;const sel=q('#coinSelect');if(sel){sel.value=market;sel.dispatchEvent(new Event('change',{bubbles:true}))}if(typeof renderCoin==='function')renderCoin();setTimeout(renderResearch,80)}
  function renderSearch(term){const box=q('#v4SearchResults');if(!box)return;const t=String(term||'').trim().toLowerCase();if(!t){box.innerHTML='';return}const out=rows().filter(r=>`${r.symbol||''} ${r.name||''} ${r.market||''}`.toLowerCase().includes(t)).slice(0,8);box.innerHTML=out.map(r=>`<button data-market="${esc(r.market)}"><span><b>${esc(r.symbol||r.market)}</b><small>${esc(r.name||'')}</small></span><strong>${n(r.opportunity_score).toFixed(0)}</strong></button>`).join('')||'<span class="none">검색 결과 없음</span>'}

  function ensurePaper(){
    const panel=q('[data-view-panel="results"]'),head=q('.page-head',panel);if(!panel||!head)return null;
    let nav=q('#v4PaperNav',panel);if(!nav){nav=document.createElement('nav');nav.id='v4PaperNav';nav.className='v4-paper-nav';nav.innerHTML='<button data-paper-mode="summary">요약</button><button data-paper-mode="markets">코인별 성과</button><button data-paper-mode="strategy">전략 비교</button><button data-paper-mode="records">거래 기록</button><button data-paper-mode="compare">거래소 비교</button>';head.insertAdjacentElement('afterend',nav)}
    let ctx=q('#v4PaperContext',panel);if(!ctx){ctx=document.createElement('div');ctx.id='v4PaperContext';ctx.className='v4-paper-context';ctx.innerHTML='<div class="v4-segment"><button data-paper-ex="bithumb">빗썸</button><button data-paper-ex="upbit">업비트</button></div><button id="v4PaperReset">필터 초기화</button>';nav.insertAdjacentElement('afterend',ctx)}
    let overview=q('#v4PaperOverview',panel);if(!overview){overview=document.createElement('section');overview.id='v4PaperOverview';overview.className='v4-paper-overview';ctx.insertAdjacentElement('afterend',overview)}
    let current=q('#v4PaperCurrent',panel);if(!current){current=document.createElement('section');current.id='v4PaperCurrent';current.className='v4-paper-current';overview.insertAdjacentElement('afterend',current)}
    let records=q('#v4PaperRecords',panel);if(!records){records=document.createElement('section');records.id='v4PaperRecords';records.className='v4-paper-records';current.insertAdjacentElement('afterend',records)}
    syncRecords();return panel;
  }
  function syncRecords(){const host=q('#v4PaperRecords');if(!host)return;const root=q('#recordsPort');if(root&&root.parentElement!==host)host.append(root)}
  function resetMarketFilters(){const s=stateRef();if(!s)return;s.filter='all';s.search='';q('#searchInput')&&(q('#searchInput').value='');qa('#filterRow [data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));if(typeof renderMarkets==='function')renderMarkets(true)}
  function renderPaperOverview(){
    const root=q('#v4PaperOverview');if(!root||!ready())return;const cp=combinedPaper(),ret=cp.start?cp.pnl/cp.start*100:0,b=exchangeData('bithumb'),u=exchangeData('upbit'),lab=pub().strategy_lab||{},sum=lab.candidate_summary||{};
    root.innerHTML=`<section class="v4-paper-total"><div><span>전체 PAPER 증감</span><b class="${cp.pnl<0?'negative':cp.pnl>0?'positive':''}">${cp.pnl>=0?'+':''}${money(cp.pnl)}</b><small>${pct(ret)} · 빗썸+업비트 통합</small></div><div><span>현재 평가액</span><b>${money(cp.equity)}</b><small>시작 ${money(cp.start)}</small></div><div><span>현재 보유</span><b>${cp.active.toLocaleString('ko-KR')}개</b><small>${cp.markets.toLocaleString('ko-KR')}개 독립 계좌</small></div><div><span>전략 검증</span><b>${n(sum.candidate)} 후보</b><small>${n(sum.warming)} 검증 중 · ${n(sum.rejected)} 미통과</small></div></section><section class="v4-paper-exchanges">${[['bithumb',b],['upbit',u]].map(([k,x])=>x?`<button data-open-ex="${k}"><header><b>${exLabel(k)}</b><span>코인 ${n(x.market_count)}개</span></header><strong class="${n(x.pnl_krw)<0?'negative':n(x.pnl_krw)>0?'positive':''}">${n(x.pnl_krw)>=0?'+':''}${money(x.pnl_krw)}</strong><small>${pct(x.return_pct)} · 보유 ${n(x.active_positions)}개 · 완료 ${totalClosed(x).toLocaleString('ko-KR')}회</small></button>`:`<button><header><b>${exLabel(k)}</b></header><strong>-</strong><small>데이터 대기</small></button>`).join('')}</section>`;
  }
  function renderPaperCurrent(){const root=q('#v4PaperCurrent');if(!root||!ready())return;const x=pub(),start=n(x.aggregate_virtual_capital_krw),equity=n(x.equity_krw),pnl=n(x.pnl_krw||equity-start),ret=start?pnl/start*100:n(x.return_pct),closed=totalClosed(x),win=weightedWin(x),mode=exchangeMode()==='upbit'?'upbit':'bithumb';lastExchange=mode;root.innerHTML=`<div class="v4-paper-kpis"><div class="primary"><span>${exLabel(mode)} 전체 증감</span><b class="${pnl<0?'negative':pnl>0?'positive':''}">${pnl>=0?'+':''}${money(pnl)}</b><small>${pct(ret)}</small></div><div><span>현재 평가액</span><b>${money(equity)}</b></div><div><span>보유</span><b>${n(x.active_positions)}개</b></div><div><span>완료 거래</span><b>${closed.toLocaleString('ko-KR')}회</b><small>승률 ${win.toFixed(1)}%</small></div></div>`}
  function setPaperMode(mode){paperMode=PAPER_MODES.includes(mode)?mode:'summary';try{localStorage.setItem('v4PaperMode',paperMode)}catch{};window.switchView?.('results');if(paperMode==='compare')window.cryptoResearchExchange?.setMode?.('compare');else if(exchangeMode()==='compare')window.cryptoResearchExchange?.setMode?.(lastExchange);setTimeout(()=>{syncRecords();renderPaper();applyPaperMode()},80)}
  function applyPaperMode(){
    const panel=q('[data-view-panel="results"]');if(!panel)return;qa('#v4PaperNav [data-paper-mode]').forEach(b=>b.classList.toggle('active',b.dataset.paperMode===paperMode));
    const overview=q('#v4PaperOverview'),current=q('#v4PaperCurrent'),records=q('#v4PaperRecords'),strategy=q('#strategyLabCard'),compare=q('#phase3CompareWorkspace'),layout=q('#parityResearchLayout'),card=q('.results-card',panel),ctx=q('#v4PaperContext');
    if(overview)overview.hidden=paperMode!=='summary';if(current)current.hidden=paperMode!=='markets';if(records)records.hidden=paperMode!=='records';if(strategy)strategy.hidden=paperMode!=='strategy';if(compare)compare.hidden=paperMode!=='compare';if(layout)layout.hidden=paperMode!=='markets';if(card)card.hidden=paperMode!=='markets';if(ctx)ctx.hidden=!['markets','strategy','records'].includes(paperMode);
    q('#leaderText',panel)?.classList.add('v4-hidden');q('#v3ResultSummary',panel)?.classList.add('v4-hidden');q('#v3ResultModes',panel)?.classList.add('v4-hidden');q('#uxStrategyToggle',panel)?.classList.add('v4-hidden');
  }
  function renderPaper(){ensurePaper();if(!ready()){q('#v4PaperOverview').innerHTML=loading('PAPER 데이터를 불러오는 중입니다.');return}renderPaperOverview();renderPaperCurrent();const mode=exchangeMode()==='upbit'?'upbit':'bithumb';qa('[data-paper-ex]').forEach(b=>b.classList.toggle('active',b.dataset.paperEx===mode));applyPaperMode()}

  function wrapSwitch(){if(typeof window.switchView!=='function'||window.switchView.__canonicalV4)return;const original=window.switchView;const wrapped=function(view){if(view==='records'){paperMode='records';view='results'}original(view);ensureHeader();pageCopy();if(view==='home')renderDashboard();if(view==='coin')setTimeout(renderResearch,40);if(view==='results')renderPaper();if(view==='assets')renderAssets();if(['home','coin','results','assets','settings'].includes(view))requestAnimationFrame(()=>window.scrollTo({top:0,left:0,behavior:'auto'}))};wrapped.__canonicalV4=true;window.switchView=wrapped}
  function bind(){
    document.addEventListener('click',e=>{
      const jump=e.target.closest?.('[data-jump]');if(jump){const market=jump.dataset.market;if(market)chooseMarket(market);if(jump.dataset.paper)setPaperMode(jump.dataset.paper);else window.switchView?.(jump.dataset.jump);return}
      const market=e.target.closest?.('[data-market]');if(market&&market.closest('#v4ResearchShell')){chooseMarket(market.dataset.market);return}
      const rex=e.target.closest?.('[data-research-ex]');if(rex){window.cryptoResearchExchange?.setMode?.(rex.dataset.researchEx);return}
      const pm=e.target.closest?.('[data-paper-mode]');if(pm){setPaperMode(pm.dataset.paperMode);return}
      const pe=e.target.closest?.('[data-paper-ex]');if(pe){lastExchange=pe.dataset.paperEx;window.cryptoResearchExchange?.setMode?.(lastExchange);return}
      if(e.target.closest?.('#v4PaperReset')){resetMarketFilters();return}
      const oe=e.target.closest?.('[data-open-ex]');if(oe){lastExchange=oe.dataset.openEx;window.cryptoResearchExchange?.setMode?.(lastExchange);paperMode='markets';setTimeout(renderPaper,100);return}
      const prm=e.target.closest?.('[data-paper-market]');if(prm){lastExchange=exchangeMode()==='upbit'?'upbit':'bithumb';window.switchView?.('results');paperMode='markets';const s=stateRef();if(s){s.search=String(prm.dataset.paperMarket||'').replace(/^KRW-/,'');s.filter='all'}setTimeout(()=>{renderPaper();q('#searchInput')&&(q('#searchInput').value=s?.search||'');if(typeof renderMarkets==='function')renderMarkets(true)},100)}
    });
    document.addEventListener('input',e=>{if(e.target.id==='v4CoinSearch')renderSearch(e.target.value)});
    document.addEventListener('phase3exchangechange',e=>{const x=e.detail?.exchange;if(['bithumb','upbit'].includes(x))lastExchange=x;setTimeout(()=>{renderDashboard();renderResearch();renderPaper()},100)});
    document.addEventListener('viewer:snapshot',()=>setTimeout(renderAll,0));
    const source=q('[data-view-panel="records"]');if(source)new MutationObserver(()=>syncRecords()).observe(source,{childList:true});
  }
  function renderAll(){ensureHeader();pageCopy();ensureAssets();renderDashboard();renderAssets();renderResearch();renderPaper();syncRecords()}
  function install(){if(installed)return;installed=true;document.documentElement.classList.remove('canonical-v1','canonical-v2','canonical-v3','ia-v5','ux-v4');document.documentElement.classList.add('canonical-v4');try{paperMode=localStorage.getItem('v4PaperMode')||'summary'}catch{};if(!PAPER_MODES.includes(paperMode))paperMode='summary';ensureAssets();ensurePaper();wrapSwitch();bind();renderAll()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
