(function(){
  if(window.__cryptoDashboardNavigationV3)return;
  window.__cryptoDashboardNavigationV3=true;

  const BREEZE='cubic-bezier(0.34,1.56,0.64,1)';
  const SOFT='cubic-bezier(0.22,0.78,0.28,1)';
  const VIEW_ORDER=['overview','assets','performance','activity','settings'];
  const controllers=new WeakMap();
  const $=(selector,root=document)=>root.querySelector(selector);
  const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
  const reduced=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches===true;

  function ensureIndicator(host,className){
    if(!host)return null;
    const found=$$(`:scope > .${className}`,host);
    found.slice(1).forEach(node=>node.remove());
    let indicator=found[0];
    if(!indicator){
      indicator=document.createElement('span');
      indicator.className=className;
      indicator.setAttribute('aria-hidden','true');
      indicator.innerHTML='<span class="dashboard-liquid-skin" aria-hidden="true"></span>';
      host.appendChild(indicator);
    }
    return indicator;
  }

  function geometry(item,host,bleedX=0,bleedY=0){
    if(!item||!host)return null;
    const ir=item.getBoundingClientRect();
    const hr=host.getBoundingClientRect();
    if(ir.width<2||ir.height<2)return null;
    return {x:ir.left-hr.left-bleedX,y:ir.top-hr.top-bleedY,w:ir.width+bleedX*2,h:ir.height+bleedY*2};
  }

  function makeLiquidController(root,{itemSelector,indicatorClass,host=root,bleedX=0,bleedY=0}){
    if(!root||!host)return null;
    const old=controllers.get(root);if(old){old.repair();return old;}
    let indicator=ensureIndicator(host,indicatorClass);
    const state={ready:false,x:0,y:0,w:0,h:0,animation:null,raf:0};
    const activeItem=()=>root.querySelector(`${itemSelector}.is-active`)||root.querySelector(itemSelector);

    function settle(next){
      state.animation?.cancel?.();state.animation=null;
      indicator.style.transition='none';indicator.style.width=`${next.w}px`;indicator.style.height=`${next.h}px`;
      indicator.style.transform=`translate3d(${next.x}px,${next.y}px,0)`;indicator.dataset.ready='true';
      Object.assign(state,{ready:true,...next});
    }
    function animate(next){
      const oldValue={x:state.x,y:state.y,w:state.w||next.w,h:state.h||next.h};
      const dx=next.x-oldValue.x;
      const distance=Math.max(Math.abs(dx),Math.abs(next.y-oldValue.y),Math.abs(next.w-oldValue.w));
      const direction=Math.sign(dx)||1,duration=Math.round(clamp(280+distance*.22,310,500));
      const stretch=clamp(distance*.12,6,24),overshoot=clamp(distance*.04,3,8)*direction;
      state.animation?.cancel?.();
      if(!indicator.animate||reduced()){settle(next);return;}
      state.animation=indicator.animate([
        {transform:`translate3d(${oldValue.x}px,${oldValue.y}px,0) scale(1)`,width:`${oldValue.w}px`,height:`${oldValue.h}px`,offset:0},
        {transform:`translate3d(${next.x-direction*stretch*.35}px,${next.y}px,0) scale(1.018,.988)`,width:`${next.w+stretch}px`,height:`${next.h}px`,offset:.42,easing:SOFT},
        {transform:`translate3d(${next.x+overshoot}px,${next.y}px,0) scale(.99,1.012)`,width:`${next.w}px`,height:`${next.h}px`,offset:.76,easing:BREEZE},
        {transform:`translate3d(${next.x}px,${next.y}px,0) scale(1)`,width:`${next.w}px`,height:`${next.h}px`,offset:1,easing:BREEZE}
      ],{duration,fill:'forwards'});
      state.animation.onfinish=()=>settle(next);Object.assign(state,{ready:true,...next});
    }
    function update({instant=false}={}){
      cancelAnimationFrame(state.raf);
      state.raf=requestAnimationFrame(()=>{
        const item=activeItem();if(!item||!root.isConnected||!host.isConnected)return;
        indicator=ensureIndicator(host,indicatorClass);const next=geometry(item,host,bleedX,bleedY);if(!next)return;
        if(instant||!state.ready||reduced())settle(next);else animate(next);
        $$(itemSelector,root).forEach(button=>button.setAttribute('aria-selected',button===item?'true':'false'));
      });
    }
    function repair(){indicator=ensureIndicator(host,indicatorClass);update({instant:!state.ready});}
    const observer=new MutationObserver(records=>{if(records.some(r=>r.type==='attributes'&&r.attributeName==='class'))update()});
    observer.observe(root,{subtree:true,attributes:true,attributeFilter:['class']});
    if('ResizeObserver'in window){const ro=new ResizeObserver(()=>update({instant:true}));ro.observe(root);if(host!==root)ro.observe(host)}
    root.addEventListener('scroll',()=>update({instant:true}),{passive:true});
    root.addEventListener('pointerdown',event=>{if(event.target.closest?.(itemSelector))host.classList.add('is-liquid-pressing')},{passive:true});
    ['pointerup','pointercancel','pointerleave'].forEach(type=>root.addEventListener(type,()=>host.classList.remove('is-liquid-pressing'),{passive:true}));
    window.addEventListener('orientationchange',()=>setTimeout(()=>update({instant:true}),120),{passive:true});
    const controller={update,repair};controllers.set(root,controller);update({instant:true});return controller;
  }

  function installMainRail(){
    const root=$('.view-rail-inner'),host=$('.view-rail');if(!root||!host)return;
    host.classList.add('liquid-overlay-host');makeLiquidController(root,{itemSelector:'.view-tab',indicatorClass:'dashboard-liquid-indicator',host,bleedX:3,bleedY:3});
  }
  function appState(){return typeof ui==='undefined'?null:ui;}
  function assetMarkets(){return Object.keys(appState()?.snapshot?.assets||{});}

  function renderAssetChipRail(){
    const head=$('[data-view-panel="assets"] .asset-head');if(!head)return;
    let shell=$('#assetChipShell');
    if(!shell){shell=document.createElement('div');shell.id='assetChipShell';shell.className='asset-chip-shell liquid-overlay-host';shell.innerHTML='<div id="assetChipRail" class="asset-chip-rail" role="tablist" aria-label="코인 선택"></div>';head.insertAdjacentElement('afterend',shell)}
    const rail=$('#assetChipRail');if(!rail)return;
    const markets=assetMarkets();if(!markets.length){shell.hidden=true;return}shell.hidden=false;
    const signature=markets.map(m=>`${m}:${appState()?.snapshot?.assets?.[m]?.symbol||''}`).join('|');
    if(rail.dataset.signature!==signature){
      rail.dataset.signature=signature;
      rail.innerHTML=markets.map(m=>{const item=appState().snapshot.assets[m]||{},label=item.symbol||m.replace('KRW-','');return `<button type="button" class="asset-chip" data-market="${esc(m)}" role="tab">${esc(label)}</button>`}).join('');
      rail.querySelectorAll('.asset-chip').forEach(button=>button.addEventListener('click',()=>{window.selectMarket?.(button.dataset.market,false);requestAnimationFrame(()=>requestAnimationFrame(renderAssetChipRail))}));
    }
    const selected=appState()?.selectedMarket||markets[0];rail.querySelectorAll('.asset-chip').forEach(button=>button.classList.toggle('is-active',button.dataset.market===selected));
    const controller=makeLiquidController(rail,{itemSelector:'.asset-chip',indicatorClass:'asset-chip-indicator',host:shell,bleedX:4,bleedY:7});controller?.repair();
    if(rail.dataset.selectedMarket!==selected){rail.dataset.selectedMarket=selected;const active=rail.querySelector('.asset-chip.is-active');requestAnimationFrame(()=>active?.scrollIntoView({block:'nearest',inline:'center',behavior:reduced()?'auto':'smooth'}));setTimeout(()=>controller?.update({instant:true}),260)}
  }

  function polishAssetHeroMetrics(){
    const market=appState()?.selectedMarket,holding=typeof window.holdingFor==='function'?window.holdingFor(market):null,chips=$$('.v2-holding-chip');if(chips.length<2)return;
    const has=!!(holding&&Number(holding.volume)>0),pnl=has?Number(holding.unrealized_pnl_krw||0):0,p=has?Number(holding.unrealized_pnl_pct||0):0;
    chips[0].innerHTML=`<span>내 평단</span><b class="v4-average-value">${has?`${num(holding.avg_price,8)}원`:'입력 안 함'}</b>`;
    chips[1].innerHTML=`<span>현재 손익</span><b class="v4-pnl-value ${has?clsSign(pnl):''}">${has?`<span>${money(pnl)}</span><small>${signedPct(p)}</small>`:'-'}</b>`;
  }
  function wrapFunction(name,tag,after){const fn=window[name];if(typeof fn!=='function'||fn[tag])return;const wrapped=function(...args){const result=fn.apply(this,args);requestAnimationFrame(after);return result};wrapped[tag]=true;window[name]=wrapped}
  function installPatches(){wrapFunction('renderAssets','__navV3',()=>{renderAssetChipRail();polishAssetHeroMetrics()});wrapFunction('renderSelectedAsset','__navV3',polishAssetHeroMetrics);wrapFunction('selectMarket','__navV3',()=>{renderAssetChipRail();polishAssetHeroMetrics()})}

  function interactiveSwipeTarget(target){return !!target?.closest?.('.view-rail-inner,.asset-chip-rail,.range-control,.avg-list,.chart-box,input,textarea,select,button,a,dialog,[contenteditable="true"],.access-url,.technical-details,.demo-research')}
  function switchAdjacentView(direction){const current=VIEW_ORDER.indexOf(appState()?.view||'overview'),next=current+direction;if(next<0||next>=VIEW_ORDER.length||typeof window.switchView!=='function')return false;window.switchView(VIEW_ORDER[next]);requestAnimationFrame(()=>controllers.get($('.view-rail-inner'))?.update());return true}
  function switchAdjacentAsset(direction){const markets=assetMarkets();if(!markets.length||typeof window.selectMarket!=='function')return false;const current=Math.max(0,markets.indexOf(appState()?.selectedMarket)),next=current+direction;if(next<0||next>=markets.length)return false;window.selectMarket(markets[next],false);requestAnimationFrame(renderAssetChipRail);return true}
  function installSwipePaging(){
    if(document.documentElement.dataset.dashboardSwipeV3==='true')return;document.documentElement.dataset.dashboardSwipeV3='true';let gesture=null;
    document.addEventListener('touchstart',event=>{if(event.touches.length!==1||interactiveSwipeTarget(event.target)){gesture=null;return}const touch=event.touches[0];gesture={x:touch.clientX,y:touch.clientY,t:performance.now(),view:appState()?.view||'overview'}},{passive:true});
    document.addEventListener('touchend',event=>{if(!gesture||event.changedTouches.length!==1){gesture=null;return}const touch=event.changedTouches[0],dx=touch.clientX-gesture.x,dy=touch.clientY-gesture.y,dt=performance.now()-gesture.t,start=gesture;gesture=null;if(dt>850||Math.abs(dx)<58||Math.abs(dx)<Math.abs(dy)*1.35)return;const direction=dx<0?1:-1;if(start.view==='assets'&&switchAdjacentAsset(direction))return;switchAdjacentView(direction)},{passive:true});
  }
  function watchForDashboardSync(){let lastReload='';setInterval(()=>{const sync=appState()?.snapshot?.sync||{},changed=[...(Array.isArray(sync.changed)?sync.changed:[]),...(Array.isArray(sync.remote_changed)?sync.remote_changed:[])];if(!['updated','published','reconciled'].includes(sync.status)||!changed.some(path=>String(path).startsWith('dashboard/')))return;const marker=String(sync.to||sync.commit||sync.remote||changed.join('|'));if(!marker||marker===lastReload)return;lastReload=marker;const key=`cryptoDashboardReload:${marker}`;if(sessionStorage.getItem(key)==='1')return;sessionStorage.setItem(key,'1');setTimeout(()=>location.reload(),250)},1200)}
  function loadResearchUi(){
    if(!document.querySelector('link[data-demo-research]')){const link=document.createElement('link');link.rel='stylesheet';link.href='./demo-research.css?v=2';link.dataset.demoResearch='1';document.head.appendChild(link)}
    if(!window.__demoResearchLoading&&!window.__demoResearchLoaded){window.__demoResearchLoading=true;const script=document.createElement('script');script.src='./demo-research.js?v=2';script.onload=()=>{window.__demoResearchLoading=false};script.onerror=()=>{window.__demoResearchLoading=false};document.body.appendChild(script)}
  }
  function install(){installMainRail();installPatches();renderAssetChipRail();polishAssetHeroMetrics();installSwipePaging();watchForDashboardSync();loadResearchUi()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
  [100,420,1000].forEach(delay=>setTimeout(()=>{installMainRail();installPatches();renderAssetChipRail();polishAssetHeroMetrics()},delay));
})();
