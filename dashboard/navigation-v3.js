(function(){
  if(window.__cryptoDashboardNavigationV3)return;
  window.__cryptoDashboardNavigationV3=true;

  const BREEZE='cubic-bezier(0.34, 1.56, 0.64, 1)';
  const SOFT='cubic-bezier(0.22, 0.78, 0.28, 1)';
  const VIEW_ORDER=['overview','assets','performance','activity','settings'];
  const controllers=new WeakMap();
  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
  const reduced=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches===true;

  function ensureIndicator(root,className){
    if(!root)return null;
    const existing=$$(`:scope > .${className}`,root);
    existing.slice(1).forEach(node=>node.remove());
    let indicator=existing[0];
    if(!indicator){
      indicator=document.createElement('span');
      indicator.className=className;
      indicator.setAttribute('aria-hidden','true');
      indicator.innerHTML='<span class="dashboard-liquid-skin" aria-hidden="true"></span>';
      root.prepend(indicator);
    }
    if(!indicator.querySelector(':scope > .dashboard-liquid-skin')){
      indicator.innerHTML='<span class="dashboard-liquid-skin" aria-hidden="true"></span>';
    }
    return indicator;
  }

  function geometry(item){
    if(!item)return null;
    const x=item.offsetLeft,y=item.offsetTop,w=item.offsetWidth,h=item.offsetHeight;
    return w&&h?{x,y,w,h}:null;
  }

  function makeLiquidController(root,{itemSelector,indicatorClass}){
    if(!root)return null;
    const old=controllers.get(root);
    if(old){old.repair();return old;}
    let indicator=ensureIndicator(root,indicatorClass);
    const state={ready:false,x:0,y:0,w:0,h:0,animation:null};

    function activeItem(){return $(`${itemSelector}.is-active`,root)||$(itemSelector,root);}
    function settle(next){
      indicator.style.transition='none';
      indicator.style.width=`${next.w}px`;
      indicator.style.height=`${next.h}px`;
      indicator.style.transform=`translate3d(${next.x}px,${next.y}px,0)`;
      indicator.dataset.ready='true';
      state.ready=true;state.x=next.x;state.y=next.y;state.w=next.w;state.h=next.h;
    }
    function animateTaffy(next){
      const dx=next.x-state.x;
      const distance=Math.max(Math.abs(dx),Math.abs(next.w-state.w));
      const direction=Math.sign(dx)||1;
      const duration=Math.round(clamp(270+distance*.22,300,480));
      const stretch=clamp(distance*.14,7,26);
      const overshoot=clamp(distance*.045,3,9)*direction;
      const old={x:state.x,y:state.y,w:state.w||next.w,h:state.h||next.h};
      state.animation?.cancel?.();
      indicator.style.transition='none';
      if(!indicator.animate||reduced()){
        indicator.style.transition=`transform ${duration}ms ${BREEZE},width ${duration}ms ${BREEZE},height ${duration}ms ${BREEZE}`;
        indicator.style.width=`${next.w}px`;
        indicator.style.height=`${next.h}px`;
        indicator.style.transform=`translate3d(${next.x}px,${next.y}px,0)`;
        return;
      }
      const stretchX=next.x-direction*stretch*.44;
      const stretchW=next.w+stretch;
      state.animation=indicator.animate([
        {transform:`translate3d(${old.x}px,${old.y}px,0)`,width:`${old.w}px`,height:`${old.h}px`,offset:0},
        {transform:`translate3d(${stretchX}px,${next.y}px,0)`,width:`${stretchW}px`,height:`${next.h}px`,offset:.46,easing:SOFT},
        {transform:`translate3d(${next.x+overshoot}px,${next.y}px,0)`,width:`${Math.max(1,next.w-stretch*.10)}px`,height:`${next.h}px`,offset:.76,easing:BREEZE},
        {transform:`translate3d(${next.x}px,${next.y}px,0)`,width:`${next.w}px`,height:`${next.h}px`,offset:1,easing:BREEZE}
      ],{duration,fill:'forwards'});
      state.animation.onfinish=()=>{
        if(!indicator?.isConnected)return;
        state.animation=null;
        settle(next);
      };
    }
    function update({instant=false}={}){
      const item=activeItem();
      const next=geometry(item);
      if(!next||!root.isConnected)return;
      indicator=ensureIndicator(root,indicatorClass);
      const first=!state.ready;
      if(instant||first||reduced())settle(next);
      else animateTaffy(next);
      state.x=next.x;state.y=next.y;state.w=next.w;state.h=next.h;state.ready=true;
      $$(itemSelector,root).forEach(button=>button.setAttribute('aria-selected',button===item?'true':'false'));
    }
    function repair(){
      indicator=ensureIndicator(root,indicatorClass);
      update({instant:!state.ready});
    }

    const observer=new MutationObserver(records=>{
      if(records.some(record=>record.type==='attributes'&&record.attributeName==='class'))requestAnimationFrame(()=>update());
    });
    observer.observe(root,{subtree:true,attributes:true,attributeFilter:['class']});
    if('ResizeObserver'in window)new ResizeObserver(()=>update({instant:true})).observe(root);
    window.addEventListener('orientationchange',()=>setTimeout(()=>update({instant:true}),80),{passive:true});
    root.addEventListener('pointerdown',event=>{
      const item=event.target.closest?.(itemSelector);
      if(item)root.classList.add('is-liquid-pressing');
    },{passive:true});
    ['pointerup','pointercancel','pointerleave'].forEach(type=>root.addEventListener(type,()=>root.classList.remove('is-liquid-pressing'),{passive:true}));
    const controller={update,repair};controllers.set(root,controller);
    requestAnimationFrame(()=>update({instant:true}));
    return controller;
  }

  function installMainRail(){
    const root=$('.view-rail-inner');
    if(!root)return;
    root.dataset.liquidOwner='navigation-v3';
    makeLiquidController(root,{itemSelector:'.view-tab',indicatorClass:'dashboard-liquid-indicator'});
  }

  function appState(){return typeof ui==='undefined'?null:ui;}
  function assetMarkets(){return Object.keys(appState()?.snapshot?.assets||{});}

  function renderAssetChipRail(){
    const head=$('[data-view-panel="assets"] .asset-head');
    if(!head)return;
    let shell=$('#assetChipShell');
    if(!shell){
      shell=document.createElement('div');
      shell.id='assetChipShell';
      shell.className='asset-chip-shell';
      shell.innerHTML='<div id="assetChipRail" class="asset-chip-rail" role="tablist" aria-label="코인 선택"></div>';
      head.insertAdjacentElement('afterend',shell);
    }
    const rail=$('#assetChipRail');
    if(!rail)return;
    const markets=assetMarkets();
    if(!markets.length){shell.hidden=true;return;}
    shell.hidden=false;
    const signature=markets.map(m=>`${m}:${appState()?.snapshot?.assets?.[m]?.symbol||''}`).join('|');
    if(rail.dataset.signature!==signature){
      rail.dataset.signature=signature;
      const indicator=rail.querySelector(':scope > .asset-chip-indicator');
      rail.innerHTML=markets.map(m=>{
        const item=appState().snapshot.assets[m]||{};
        const label=item.symbol||m.replace('KRW-','');
        return `<button type="button" class="asset-chip" data-market="${String(m).replace(/[&<>\"']/g,'')}" role="tab">${String(label).replace(/[&<>]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]))}</button>`;
      }).join('');
      if(indicator)rail.prepend(indicator);
      rail.querySelectorAll('.asset-chip').forEach(button=>button.addEventListener('click',()=>{
        if(typeof window.selectMarket==='function')window.selectMarket(button.dataset.market,false);
        requestAnimationFrame(renderAssetChipRail);
      }));
    }
    const selected=appState()?.selectedMarket||markets[0];
    rail.querySelectorAll('.asset-chip').forEach(button=>button.classList.toggle('is-active',button.dataset.market===selected));
    const controller=makeLiquidController(rail,{itemSelector:'.asset-chip',indicatorClass:'asset-chip-indicator'});
    controller?.repair();
    if(rail.dataset.selectedMarket!==selected){
      rail.dataset.selectedMarket=selected;
      const active=rail.querySelector('.asset-chip.is-active');
      requestAnimationFrame(()=>active?.scrollIntoView({block:'nearest',inline:'center',behavior:reduced()?'auto':'smooth'}));
    }
  }

  function polishAssetHeroMetrics(){
    const market=appState()?.selectedMarket;
    const holding=typeof window.holdingFor==='function'?window.holdingFor(market):null;
    const chips=$$('.v2-holding-chip');
    if(chips.length<2)return;
    const has=!!(holding&&Number(holding.volume)>0);
    const pnl=has?Number(holding.unrealized_pnl_krw||0):0;
    const pct=has?Number(holding.unrealized_pnl_pct||0):0;
    chips[0].innerHTML=`<span>내 평단</span><b class="v4-average-value">${has?`${num(holding.avg_price,8)}원`:'입력 안 함'}</b>`;
    chips[1].innerHTML=`<span>현재 손익</span><b class="v4-pnl-value ${has?clsSign(pnl):''}">${has?`<span>${money(pnl)}</span><small>${signedPct(pct)}</small>`:'-'}</b>`;
  }

  function patchRenderAssets(){
    if(typeof window.renderAssets!=='function'||window.renderAssets.__navigationV3Wrapped)return;
    const base=window.renderAssets;
    const wrapped=function(...args){
      const result=base.apply(this,args);
      requestAnimationFrame(()=>{renderAssetChipRail();polishAssetHeroMetrics();});
      return result;
    };
    wrapped.__navigationV3Wrapped=true;
    window.renderAssets=wrapped;
  }

  function patchRenderSelectedAsset(){
    if(typeof window.renderSelectedAsset!=='function'||window.renderSelectedAsset.__navigationV3MetricsWrapped)return;
    const base=window.renderSelectedAsset;
    const wrapped=function(...args){
      const result=base.apply(this,args);
      requestAnimationFrame(polishAssetHeroMetrics);
      return result;
    };
    wrapped.__navigationV3MetricsWrapped=true;
    window.renderSelectedAsset=wrapped;
  }

  function patchSelectMarket(){
    if(typeof window.selectMarket!=='function'||window.selectMarket.__navigationV3Wrapped)return;
    const base=window.selectMarket;
    const wrapped=function(...args){
      const result=base.apply(this,args);
      requestAnimationFrame(()=>{renderAssetChipRail();polishAssetHeroMetrics();});
      return result;
    };
    wrapped.__navigationV3Wrapped=true;
    window.selectMarket=wrapped;
  }

  function interactiveSwipeTarget(target){
    return !!target?.closest?.('.view-rail-inner,.asset-chip-rail,.range-control,.avg-list,.chart-box,input,textarea,select,button,a,dialog,[contenteditable="true"],.access-url,.technical-details');
  }

  function switchAdjacentView(direction){
    const current=VIEW_ORDER.indexOf(appState()?.view||'overview');
    const next=current+direction;
    if(next<0||next>=VIEW_ORDER.length||typeof window.switchView!=='function')return false;
    window.switchView(VIEW_ORDER[next]);
    requestAnimationFrame(()=>controllers.get($('.view-rail-inner'))?.update());
    return true;
  }

  function switchAdjacentAsset(direction){
    const markets=assetMarkets();
    if(!markets.length||typeof window.selectMarket!=='function')return false;
    const current=Math.max(0,markets.indexOf(appState()?.selectedMarket));
    const next=current+direction;
    if(next<0||next>=markets.length)return false;
    window.selectMarket(markets[next],false);
    requestAnimationFrame(renderAssetChipRail);
    return true;
  }

  function installSwipePaging(){
    if(document.documentElement.dataset.dashboardSwipeV3==='true')return;
    document.documentElement.dataset.dashboardSwipeV3='true';
    let gesture=null;
    document.addEventListener('touchstart',event=>{
      if(event.touches.length!==1||interactiveSwipeTarget(event.target)){gesture=null;return;}
      const touch=event.touches[0];
      gesture={x:touch.clientX,y:touch.clientY,t:performance.now(),view:appState()?.view||'overview'};
    },{passive:true});
    document.addEventListener('touchend',event=>{
      if(!gesture||event.changedTouches.length!==1){gesture=null;return;}
      const touch=event.changedTouches[0];
      const dx=touch.clientX-gesture.x,dy=touch.clientY-gesture.y,dt=performance.now()-gesture.t;
      const absX=Math.abs(dx),absY=Math.abs(dy);
      const start=gesture;gesture=null;
      if(dt>850||absX<58||absX<absY*1.35)return;
      const direction=dx<0?1:-1;
      if(start.view==='assets'&&switchAdjacentAsset(direction))return;
      switchAdjacentView(direction);
    },{passive:true});
  }

  function demoCardShell(){
    const overview=$('[data-view-panel="overview"]');
    const holdings=$('#myHoldingsOverview');
    if(!overview||$('#autoDemoCard'))return;
    const card=document.createElement('section');
    card.id='autoDemoCard';card.className='panel auto-demo-card';
    card.innerHTML='<div class="panel-head"><div><h3>1,000만원 자동매매 데모</h3><p class="panel-copy">빗썸 원화마켓을 훑고 조건이 좋은 코인만 가상으로 매매합니다.</p></div><span class="status-pill neutral" id="autoDemoPill">준비 중</span></div><div id="autoDemoBody" class="auto-demo-body"><p class="muted">데모 상태를 불러오는 중입니다.</p></div>';
    (holdings||overview.querySelector('.kpi-grid'))?.insertAdjacentElement('afterend',card);
  }

  function won(value){return Number(value||0).toLocaleString('ko-KR',{maximumFractionDigits:0})+'원';}
  async function refreshDemoCard(){
    demoCardShell();
    const body=$('#autoDemoBody'),pill=$('#autoDemoPill');if(!body)return;
    try{
      const response=await fetch(`./runtime-demo.json?t=${Date.now()}`,{cache:'no-store'});
      if(!response.ok)throw new Error('not ready');
      const data=await response.json();
      const positions=Array.isArray(data.positions)?data.positions:[];
      const candidates=Array.isArray(data.candidates)?data.candidates:[];
      const pnl=Number(data.equity_krw||data.start_krw||0)-Number(data.start_krw||0);
      if(pill){pill.textContent=data.running?'가상매매 중':'대기';pill.className=`status-pill ${data.running?'good':'neutral'}`;}
      body.innerHTML=`<div class="auto-demo-metrics"><div><span>가상 자산</span><strong>${won(data.equity_krw)}</strong><small class="${pnl>=0?'positive':'negative'}">${pnl>=0?'+':''}${won(pnl)}</small></div><div><span>남은 현금</span><strong>${won(data.cash_krw)}</strong><small>실제 주문 없음</small></div></div><div class="auto-demo-row"><span>보유 중</span><b>${positions.length?positions.map(p=>p.symbol||String(p.market||'').replace('KRW-','')).join(', '):'없음'}</b></div><div class="auto-demo-row"><span>현재 후보</span><b>${candidates.length?candidates.slice(0,5).map(c=>c.symbol||String(c.market||'').replace('KRW-','')).join(', '):'탐색 중'}</b></div><p class="auto-demo-note">별도 가상계좌입니다. 내 실제 보유량과 기존 PAPER 기록에는 영향을 주지 않습니다.</p>`;
    }catch{
      if(pill){pill.textContent='준비 중';pill.className='status-pill neutral';}
      body.innerHTML='<p class="muted">자동 데모 프로세스가 시작되면 여기에 결과가 표시됩니다.</p>';
    }
  }

  function watchForDashboardSync(){
    let lastReload='';
    setInterval(()=>{
      const sync=appState()?.snapshot?.sync||{};
      const changed=Array.isArray(sync.changed)?sync.changed:[];
      if(sync.status!=='updated'||!changed.some(path=>String(path).startsWith('dashboard/')))return;
      const marker=String(sync.to||sync.commit||changed.join('|'));
      if(!marker||marker===lastReload)return;
      lastReload=marker;
      const key=`cryptoDashboardReload:${marker}`;
      if(sessionStorage.getItem(key)==='1')return;
      sessionStorage.setItem(key,'1');
      setTimeout(()=>location.reload(),180);
    },1800);
  }

  function install(){
    installMainRail();
    patchRenderAssets();patchRenderSelectedAsset();patchSelectMarket();
    renderAssetChipRail();polishAssetHeroMetrics();
    installSwipePaging();watchForDashboardSync();
    demoCardShell();refreshDemoCard();
    setInterval(refreshDemoCard,10000);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
  [120,500,1200].forEach(delay=>setTimeout(()=>{installMainRail();patchRenderAssets();patchRenderSelectedAsset();patchSelectMarket();renderAssetChipRail();polishAssetHeroMetrics();},delay));
})();
