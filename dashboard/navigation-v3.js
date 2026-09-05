(function(){
  if(window.__cryptoDashboardNavigationV4)return;
  window.__cryptoDashboardNavigationV4=true;

  const BREEZE='cubic-bezier(0.34, 1.56, 0.64, 1)';
  const EDGE='cubic-bezier(0.34, 1.24, 0.64, 1)';
  const VIEW_ORDER=['overview','assets','performance','activity','settings'];
  const controllers=new WeakMap();
  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
  const reduced=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches===true;

  function skinMarkup(){return '<span class="dashboard-liquid-skin" aria-hidden="true"></span>'}

  function ensureIndicator(root,indicatorClass){
    if(!root)return null;
    const indicators=$$(`:scope > .${indicatorClass}`,root);
    indicators.slice(1).forEach(node=>node.remove());
    let indicator=indicators[0];
    if(!indicator){
      indicator=document.createElement('span');
      indicator.className=indicatorClass;
      indicator.setAttribute('aria-hidden','true');
      indicator.innerHTML=skinMarkup();
      root.prepend(indicator);
    }
    if(!indicator.querySelector(':scope > .dashboard-liquid-skin'))indicator.innerHTML=skinMarkup();
    return indicator;
  }

  function makeLiquidController(root,{itemSelector,indicatorClass,readyClass,slow=false,durationScale=1}={}){
    if(!root)return null;
    const existing=controllers.get(root);
    if(existing){existing.repair();return existing;}

    let indicator=ensureIndicator(root,indicatorClass);
    const state={x:0,y:0,w:0,h:0,ready:false,lastWidth:root.clientWidth||0,resizeTimer:0};

    function activeItem(){return root.querySelector(`${itemSelector}.is-active`)||root.querySelector(itemSelector)}
    function geometry(){
      const item=activeItem();
      if(!item)return null;
      const x=item.offsetLeft,y=item.offsetTop,w=item.offsetWidth,h=item.offsetHeight;
      if(!w||!h)return null;
      return {item,x,y,w,h};
    }
    function durationFor(x,w){
      const distance=Math.max(Math.abs(x-state.x),Math.abs(w-state.w));
      const base=clamp((slow?300:245)+distance*(slow?.18:.10),slow?320:255,slow?470:380);
      return Math.round(base*durationScale);
    }
    function setTransition(duration,easing,instant){
      indicator.style.transition=(instant||reduced())?'none':`transform ${duration}ms ${easing}, width ${duration}ms ${easing}, height ${duration}ms ${easing}`;
    }
    function update({instant=false}={}){
      if(!root.isConnected)return;
      const next=geometry();if(!next)return;
      indicator=ensureIndicator(root,indicatorClass);
      const first=!state.ready;
      const duration=durationFor(next.x,next.w);
      const firstItem=root.querySelector(itemSelector);
      const easing=next.item===firstItem?EDGE:BREEZE;
      setTransition(duration,easing,instant||first);
      indicator.style.width=`${next.w}px`;
      indicator.style.height=`${next.h}px`;
      indicator.style.transform=`translate3d(${next.x}px,${next.y}px,0)`;
      indicator.dataset.ready='true';
      Object.assign(state,{x:next.x,y:next.y,w:next.w,h:next.h,ready:true});
      root.classList.add(readyClass,'dashboard-liquid-ready');
      $$(itemSelector,root).forEach(button=>button.setAttribute('aria-selected',button===next.item?'true':'false'));
      if((instant||first)&&!reduced())requestAnimationFrame(()=>{
        if(indicator?.isConnected)setTransition(duration,easing,false);
      });
    }
    function repair(){
      if(!root.isConnected)return;
      const hasIndicator=Boolean(indicator?.isConnected&&indicator.parentNode===root);
      const hasSkin=hasIndicator&&Boolean(indicator.querySelector(':scope > .dashboard-liquid-skin'));
      if(hasIndicator&&hasSkin&&root.classList.contains(readyClass))return update({instant:true});
      indicator=ensureIndicator(root,indicatorClass);
      update({instant:true});
    }

    const classObserver=new MutationObserver(records=>{
      if(records.some(record=>record.type==='attributes'&&record.attributeName==='class'&&record.target.matches?.(itemSelector))){
        requestAnimationFrame(()=>update({instant:false}));
      }
    });
    classObserver.observe(root,{subtree:true,attributes:true,attributeFilter:['class']});

    const childObserver=new MutationObserver(()=>{
      const hasIndicator=Boolean(root.querySelector(`:scope > .${indicatorClass}`));
      const hasSkin=Boolean(root.querySelector(`:scope > .${indicatorClass} > .dashboard-liquid-skin`));
      if(!hasIndicator||!hasSkin)requestAnimationFrame(repair);
    });
    childObserver.observe(root,{childList:true,subtree:true});

    const onResize=()=>{
      const width=root.clientWidth||0;
      if(Math.abs(width-state.lastWidth)<2)return;
      state.lastWidth=width;
      clearTimeout(state.resizeTimer);
      state.resizeTimer=setTimeout(()=>update({instant:true}),90);
    };
    window.addEventListener('resize',onResize,{passive:true});
    window.visualViewport?.addEventListener?.('resize',onResize,{passive:true});

    const controller={update,repair};
    controllers.set(root,controller);
    root.__cryptoLiquidController=controller;
    requestAnimationFrame(()=>update({instant:true}));
    return controller;
  }

  function installMainRail(){
    const rail=$('.view-rail-inner');
    if(!rail)return;
    makeLiquidController(rail,{itemSelector:'.view-tab',indicatorClass:'dashboard-liquid-indicator',readyClass:'dashboard-nav-ready',durationScale:1.08});
  }

  function appState(){return typeof ui==='undefined'?null:ui}
  function assetMarkets(){return Object.keys(appState()?.snapshot?.assets||{})}

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
    const rail=$('#assetChipRail');if(!rail)return;
    const markets=assetMarkets();
    if(!markets.length){shell.hidden=true;return}
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
        window.selectMarket?.(button.dataset.market,false);
        requestAnimationFrame(renderAssetChipRail);
      }));
    }

    const selected=appState()?.selectedMarket||markets[0];
    rail.querySelectorAll('.asset-chip').forEach(button=>button.classList.toggle('is-active',button.dataset.market===selected));
    makeLiquidController(rail,{itemSelector:'.asset-chip',indicatorClass:'asset-chip-indicator',readyClass:'asset-chip-ready',slow:true})?.repair();
    rail.dataset.selectedMarket=selected;
  }

  function polishAssetHeroMetrics(){
    const market=appState()?.selectedMarket;
    const holding=typeof window.holdingFor==='function'?window.holdingFor(market):null;
    const chips=$$('.v2-holding-chip');if(chips.length<2)return;
    const has=!!(holding&&Number(holding.volume)>0);
    const pnl=has?Number(holding.unrealized_pnl_krw||0):0;
    const p=has?Number(holding.unrealized_pnl_pct||0):0;
    chips[0].innerHTML=`<span>내 평단</span><b class="v4-average-value">${has?`${num(holding.avg_price,8)}원`:'입력 안 함'}</b>`;
    chips[1].innerHTML=`<span>현재 손익</span><b class="v4-pnl-value ${has?clsSign(pnl):''}">${has?`<span>${money(pnl)}</span><small>${signedPct(p)}</small>`:'-'}</b>`;
  }

  function wrapFunction(name,tag,after){
    const fn=window[name];if(typeof fn!=='function'||fn[tag])return;
    const wrapped=function(...args){const result=fn.apply(this,args);requestAnimationFrame(after);return result};
    wrapped[tag]=true;window[name]=wrapped;
  }
  function installPatches(){
    wrapFunction('renderAssets','__navCanonical',()=>{renderAssetChipRail();polishAssetHeroMetrics()});
    wrapFunction('renderSelectedAsset','__navCanonical',polishAssetHeroMetrics);
    wrapFunction('selectMarket','__navCanonical',()=>{renderAssetChipRail();polishAssetHeroMetrics()});
  }

  function interactiveSwipeTarget(target){
    return !!target?.closest?.('.view-rail-inner,.asset-chip-rail,.range-control,.avg-list,.chart-box,input,textarea,select,button,a,dialog,[contenteditable="true"],.access-url,.technical-details,.demo-research');
  }
  function switchAdjacentView(direction){
    const current=VIEW_ORDER.indexOf(appState()?.view||'overview'),next=current+direction;
    if(next<0||next>=VIEW_ORDER.length||typeof window.switchView!=='function')return false;
    window.switchView(VIEW_ORDER[next]);
    requestAnimationFrame(()=>controllers.get($('.view-rail-inner'))?.update());
    return true;
  }
  function switchAdjacentAsset(direction){
    const markets=assetMarkets();if(!markets.length||typeof window.selectMarket!=='function')return false;
    const current=Math.max(0,markets.indexOf(appState()?.selectedMarket)),next=current+direction;
    if(next<0||next>=markets.length)return false;
    window.selectMarket(markets[next],false);
    requestAnimationFrame(renderAssetChipRail);
    return true;
  }
  function installSwipePaging(){
    if(document.documentElement.dataset.dashboardSwipeCanonical==='true')return;
    document.documentElement.dataset.dashboardSwipeCanonical='true';
    let gesture=null;
    document.addEventListener('touchstart',event=>{
      if(event.touches.length!==1||interactiveSwipeTarget(event.target)){gesture=null;return}
      const touch=event.touches[0];
      gesture={x:touch.clientX,y:touch.clientY,t:performance.now(),view:appState()?.view||'overview'};
    },{passive:true});
    document.addEventListener('touchend',event=>{
      if(!gesture||event.changedTouches.length!==1){gesture=null;return}
      const touch=event.changedTouches[0],dx=touch.clientX-gesture.x,dy=touch.clientY-gesture.y,dt=performance.now()-gesture.t,start=gesture;
      gesture=null;
      if(dt>850||Math.abs(dx)<58||Math.abs(dx)<Math.abs(dy)*1.35)return;
      const direction=dx<0?1:-1;
      if(start.view==='assets'&&switchAdjacentAsset(direction))return;
      switchAdjacentView(direction);
    },{passive:true});
  }

  function install(){
    installMainRail();
    installPatches();
    renderAssetChipRail();
    polishAssetHeroMetrics();
    installSwipePaging();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
  [120,520,1200].forEach(delay=>setTimeout(()=>{
    installMainRail();installPatches();renderAssetChipRail();polishAssetHeroMetrics();
  },delay));
})();
