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
