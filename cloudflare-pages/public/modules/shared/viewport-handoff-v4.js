const COMPACT_QUERY='(max-width: 900px)';
const CLICK_TARGETS=[
  {trigger:'[data-research-market]',target:'#researchDetail',source:'.research-master',backLabel:'코인 목록'},
  {trigger:'[data-asset-market]',target:'#assetDetail',source:'.asset-master',backLabel:'보유 종목'},
  {trigger:'[data-paper-market]',target:'#paperDetail',source:'.paper-master',backLabel:'모의투자 목록'},
  {trigger:'[data-strategy-key]',target:'#strategyDetail',source:'.strategy-table',backLabel:'매매방법 목록'},
];

function prefersReducedMotion(){
  return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

function compactViewport(){
  return Boolean(window.matchMedia?.(COMPACT_QUERY).matches);
}

function headerOffset(){
  const header=document.querySelector('.app-header');
  const height=header?.getBoundingClientRect?.().height||0;
  const value=Math.max(12,Math.ceil(height)+12);
  document.documentElement.style.setProperty('--shell-header-offset',`${Math.max(0,Math.ceil(height))}px`);
  return value;
}

function scrollTargetIntoView(target,{settle=false}={}){
  if(!target?.getBoundingClientRect)return;
  const rect=target.getBoundingClientRect();
  const top=Math.max(0,window.scrollY+rect.top-headerOffset());
  if(Math.abs(window.scrollY-top)<8)return;
  window.scrollTo({top,left:0,behavior:settle||prefersReducedMotion()?'auto':'smooth'});
}

function rowContext(hit){
  const primary=String(hit?.querySelector?.('b')?.textContent||'').trim();
  const secondary=String(hit?.querySelector?.('small')?.textContent||'').trim();
  return primary||secondary||'';
}

function removeReturnBars(root){
  root?.querySelectorAll?.('.viewport-return-bar').forEach(node=>node.remove());
}

export function installViewportHandoff({root}){
  if(!root)return()=>{};
  let returnState=null;

  function installReturnBar(target,config,hit){
    if(!compactViewport()||!target||!config)return;
    removeReturnBars(root);
    const bar=document.createElement('div');
    const button=document.createElement('button');
    const context=document.createElement('span');
    bar.className='viewport-return-bar';
    bar.setAttribute('role','navigation');
    bar.setAttribute('aria-label','목록으로 돌아가기');
    button.type='button';
    button.dataset.viewportBack='1';
    button.textContent=`← ${config.backLabel}`;
    context.textContent=rowContext(hit)||'선택한 항목 상세';
    bar.append(button,context);
    target.prepend(bar);
    returnState={source:config.source,trigger:hit};
  }

  function reveal(selector,{force=false,retries=6,returnConfig=null}={}){
    if(!selector)return;
    if(!force&&!compactViewport())return;
    let remaining=Math.max(1,retries);
    const attempt=()=>requestAnimationFrame(()=>{
      const target=root.querySelector(selector);
      if(target){
        if(returnConfig)installReturnBar(target,returnConfig.config,returnConfig.hit);
        scrollTargetIntoView(target);
        requestAnimationFrame(()=>{
          const settled=root.querySelector(selector);
          if(settled)scrollTargetIntoView(settled,{settle:true});
        });
        return;
      }
      remaining-=1;
      if(remaining>0)attempt();
    });
    attempt();
  }

  function returnToSource(){
    const state=returnState;
    if(!state)return;
    const source=root.querySelector(state.source);
    const trigger=state.trigger?.isConnected?state.trigger:null;
    if(trigger?.scrollIntoView){
      trigger.scrollIntoView({block:'nearest',inline:'nearest',behavior:'auto'});
    }
    requestAnimationFrame(()=>{
      const destination=source||trigger;
      if(destination)scrollTargetIntoView(destination);
    });
  }

  function click(event){
    const back=event.target.closest('[data-viewport-back]');
    if(back&&root.contains(back)){
      event.preventDefault();
      returnToSource();
      return;
    }

    const paperNext=event.target.closest('.paper-next [data-paper-tab]');
    if(paperNext&&root.contains(paperNext)){
      reveal('#paperBody',{force:true});
      return;
    }

    for(const config of CLICK_TARGETS){
      const hit=event.target.closest(config.trigger);
      if(!hit||!root.contains(hit))continue;
      reveal(config.target,{returnConfig:{config,hit}});
      return;
    }
  }

  function handoff(event){
    const detail=event.detail||{};
    reveal(String(detail.selector||''),{
      force:detail.force===true,
      retries:Number.isFinite(Number(detail.retries))?Number(detail.retries):6,
    });
  }

  function resize(){
    headerOffset();
    if(!compactViewport()){
      removeReturnBars(root);
      returnState=null;
    }
  }

  root.addEventListener('click',click);
  root.addEventListener('viewport:handoff',handoff);
  window.addEventListener('resize',resize,{passive:true});
  headerOffset();

  return()=>{
    root.removeEventListener('click',click);
    root.removeEventListener('viewport:handoff',handoff);
    window.removeEventListener('resize',resize);
    removeReturnBars(root);
  };
}
