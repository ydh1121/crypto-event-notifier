(function(){
  if(window.__cryptoDashboardNavigationV3)return;
  window.__cryptoDashboardNavigationV3=true;

  const BREEZE='cubic-bezier(0.34, 1.56, 0.64, 1)';
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

  function makeLiquidController(root,{itemSelector,indicatorClass}){
    if(!root)return null;
    const old=controllers.get(root);
    if(old){old.update({instant:true});return old;}
    let indicator=ensureIndicator(root,indicatorClass);
    const state={ready:false,x:0,w:0};

    function activeItem(){return $(`${itemSelector}.is-active`,root)||$(itemSelector,root);}
    function update({instant=false}={}){
      const item=activeItem();
      if(!item||!root.isConnected)return;
      indicator=ensureIndicator(root,indicatorClass);
      const x=item.offsetLeft,y=item.offsetTop,w=item.offsetWidth,h=item.offsetHeight;
      if(!w||!h)return;
      const distance=Math.max(Math.abs(x-state.x),Math.abs(w-state.w));
      const duration=Math.round(clamp(245+distance*.10,255,380));
      const first=!state.ready;
      indicator.style.transition=(instant||first||reduced())?'none':`transform ${duration}ms ${BREEZE}, width ${duration}ms ${BREEZE}, height ${duration}ms ${BREEZE}`;
      indicator.style.width=`${w}px`;
      indicator.style.height=`${h}px`;
      indicator.style.transform=`translate3d(${x}px,${y}px,0)`;
      indicator.dataset.ready='true';
      state.ready=true;state.x=x;state.w=w;
      $$(itemSelector,root).forEach(button=>button.setAttribute('aria-selected',button===item?'true':'false'));
      if((instant||first)&&!reduced())requestAnimationFrame(()=>{
        if(indicator?.isConnected)indicator.style.transition=`transform ${duration}ms ${BREEZE}, width ${duration}ms ${BREEZE}, height ${duration}ms ${BREEZE}`;
      });
    }

    const observer=new MutationObserver(records=>{
      if(records.some(record=>record.type==='attributes'&&record.attributeName==='class'))requestAnimationFrame(()=>update());
    });
    observer.observe(root,{subtree:true,attributes:true,attributeFilter:['class']});
    if('ResizeObserver'in window)new ResizeObserver(()=>update({instant:true})).observe(root);
    window.addEventListener('orientationchange',()=>setTimeout(()=>update({instant:true}),80),{passive:true});
    const controller={update};controllers.set(root,controller);
    requestAnimationFrame(()=>update({instant:true}));
    return controller;
  }

  function installMainRail(){
    const root=$('.view-rail-inner');
    if(!root)return;
    root.dataset.liquidOwner='navigation-v3';
    makeLiquidController(root,{itemSelector:'.view-tab',indicatorClass:'dashboard-liquid-indicator'});
  }

  function assetMarkets(){return Object.keys(window.ui?.snapshot?.assets||{});}

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
    const signature=markets.map(m=>`${m}:${window.ui?.snapshot?.assets?.[m]?.symbol||''}`).join('|');
    if(rail.dataset.signature!==signature){
      rail.dataset.signature=signature;
      rail.innerHTML=markets.map(m=>{
        const item=window.ui.snapshot.assets[m]||{};
        const label=item.symbol||m.replace('KRW-','');
        return `<button type="button" class="asset-chip" data-market="${String(m).replace(/[&<>\"']/g,'')}" role="tab">${String(label).replace(/[&<>]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]))}</button>`;
      }).join('');
      rail.querySelectorAll('.asset-chip').forEach(button=>button.addEventListener('click',()=>{
        if(typeof window.selectMarket==='function')window.selectMarket(button.dataset.market,false);
        requestAnimationFrame(()=>renderAssetChipRail());
      }));
      controllers.delete(rail);
    }
    const selected=window.ui?.selectedMarket||markets[0];
    rail.querySelectorAll('.asset-chip').forEach(button=>button.classList.toggle('is-active',button.dataset.market===selected));
    const controller=makeLiquidController(rail,{itemSelector:'.asset-chip',indicatorClass:'asset-chip-indicator'});
    controller?.update();
    if(rail.dataset.selectedMarket!==selected){
      rail.dataset.selectedMarket=selected;
      const active=rail.querySelector('.asset-chip.is-active');
      requestAnimationFrame(()=>active?.scrollIntoView({block:'nearest',inline:'center',behavior:reduced()?'auto':'smooth'}));
    }
  }

  function patchRenderAssets(){
    if(typeof window.renderAssets!=='function'||window.renderAssets.__navigationV3Wrapped)return;
    const base=window.renderAssets;
    const wrapped=function(...args){
      const result=base.apply(this,args);
      requestAnimationFrame(renderAssetChipRail);
      return result;
    };
    wrapped.__navigationV3Wrapped=true;
    window.renderAssets=wrapped;
  }

  function patchSelectMarket(){
    if(typeof window.selectMarket!=='function'||window.selectMarket.__navigationV3Wrapped)return;
    const base=window.selectMarket;
    const wrapped=function(...args){
      const result=base.apply(this,args);
      requestAnimationFrame(renderAssetChipRail);
      return result;
    };
    wrapped.__navigationV3Wrapped=true;
    window.selectMarket=wrapped;
  }

  function interactiveSwipeTarget(target){
    return !!target?.closest?.('.view-rail-inner,.asset-chip-rail,.range-control,.avg-list,.chart-box,input,textarea,select,button,a,dialog,[contenteditable="true"],.access-url,.technical-details');
  }

  function switchAdjacentView(direction){
    const current=VIEW_ORDER.indexOf(window.ui?.view||'overview');
    const next=current+direction;
    if(next<0||next>=VIEW_ORDER.length||typeof window.switchView!=='function')return false;
    window.switchView(VIEW_ORDER[next]);
    requestAnimationFrame(()=>controllers.get($('.view-rail-inner'))?.update());
    return true;
  }

  function switchAdjacentAsset(direction){
    const markets=assetMarkets();
    if(!markets.length||typeof window.selectMarket!=='function')return false;
    const current=Math.max(0,markets.indexOf(window.ui?.selectedMarket));
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
      gesture={x:touch.clientX,y:touch.clientY,t:performance.now(),view:window.ui?.view||'overview'};
    },{passive:true});
    document.addEventListener('touchend',event=>{
      if(!gesture||event.changedTouches.length!==1){gesture=null;return;}
      const touch=event.changedTouches[0];
      const dx=touch.clientX-gesture.x,dy=touch.clientY-gesture.y,dt=performance.now()-gesture.t;
      const absX=Math.abs(dx),absY=Math.abs(dy);
      const start=gesture;gesture=null;
      if(dt>850||absX<58||absX<absY*1.35)return;
      const direction=dx<0?1:-1;
      if(start.view==='assets'){
        if(switchAdjacentAsset(direction))return;
      }
      switchAdjacentView(direction);
    },{passive:true});
  }

  function watchForDashboardSync(){
    let lastReload='';
    setInterval(()=>{
      const sync=window.ui?.snapshot?.sync||{};
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
    patchRenderAssets();
    patchSelectMarket();
    renderAssetChipRail();
    installSwipePaging();
    watchForDashboardSync();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
  [120,500,1200].forEach(delay=>setTimeout(()=>{installMainRail();patchRenderAssets();patchSelectMarket();renderAssetChipRail();},delay));
})();
