import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {holdingDraft,importHoldingPlan,scopedStrategies,holdingChanged,buyAllocations,holdingTarget} from '../public/modules/shared/holdings-workbench-model.js';
import {holdingHeaderHtml,holdingsListHtml,holdingCalculationHtml} from '../public/modules/shared/holdings-workbench-view.js';
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
test('sell-only import needs no buy budget and buy-only import keeps edited exits',()=>{
 const h=holding(),a=account(),d=holdingDraft(h);
 const sale=importHoldingPlan(d,h,a,{part:'sell'}).draft;
 assert.deepEqual(sale.buys,[]);assert.equal(sale.budget,'');
 assert.ok(Math.abs(Number(sale.sells[0].price)-114)<1e-10);
 assert.ok(Math.abs(calculatePlan(sale).realized-139.544)<1e-9);
 const manual={...d,budget:'900',sells:[{price:'123',weight:'30'},{price:'140',weight:'40'}]};
 const bought=importHoldingPlan(manual,h,a,{part:'buy'}).draft;
 assert.deepEqual(bought.sells,manual.sells);assert.notEqual(bought.sells,manual.sells);
 const changed=importHoldingPlan(bought,h,a,{part:'sell'}).draft;
 assert.deepEqual(changed.buys,bought.buys);
 assert.ok(Math.abs(Number(changed.sells[0].price)-calculatePlan({...bought,sells:[]}).average*1.14)<1e-9);
 assert.ok(importHoldingPlan(d,h,{...a,plan:{...a.plan,entries:[]}},{part:'buy'}).error);
});
test('holding target uses real average, not PAPER price or balance; empty plan has no realized estimate',()=>{
 const h={...holding(),avg_price:.7759,current_price:.9337},a=account();
 const target=holdingTarget(h,a);assert.ok(Math.abs(target.price-.884526)<1e-12);assert.ok(target.distance>0);
 assert.equal(holdingTarget(h,{...a,reconciliation:{matches:false}}),null);
 assert.equal(holdingTarget({...h,price_ts:1},a).distance,null);
 const html=holdingCalculationHtml(h,holdingDraft(h));
 assert.match(html,/예상 실현손익<\/dt><dd class="">—<\/dd>/);
 assert.match(holdingCalculationHtml(h,{...holdingDraft(h),sells:[{price:'',weight:''}]}),/예상 실현손익<\/dt><dd class="">—<\/dd>/);
});
test('BTC holding shows native price and PnL with separate KRW valuation',()=>{
 const h={...holding(),quote_currency:'BTC',market:'KRW-ETH/BTC',symbol:'ETH',current_price:.04,
   avg_price:.03,volume:2,value_quote:.08,value_krw:8000000,current_price_krw:4000000,valuation_ts:now,valuation_basis:'quote_conversion',unrealized_pnl_quote:.02,quote_to_krw:100000000,conversion_ts:now,planning_available:false};
 const html=holdingHeaderHtml(h);assert.match(html,/0.04 BTC/);assert.match(html,/0.02 BTC/);assert.match(html,/8,000,000원/);
 assert.match(html,/coin-price"><b>4,000,000원<\/b>/);assert.match(html,/BTC마켓 원화 환산가/);
 const list=holdingsListHtml({status:'read',holdings:[h]},h.key);assert.match(list,/BTC 기준/);assert.match(list,/8,000,000원/);
 const direct=holdingHeaderHtml({...h,current_price:null,current_price_krw:4100000,value_krw:8200000,unrealized_pnl_quote:null,valuation_basis:'krw_market'});
 assert.match(direct,/coin-price"><b>4,100,000원<\/b>/);assert.match(direct,/빗썸 원화마켓 평가가/);
 assert.ok(!direct.includes('0.04 BTC'));assert.ok(!direct.includes('0.02 BTC'));
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
let priceRequests=0,priceOffline=false;
const page=createHoldingsWorkbench({store,onPaper:(...args)=>ledger.push(args),onRefreshPrices:async()=>{
 priceRequests++;if(priceOffline)throw Error('offline');
 state.snapshot.local_holdings={...data,public_quotes:{status:'complete',requested:2,received:2}};poll();
}});page.mount(document.getElementById('root'));
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
 click('[data-action="import-holding-sell"]');assert.ok(shadow().querySelector('[data-sell-price="0"]'));
 input('[data-draft="budget"]','900');click('[data-action="import-holding-buy"]');
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
test('public quote refresh is explicit and preserves drafts through success and failure',async()=>{
 assert.equal(priceRequests,0);click('[data-action="refresh-prices"]');
 assert.equal(shadow().querySelector('[data-action="refresh-prices"]').disabled,true);await flush();
 assert.equal(priceRequests,1);assert.match(shadow().textContent,/거래소 가격 반영/);
 assert.equal(shadow().querySelector('[data-buy-amount="0"]').value,'555');
 priceOffline=true;click('[data-action="refresh-prices"]');await flush();
 assert.match(shadow().textContent,/가격을 조회하지 못했습니다/);
 assert.equal(shadow().querySelector('[data-buy-amount="0"]').value,'555');
 state.snapshot.local_holdings=data;
});
test('holding updates require explicit starting-position refresh and keep calculation rows',async()=>{
 data.holdings[0]={...data.holdings[0],volume:20,updated_ts:124};poll();await flush();
 assert.equal(shadow().querySelector('[data-draft="volume"]').value,'10');
 assert.equal(shadow().querySelector('[data-action="import-holding-buy"]').disabled,true);
 assert.equal(shadow().querySelector('[data-action="import-holding-sell"]').disabled,true);
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
