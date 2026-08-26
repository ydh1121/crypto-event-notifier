const STORAGE_KEY='cryptoViewerUiV6';
const defaults={
  route:'dashboard',
  researchExchange:'bithumb',paperExchange:'bithumb',strategyExchange:'bithumb',
  researchMarket:'',assetMarket:'',paperMarket:'',
  researchSearch:'',researchFilter:'all',
  paperTab:'summary',paperSearch:'',paperFilter:'all',paperSort:'return_desc',
  paperCompareSearch:'',paperCompareSort:'gap_desc',
  strategyMarket:'',recordsExchange:'bithumb',recordsFilter:'all',recordsPeriod:'all',recordsSearch:''
};
let saved={};try{saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')}catch{}
const state={user:null,snapshot:null,loading:true,error:null,ui:{...defaults,...saved}};
const listeners=new Set();
function persist(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state.ui))}catch{}}
function emit(meta={}){for(const fn of listeners){try{fn(state,meta)}catch(err){console.error('store listener',err)}}}
export const store={
  get:()=>state,
  subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},
  set(patch,meta={}){Object.assign(state,patch);emit(meta)},
  setUser(user){state.user=user||null;emit({type:'user'})},
  setSnapshot(snapshot,user){state.snapshot=snapshot||null;if(user)state.user=user;state.loading=false;state.error=null;emit({type:'snapshot'})},
  setError(error){state.error=error||null;state.loading=false;emit({type:'error'})},
  setUi(patch,meta={}){Object.assign(state.ui,patch);persist();emit({type:'ui',...meta})},
  resetSession(){state.user=null;state.snapshot=null;state.loading=false;state.error=null;emit({type:'session-reset'})}
};
