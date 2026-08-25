(()=>{
  if(window.__exchangePhase3Loaded)return;
  window.__exchangePhase3Loaded=true;

  const STORAGE_KEY='cryptoViewerExchangePhase3';
  const originalFetch=window.fetch.bind(window);
  let mode='bithumb';
  let compareSearch='';
  let compareSort='return_gap';
  let selectedCompareMarket='KRW-BTC';
  let lastSignature='';

  try{
    const saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}');
    if(['bithumb','upbit','compare'].includes(saved.mode))mode=saved.mode;
    if(typeof saved.search==='string')compareSearch=saved.search;
    if(typeof saved.sort==='string')compareSort=saved.sort;
    if(typeof saved.market==='string'&&saved.market)selectedCompareMarket=saved.market;
  }catch{}

  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=v=>Number(v||0);
  const pct=(v,d=2)=>`${n(v)>=0?'+':''}${n(v).toFixed(d)}%`;
  const won=v=>`${Math.round(n(v)).toLocaleString('ko-KR')}원`;
  const price=v=>{const x=n(v);if(!x)return'-';const d=x>=1000?0:x>=100?1:x>=1?3:x>=.1?5:8;return`${x.toLocaleString('ko-KR',{maximumFractionDigits:d})}원`};
  const tone=v=>n(v)>0?'positive':n(v)<0?'negative':'';
  const label=x=>x==='upbit'?'업비트':'빗썸';
  const save=()=>{try{localStorage.setItem(STORAGE_KEY,JSON.stringify({mode,search:compareSearch,sort:compareSort,market:selectedCompareMarket}))}catch{}};

  function projectPublic(pub,exchange){
    if(!pub||!pub.exchanges||!pub.exchanges[exchange])return pub;
    const selected=pub.exchanges[exchange]||{};
    return {
      ...pub,
      ...selected,
      exchange,
      exchanges:pub.exchanges,
      exchange_records:pub.exchange_records||{},
      research_node:pub.research_node,
      recent_records:pub.exchange_records?.[exchange]||pub.recent_records,
      published_at:pub.published_at,
      multi_exchange_updated_at:pub.multi_exchange_updated_at,
    };
  }

  function transformSnapshotBody(body){
    if(!body?.snapshot?.public||mode==='compare')return body;
    const pub=body.snapshot.public;
    const selected=pub.exchanges?.[mode];
    if(!selected||!Array.isArray(selected.leaderboard)||!selected.leaderboard.length)return body;
    body.snapshot.public=projectPublic(pub,mode);
    if(n(selected.source_updated_at)>0)body.snapshot.source_ts=n(selected.source_updated_at);
    return body;
  }

  window.fetch=async(input,init)=>{
    let requestInput=input;
    try{
      const raw=typeof input==='string'?input:(input instanceof Request?input.url:String(input||''));
      const url=new URL(raw,location.origin);
      if(url.origin===location.origin&&url.pathname==='/api/market-detail'&&mode!=='compare'){
        url.searchParams.set('exchange',mode);
        requestInput=typeof input==='string'?`${url.pathname}${url.search}`:new Request(url.toString(),input);
      }
    }catch{}
    const response=await originalFetch(requestInput,init);
    try{
      const raw=typeof requestInput==='string'?requestInput:(requestInput instanceof Request?requestInput.url:String(requestInput||''));
      const url=new URL(raw,location.origin);
      if(url.origin===location.origin&&url.pathname==='/api/snapshot'&&response.ok){
        const body=transformSnapshotBody(await response.clone().json());
        const headers=new Headers(response.headers);headers.set('content-type','application/json; charset=utf-8');
        return new Response(JSON.stringify(body),{status:response.status,statusText:response.statusText,headers});
      }
    }catch{}
    return response;
  };

  function fullPublic(){
    if(typeof state==='undefined')return{};
    const pub=state.snapshot?.public||{};
    return pub.exchanges?pub:(pub.__phase3Full||pub);
  }

  function exchangeData(name){
    const pub=fullPublic();
    return pub.exchanges?.[name]||null;
  }

  function ensureFullSnapshotReference(){
    if(typeof state==='undefined'||!state.snapshot?.public)return;
    const pub=state.snapshot.public;
    if(pub.exchanges)return;
    // When app.js received a projected snapshot, the selected public payload still
    // carries the complete exchanges object by design. Nothing else is required.
  }

  function ensureBar(){
    const nav=document.getElementById('viewerNav');if(!nav)return null;
    let bar=document.getElementById('phase3ExchangeBar');
    if(bar)return bar;
    bar=document.createElement('div');
    bar.id='phase3ExchangeBar';bar.className='phase3-exchange-bar';
    bar.innerHTML='<div class="phase3-exchange-inner"><span class="phase3-exchange-label">PAPER 거래소</span><div class="phase3-exchange-segments"><button type="button" data-p3-exchange="bithumb">빗썸</button><button type="button" data-p3-exchange="upbit">업비트</button><button type="button" data-p3-exchange="compare">비교</button></div><span id="phase3ExchangeMeta" class="phase3-exchange-meta">데이터 확인 중</span></div>';
    nav.insertAdjacentElement('afterend',bar);
    bar.addEventListener('click',event=>{const btn=event.target.closest?.('[data-p3-exchange]');if(!btn)return;setMode(btn.dataset.p3Exchange)});
    return bar;
  }

  function updateBar(){
    const bar=ensureBar();if(!bar)return;
    const b=exchangeData('bithumb'),u=exchangeData('upbit');
    bar.querySelectorAll('[data-p3-exchange]').forEach(btn=>{
      const x=btn.dataset.p3Exchange;btn.classList.toggle('active',x===mode);
      if(x==='bithumb'&&b)btn.textContent=`빗썸 ${n(b.market_count)||b.leaderboard?.length||0}`;
      if(x==='upbit'&&u)btn.textContent=`업비트 ${n(u.market_count)||u.leaderboard?.length||0}`;
      if(x==='compare')btn.textContent='거래소 비교';
    });
    const meta=document.getElementById('phase3ExchangeMeta');
    if(meta){
      if(mode==='compare')meta.textContent='같은 KRW 종목의 PAPER 성과를 나란히 비교';
      else{
        const d=exchangeData(mode);meta.textContent=d?`${label(mode)} · 보유 ${n(d.active_positions)}개 · 전체 ${pct(d.return_pct)}`:`${label(mode)} 데이터 대기`;
      }
    }
  }

  function setMode(next){
    if(!['bithumb','upbit','compare'].includes(next))return;
    mode=next;save();updateBar();
    if(mode==='compare'){
      document.querySelector('#viewerNav [data-view="results"]')?.click();
      setTimeout(()=>{toggleCompare(true);renderCompare(true)},40);
      return;
    }
    toggleCompare(false);
    if(typeof loadSnapshot==='function')loadSnapshot();
    setTimeout(()=>{
      try{if(typeof renderAll==='function'&&typeof state!=='undefined'&&state.snapshot)renderAll(state.snapshot)}catch{}
      document.dispatchEvent(new CustomEvent('phase3exchangechange',{detail:{exchange:mode}}));
    },120);
  }

  function ensureCompare(){
    const panel=document.querySelector('[data-view-panel="results"]');if(!panel)return null;
    let root=document.getElementById('phase3CompareWorkspace');if(root)return root;
    root=document.createElement('section');root.id='phase3CompareWorkspace';root.className='phase3-compare-workspace';
    root.innerHTML='<div class="phase3-compare-empty">두 거래소 데이터를 기다리는 중입니다.</div>';
    const anchor=document.getElementById('parityResearchLayout')||panel.querySelector('.results-card');
    if(anchor)anchor.insertAdjacentElement('beforebegin',root);else panel.appendChild(root);
    root.addEventListener('input',event=>{if(event.target.id==='phase3CompareSearch'){compareSearch=event.target.value||'';save();renderCompare(false)}});
    root.addEventListener('change',event=>{if(event.target.id==='phase3CompareSort'){compareSort=event.target.value||'return_gap';save();renderCompare(false)}});
    root.addEventListener('click',event=>{
      const row=event.target.closest?.('[data-p3-compare-market]');if(row){selectedCompareMarket=row.dataset.p3CompareMarket;save();renderCompare(false);setTimeout(()=>document.getElementById('phase3CompareDetail')?.scrollIntoView({behavior:'smooth',block:'nearest'}),20);return}
      const view=event.target.closest?.('[data-p3-view-exchange]');if(view){selectedCompareMarket=view.dataset.market||selectedCompareMarket;mode=view.dataset.p3ViewExchange;save();updateBar();toggleCompare(false);if(typeof loadSnapshot==='function')loadSnapshot();setTimeout(()=>document.querySelector('#viewerNav [data-view="coin"]')?.click(),180)}
    });
    return root;
  }

  function toggleCompare(on){
    const panel=document.querySelector('[data-view-panel="results"]');if(!panel)return;
    panel.classList.toggle('phase3-compare-mode',Boolean(on));
    const root=ensureCompare();if(root)root.hidden=!on;
  }

  function compareRows(){
    const b=exchangeData('bithumb'),u=exchangeData('upbit');if(!b||!u)return[];
    const bm=new Map((b.leaderboard||[]).map(r=>[r.market,r]));
    const um=new Map((u.leaderboard||[]).map(r=>[r.market,r]));
    let rows=[];
    for(const [market,br] of bm){const ur=um.get(market);if(!ur)continue;rows.push({market,b:br,u:ur,returnGap:n(br.return_pct)-n(ur.return_pct),oppGap:n(br.opportunity_score)-n(ur.opportunity_score)})}
    const q=compareSearch.trim().toLowerCase();if(q)rows=rows.filter(x=>`${x.market} ${x.b.symbol||''} ${x.b.name||''} ${x.u.name||''}`.toLowerCase().includes(q));
    const sorters={return_gap:(a,b)=>Math.abs(b.returnGap)-Math.abs(a.returnGap),opportunity_gap:(a,b)=>Math.abs(b.oppGap)-Math.abs(a.oppGap),bithumb_return:(a,b)=>n(b.b.return_pct)-n(a.b.return_pct),upbit_return:(a,b)=>n(b.u.return_pct)-n(a.u.return_pct),symbol:(a,b)=>String(a.b.symbol||a.market).localeCompare(String(b.b.symbol||b.market),'ko')};
    rows.sort(sorters[compareSort]||sorters.return_gap);return rows;
  }

  function sideCard(title,exchange,row){
    if(!row)return`<article class="phase3-side-card"><h4>${esc(title)}</h4><div class="phase3-none">데이터 없음</div></article>`;
    return`<article class="phase3-side-card"><div class="phase3-side-head"><div><span>${esc(title)}</span><h4>${esc(row.symbol||row.market)}</h4></div><b class="${tone(row.return_pct)}">${pct(row.return_pct)}</b></div><div class="phase3-side-grid"><div><span>현재가</span><b>${price(row.price)}</b></div><div><span>가상계좌</span><b>${won(row.equity_krw)}</b></div><div><span>기회점수</span><b>${n(row.opportunity_score).toFixed(1)}</b></div><div><span>시장 / 진입</span><b>${n(row.regime_score).toFixed(0)} / ${n(row.entry_score).toFixed(0)}</b></div><div><span>보유금액</span><b>${won(row.position_value_krw)}</b></div><div><span>승률</span><b>${n(row.win_rate_pct).toFixed(1)}%</b></div></div><button type="button" data-p3-view-exchange="${exchange}" data-market="${esc(row.market)}">${esc(title)} 코인 화면으로 보기</button></article>`;
  }

  function renderCompare(force=false){
    if(mode!=='compare')return;
    const root=ensureCompare();if(!root)return;
    const b=exchangeData('bithumb'),u=exchangeData('upbit');
    if(!b||!u||!(b.leaderboard||[]).length||!(u.leaderboard||[]).length){root.innerHTML='<div class="phase3-compare-empty">빗썸·업비트 스냅샷이 모두 도착하면 비교가 시작됩니다.</div>';return}
    const rows=compareRows();
    const signature=`${n(b.source_updated_at)}|${n(u.source_updated_at)}|${compareSearch}|${compareSort}|${selectedCompareMarket}|${rows.length}`;
    if(!force&&signature===lastSignature)return;lastSignature=signature;
    if(!rows.some(x=>x.market===selectedCompareMarket)&&rows.length)selectedCompareMarket=rows[0].market;
    const selected=rows.find(x=>x.market===selectedCompareMarket)||rows[0];
    const common=new Set((b.leaderboard||[]).map(r=>r.market).filter(m=>(u.leaderboard||[]).some(r=>r.market===m))).size;
    root.innerHTML=`<div class="phase3-compare-head"><div><p class="kicker">EXCHANGE COMPARISON</p><h3>같은 코인, 거래소별 PAPER 결과</h3><p>가격 차이가 아니라 각 거래소의 독립 1,000만원 PAPER 계좌가 어떻게 달라지는지 비교합니다.</p></div><div class="phase3-compare-kpis"><div><span>공통 종목</span><b>${common}</b></div><div><span>빗썸 전체</span><b class="${tone(b.return_pct)}">${pct(b.return_pct)}</b></div><div><span>업비트 전체</span><b class="${tone(u.return_pct)}">${pct(u.return_pct)}</b></div></div></div><div class="phase3-compare-controls"><input id="phase3CompareSearch" type="search" value="${esc(compareSearch)}" placeholder="공통 코인 검색"><select id="phase3CompareSort"><option value="return_gap" ${compareSort==='return_gap'?'selected':''}>수익률 차이 큰 순</option><option value="opportunity_gap" ${compareSort==='opportunity_gap'?'selected':''}>기회점수 차이 큰 순</option><option value="bithumb_return" ${compareSort==='bithumb_return'?'selected':''}>빗썸 수익률 높은 순</option><option value="upbit_return" ${compareSort==='upbit_return'?'selected':''}>업비트 수익률 높은 순</option><option value="symbol" ${compareSort==='symbol'?'selected':''}>코인 이름순</option></select></div><div class="phase3-compare-table"><div class="phase3-compare-header"><span>코인</span><span>빗썸</span><span>업비트</span><span>차이</span></div>${rows.slice(0,286).map(x=>`<button type="button" class="phase3-compare-row ${x.market===selectedCompareMarket?'selected':''}" data-p3-compare-market="${esc(x.market)}"><span class="coin"><b>${esc(x.b.symbol||x.market.replace(/^KRW-/,''))}</b><small>${esc(x.b.name||x.u.name||x.market)}</small></span><span><b class="${tone(x.b.return_pct)}">${pct(x.b.return_pct)}</b><small>기회 ${n(x.b.opportunity_score).toFixed(1)} · ${x.b.has_position?'보유':'대기'}</small></span><span><b class="${tone(x.u.return_pct)}">${pct(x.u.return_pct)}</b><small>기회 ${n(x.u.opportunity_score).toFixed(1)} · ${x.u.has_position?'보유':'대기'}</small></span><span><b class="${tone(x.returnGap)}">${pct(x.returnGap)}</b><small>기회차 ${x.oppGap>=0?'+':''}${x.oppGap.toFixed(1)}</small></span></button>`).join('')}</div><div id="phase3CompareDetail" class="phase3-compare-detail"><div class="phase3-compare-detail-head"><span>${esc(selected?.market||'-')}</span><b>동일 종목 상세 비교</b></div><div class="phase3-side-by-side">${sideCard('빗썸','bithumb',selected?.b)}${sideCard('업비트','upbit',selected?.u)}</div></div>`;
  }

  function sync(){
    ensureFullSnapshotReference();updateBar();
    if(mode==='compare'){toggleCompare(true);renderCompare(false)}else toggleCompare(false);
  }

  function install(){
    ensureBar();updateBar();
    document.addEventListener('click',event=>{
      const nav=event.target.closest?.('#viewerNav [data-view]');if(nav&&mode==='compare'&&nav.dataset.view!=='results'){mode='bithumb';save();updateBar();toggleCompare(false);if(typeof loadSnapshot==='function')loadSnapshot()}
    });
    setInterval(sync,1000);
    setTimeout(()=>{
      if(mode==='compare'){document.querySelector('#viewerNav [data-view="results"]')?.click();toggleCompare(true)}
      else if(typeof loadSnapshot==='function')loadSnapshot();
      sync();
    },250);
  }

  window.cryptoResearchExchange={get mode(){return mode},setMode};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
