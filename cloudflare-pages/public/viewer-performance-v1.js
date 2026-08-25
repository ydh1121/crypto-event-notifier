(()=>{
  if(window.__viewerPerformanceV1Loaded)return;
  window.__viewerPerformanceV1Loaded=true;

  const nativeFetch=window.fetch.bind(window);
  const nativeSetInterval=window.setInterval.bind(window);
  const NativeMutationObserver=window.MutationObserver;
  const stats={longTasks:0,maxLongTaskMs:0,marketPasses:0,marketNodeWrites:0,snapshotRequests:0};
  let patched=false;
  let snapshotInFlight=null;

  const activeView=()=>{try{return typeof state!=='undefined'?state.activeView:''}catch{return''}};
  const stackSource=()=>{try{return String(new Error().stack||'')}catch{return''}};

  window.setInterval=(callback,delay,...args)=>{
    const stack=stackSource();
    let nextDelay=Number(delay)||0;
    let guard=null;
    if(stack.includes('exchange-phase3.js')&&nextDelay<=1000)nextDelay=5000;
    if(stack.includes('asset-local-port.js')&&nextDelay===15000){nextDelay=30000;guard=()=>activeView()==='coin'}
    if(stack.includes('records-port.js')&&nextDelay===15000){nextDelay=30000;guard=()=>activeView()==='records'}
    if(stack.includes('strategy-lab-v1.js')&&nextDelay===15000){nextDelay=30000;guard=()=>activeView()==='results'}
    if(stack.includes('viewer-shell-v3.js')&&nextDelay===15000){nextDelay=30000;guard=()=>['home','results','settings'].includes(activeView())}
    if(!guard)return nativeSetInterval(callback,nextDelay,...args);
    return nativeSetInterval(()=>{if(!document.hidden&&guard())callback(...args)},nextDelay);
  };

  if(NativeMutationObserver){
    window.MutationObserver=class ViewerMutationObserver extends NativeMutationObserver{
      observe(target,options={}){
        const next={...options};
        if(target?.id==='marketList'){
          next.attributes=false;
          delete next.attributeFilter;
          next.childList=true;
          next.subtree=true;
        }else if(target?.id==='parityResultDetail'){
          next.attributes=false;
          delete next.attributeFilter;
          next.childList=true;
          next.subtree=false;
        }
        return super.observe(target,next);
      }
    };
  }

  try{
    const observer=new PerformanceObserver(list=>{
      for(const entry of list.getEntries()){
        stats.longTasks+=1;
        stats.maxLongTaskMs=Math.max(stats.maxLongTaskMs,Number(entry.duration)||0);
      }
    });
    observer.observe({entryTypes:['longtask']});
  }catch{}

  function installContainment(){
    if(document.getElementById('viewerPerformanceContainment'))return;
    const style=document.createElement('style');
    style.id='viewerPerformanceContainment';
    style.textContent='#marketList>.market-row{content-visibility:auto;contain-intrinsic-size:auto 86px}.phase3-compare-table>.phase3-compare-row{content-visibility:auto;contain-intrinsic-size:auto 72px}';
    document.head.appendChild(style);
  }

  const pEsc=v=>String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const pWon=v=>`${Math.round(Number(v||0)).toLocaleString('ko-KR')}원`;
  const pPct=(v,d=2)=>`${Number(v||0)>=0?'+':''}${Number(v||0).toFixed(d)}%`;
  const pPrice=v=>{const x=Number(v||0);if(!x)return'-';return`${x.toLocaleString('ko-KR',{maximumFractionDigits:x<1?8:x<100?4:2})}원`};
  const pTone=v=>Number(v||0)>0?'positive':Number(v||0)<0?'negative':'';
  const pStateLabel=row=>row?.state_label||(row?.has_position?'보유 중':Number(row?.closed_trades||0)>0?'매매 완료 · 대기':'미진입');
  const setText=(node,value)=>{if(node&&node.textContent!==String(value))node.textContent=String(value)};
  const setTone=(node,value)=>{if(!node)return;node.classList.remove('positive','negative');const tone=pTone(value);if(tone)node.classList.add(tone)};

  function ensureMarketStructure(node){
    if(node.querySelector('[data-market-slot="rank"]'))return false;
    node.innerHTML='<div class="rank" data-market-slot="rank"></div><div class="market-name"><b data-market-slot="symbol"></b><i data-market-slot="state"></i><small data-market-slot="name"></small></div><div class="market-metric"><span>현재가</span><b data-market-slot="price"></b><small data-market-slot="avg"></small></div><div class="market-metric"><span>보유금액</span><b data-market-slot="holding"></b><small data-market-slot="unrealized"></small></div><div class="market-metric market-return"><span>수익률</span><b data-market-slot="return"></b><small data-market-slot="trades"></small></div>';
    return true;
  }

  function updateMarketNode(node,row,index){
    const signature=[index,row.market,row.symbol,row.name,pStateLabel(row),row.price,row.position_avg_price,row.position_value_krw,row.unrealized_pnl_krw,row.return_pct,row.closed_trades,row.win_rate_pct].join('|');
    if(node.dataset.marketRenderSignature===signature)return false;
    node.dataset.marketRenderSignature=signature;
    const rebuilt=ensureMarketStructure(node);
    node.type='button';
    node.classList.add('market-row');
    node.dataset.openMarket=row.market||'';
    setText(node.querySelector('[data-market-slot="rank"]'),index+1);
    setText(node.querySelector('[data-market-slot="symbol"]'),row.symbol||row.market||'');
    setText(node.querySelector('[data-market-slot="state"]'),pStateLabel(row));
    setText(node.querySelector('[data-market-slot="name"]'),row.name||row.market||'');
    setText(node.querySelector('[data-market-slot="price"]'),pPrice(row.price));
    setText(node.querySelector('[data-market-slot="avg"]'),row.position_avg_price?`평단 ${pPrice(row.position_avg_price)}`:'평단 없음');
    setText(node.querySelector('[data-market-slot="holding"]'),pWon(row.position_value_krw));
    setText(node.querySelector('[data-market-slot="unrealized"]'),`미실현 ${Number(row.unrealized_pnl_krw||0)>=0?'+':''}${pWon(row.unrealized_pnl_krw)}`);
    const ret=node.querySelector('[data-market-slot="return"]');
    setText(ret,pPct(row.return_pct));setTone(ret,row.return_pct);
    setText(node.querySelector('[data-market-slot="trades"]'),`${Number(row.closed_trades||0)}회 · 승률 ${Number(row.win_rate_pct||0).toFixed(1)}%`);
    stats.marketNodeWrites+=1;
    return rebuilt||true;
  }

  function projectSnapshotData(data){
    const mode=window.cryptoResearchExchange?.mode;
    if(!data?.snapshot?.public||mode==='compare'||!['bithumb','upbit'].includes(mode))return data;
    const pub=data.snapshot.public;
    const selected=pub.exchanges?.[mode];
    if(!selected||!Array.isArray(selected.leaderboard)||!selected.leaderboard.length)return data;
    data.snapshot.public={...pub,...selected,exchange:mode,exchanges:pub.exchanges,exchange_records:pub.exchange_records||{},research_node:pub.research_node,recent_records:pub.exchange_records?.[mode]||pub.recent_records,published_at:pub.published_at,multi_exchange_updated_at:pub.multi_exchange_updated_at};
    if(Number(selected.source_updated_at)>0)data.snapshot.source_ts=Number(selected.source_updated_at);
    return data;
  }

  function patchCore(){
    if(patched)return;
    if(typeof state==='undefined'||typeof filteredRows!=='function'||typeof request!=='function')return;
    patched=true;
    installContainment();

    const exchangeFetch=window.fetch.bind(window);
    window.fetch=async(input,init)=>{
      try{
        const raw=typeof input==='string'?input:(input instanceof Request?input.url:String(input||''));
        const url=new URL(raw,location.origin);
        if(url.origin===location.origin&&url.pathname==='/api/snapshot')return nativeFetch(input,init);
      }catch{}
      return exchangeFetch(input,init);
    };

    renderMarkets=function(_force=false){
      const list=filteredRows();
      const signature=`${state.filter}|${state.sort}|${state.search}|${list.map((row,index)=>[index,row.market,row.symbol,row.name,pStateLabel(row),row.price,row.position_avg_price,row.position_value_krw,row.unrealized_pnl_krw,row.return_pct,row.closed_trades,row.win_rate_pct].join(':')).join(';')}`;
      if(signature===state.listSignature)return;
      state.listSignature=signature;
      const box=document.getElementById('marketList');if(!box)return;
      const scroll=box.scrollTop;
      stats.marketPasses+=1;
      if(!list.length){if(!box.querySelector(':scope>.empty'))box.innerHTML='<div class="empty">조건에 맞는 코인이 없습니다.</div>';document.dispatchEvent(new CustomEvent('viewer:marketrowsupdated'));return}
      const existing=new Map([...box.querySelectorAll(':scope>[data-open-market]')].map(node=>[node.dataset.openMarket,node]));
      const wanted=new Set(list.map(row=>String(row.market||'')));
      [...box.children].filter(node=>!node.matches('[data-open-market]')).forEach(node=>node.remove());
      let cursor=box.firstElementChild;
      for(let index=0;index<list.length;index+=1){
        const row=list[index],market=String(row.market||'');
        let node=existing.get(market);
        if(!node){node=document.createElement('button');node.className='market-row';node.dataset.openMarket=market}
        updateMarketNode(node,row,index);
        if(node!==cursor)box.insertBefore(node,cursor||null);
        cursor=node.nextElementSibling;
      }
      [...box.querySelectorAll(':scope>[data-open-market]')].forEach(node=>{if(!wanted.has(node.dataset.openMarket||''))node.remove()});
      box.scrollTop=Math.max(0,Math.min(scroll,box.scrollHeight-box.clientHeight));
      document.dispatchEvent(new CustomEvent('viewer:marketrowsupdated'));
    };

    const renderActive=()=>{
      const snapshot=state.snapshot;if(!snapshot)return;
      const pub=snapshot.public||{};
      const best=pub.best_market;
      const leader=document.getElementById('leaderText');if(leader)leader.textContent=best?.symbol?`현재 1위 ${best.symbol} ${pPct(best.return_pct)}`:'아직 순위 계산 중';
      if(state.activeView==='home'){renderCapital(pub);renderHoldings(snapshot.private,snapshot.private_visible);renderHome(pub)}
      else if(state.activeView==='coin'){populateCoinSelect();renderCoin()}
      else if(state.activeView==='results')renderMarkets(false);
      else if(state.activeView==='records')renderRecords(pub);
      else if(state.activeView==='settings')renderSettings(pub);
    };

    switchView=function(view){
      state.activeView=view;
      document.querySelectorAll('[data-view-panel]').forEach(panel=>panel.classList.toggle('active',panel.dataset.viewPanel===view));
      document.querySelectorAll('#viewerNav button[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===view));
      renderActive();
      document.dispatchEvent(new CustomEvent('viewer:viewchange',{detail:{view}}));
    };

    renderSnapshot=function(payload){
      state.snapshot=payload?.snapshot||null;
      if(!state.snapshot){const sub=document.getElementById('viewerSub');if(sub)sub.textContent='PC에서 첫 데이터를 보내면 이 화면이 자동으로 채워집니다.';updateFreshness(0,0);return}
      const pub=state.snapshot.public||{};
      const sub=document.getElementById('viewerSub');if(sub)sub.textContent='PC 원본 DB는 외부에 공개하지 않고 조회용 스냅샷만 표시합니다.';
      updateFreshness(state.snapshot.received_at,pub.source_updated_at||state.snapshot.source_ts);
      renderActive();
      document.dispatchEvent(new CustomEvent('viewer:snapshot',{detail:{view:state.activeView,sourceTs:pub.source_updated_at||state.snapshot.source_ts||0}}));
    };

    loadSnapshot=async function(){
      if(!state.user)return;
      if(snapshotInFlight)return snapshotInFlight;
      snapshotInFlight=(async()=>{
        stats.snapshotRequests+=1;
        try{
          let data=await request('/api/snapshot');
          data=projectSnapshotData(data);
          if(data.user)state.user=data.user;
          renderSnapshot(data);
          return data;
        }catch(err){if(err?.status===401){state.user=null;showAuth()}return null}
        finally{snapshotInFlight=null}
      })();
      return snapshotInFlight;
    };

    document.addEventListener('viewer:viewchange',()=>{if(!document.hidden)requestAnimationFrame(()=>{try{window.cryptoResearchExchange?.mode==='compare'&&document.querySelector('[data-view-panel="results"]')?.classList.contains('active')}catch{}})});
    window.__viewerPerformance={version:1,stats,get activeView(){return activeView()},get snapshotBusy(){return Boolean(snapshotInFlight)}};
  }

  setTimeout(patchCore,0);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(patchCore,0),{once:true});
  else setTimeout(patchCore,0);
})();