import{getJson}from'./http.js';
export function createSnapshotPoller({store,onUnauthorized}){
  let timer=0,inFlight=null,stopped=false;
  async function load(){
    if(stopped||!store.get().user)return null;
    if(inFlight)return inFlight;
    inFlight=(async()=>{try{const data=await getJson('/api/snapshot');store.setSnapshot(data.snapshot||null,data.user||null);return data}catch(err){if(err.status===401){store.resetSession();onUnauthorized?.()}else store.setError(err);return null}finally{inFlight=null}})();
    return inFlight;
  }
  function start(){stopped=false;load();clearInterval(timer);timer=setInterval(()=>{if(!document.hidden)load()},15000)}
  function stop(){stopped=true;clearInterval(timer);timer=0}
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!stopped)load()});
  return{start,stop,load};
}
