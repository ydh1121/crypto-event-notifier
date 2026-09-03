import{patchPreservingUi}from'../shared/ui-continuity.js';
const ROUTES=new Set(['dashboard','dashboard-detail','research','assets','paper','strategy','sectors','records','system']);
const NAV_PARENT={
  'dashboard-detail':'dashboard',
  strategy:'paper',
};
export function navRouteFor(name){return NAV_PARENT[name]||name}
export function routeContextFor(ui,name){
  if(name==='research')return{exchange:ui.researchExchange,market:ui.researchMarket};
  if(name==='sectors')return{exchange:ui.sectorExchange,market:ui.sectorCoinMarket};
  if(name==='paper')return{exchange:ui.paperExchange,market:ui.paperMarket};
  if(name==='strategy')return{exchange:ui.strategyExchange,market:ui.strategyTab==='matrix'?ui.strategyCoinMarket:''};
  if(name==='assets')return{exchange:'',market:ui.assetMarket};
  return{exchange:'',market:''};
}
function carryContext(store,from,to){
  if(!from||from===to)return;
  const ui=store.get().ui,ctx=routeContextFor(ui,from),patch={};
  if(to==='research'){
    if(ctx.exchange)patch.researchExchange=ctx.exchange;
    if(ctx.market)patch.researchMarket=ctx.market;
  }else if(to==='sectors'){
    if(ctx.exchange)patch.sectorExchange=ctx.exchange;
    if(ctx.market)patch.sectorCoinMarket=ctx.market;
  }else if(to==='paper'){
    if(ctx.exchange)patch.paperExchange=ctx.exchange;
    if(ctx.market)patch.paperMarket=ctx.market;
  }else if(to==='strategy'){
    if(ctx.exchange)patch.strategyExchange=ctx.exchange;
    if(ctx.market)patch.strategyCoinMarket=ctx.market;
  }else if(to==='assets'&&ctx.market){
    patch.assetMarket=ctx.market;
  }
  if(Object.keys(patch).length)store.setUi(patch,{scope:'route-context'});
}
export function createRouter({store,root,nav,pages,onChange}){
  let current=null,currentName='';
  function syncNav(name){const active=navRouteFor(name);nav?.querySelectorAll('[data-route]').forEach(b=>b.classList.toggle('active',b.dataset.route===active))}
  function go(name,{replace=false}={}){
    if(!ROUTES.has(name))name='dashboard';
    if(currentName===name){patchPreservingUi(root,()=>current?.render?.(),{scrollSelectors:['[data-preserve-scroll]']});syncNav(name);onChange?.(name);return}
    carryContext(store,currentName,name);
    current?.destroy?.();currentName=name;store.setUi({route:name},{scope:'router'});syncNav(name);root.innerHTML='';current=pages[name]?.();if(!current)throw new Error(`unknown page ${name}`);current.mount(root);current.render();onChange?.(name);if(!replace)window.scrollTo({top:0,left:0,behavior:'auto'})
  }
  nav?.addEventListener('click',e=>{const b=e.target.closest('[data-route]');if(b)go(b.dataset.route)});
  return{go,current:()=>currentName,render:()=>current?.render?.()};
}
