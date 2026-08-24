/* Mobile navigation/coin rail behavior.
   Mirrors the Photo-eBook liquid selector contract: one rail, one moving indicator,
   real item geometry, spring motion, and native iOS horizontal scrolling. */
(function(){
  if(window.__cryptoLiquidNavigationInstalled)return;
  window.__cryptoLiquidNavigationInstalled=true;

  const VIEW_ORDER=['overview','assets','performance','activity','settings'];
  const SPRING='cubic-bezier(.34,1.56,.64,1)';
  const EDGE='cubic-bezier(.34,1.24,.64,1)';
  const controllers=new WeakMap();
  const clamp=(v,min,max)=>Math.min(max,Math.max(min,v));
  const reduced=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)').matches===true;

  function ensureIndicator(root,className){
    if(!root)return null;
    const all=[...root.querySelectorAll(`:scope > .${className}`)];
    all.slice(1).forEach(node=>node.remove());
    let indicator=all[0];
    if(!indicator){
      indicator=document.createElement('span');
      indicator.className=className;
      indicator.setAttribute('aria-hidden','true');
      indicator.innerHTML='<span class="liquid-skin" aria-hidden="true"></span>';
      root.prepend(indicator);
    }else if(!indicator.querySelector(':scope > .liquid-skin')){
      indicator.innerHTML='<span class="liquid-skin" aria-hidden="true"></span>';
    }
    return indicator;
  }

  function makeLiquidController(root,{itemSelector,indicatorClass}={}){
    if(!root)return null;
    const existing=controllers.get(root);
    if(existing){existing.repair();return existing;}

    let indicator=ensureIndicator(root,indicatorClass);
    const state={x:0,y:0,w:0,h:0,ready:false};

    function activeItem(){
      return root.querySelector(`${itemSelector}.is-active`)||root.querySelector(itemSelector);
    }

    function geometry(){
      const item=activeItem();
      if(!item)return null;
      const x=item.offsetLeft,y=item.offsetTop,w=item.offsetWidth,h=item.offsetHeight;
      if(!w||!h)return null;
      return {item,x,y,w,h};
    }

    function durationFor(next){
      const distance=Math.max(Math.abs(next.x-state.x),Math.abs(next.w-state.w));
      return Math.round(clamp(245+distance*.11,255,390));
    }

    function centerItem(item,behavior='smooth'){
      if(!item||!root.isConnected||root.scrollWidth<=root.clientWidth+2)return;
      const left=item.offsetLeft-(root.clientWidth-item.offsetWidth)/2;
      const max=Math.max(0,root.scrollWidth-root.clientWidth);
      root.scrollTo({left:clamp(left,0,max),behavior:reduced()?'auto':behavior});
    }

    function update({instant=false,center=false}={}){
      if(!root.isConnected)return;
      const next=geometry();
      if(!next)return;
      indicator=ensureIndicator(root,indicatorClass);
      const first=!state.ready;
      const duration=durationFor(next);
      const firstItem=root.querySelector(itemSelector);
      const easing=next.item===firstItem?EDGE:SPRING;
      indicator.style.transition=(instant||first||reduced())
        ?'none'
        :`transform ${duration}ms ${easing},width ${duration}ms ${easing},height ${duration}ms ${easing}`;
      indicator.style.width=`${next.w}px`;
      indicator.style.height=`${next.h}px`;
      indicator.style.transform=`translate3d(${next.x}px,${next.y}px,0)`;
      indicator.dataset.ready='true';
      state.x=next.x;state.y=next.y;state.w=next.w;state.h=next.h;state.ready=true;
      root.classList.add('liquid-ready');
      if(center)centerItem(next.item);
      if((instant||first)&&!reduced())requestAnimationFrame(()=>{
        if(indicator?.isConnected)indicator.style.transition=`transform ${duration}ms ${easing},width ${duration}ms ${easing},height ${duration}ms ${easing}`;
      });
    }

    function repair(){
      indicator=ensureIndicator(root,indicatorClass);
      requestAnimationFrame(()=>update({instant:true}));
    }

    const observer=new MutationObserver(records=>{
      const relevant=records.some(record=>record.type==='childList'||record.attributeName==='class');
      if(relevant)requestAnimationFrame(()=>update({instant:false}));
    });
    observer.observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});

    const resize=()=>requestAnimationFrame(()=>update({instant:true}));
    window.addEventListener('resize',resize,{passive:true});
    window.visualViewport?.addEventListener?.('resize',resize,{passive:true});
    if(window.ResizeObserver)new ResizeObserver(resize).observe(root);

    const controller={update,repair,centerItem};
    controllers.set(root,controller);
    requestAnimationFrame(()=>update({instant:true}));
    return controller;
  }

  function installTopNavigation(){
    const rail=document.querySelector('.view-rail-inner');
    if(!rail)return;
    const controller=makeLiquidController(rail,{itemSelector:'.view-tab',indicatorClass:'view-liquid-indicator'});
    rail.addEventListener('click',event=>{
      const tab=event.target.closest('.view-tab');
      if(!tab)return;
      requestAnimationFrame(()=>controller?.update({center:false}));
    });
  }

  function ensureAssetRail(){
    const head=document.querySelector('[data-view-panel="assets"] .asset-head');
    const select=document.getElementById('assetSelect');
    const label=select?.closest('.asset-select-label');
    if(!head||!select||!label)return null;
    label.classList.add('liquid-select-fallback');
    let shell=head.querySelector('.asset-chip-shell');
    if(!shell){
      shell=document.createElement('div');
      shell.className='asset-chip-shell';
      shell.innerHTML='<div class="asset-chip-rail" data-liquid-horizontal="true" role="tablist" aria-label="코인 선택"></div>';
      label.insertAdjacentElement('beforebegin',shell);
    }
    return shell.querySelector('.asset-chip-rail');
  }

  function renderAssetRail({center=false}={}){
    const rail=ensureAssetRail();
    const select=document.getElementById('assetSelect');
    if(!rail||!select)return;
    const options=[...select.options];
    const markets=options.map(option=>({market:option.value,label:option.textContent||option.value}));
    const active=(typeof ui!=='undefined'&&ui.selectedMarket)||select.value;

    const existing=new Map([...rail.querySelectorAll('.asset-chip')].map(button=>[button.dataset.market,button]));
    markets.forEach(({market,label})=>{
      let button=existing.get(market);
      if(!button){
        button=document.createElement('button');
        button.type='button';
        button.className='asset-chip';
        button.dataset.market=market;
        button.setAttribute('role','tab');
        button.addEventListener('click',()=>{
          if(typeof selectMarket==='function')selectMarket(market,false);
          requestAnimationFrame(()=>{
            renderAssetRail({center:true});
            controllers.get(rail)?.update({center:true});
          });
        });
      }
      button.textContent=String(label).replace(/^KRW-/,'');
      button.classList.toggle('is-active',market===active);
      button.setAttribute('aria-selected',market===active?'true':'false');
      rail.appendChild(button);
      existing.delete(market);
    });
    existing.forEach(button=>button.remove());

    const controller=makeLiquidController(rail,{itemSelector:'.asset-chip',indicatorClass:'asset-chip-indicator'});
    requestAnimationFrame(()=>controller?.update({center}));
  }

  function installAssetRailWatcher(){
    const select=document.getElementById('assetSelect');
    if(!select)return;
    renderAssetRail({center:false});
    const observer=new MutationObserver(()=>renderAssetRail({center:false}));
    observer.observe(select,{childList:true,subtree:true,attributes:true});
    setInterval(()=>renderAssetRail({center:false}),5000);
  }

  function ignoredGestureTarget(target){
    return !!target?.closest?.('input,textarea,select,button,a,dialog,summary,.range-control,.chart-box,[data-liquid-horizontal]');
  }

  function createSwipeGesture(root,onSwipe,{allowStart}={}){
    if(!root)return;
    let start=null;
    root.addEventListener('pointerdown',event=>{
      if(event.pointerType&&event.pointerType!=='touch')return;
      if(ignoredGestureTarget(event.target))return;
      if(allowStart&&!allowStart(event))return;
      start={x:event.clientX,y:event.clientY,id:event.pointerId,target:event.target};
    },{passive:true});
    root.addEventListener('pointerup',event=>{
      if(!start||event.pointerId!==start.id){start=null;return}
      const dx=event.clientX-start.x,dy=event.clientY-start.y;
      start=null;
      if(Math.abs(dx)<64||Math.abs(dx)<Math.abs(dy)*1.35)return;
      onSwipe(dx<0?'left':'right',event);
    },{passive:true});
    root.addEventListener('pointercancel',()=>{start=null},{passive:true});
  }

  function switchCoin(direction){
    const assets=(typeof ui!=='undefined'&&ui.snapshot?.assets)||{};
    const markets=Object.keys(assets);
    if(markets.length<2)return;
    let index=markets.indexOf(ui.selectedMarket);
    if(index<0)index=0;
    index=direction==='left'?(index+1)%markets.length:(index-1+markets.length)%markets.length;
    if(typeof selectMarket==='function')selectMarket(markets[index],false);
    renderAssetRail({center:true});
    const symbol=String(markets[index]).replace('KRW-','');
    if(typeof showUxToast==='function')showUxToast(`${symbol}로 이동`);
  }

  function installCoinSwipe(){
    const panel=document.querySelector('[data-view-panel="assets"]');
    if(!panel)return;
    createSwipeGesture(panel,direction=>switchCoin(direction),{
      allowStart:event=>{
        const edge=28;
        const x=event.clientX;
        if(x<=edge||x>=window.innerWidth-edge)return false;
        return !event.target.closest('.personal-tools,.asset-chip-shell');
      },
    });
  }

  function installViewSwipe(){
    const main=document.querySelector('.app-main');
    if(!main)return;
    createSwipeGesture(main,direction=>{
      if(typeof ui==='undefined'||typeof switchView!=='function')return;
      const index=VIEW_ORDER.indexOf(ui.view);
      if(index<0)return;
      const next=direction==='left'?index+1:index-1;
      if(next<0||next>=VIEW_ORDER.length)return;
      switchView(VIEW_ORDER[next]);
    },{
      allowStart:event=>{
        if(typeof ui==='undefined')return true;
        if(ui.view!=='assets')return true;
        const edge=28;
        return event.clientX<=edge||event.clientX>=window.innerWidth-edge;
      },
    });
  }

  function installGitSyncAutoReload(){
    const storageKey='cryptoTraderLoadedGitCommit';
    let baseline='';
    try{baseline=sessionStorage.getItem(storageKey)||''}catch{}

    setInterval(()=>{
      if(typeof ui==='undefined')return;
      const sync=ui.snapshot?.sync||{};
      const status=String(sync.status||'').toLowerCase();
      const commit=String(sync.to||sync.commit||'');
      if(!commit)return;

      if(!baseline){
        baseline=commit;
        try{sessionStorage.setItem(storageKey,commit)}catch{}
        return;
      }

      if(status==='published'){
        baseline=commit;
        try{sessionStorage.setItem(storageKey,commit)}catch{}
        return;
      }

      if(commit===baseline)return;
      if(!['updated','reconciled','up_to_date'].includes(status))return;

      baseline=commit;
      try{sessionStorage.setItem(storageKey,commit)}catch{}
      if(typeof showUxToast==='function')showUxToast('GitHub 변경사항을 적용합니다.');
      setTimeout(()=>window.location.reload(),350);
    },2200);
  }

  function install(){
    installTopNavigation();
    installAssetRailWatcher();
    installCoinSwipe();
    installViewSwipe();
    installGitSyncAutoReload();
    window.addEventListener('pageshow',()=>{
      installTopNavigation();
      renderAssetRail({center:false});
    },{passive:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
})();
