const DEFAULT_SCROLL_SELECTOR='[data-preserve-scroll]';

function focusIdentity(element){
  if(!(element instanceof HTMLElement))return'';
  const explicit=element.getAttribute('data-continuity-key');
  if(explicit)return`[data-continuity-key="${CSS.escape(explicit)}"]`;
  if(element.id)return`#${CSS.escape(element.id)}`;
  const named=element.getAttribute('name');
  if(named)return`[name="${CSS.escape(named)}"]`;
  return'';
}

function captureSelection(element){
  if(!(element instanceof HTMLInputElement||element instanceof HTMLTextAreaElement))return null;
  return{
    start:Number.isInteger(element.selectionStart)?element.selectionStart:null,
    end:Number.isInteger(element.selectionEnd)?element.selectionEnd:null,
    direction:element.selectionDirection||'none',
  };
}

function stableSelector(element,root){
  if(!(element instanceof HTMLElement))return'';
  const explicit=element.getAttribute('data-continuity-key');
  if(explicit)return`[data-continuity-key="${CSS.escape(explicit)}"]`;
  if(element.id)return`#${CSS.escape(element.id)}`;
  const classes=[...element.classList].filter(Boolean);
  for(const name of classes){
    const selector=`.${CSS.escape(name)}`;
    if(root?.querySelectorAll?.(selector)?.length===1)return selector;
  }
  return'';
}

function isScrollable(element){
  if(!(element instanceof HTMLElement))return false;
  return element.scrollHeight>element.clientHeight+1||element.scrollWidth>element.clientWidth+1;
}

function captureScrollableAncestors(root,target){
  const items=[];
  let element=target instanceof HTMLElement?target.parentElement:null;
  while(element&&element!==root){
    if(isScrollable(element)){
      const selector=stableSelector(element,root);
      if(selector)items.push({selector,index:0,top:element.scrollTop,left:element.scrollLeft});
    }
    element=element.parentElement;
  }
  return items;
}

export function captureUiContinuity(root,{scrollSelectors=[DEFAULT_SCROLL_SELECTOR],preserveWindow=true,preserveFocus=true}={}){
  const scroll=[];
  for(const selector of scrollSelectors){
    root?.querySelectorAll?.(selector)?.forEach((element,index)=>{
      scroll.push({selector,index,top:element.scrollTop,left:element.scrollLeft});
    });
  }
  const active=preserveFocus&&root?.contains?.(document.activeElement)?document.activeElement:null;
  return{
    window:preserveWindow?{x:window.scrollX,y:window.scrollY}:null,
    scroll,
    focus:active?{selector:focusIdentity(active),selection:captureSelection(active)}:null,
  };
}

function restoreSelection(element,selection){
  if(!selection||!(element instanceof HTMLInputElement||element instanceof HTMLTextAreaElement))return;
  if(selection.start===null||selection.end===null)return;
  try{element.setSelectionRange(selection.start,selection.end,selection.direction)}catch{}
}

export function restoreUiContinuity(root,snapshot,{repeatOnFrame=true}={}){
  if(!snapshot)return;
  const apply=()=>{
    for(const item of snapshot.scroll||[]){
      const elements=root?.querySelectorAll?.(item.selector)||[];
      const element=elements[item.index];
      if(element){element.scrollTop=item.top;element.scrollLeft=item.left}
    }
    if(snapshot.focus?.selector){
      const element=root?.querySelector?.(snapshot.focus.selector);
      if(element instanceof HTMLElement){
        try{element.focus({preventScroll:true})}catch{element.focus()}
        restoreSelection(element,snapshot.focus.selection);
      }
    }
    if(snapshot.window)window.scrollTo(snapshot.window.x,snapshot.window.y);
  };
  apply();
  if(repeatOnFrame)requestAnimationFrame(apply);
}

export function patchPreservingUi(root,mutate,options={}){
  const snapshot=captureUiContinuity(root,options);
  const result=mutate();
  restoreUiContinuity(root,snapshot,options);
  return result;
}

export function installSamePageInteractionContinuity(root,{skipSelector='a[href],[data-route],[data-allow-scroll-jump]'}={}){
  if(!root)return()=>{};
  const onClickCapture=event=>{
    const target=event.target instanceof HTMLElement?event.target:null;
    if(!target||target.closest(skipSelector))return;
    const snapshot={
      window:{x:window.scrollX,y:window.scrollY},
      scroll:captureScrollableAncestors(root,target),
      focus:null,
    };
    queueMicrotask(()=>restoreUiContinuity(root,snapshot,{repeatOnFrame:true}));
  };
  root.addEventListener('click',onClickCapture,true);
  return()=>root.removeEventListener('click',onClickCapture,true);
}
