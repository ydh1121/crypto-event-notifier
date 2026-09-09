const COMPACT_QUERY='(max-width: 900px)';
const CLICK_TARGETS=[
  ['[data-research-market]','#researchDetail'],
  ['[data-asset-market]','#assetDetail'],
  ['[data-paper-market]','#paperDetail'],
  ['[data-strategy-key]','#strategyDetail'],
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
  return Math.max(12,Math.ceil(height)+12);
}

function scrollTargetIntoView(target,{settle=false}={}){
  const rect=target.getBoundingClientRect();
  const top=Math.max(0,window.scrollY+rect.top-headerOffset());
  if(Math.abs(window.scrollY-top)<8)return;
  window.scrollTo({top,left:0,behavior:settle||prefersReducedMotion()?'auto':'smooth'});
}

function reveal(root,selector,{force=false,retries=6}={}){
  if(!root||!selector)return;
  if(!force&&!compactViewport())return;
  let remaining=Math.max(1,retries);
  const attempt=()=>requestAnimationFrame(()=>{
    const target=root.querySelector(selector);
    if(target){
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

export function installViewportHandoff({root}){
  if(!root)return()=>{};

  function click(event){
    const paperNext=event.target.closest('.paper-next [data-paper-tab]');
    if(paperNext&&root.contains(paperNext)){
      reveal(root,'#paperBody',{force:true});
      return;
    }

    for(const[trigger,selector]of CLICK_TARGETS){
      const hit=event.target.closest(trigger);
      if(!hit||!root.contains(hit))continue;
      reveal(root,selector);
      return;
    }
  }

  function handoff(event){
    const detail=event.detail||{};
    reveal(root,String(detail.selector||''),{
      force:detail.force===true,
      retries:Number.isFinite(Number(detail.retries))?Number(detail.retries):6,
    });
  }

  root.addEventListener('click',click);
  root.addEventListener('viewport:handoff',handoff);

  return()=>{
    root.removeEventListener('click',click);
    root.removeEventListener('viewport:handoff',handoff);
  };
}
