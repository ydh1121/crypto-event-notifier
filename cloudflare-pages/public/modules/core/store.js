const STORAGE_KEY='cryptoViewerUiV6';
const defaults={
  route:'dashboard',
  researchExchange:'bithumb',paperExchange:'bithumb',strategyExchange:'bithumb',sectorExchange:'bithumb',
  researchMarket:'',assetMarket:'',assetHistoryRange:'7d',paperMarket:'',sectorSelected:'',sectorRange:'24h',sectorCoinMarket:'',sectorCoinSort:'turnover_desc',
  researchSearch:'',researchFilter:'all',researchRange:'24h',
  paperTab:'summary',paperSearch:'',paperFilter:'all',paperStrategyFilter:'all',paperSort:'return_desc',paperRange:'24h',paperPortfolioRange:'24h',
  paperCompareSearch:'',paperCompareSort:'gap_desc',
  strategyMarket:'',strategyTab:'overview',strategyRange:'24h',strategyOverviewExperiment:'',strategyCoinExperiment:'',strategyCoinSort:'return_desc',strategyCoinMarket:'',strategyCoinSearch:'',
  recordsExchange:'bithumb',recordsFilter:'all',recordsPeriod:'all',recordsSearch:'',recordsStrategy:'all'
};
let saved={};try{saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')}catch{}
const state={user:null,snapshot:null,loading:true,error:null,ui:{...defaults,...saved}};
const listeners=new Set();
let exchangeDefaultApplied=false;
function persist(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(state.ui))}catch{}}
function emit(meta={}){for(const fn of listeners){try{fn(state,meta)}catch(err){console.error('store listener',err)}}}
function defaultExchange(snapshot){const list=Array.isArray(snapshot?.private?.manual_holdings?.holdings)?snapshot.private.manual_holdings.holdings:[];if(!snapshot?.private_visible||!list.length)return'bithumb';const totals={bithumb:0,upbit:0};for(const row of list){const ex=String(row?.exchange||'bithumb').toLowerCase();if(!(ex in totals))continue;const value=Math.max(0,Number(row?.value_krw||row?.invested_krw||0));totals[ex]+=Number.isFinite(value)?value:0}return totals.upbit>totals.bithumb?'upbit':'bithumb'}
function applyExchangeDefault(snapshot){if(exchangeDefaultApplied)return;exchangeDefaultApplied=true;const exchange=defaultExchange(snapshot);Object.assign(state.ui,{researchExchange:exchange,paperExchange:exchange,strategyExchange:exchange,recordsExchange:exchange,sectorExchange:exchange});persist()}
export const store={
  get:()=>state,
  subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},
  set(patch,meta={}){Object.assign(state,patch);emit(meta)},
  setUser(user){state.user=user||null;emit({type:'user'})},
  setSnapshot(snapshot,user){state.snapshot=snapshot||null;if(user)state.user=user;state.loading=false;state.error=null;if(snapshot)applyExchangeDefault(snapshot);emit({type:'snapshot'})},
  setError(error){state.error=error||null;state.loading=false;emit({type:'error'})},
  setUi(patch,meta={}){Object.assign(state.ui,patch);persist();emit({type:'ui',...meta})},
  resetSession(){state.user=null;state.snapshot=null;state.loading=false;state.error=null;exchangeDefaultApplied=false;emit({type:'session-reset'})}
};
