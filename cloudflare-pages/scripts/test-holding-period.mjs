// Integration and calculation checks; no visual-browser acceptance claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createHoldingsWorkbench} from '../public/modules/pages/holdings-workbench.js';
import {clearMarketDetail} from '../public/modules/services/market-detail.js';
import {holdingStrategiesHtml} from '../public/modules/shared/holdings-workbench-view.js';

const tick=()=>new Promise(resolve=>setTimeout(resolve,15));
const realNow=Date.now;let clock=realNow(),ctx;
const holding=(exchange='bithumb')=>({key:`${exchange}|KRW-B3|KRW`,exchange,market:'KRW-B3',symbol:'B3',quote_currency:'KRW',volume:10,avg_price:100,updated_ts:1,planning_available:true,recording_available:true,valid:true,closed:false,current_price:120,price_ts:clock/1000,value_quote:1200});
const account=(exchange,style)=>({experiment_id:`${exchange}|${style}|v1`,style,label:{aggressive:'공격적',balanced:'균형',conservative:'보수적'}[style],return_pct:style==='balanced'?999:99,closed_trades:777,wins:700,win_rate_pct:90,max_drawdown_pct:-44,reconciliation:{matches:true},volume:99999,avg_price:99999,plan:{available:true,source_ts:clock/1000,rules:{take_profit_pct:style==='balanced'?8:14},entries:[{price:style==='balanced'?50:80,amount_krw:200,weight_pct:20},{price:40,amount_krw:100,weight_pct:10}]}});
const emptyRecords=()=>({plan:null,plan_revision:0,ledger_revision:0,records:[],summary:{volume:0,average:null,realized:0,fees:0,trades:[]},comparison:{start:null,end:null,manual:{closed:0,wins:0,mean_return_pct:null},paper:null}});
function reviewFor(u) {
  const exchange=u.searchParams.get('exchange'),market=u.searchParams.get('market'),period=u.searchParams.get('period');
  const strategies=['aggressive','balanced','conservative'].map(style=>{
    const closed=style==='conservative'?0:style==='balanced'?2:1,pnl=closed?closed*(exchange==='upbit'?100:10):null;
    return {...account(exchange,style),status:'ok',current:{closed,open:0,wins:closed||null,realized_pnl_krw:pnl,return_pct:pnl,worst_return_pct:pnl,invested_krw:closed?100:null,proceeds_krw:closed?100+pnl:null,open_invested_krw:0,carried_positions:0},previous:period==='all'?null:{closed:1,open:1,wins:0,realized_pnl_krw:-5,return_pct:-5}};
  });
  return {status:'ok',exchange,market,period,observed_at:clock/1000,start:clock/1000-86400,end:clock/1000,selected_experiment:u.searchParams.get('experiment')||strategies[0].experiment_id,strategies,witnesses:[],witnesses_total:0,witnesses_limit:20};
}
function setup({offline=false,delay=false,mismatch=false,btc=false}={}) {
  const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
  for(const name of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element','Document','DocumentFragment','Event'])globalThis[name]=dom.window[name];
  globalThis.CSS={escape:String};globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);window.scrollTo=()=>{};Date.now=()=>clock;
  for(const ex of ['bithumb','upbit'])clearMarketDetail(ex,'KRW-B3');
  const data={status:'read',planning_enabled:true,holdings:[holding(),holding('upbit')],holding_count:2,closed_count:0,priced_count:2};
  if(btc)data.holdings=[{...holding(),key:'bithumb|KRW-ETH/BTC|BTC',market:'KRW-ETH/BTC',symbol:'ETH',quote_currency:'BTC',planning_available:false,recording_available:false,current_price:.04,current_price_krw:4000000,value_krw:8000000,quote_to_krw:100000000,conversion_ts:clock/1000,valuation_ts:clock/1000}];
  const state={snapshot:{local_holdings:data},ui:{}},listeners=new Set(),requests=[],writes=[],ledger=[];
  let release;
  globalThis.fetch=async(path,options)=>{
    const u=new URL(path,'http://127.0.0.1:8766'),ex=u.searchParams.get('exchange'),market=u.searchParams.get('market');requests.push({u,options});
    if(u.pathname==='/api/strategy-period') {
      const review=reviewFor(u);if(mismatch)review.exchange='wrong';
      if(delay){delay=false;await new Promise(r=>release=r);}
      if(offline)throw Error('offline');
      return {ok:true,json:async()=>({review})};
    }
    assert.equal(u.pathname,'/api/market-detail');
    return {ok:true,json:async()=>({detail:{exchange:ex,market,data:{strategy_lab:{version:2,exchange:ex,market,period_review_available:true,experiments:['aggressive','balanced','conservative'].map(style=>account(ex,style))}}}})};
  };
  const store={get:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);}};
  const page=createHoldingsWorkbench({store,onPaper:(...args)=>ledger.push(args),manualClient:{read:async()=>emptyRecords(),write:async(...args)=>{writes.push(args);return emptyRecords();}}});
  page.mount(document.getElementById('root'));
  const root=()=>document.getElementById('root').firstElementChild.shadowRoot;
  return {page,data,requests,writes,ledger,root,release:()=>release(),online:()=>offline=false,
    click(selector){const el=root().querySelector(selector);assert.ok(el,selector);el.click();},
    input(selector,value){const el=root().querySelector(selector);assert.ok(el,selector);el.value=value;el.dispatchEvent(new Event('input',{bubbles:true}));return el;},
    poll(){for(const listener of listeners)listener(state,{type:'snapshot-live'});},
    close(){page.destroy();dom.window.close();Date.now=realNow;},
  };
}
test.afterEach(()=>ctx?.close());

test('real plan uses the same period evidence, stable tabs, and null for no completed trades',async()=>{
  ctx=setup();await tick();const root=ctx.root();
  assert.equal(root.querySelector('[data-strategy][aria-selected=true]').dataset.strategy,'bithumb|aggressive|v1');
  assert.match(root.querySelector('#holding-strategies').textContent,/최근 30일 첫 진입/);
  assert.match(root.querySelector('.holding-strategy-evidence').textContent,/실현손익 10원.*완료 1회/);
  assert.doesNotMatch(root.querySelector('#holding-strategies').textContent,/999%|99%|777회|최대 하락|누적수익 순/);
  ctx.click('[data-strategy="bithumb|conservative|v1"]');
  assert.match(root.querySelector('[data-strategy][aria-selected=true]').textContent,/— · 완료 0회/);
  assert.match(root.querySelector('.holding-strategy-evidence').textContent,/실현손익 —/);
  assert.equal(ctx.requests.filter(r=>r.u.pathname==='/api/strategy-period').length,1);
});
test('period choice leads into that strategy calculator and preserves per-strategy drafts without writes',async()=>{
  ctx=setup();await tick();
  ctx.input('[data-draft=budget]','900');ctx.click('[data-action=import-holding-buy]');ctx.input('[data-buy-amount="0"]','555');
  ctx.click('[data-holding-comparison=compare]');await tick();ctx.click('[data-period-range="7d"]');await tick();
  ctx.click('[data-period-experiment="bithumb|balanced|v1"]');await tick();ctx.click('[data-period-journal]');
  assert.deepEqual(ctx.ledger.at(-1),['bithumb','KRW-B3','balanced']);
  assert.equal(ctx.root().querySelector('#holding-calculator'),null);
  ctx.click('[data-period-use]');await tick();
  assert.equal(ctx.root().querySelector('[data-strategy][aria-selected=true]').dataset.strategy,'bithumb|balanced|v1');
  assert.match(ctx.root().querySelector('#holding-strategies').textContent,/최근 7일/);
  ctx.input('[data-draft=budget]','900');ctx.click('[data-action=import-holding-buy]');ctx.click('[data-action=import-holding-sell]');
  assert.equal(ctx.root().querySelector('[data-buy-price="0"]').value,'50');
  assert.equal(ctx.root().querySelector('[data-buy-amount="0"]').value,'600');
  assert.equal(ctx.root().querySelector('[data-buy-amount="1"]').value,'300');
  assert.equal(ctx.root().querySelector('[data-draft=volume]').value,'10');
  assert.equal(ctx.root().querySelector('[data-draft=average]').value,'100');
  const average=1900/(10+600/1.0004/50+300/1.0004/40);
  assert.ok(Math.abs(Number(ctx.root().querySelector('[data-sell-price="0"]').value)-average*1.08)<1e-9);
  ctx.click('[data-strategy="bithumb|aggressive|v1"]');
  assert.equal(ctx.root().querySelector('[data-buy-amount="0"]').value,'555');
  ctx.click('[data-holding-comparison=compare]');await tick();
  assert.equal(ctx.root().querySelector('[data-period-experiment][aria-pressed=true]').dataset.periodExperiment,'bithumb|aggressive|v1');
  assert.equal(ctx.root().querySelector('[data-period-range][aria-pressed=true]').dataset.periodRange,'7d');
  assert.deepEqual(ctx.writes,[]);assert.ok(ctx.requests.every(r=>!r.options?.method||r.options.method==='GET'));
});
test('background period refresh keeps calculator focus, edits and expanded calculation',async()=>{
  ctx=setup();await tick();ctx.input('[data-draft=budget]','900');ctx.click('[data-action=import-holding-buy]');
  const field=ctx.input('[data-buy-amount="0"]','555');field.focus();
  ctx.root().querySelector('[data-continuity-key=calculation-stages]').open=true;
  clock+=21000;ctx.poll();await tick();
  assert.equal(ctx.root().querySelector('[data-buy-amount="0"]').value,'555');
  assert.equal(ctx.root().activeElement,ctx.root().querySelector('[data-buy-amount="0"]'));
  assert.equal(ctx.root().querySelector('[data-continuity-key=calculation-stages]').open,true);
  assert.equal(ctx.requests.filter(r=>r.u.pathname==='/api/strategy-period').length,2);
});
test('late same-ticker response cannot cross exchanges or change selected strategy',async()=>{
  ctx=setup({delay:true});await tick();ctx.click('[data-holding="upbit|KRW-B3|KRW"]');await tick();
  ctx.click('[data-strategy="upbit|balanced|v1"]');ctx.release();await tick();
  assert.match(ctx.root().querySelector('.holding-strategy-evidence').textContent,/실현손익 200원/);
  assert.equal(ctx.root().querySelector('[data-strategy][aria-selected=true]').dataset.strategy,'upbit|balanced|v1');
  ctx.click('[data-holding-comparison=compare]');await tick();ctx.click('[data-period-use]');
  assert.equal(ctx.root().querySelector('[data-draft=fee]').value,'0.05');assert.deepEqual(ctx.writes,[]);
});
test('read failure is bounded, keeps manual calculation and can retry without false zero performance',async()=>{
  ctx=setup({offline:true});await tick();for(let i=0;i<4;i++)ctx.page.render();await tick();
  assert.equal(ctx.requests.filter(r=>r.u.pathname==='/api/strategy-period').length,1);
  assert.match(ctx.root().querySelector('#holding-strategies').textContent,/기간 성과를 불러오지 못했습니다/);
  assert.doesNotMatch(ctx.root().querySelector('#holding-strategies').textContent,/99%|실현손익 0원/);
  ctx.input('[data-draft=budget]','900');ctx.click('[data-action=import-holding-buy]');
  ctx.click('[data-holding-comparison=compare]');await tick();ctx.online();ctx.click('[data-period-retry]');await tick();ctx.click('[data-period-use]');
  assert.equal(ctx.root().querySelector('[data-buy-amount="0"]').value,'600');
});
test('untrusted scope is hidden; native BTC holding retains KRW valuation without KRW strategy matching',async()=>{
  ctx=setup({mismatch:true});await tick();assert.match(ctx.root().querySelector('#holding-strategies').textContent,/불러오지 못했습니다/);ctx.close();
  ctx=setup({btc:true});await tick();assert.match(ctx.root().textContent,/4,000,000원/);assert.match(ctx.root().textContent,/8,000,000원/);
  assert.equal(ctx.root().querySelector('[data-holding-comparison]'),null);assert.equal(ctx.requests.length,0);
});
test('period rendering rejects wrong coin even if experiment IDs are shared across coins',()=>{
  ctx=setup();const h=holding(),a=account('bithumb','aggressive');
  const data=reviewFor(new URL('http://localhost/?exchange=bithumb&market=KRW-OTHER&period=30d'));
  const html=holdingStrategiesHtml([a],a.experiment_id,{holding:h,comparison:{data,selection:{period:'30d'}}});
  assert.doesNotMatch(html,/실현손익 10원|99%/);assert.match(html,/기간 성과 확인 필요/);
});
