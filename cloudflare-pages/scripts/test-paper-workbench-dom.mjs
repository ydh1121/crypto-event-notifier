// DOM integration tests only; these are not visual/mobile-browser acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createPaperWorkbench} from '../public/modules/pages/paper-workbench.js';
const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
for(const key of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element','Document','DocumentFragment','Event'])globalThis[key]=dom.window[key];
globalThis.CSS={escape:value=>String(value)};globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);window.scrollTo=()=>{};
let revision=1,clock=Date.now();const realNow=Date.now;Date.now=()=>clock;
const acc=(style,ex='bithumb')=>({experiment_id:`${ex}|${style}|v1`,style,label:style==='aggressive'?'공격적':'균형',revision:`${style}-${revision}`,volume:10,avg_price:100,cash_krw:9000,equity_krw:10000,position_value_krw:1000,closed_trades:2,wins:1,win_rate_pct:50,return_pct:0,realized_pnl_krw:0,unrealized_pnl_krw:0,max_drawdown_pct:-2,source_ts:clock/1000-7200,reconciliation:{matches:true},journal:{total:2,complete:true},plan:{available:true,fee_rate:.0004,slippage_rate:.0005,source_ts:clock/1000,entry_bias:0,entry_conditions_met:true,completed_entries:1,rules:{max_buys:4,entry_regime:54,entry_score:55,opportunity:58,max_position_pct:45,add_drop_pct:2.5},entries:[{round:2,price:97.5,amount_krw:780,weight_pct:7.8,basis:'next_condition'}],exits:[{price:114,weight_pct:100}],weak_market_exit:{below:42,after_seconds:300},stop_price:92}});
const state={snapshot:{public:{exchanges:{bithumb:{leaderboard:[{market:'KRW-B3',symbol:'B3',price:100,signal_ts:clock/1000},{market:'KRW-DEXE',symbol:'DEXE',price:200,signal_ts:clock/1000}]},upbit:{leaderboard:[{market:'KRW-B3',symbol:'B3',price:101,signal_ts:clock/1000}]}}}},ui:{paperExchange:'bithumb',paperMarket:'KRW-B3',paperLabStyle:'aggressive'}};
const listeners=new Set();const store={get:()=>state,setUi(p){Object.assign(state.ui,p)},subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)}};
const requests=[];
globalThis.fetch=async path=>{const u=new URL(path,'http://127.0.0.1:8766'),ex=u.searchParams.get('exchange'),market=u.searchParams.get('market');requests.push(u);
 const accounts=['aggressive','balanced'].map(s=>acc(s,ex));let body;
 if(u.searchParams.has('experiment')) {const account=accounts.find(a=>a.experiment_id===u.searchParams.get('experiment'));body={exchange:ex,market,journal:{account,trades:[],revision:account.revision,total:0,offset:0,limit:30,next_offset:null}};}
 else body={detail:{exchange:ex,market,data:{strategy_lab:{version:2,exchange:ex,market,experiments:accounts,price_history:[{ts:clock/1000-7200,price:98},{ts:clock/1000-3600,price:100}],events:[]}}}};
 return {ok:true,json:async()=>structuredClone(body)};
};
const page=createPaperWorkbench({store});const root=document.getElementById('root');page.mount(root);page.render();
const flush=()=>new Promise(r=>setTimeout(r,20));
const shadow=()=>root.firstElementChild.shadowRoot;
const click=selector=>{const el=shadow().querySelector(selector);assert.ok(el,selector);el.click();};
test('strategy switch keeps coin identity and requests its own ledger',async()=>{
 await flush();assert.ok(shadow().textContent.includes('계좌·원장 일치'));assert.ok(shadow().textContent.includes('갱신 지연'));
 click('[data-experiment="bithumb|balanced|v1"]');await flush();assert.equal(state.ui.paperMarket,'KRW-B3');assert.equal(state.ui.paperLabStyle,'balanced');
 assert.equal(requests.at(-1).searchParams.get('experiment'),'bithumb|balanced|v1');
});
test('polling preserves calculator inputs, focus, and open rule details',async()=>{
 click('[data-action="import-plan"]');let field=shadow().querySelector('[data-buy-amount="0"]');field.value='4321';field.focus();field.dispatchEvent(new window.Event('input',{bubbles:true}));
 shadow().querySelector('[data-continuity-key="plan-rules"]').open=true;
 revision++;clock+=21000;for(const fn of listeners)fn(state,{type:'snapshot-live'});await flush();
 field=shadow().querySelector('[data-buy-amount="0"]');assert.equal(field.value,'4321');assert.equal(shadow().activeElement,field);assert.equal(shadow().querySelector('[data-continuity-key="plan-rules"]').open,true);
 assert.equal(shadow().querySelector('[role="tab"][aria-selected="true"]').dataset.experiment,'bithumb|balanced|v1');
});
test('calculator split limits and exchange switch keep drafts scoped',async()=>{
 click('[data-action="add-sell"]');const weight=shadow().querySelector('[data-sell-weight="1"]'),price=shadow().querySelector('[data-sell-price="1"]');weight.value='20';price.value='120';price.dispatchEvent(new window.Event('input',{bubbles:true}));weight.dispatchEvent(new window.Event('input',{bubbles:true}));
 assert.ok(shadow().getElementById('calculation-result').textContent.includes('100% 이하'));
 click('[data-exchange="upbit"]');await flush();assert.equal(state.ui.paperExchange,'upbit');assert.equal(shadow().getElementById('calculator').hidden,true);
 assert.equal(requests.at(-1).searchParams.get('experiment'),'upbit|balanced|v1');
});
test('ticker identifiers remain intact and existing accounts remain reachable',async()=>{
 click('[data-exchange="bithumb"]');await flush();click('[data-coin="KRW-DEXE"]');await flush();assert.ok(shadow().getElementById('coin-heading').textContent.includes('DEXE'));
 click('[data-overview="summary"]');assert.ok(root.querySelector('[data-return-workbench]'));assert.ok(root.querySelector('[data-paper-tab="coins"]'));
 root.querySelector('[data-return-workbench]').click();await flush();assert.ok(shadow().getElementById('coin-heading').textContent.includes('DEXE'));
});
test('theme changes reach the isolated coin view; standalone review has no unsupported aggregate routes',async()=>{
 const {applyTheme}=await import('../public/modules/shared/theme.js');
 applyTheme('dark');assert.equal(shadow().host.dataset.theme,'dark');
 applyTheme('light');assert.equal(shadow().host.dataset.theme,'light');
 page.destroy();const review=createPaperWorkbench({store,allowOverview:false});review.mount(root);review.render();await flush();
 assert.equal(shadow().querySelector('[data-overview]'),null);assert.ok(shadow().querySelector('[data-experiment]'));review.destroy();
});
test.after(()=>{page.destroy();Date.now=realNow;dom.window.close();});
