import {getMarketDetail} from '../services/market-detail.js';
import {patchPreservingUi} from '../shared/ui-continuity.js';
import {holdingDraft,scopedStrategies} from '../shared/holdings-workbench-model.js';
import {importHoldingPlan} from '../shared/holdings-workbench-model.js';
import {holdingsShell,holdingsSummaryHtml,holdingsListHtml,holdingHeaderHtml,holdingStrategiesHtml,holdingCalculatorHtml,holdingCalculationHtml,allocationHtml,priceRefreshHtml} from '../shared/holdings-workbench-view.js';
import {createHoldingRecordsSession} from '../shared/holding-records-session.js';
import {savedPlanHtml,manualRecordsHtml} from '../shared/holding-records-view.js';

/** Composition only. Per-holding/strategy drafts persist only through the
 * explicitly enabled local planning service; actual holdings remain separate. */
export function createHoldingsWorkbench({store,onPaper=()=>{},onRefreshPrices=null,manualClient}) {
  let root,view,unsub,selected='',strategy='',detail=null,request=0,loading=false,error='';
  let priceBusy=false,priceError='';
  const drafts=new Map(),selections=new Map();
  const edited=new Set(),panels=new Map();
  const records=createHoldingRecordsSession({client:manualClient,restore:(k,d)=>{drafts.set(k,d);edited.delete(k);},changed:()=>render()});
  const data=()=>store.get().snapshot?.local_holdings;
  const selectable=()=>data()?.holdings?.filter(h=>!h.closed||(data().planning_enabled&&h.recording_available))||[];
  const holding=()=>selectable().find(h=>h.key===selected);
  const accounts=()=>scopedStrategies(detail,holding()).slice().sort((a,b)=>(b.return_pct??-Infinity)-(a.return_pct??-Infinity));
  const account=()=>accounts().find(a=>a.experiment_id===strategy);
  const key=()=>`${selected}|${strategy}`;
  const record=()=>records.get(key());
  const panel=()=>holding()?.closed?'records':panels.get(key())||'plan';
  const markEdited=()=>{edited.add(key());records.edit(key());};
  const draft=()=>{if(!drafts.has(key()))drafts.set(key(),holdingDraft(holding()));return drafts.get(key());};
  const el=id=>view?.getElementById(id);
  const set=(id,html)=>{const node=el(id);if(node)node.innerHTML=html;};
  const syncTheme=()=>{if(view)view.host.dataset.theme=document.documentElement.dataset.theme||'light';};
  function render() {
    if(!view)return;
    const list=selectable();
    if(data()?.status==='read'&&!list.some(h=>h.key===selected)) {
      selected=(list.find(h=>!h.closed)||list[0])?.key||'';strategy=selections.get(selected)||'';detail=null;error='';request++;
    }
    const h=holding(),rows=accounts();
    if(rows.length&&!rows.some(a=>a.experiment_id===strategy)) {
      const previousKey=key(),initial=!strategy;strategy=rows[0].experiment_id;
      if(initial&&drafts.has(previousKey)&&!drafts.has(key()))drafts.set(key(),drafts.get(previousKey));
      if(initial&&edited.has(previousKey))edited.add(key());
    }
    if(selected)selections.set(selected,strategy);
    const saved=data()?.planning_enabled&&(h?.planning_available||h?.recording_available)&&account()?records.ensure(key(),{exchange:h.exchange,market:h.market,experiment:strategy},edited.has(key())):null;
    const recordPanel=saved&&panel()==='records';
    patchPreservingUi(view,()=>{
      set('holdings-summary',holdingsSummaryHtml(data()));set('holdings-list',holdingsListHtml(data(),selected));
      set('holding-price-refresh',priceRefreshHtml(data(),{available:Boolean(onRefreshPrices),busy:priceBusy,error:priceError}));
      set('holding-detail',h?`${holdingHeaderHtml(h)}<section id="holding-strategies">${holdingStrategiesHtml(rows,strategy,{loading,error,holding:h})}</section>${saved?`<nav class="holding-work-tabs" aria-label="실전 기록">${h.closed?'':'<button data-holding-panel="plan" aria-pressed="'+!recordPanel+'">매매 계획</button>'}<button data-holding-panel="records" aria-pressed="${recordPanel}">소액 매매${h.closed?' · 매도 완료':''}</button></nav><div id="holding-save-state">${savedPlanHtml(saved,panel())}</div>`:''}<section id="holding-calculator" ${recordPanel||h.closed?'hidden':''}>${holdingCalculatorHtml(h,draft(),account())}</section>${saved?`<section id="holding-records" ${recordPanel?'':'hidden'}>${manualRecordsHtml(saved,{closed:h.closed})}</section>`:''}`:'');
    });
  }
  async function load() {
    const h=holding();if(!(h?.planning_available||h?.recording_available)||!view)return;
    const id=++request,identity=selected;loading=true;render();
    try {
      const result=await getMarketDetail(h.exchange,h.market);
      if(!view||id!==request||identity!==selected)return;
      detail=result;error='';
    }catch {if(id===request&&identity===selected)error='전략 기록을 불러오지 못했습니다.';}
    finally {if(view&&id===request&&identity===selected){loading=false;render();}}
  }
  function renderCalculator() {
    const h=holding();if(!h)return;
    patchPreservingUi(view,()=>set('holding-calculator',holdingCalculatorHtml(h,draft(),account())));
  }
  function calculate() {
    const h=holding();if(!h)return;
    patchPreservingUi(view,()=>{set('calculation-result',holdingCalculationHtml(h,draft()));set('holding-allocation',allocationHtml(draft()));set('holding-save-state',savedPlanHtml(record(),panel()));});
  }
  async function refreshPrices() {
    if(priceBusy||!onRefreshPrices)return;
    priceBusy=true;priceError='';render();
    try {await onRefreshPrices();}catch {priceError='가격을 조회하지 못했습니다. 잠시 후 다시 시도하세요.';}
    finally {priceBusy=false;render();}
  }
  function click(e) {
    const b=e.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.action==='refresh-prices'){void refreshPrices();return;}
    if(b.dataset.holding){selected=b.dataset.holding;strategy=selections.get(selected)||'';detail=null;error='';request++;render();void load();return;}
    if(b.dataset.strategy){strategy=b.dataset.strategy;selections.set(selected,strategy);render();return;}
    if(b.dataset.holdingPanel){panels.set(key(),b.dataset.holdingPanel);render();return;}
    const action=b.dataset.action,h=holding();if(!h)return;
    if(action==='retry-strategies'){void load();return;}
    if(action==='paper-ledger'){const a=account();if(a)onPaper(h.exchange,h.market,a.style);return;}
    if(action==='load-holding-plan'){void records.read(key(),true);return;}
    if(action==='record-manual-fill'){void records.write(key(),'fill');return;}
    if(b.dataset.voidRecord){void records.write(key(),'void',null,b.dataset.voidRecord);return;}
    if(!h.planning_available)return;
    if(action==='save-holding-plan'){void records.write(key(),'save',draft());return;}
    if(action==='reload-holding'){const d=draft(),start=holdingDraft(h);d.volume=start.volume;d.average=start.average;d.holdingRevision=start.holdingRevision;markEdited();renderCalculator();calculate();return;}
    if(action==='import-holding-buy'||action==='import-holding-sell'){
      const result=importHoldingPlan(draft(),h,account(),{part:action==='import-holding-buy'?'buy':'sell'});
      if(result.error){el('holding-plan-error').textContent=result.error;return;}
      drafts.set(key(),result.draft);markEdited();renderCalculator();calculate();return;
    }
    const d=draft();
    if(action==='add-buy'&&d.buys.length<20)d.buys.push({price:'',amount:''});
    else if(action==='add-sell'&&d.sells.length<20)d.sells.push({price:'',weight:''});
    else if(b.dataset.removeBuy!==undefined)d.buys.splice(Number(b.dataset.removeBuy),1);
    else if(b.dataset.removeSell!==undefined)d.sells.splice(Number(b.dataset.removeSell),1);
    else return;
    d.origin='manual';markEdited();renderCalculator();calculate();
  }
  function input(e) {
    const field=e.target;
    if(field.dataset.recordField){records.input(key(),field.dataset.recordField,field.value);if(field.dataset.recordField==='side')render();return;}
    if(!holding()?.planning_available)return;
    const d=draft();
    if(['volume','average','fee','slippage','budget'].includes(field.dataset.draft))d[field.dataset.draft]=field.value;
    else if(field.dataset.buyPrice!==undefined)d.buys[Number(field.dataset.buyPrice)].price=field.value;
    else if(field.dataset.buyAmount!==undefined)d.buys[Number(field.dataset.buyAmount)].amount=field.value;
    else if(field.dataset.sellPrice!==undefined)d.sells[Number(field.dataset.sellPrice)].price=field.value;
    else if(field.dataset.sellWeight!==undefined)d.sells[Number(field.dataset.sellWeight)].weight=field.value;
    else return;
    d.origin='manual';markEdited();calculate();
  }
  return {mount(node){root=node;root.innerHTML='<crypto-holdings-workbench data-raw-text></crypto-holdings-workbench>';view=root.firstElementChild.attachShadow({mode:'open'});view.innerHTML=holdingsShell();syncTheme();view.addEventListener('click',click);view.addEventListener('input',input);document.addEventListener('viewer-theme-change',syncTheme);unsub=store.subscribe((_,meta)=>{if(['snapshot','snapshot-live'].includes(meta?.type)){render();void load();}});render();void load();},render,refresh(){render();void load();},
    destroy(){request++;unsub?.();records.destroy();document.removeEventListener('viewer-theme-change',syncTheme);view=null;root=null;}};
}
