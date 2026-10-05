import {patchPreservingUi} from './ui-continuity.js';

/** Shared lazy read lifecycle: scoped selections, polling continuity and stale-response rejection. */
export function createScopedReview({scopeKey, defaults, fetchReview, renderHtml, receive, action, placeholder}) {
  const selections=new Map();
  let node,scope,key='',sequence=0,data=null,loading=false,error='',loadedAt=0;
  const selection=()=>selections.get(key);
  const html=()=>renderHtml(data,selection(),{loading,error});
  const render=()=>{if(node?.isConnected)patchPreservingUi(node.getRootNode(),()=>{node.innerHTML=html();});};
  async function load() {
    const id=++sequence,current=key,query={...selection()};loading=true;error='';render();
    try {
      const result=await fetchReview(scope,query);
      if(id!==sequence||key!==current)return;
      data=result;loadedAt=Date.now();loading=false;
      if(result.status==='ok')receive?.(selection(),result);
    } catch(err) {if(id!==sequence||key!==current)return;loading=false;error=err.message;}
    render();
  }
  return {
    html(nextScope){return scopeKey(nextScope)===key?html():`<p class="placeholder">${placeholder}</p>`;},
    mount(nextNode,nextScope){
      node=nextNode;scope=nextScope;
      const nextKey=scopeKey(scope);
      if(nextKey!==key){key=nextKey;sequence++;data=null;loading=false;error='';loadedAt=0;}
      if(!selections.has(key))selections.set(key,defaults(scope));
      node.onclick=event=>{
        const button=event.target.closest('button');if(!button||button.disabled)return;
        if(action(button,selection(),data)){data=null;void load();}
      };
      render();
      if(!loading&&(!loadedAt||Date.now()-loadedAt>=20000))void load();
    },
    destroy(){sequence++;node=null;},
  };
}
