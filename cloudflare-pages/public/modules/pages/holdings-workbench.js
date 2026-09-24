import {getMarketDetail} from '../services/market-detail.js';
import {patchPreservingUi} from '../shared/ui-continuity.js';
import {holdingDraft,scopedStrategies} from '../shared/holdings-workbench-model.js';
import {importHoldingPlan} from '../shared/holdings-workbench-model.js';
import {holdingsShell,holdingsSummaryHtml,holdingsListHtml,holdingHeaderHtml,holdingStrategiesHtml,holdingCalculatorHtml,allocationHtml} from '../shared/holdings-workbench-view.js';
import {calculationHtml} from '../shared/strategy-workbench-view.js';

/** Composition only. Reads the existing journal projection and scoped PAPER
 * accounts; all edits stay in per-holding/per-strategy calculation drafts. */
export function createHoldingsWorkbench({store,onPaper=()=>{}}) {
  let root,view,unsub,selected='',strategy='',detail=null,request=0,loading=false,error='';
  const drafts=new Map(),selections=new Map();
  const data=()=>store.get().snapshot?.local_holdings;
  const holding=()=>data()?.holdings?.find(h=>h.key===selected&&!h.closed);
  const accounts=()=>scopedStrategies(detail,holding()).slice().sort((a,b)=>(b.return_pct??-Infinity)-(a.return_pct??-Infinity));
  const account=()=>accounts().find(a=>a.experiment_id===strategy);
  const key=()=>`${selected}|${strategy}`;
  const draft=()=>{if(!drafts.has(key()))drafts.set(key(),holdingDraft(holding()));return drafts.get(key());};
  const el=id=>view?.getElementById(id);
  const set=(id,html)=>{const node=el(id);if(node)node.innerHTML=html;};
  const syncTheme=()=>{if(view)view.host.dataset.theme=document.documentElement.dataset.theme||'light';};
  function render() {
    if(!view)return;
    const list=data()?.holdings?.filter(h=>!h.closed)||[];
    if(data()?.status==='read'&&!list.some(h=>h.key===selected)) {
      selected=list[0]?.key||'';strategy=selections.get(selected)||'';detail=null;error='';request++;
    }
    const h=holding(),rows=accounts();
    if(rows.length&&!rows.some(a=>a.experiment_id===strategy)) {
      const previousKey=key(),initial=!strategy;strategy=rows[0].experiment_id;
      if(initial&&drafts.has(previousKey)&&!drafts.has(key()))drafts.set(key(),drafts.get(previousKey));
    }
    if(selected)selections.set(selected,strategy);
    patchPreservingUi(view,()=>{
      set('holdings-summary',holdingsSummaryHtml(data()));set('holdings-list',holdingsListHtml(data(),selected));
      set('holding-detail',h?`${holdingHeaderHtml(h)}<section id="holding-strategies">${holdingStrategiesHtml(rows,strategy,{loading,error})}</section><section id="holding-calculator">${holdingCalculatorHtml(h,draft(),account())}</section>`:'');
    });
  }
  async function load() {
    const h=holding();if(!h?.planning_available||!view)return;
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
    patchPreservingUi(view,()=>{set('calculation-result',calculationHtml(draft(),{exchange:h.exchange,market:h.market}));set('holding-allocation',allocationHtml(draft()));});
  }
  function click(e) {
    const b=e.target.closest('button');if(!b||b.disabled)return;
    if(b.dataset.holding){selected=b.dataset.holding;strategy=selections.get(selected)||'';detail=null;error='';request++;render();void load();return;}
    if(b.dataset.strategy){strategy=b.dataset.strategy;selections.set(selected,strategy);render();return;}
    const action=b.dataset.action,h=holding();if(!h)return;
    if(action==='retry-strategies'){void load();return;}
    if(action==='paper-ledger'){const a=account();if(a)onPaper(h.exchange,h.market,a.style);return;}
    if(!h.planning_available)return;
    if(action==='reload-holding'){const d=draft(),start=holdingDraft(h);d.volume=start.volume;d.average=start.average;d.holdingRevision=start.holdingRevision;renderCalculator();return;}
    if(action==='import-holding-plan'){
      const result=importHoldingPlan(draft(),h,account());
      if(result.error){el('holding-plan-error').textContent=result.error;return;}
      drafts.set(key(),result.draft);renderCalculator();return;
    }
    const d=draft();
    if(action==='add-buy'&&d.buys.length<20)d.buys.push({price:'',amount:''});
    else if(action==='add-sell'&&d.sells.length<20)d.sells.push({price:'',weight:''});
    else if(b.dataset.removeBuy!==undefined)d.buys.splice(Number(b.dataset.removeBuy),1);
    else if(b.dataset.removeSell!==undefined)d.sells.splice(Number(b.dataset.removeSell),1);
    else return;
    d.origin='manual';renderCalculator();
  }
  function input(e) {
    if(!holding()?.planning_available)return;
    const field=e.target,d=draft();
    if(['volume','average','fee','slippage','budget'].includes(field.dataset.draft))d[field.dataset.draft]=field.value;
    else if(field.dataset.buyPrice!==undefined)d.buys[Number(field.dataset.buyPrice)].price=field.value;
    else if(field.dataset.buyAmount!==undefined)d.buys[Number(field.dataset.buyAmount)].amount=field.value;
    else if(field.dataset.sellPrice!==undefined)d.sells[Number(field.dataset.sellPrice)].price=field.value;
    else if(field.dataset.sellWeight!==undefined)d.sells[Number(field.dataset.sellWeight)].weight=field.value;
    else return;
    d.origin='manual';calculate();
  }
  return {mount(node){root=node;root.innerHTML='<crypto-holdings-workbench data-raw-text></crypto-holdings-workbench>';view=root.firstElementChild.attachShadow({mode:'open'});view.innerHTML=holdingsShell();syncTheme();view.addEventListener('click',click);view.addEventListener('input',input);document.addEventListener('viewer-theme-change',syncTheme);unsub=store.subscribe((_,meta)=>{if(['snapshot','snapshot-live'].includes(meta?.type)){render();void load();}});render();void load();},render,refresh(){render();void load();},
    destroy(){request++;unsub?.();document.removeEventListener('viewer-theme-change',syncTheme);view=null;root=null;}};
}
