import {getEventStudy} from '../services/event-study.js';
import {eventStudyHtml} from './event-study-view.js';
import {patchPreservingUi} from './ui-continuity.js';

/** Lazy, read-only study. Keep selections across polling; discard stale responses. */
export function createEventStudy({openJournal}) {
  const selections=new Map();
  let node,scope,key='',sequence=0,study=null,loading=false,error='',loadedAt=0;
  const scopeKey=s=>`${s.exchange}|${s.market}|${s.category}`;
  const selection=()=>selections.get(key);
  const html=()=>eventStudyHtml(study,selection(),{loading,error});
  const render=()=>{if(node?.isConnected)patchPreservingUi(node.getRootNode(),()=>{node.innerHTML=html();});};
  async function load() {
    const id=++sequence,current=key,query={...selection()};loading=true;error='';render();
    try {
      const result=await getEventStudy(scope,query);
      if(id!==sequence||key!==current)return;
      study=result;loadedAt=Date.now();loading=false;
      if(result.status==='ok')Object.assign(selection(),result.selected||{},{experiment:result.selected_experiment||''});
    } catch(err) {if(id!==sequence||key!==current)return;loading=false;error=err.message;}
    render();
  }
  function click(event) {
    const b=event.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.studyJournal){openJournal(b.dataset.studyJournal);return;}
    const draft=selection();
    if(b.dataset.studyHorizon)draft.horizon=b.dataset.studyHorizon;
    else if(b.dataset.studyType)Object.assign(draft,{source_id:b.dataset.studySource,event_type:b.dataset.studyType});
    else if(b.dataset.studyExperiment)draft.experiment=b.dataset.studyExperiment;
    else if(!b.hasAttribute('data-study-retry'))return;
    // A previous horizon/group must never be relabeled as the new selection.
    study=null;void load();
  }
  return {
    html(nextScope){return scopeKey(nextScope)===key?html():'<p class="placeholder">누적 기록을 불러오는 중…</p>';},
    mount(nextNode,nextScope){
      node=nextNode;scope=nextScope;
      const nextKey=scopeKey(scope);
      if(nextKey!==key){key=nextKey;sequence++;study=null;loading=false;error='';loadedAt=0;}
      if(!selections.has(key))selections.set(key,{horizon:'15m',style:scope.style||'aggressive'});
      node.onclick=click;render();
      if(!loading&&(!loadedAt||Date.now()-loadedAt>=20000))void load();
    },
    destroy(){sequence++;node=null;},
  };
}
