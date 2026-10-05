import {getMarketDetail} from '../services/market-detail.js';
import {patchPreservingUi} from '../shared/ui-continuity.js';
import {updateHtml} from '../shared/dom-patch.js';
import {holdingDraft,scopedStrategies,refreshHoldingDraft} from '../shared/holdings-workbench-model.js';
import {importHoldingPlan} from '../shared/holdings-workbench-model.js';
import {holdingsShell,holdingsSummaryHtml,holdingsListHtml,holdingHeaderHtml,holdingStrategiesHtml,holdingCalculatorHtml,holdingCalculationHtml,allocationHtml,priceRefreshHtml} from '../shared/holdings-workbench-view.js';
import {createHoldingRecordsSession} from '../shared/holding-records-session.js';
import {savedPlanHtml,manualRecordsHtml} from '../shared/holding-records-view.js';
import {createHoldingRegistration,holdingRegistrationHtml} from '../shared/holding-registration.js';
import {createHoldingManagement} from '../shared/holding-management-session.js';
import {holdingManagementHtml,holdingAmountsHtml} from '../shared/holding-management-view.js';
import {createStrategyPeriod} from '../shared/strategy-period-workbench.js';

/** Composition only. Per-holding/strategy drafts persist only through the
 * explicitly enabled local planning service; actual holdings remain separate. */
export function createHoldingsWorkbench({store,onPaper=()=>{},onRefreshPrices=null,onHoldingsChanged=null,manualClient,registrationClient,managementClient}) {
  let root,view,unsub,selected='',strategy='',detail=null,request=0,loading=false,error='';
  let priceBusy=false,priceError='';
  const drafts=new Map(),selections=new Map(),comparing=new Set();
  const edited=new Set(),panels=new Map();
  const records=createHoldingRecordsSession({client:manualClient,restore:(k,d)=>{drafts.set(k,d);edited.delete(k);},changed:()=>render()});
  const registration=createHoldingRegistration({client:registrationClient,changed:()=>render(),onAdded:result=>{
    selected=result.holding_key;strategy='';detail=null;error='';request++;onHoldingsChanged?.(result.holdings);render();void load();
  }});
  const management=createHoldingManagement({client:managementClient,changed:()=>render(),onSaved:result=>{
    const h=result.holdings?.holdings?.find(h=>h.key===result.result?.key);
    if(h)for(const [k,d] of drafts)if(k.startsWith(h.key+'|')) {
      drafts.set(k,refreshHoldingDraft(d,h));edited.add(k);records.edit(k);
    }
    onHoldingsChanged?.(result.holdings);render();
  }});
  const data=()=>store.get().snapshot?.local_holdings;
  const selectable=()=>data()?.holdings?.filter(h=>!h.closed||(data().planning_enabled&&h.recording_available)||(data().holding_management_enabled&&h.management_available))||[];
  const holding=()=>selectable().find(h=>h.key===selected);
  const accounts=()=>scopedStrategies(detail,holding());
  const account=()=>accounts().find(a=>a.experiment_id===strategy);
  const key=()=>`${selected}|${strategy}`;
  const record=()=>records.get(key());
  const panel=()=>holding()?.closed?'records':panels.get(key())||'plan';
  const markEdited=()=>{edited.add(key());records.edit(key());};
  const draft=()=>{if(!drafts.has(key()))drafts.set(key(),holdingDraft(holding()));return drafts.get(key());};
  const el=id=>view?.getElementById(id);
  const set=(id,html,options)=>updateHtml(el(id),html,options);
  const syncTheme=()=>{if(view)view.host.dataset.theme=document.documentElement.dataset.theme||'light';};
  const periodReview=createStrategyPeriod({changed:()=>render(),
    openJournal(experiment,review){
      const h=holding(),a=accounts().find(a=>a.experiment_id===experiment);
      if(a&&review?.exchange===h.exchange&&review?.market===h.market)onPaper(h.exchange,h.market,a.style);
    },
    chooseStrategy(experiment,review){
      const h=holding();if(review?.exchange!==h?.exchange||review?.market!==h?.market||!accounts().some(a=>a.experiment_id===experiment))return;
      strategy=experiment;selections.set(selected,strategy);comparing.delete(selected);
      panels.set(key(),h.closed?'records':'plan');render();
    },
  });
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
    const canCompare=h?.quote_currency==='KRW'&&rows.length>0&&detail?.data?.strategy_lab?.period_review_available===true;
    const scope=canCompare?{exchange:h.exchange,market:h.market,style:account()?.style||'aggressive'}:null;
    const comparison=canCompare?periodReview.state(scope):null,showComparison=canCompare&&comparing.has(selected);
    const modes=canCompare?`<nav class="holding-work-tabs" aria-label="보유 전략 보기"><button data-holding-comparison="plan" data-continuity-key="holding-mode-plan" aria-pressed="${!showComparison}">${h.closed?'전략·기록':'전략·계획'}</button><button data-holding-comparison="compare" data-continuity-key="holding-mode-compare" aria-pressed="${showComparison}">기간별 비교</button></nav>`:'';
    patchPreservingUi(view,()=>{
      set('holdings-summary',holdingsSummaryHtml(data()));set('holdings-list',holdingsListHtml(data(),selected));
      set('holding-price-refresh',priceRefreshHtml(data(),{available:Boolean(onRefreshPrices),busy:priceBusy,error:priceError}));
      set('holding-registration',holdingRegistrationHtml(registration.state,Boolean(onHoldingsChanged&&data()?.status==='read'&&data()?.holding_registration_enabled),data()?.confirmed_exchange));
      const work=showComparison?`<section id="holding-period">${periodReview.html(scope)}</section>`:`<section id="holding-strategies">${holdingStrategiesHtml(rows,strategy,{loading,error,holding:h,comparison})}</section>${saved?`<nav class="holding-work-tabs" aria-label="실전 기록">${h.closed?'':'<button data-holding-panel="plan" aria-pressed="'+!recordPanel+'">매매 계획</button>'}<button data-holding-panel="records" aria-pressed="${recordPanel}">소액 매매${h.closed?' · 매도 완료':''}</button></nav><div id="holding-save-state">${savedPlanHtml(saved,panel())}</div>`:''}<section id="holding-calculator" ${recordPanel||h?.closed?'hidden':''}>${h?holdingCalculatorHtml(h,draft(),account()):''}</section>${saved?`<section id="holding-records" ${recordPanel?'':'hidden'}>${manualRecordsHtml(saved,{closed:h.closed})}</section>`:''}`;
      set('holding-detail',h?`${holdingHeaderHtml(h)}${holdingManagementHtml(h,management.get(h.key),Boolean(onHoldingsChanged&&data()?.holding_management_enabled))}${modes}${work}`:'',{busy:loading&&Boolean(h)&&!rows.length});
    });
    if(canCompare)periodReview.mount(showComparison?el('holding-period'):null,scope);
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
    if(b.dataset.action==='open-holding-add'){registration.open(data()?.confirmed_exchange);el('holding-add-form')?.querySelector('[data-add-holding="symbol"]')?.focus();return;}
    if(b.dataset.action==='close-holding-add'){registration.close();return;}
    if(b.dataset.holding){loading=true;selected=b.dataset.holding;strategy=selections.get(selected)||'';detail=null;error='';request++;render();void load();return;}
    if(b.dataset.strategy){strategy=b.dataset.strategy;selections.set(selected,strategy);render();return;}
    if(b.dataset.holdingComparison){
      if(b.dataset.holdingComparison==='compare'){
        const h=holding();if(!h)return;
        periodReview.select({exchange:h.exchange,market:h.market,style:account()?.style},{experiment:strategy});comparing.add(selected);
      }else comparing.delete(selected);
      render();return;
    }
    if(b.dataset.holdingPanel){panels.set(key(),b.dataset.holdingPanel);render();return;}
    const action=b.dataset.action,h=holding();if(!h)return;
    if(b.dataset.manageOpen){management.open(h,b.dataset.manageOpen);return;}
    if(b.dataset.manageAction){const a=b.dataset.manageAction;if(a==='close')management.close(h);if(a==='all')management.all(h);if(a==='reload')void management.read(h);if(a==='apply')void management.apply(h);return;}
    if(action==='retry-strategies'){void load();return;}
    if(action==='paper-ledger'){const a=account();if(a)onPaper(h.exchange,h.market,a.style);return;}
    if(action==='load-holding-plan'){void records.read(key(),true);return;}
    if(action==='record-manual-fill'){void records.write(key(),'fill');return;}
    if(b.dataset.voidRecord){void records.write(key(),'void',null,b.dataset.voidRecord);return;}
    if(!h.planning_available)return;
    if(action==='save-holding-plan'){void records.write(key(),'save',draft());return;}
    if(action==='reload-holding'){drafts.set(key(),refreshHoldingDraft(draft(),h));markEdited();renderCalculator();calculate();return;}
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
    if(field.dataset.manageField&&holding()){const h=holding();management.input(h,field.dataset.manageField,field.value);const s=management.get(h.key);set('holding-execution-amounts',holdingAmountsHtml(s.form,s.action,h.quote_currency));view.querySelector('.holding-change-preview')?.remove();const notice=view.querySelector('.holding-manage-editor [role=alert]');if(notice)notice.textContent='';return;}
    if(field.dataset.addHolding){registration.input(field.dataset.addHolding,field.value);if(field.dataset.addHolding==='quote_currency')render();return;}
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
  return {mount(node){root=node;root.innerHTML='<crypto-holdings-workbench data-raw-text></crypto-holdings-workbench>';view=root.firstElementChild.attachShadow({mode:'open'});view.innerHTML=holdingsShell();syncTheme();view.addEventListener('click',click);view.addEventListener('input',input);view.addEventListener('submit',e=>{if(e.target.id==='holding-add-form'){e.preventDefault();void registration.save();}if(e.target.id==='holding-manage-form'){e.preventDefault();if(holding())void management.preview(holding());}});document.addEventListener('viewer-theme-change',syncTheme);unsub=store.subscribe((_,meta)=>{if(['snapshot','snapshot-live'].includes(meta?.type)){render();void load();}});render();void load();},render,refresh(){render();void load();},
    destroy(){request++;unsub?.();periodReview.destroy();records.destroy();registration.destroy();management.destroy();document.removeEventListener('viewer-theme-change',syncTheme);view=null;root=null;}};
}
