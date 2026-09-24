import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {holdingDraft,importHoldingPlan,scopedStrategies,holdingChanged,buyAllocations} from '../public/modules/shared/holdings-workbench-model.js';
import {calculatePlan} from '../public/modules/shared/strategy-workbench-model.js';
import {createHoldingsWorkbench} from '../public/modules/pages/holdings-workbench.js';

const now=Date.now()/1000;
const holding=(exchange='bithumb')=>({key:`${exchange}|KRW-B3|KRW`,exchange,market:'KRW-B3',symbol:'B3',quote_currency:'KRW',volume:10,avg_price:100,updated_ts:123,planning_available:true,valid:true,closed:false,current_price:120,price_ts:now,value_quote:1200,unrealized_pnl_quote:200,unrealized_pnl_pct:20});
const account=(exchange='bithumb',style='aggressive')=>({experiment_id:`${exchange}|${style}|v1`,style,label:style==='aggressive'?'공격적':'균형',return_pct:style==='aggressive'?3:1,closed_trades:3,wins:2,win_rate_pct:66.67,max_drawdown_pct:-1,reconciliation:{matches:true},volume:99999,avg_price:99999,cash_krw:10000000,plan:{available:true,source_ts:now,rules:{take_profit_pct:14},entries:[{price:80,amount_krw:1000000,weight_pct:10,basis:'next_condition'},{price:75,amount_krw:500000,weight_pct:5,basis:'conditional_recalculation'}],exits:[{price:999999,weight_pct:100}]}});
test('real plan imports price proportions into the user budget, never PAPER balances',()=>{
 const h=holding(),d=holdingDraft(h);d.budget='900';const a=account();
 const before=JSON.stringify([h,d,a]),r=importHoldingPlan(d,h,a);
 assert.equal(r.draft.volume,'10');assert.equal(r.draft.average,'100');assert.equal(r.draft.fee,'0.04');
 assert.deepEqual(r.draft.buys.map(r=>r.amount),['600','300']);buyAllocations(r.draft).forEach((w,i)=>assert.ok(Math.abs(w-[200/3,100/3][i])<1e-10));
 const calc=calculatePlan(r.draft,{exchange:h.exchange,market:h.market});
 assert.ok(Math.abs(calc.buyTotal-900)<1e-9);assert.equal(calc.remaining,0);
 assert.ok(Math.abs(Number(r.draft.sells[0].price)-calc.average*1.14)<1e-9);
 assert.notEqual(r.draft.sells[0].price,'999999');assert.equal(JSON.stringify([h,d,a]),before);
 assert.equal(holdingDraft(holding('upbit')).fee,'0.05');
});
test('partial sells conserve cost, quantity and fees with actual holdings',()=>{
 const d=holdingDraft(holding());d.buys=[{price:'80',amount:'800.32'}];d.sells=[{price:'120',weight:'30'},{price:'130',weight:'40'}];
 const r=calculatePlan(d);assert.equal(r.valid,true);assert.equal(r.remaining,6);
 assert.ok(Math.abs(r.afterBuyQuantity-20)<1e-10);assert.ok(Math.abs(r.average-90.016)<1e-10);
 assert.ok(Math.abs(r.realized-(1760*.9996-14*90.016))<1e-9);
 d.sells[1].weight='71';assert.equal(calculatePlan(d).valid,false);
 d.volume='';assert.equal(calculatePlan(d).valid,false);
});
test('missing, stale, changed and mismatched sources cannot be imported as an actual plan',()=>{
 const h=holding(),d=holdingDraft(h),a=account();
 assert.ok(importHoldingPlan(d,h,a).error);d.budget='900';
 assert.ok(importHoldingPlan(d,h,{...a,reconciliation:{matches:false}}).error);
 assert.ok(importHoldingPlan(d,h,{...a,plan:{...a.plan,source_ts:1}}).error);
 assert.ok(importHoldingPlan(d,{...h,updated_ts:124},a).error);assert.equal(holdingChanged(d,{...h,volume:0}),true);
 const lab={version:2,exchange:'upbit',market:'KRW-B3',experiments:[account('upbit')]};
 assert.deepEqual(scopedStrategies({exchange:'upbit',market:'KRW-B3',data:{strategy_lab:lab}},h),[]);
 assert.deepEqual(scopedStrategies({exchange:'bithumb',market:'KRW-B3',data:{strategy_lab:lab}},h),[]);
});

const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
for(const name of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element','Document','DocumentFragment','Event'])globalThis[name]=dom.window[name];
globalThis.CSS={escape:value=>String(value)};globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);window.scrollTo=()=>{};
const data={status:'read',holdings:[holding(),holding('upbit')],holding_count:2,closed_count:1,priced_count:2,valuation_complete:true,value_krw:2400,pnl_krw:400};
const state={snapshot:{local_holdings:data},ui:{}},listeners=new Set(),requests=[],ledger=[];
const store={get:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);}};
globalThis.fetch=async path=>{const u=new URL(path,'http://127.0.0.1:8766'),exchange=u.searchParams.get('exchange'),market=u.searchParams.get('market');requests.push([exchange,market]);return {ok:true,json:async()=>({detail:{exchange,market,data:{strategy_lab:{version:2,exchange,market,experiments:[account(exchange),account(exchange,'balanced')]}}}})};};
const page=createHoldingsWorkbench({store,onPaper:(...args)=>ledger.push(args)});page.mount(document.getElementById('root'));
const flush=()=>new Promise(r=>setTimeout(r,20)),shadow=()=>document.getElementById('root').firstElementChild.shadowRoot;
const click=selector=>{const e=shadow().querySelector(selector);assert.ok(e,selector);e.click();};
const input=(selector,value)=>{const e=shadow().querySelector(selector);assert.ok(e,selector);e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));return e;};
const poll=()=>{for(const f of listeners)f(state,{type:'snapshot-live'});};
test('holding selection and original ledger links use exact exchange identity',async()=>{
 await flush();assert.equal(shadow().querySelector('[data-draft="volume"]').value,'10');
 assert.ok(shadow().textContent.includes('이 코인의 가상매매 성과'));
 click('[data-action="paper-ledger"]');assert.deepEqual(ledger.at(-1),['bithumb','KRW-B3','aggressive']);
 click('[data-holding="upbit|KRW-B3|KRW"]');await flush();assert.deepEqual(requests.at(-1),['upbit','KRW-B3']);
 assert.equal(shadow().querySelector('[data-draft="fee"]').value,'0.05');
 click('[data-action="paper-ledger"]');assert.deepEqual(ledger.at(-1),['upbit','KRW-B3','aggressive']);
 click('[data-holding="bithumb|KRW-B3|KRW"]');await flush();
});
test('strategy import, edits, focus and disclosures survive polling and strategy switches',async()=>{
 input('[data-draft="budget"]','900');click('[data-action="import-holding-plan"]');
 assert.equal(shadow().querySelector('[data-buy-amount="0"]').value,'600');
 const amount=input('[data-buy-amount="0"]','555');amount.focus();
 shadow().querySelector('[data-continuity-key="calculation-stages"]').open=true;
 poll();await flush();
 assert.equal(shadow().querySelector('[data-buy-amount="0"]').value,'555');
 assert.equal(shadow().activeElement,shadow().querySelector('[data-buy-amount="0"]'));
 assert.equal(shadow().querySelector('[data-continuity-key="calculation-stages"]').open,true);
 click('[data-strategy="bithumb|balanced|v1"]');assert.equal(shadow().querySelector('[data-buy-amount]'),null);
 click('[data-strategy="bithumb|aggressive|v1"]');assert.equal(shadow().querySelector('[data-buy-amount="0"]').value,'555');
});
test('holding updates require explicit starting-position refresh and keep calculation rows',async()=>{
 data.holdings[0]={...data.holdings[0],volume:20,updated_ts:124};poll();await flush();
 assert.equal(shadow().querySelector('[data-draft="volume"]').value,'10');
 assert.equal(shadow().querySelector('[data-action="import-holding-plan"]').disabled,true);
 assert.ok(shadow().textContent.includes('보유정보가 갱신'));
 click('[data-action="reload-holding"]');assert.equal(shadow().querySelector('[data-draft="volume"]').value,'20');
 assert.equal(shadow().querySelector('[data-buy-amount="0"]').value,'555');
});
test('read failures, theme, and explicit zero closeout retain truthful state',async()=>{
 document.documentElement.dataset.theme='dark';document.dispatchEvent(new Event('viewer-theme-change'));
 assert.equal(shadow().host.dataset.theme,'dark');
 state.snapshot.local_holdings={status:'read_failed',holdings:[]};poll();await flush();
 assert.ok(shadow().textContent.includes('읽지 못했습니다'));assert.ok(!shadow().textContent.includes('등록된 보유자산이 없습니다'));
 data.holdings[0]={...data.holdings[0],volume:0,closed:true};data.closed_count=2;data.holding_count=1;
 state.snapshot.local_holdings=data;poll();await flush();
 assert.equal(shadow().querySelector('[data-holding="bithumb|KRW-B3|KRW"]'),null);
 assert.ok(shadow().querySelector('[data-holding="upbit|KRW-B3|KRW"]'));
});
test.after(()=>{page.destroy();dom.window.close();});
