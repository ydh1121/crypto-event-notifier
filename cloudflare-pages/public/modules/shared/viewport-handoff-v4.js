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

function reveal(root,selector,{force=false}={}){
  if(!root||!selector)return;
  if(!force&&!compactViewport())return;
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    const target=root.querySelector(selector);
    if(!target)return;
    const rect=target.getBoundingClientRect();
    const top=Math.max(0,window.scrollY+rect.top-headerOffset());
    if(Math.abs(window.scrollY-top)<8)return;
    window.scrollTo({top,left:0,behavior:prefersReducedMotion()?'auto':'smooth'});
  }));
}

export function installViewportHandoff({root}){
  if(!root)return()=>{};

  function click(event){
    for(const[trigger,selector]of CLICK_TARGETS){
      const hit=event.target.closest(trigger);
      if(!hit||!root.contains(hit))continue;
      reveal(root,selector);
      return;
    }
  }

  function handoff(event){
    const detail=event.detail||{};
    reveal(root,String(detail.selector||''),{force:detail.force===true});
  }

  root.addEventListener('click',click);
  root.addEventListener('viewport:handoff',handoff);

  return()=>{
    root.removeEventListener('click',click);
    root.removeEventListener('viewport:handoff',handoff);
  };
}
