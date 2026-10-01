import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createHoldingsWorkbench} from '../public/modules/pages/holdings-workbench.js';
import {createHoldingManagement} from '../public/modules/shared/holding-management-session.js';
import {createHoldingManagementClient} from '../public/modules/services/holding-management.js';
const h={key:'bithumb|KRW-B3|KRW',exchange:'bithumb',market:'KRW-B3',quote_currency:'KRW',symbol:'B3',volume:10,avg_price:.8,valid:true,closed:false,management_available:true};
const current={current:{volume:10,avg_price:.8},revision:'a'.repeat(64),history:[],has_more:false};
const preview={before:{volume:10,avg_price:.8},after:{volume:0,avg_price:0},realized_quote:1.9};
const flush=()=>new Promise(r=>setTimeout(r,15));

test('preview cannot apply; failed apply retries same ID; editing invalidates preview',async()=>{
 let failed=true,saved=0;const calls=[];
 const s=createHoldingManagement({changed:()=>{},onSaved:()=>saved++,client:{read:async()=>current,change:async(p,mode)=>{
  calls.push({p,mode});if(mode==='apply'&&failed)throw Error('연결 실패');return {result:preview,holdings:{}};
 }}});
 s.open(h,'sell');await flush();s.input(h,'price','1');s.input(h,'fee','.1');s.all(h);
 await s.preview(h);assert.equal(saved,0);assert.equal(calls[0].mode,'preview');
 await s.apply(h);assert.match(s.get(h.key).error,/연결/);assert.equal(s.get(h.key).form.volume,'10');
 failed=false;await s.apply(h);assert.equal(saved,1);assert.equal(calls[1].p.request_id,calls[2].p.request_id);
 s.open(h,'buy');await flush();await s.preview(h);s.input(h,'volume','3');
 assert.equal(s.get(h.key).preview,null);const n=calls.length;await s.apply(h);assert.equal(calls.length,n);s.destroy();
});

test('local client sends token, exact identity, revision and separate preview/apply',async()=>{
 const old=globalThis.fetch,calls=[];
 globalThis.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>options.method?{result:preview}:{...current,csrf_token:'token'}};};
 try {
  const client=createHoldingManagementClient(),p={...h,request_id:'one',expected_revision:current.revision};
  await client.read(h);await client.change(p,'preview');await client.change(p,'apply');
  assert.match(calls[0].path,/exchange=bithumb&market=KRW-B3&quote_currency=KRW/);
  assert.equal(calls[1].options.headers['X-Planning-Token'],'token');assert.deepEqual(JSON.parse(calls[2].options.body),{...p,mode:'apply'});
 }finally{globalThis.fetch=old;}
});

test('full sell form, duplicate-click guard, polling continuity and archived BTC rebuy',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
 for(const name of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element','Document','DocumentFragment','Event'])globalThis[name]=dom.window[name];
 globalThis.CSS={escape:v=>String(v)};globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);window.scrollTo=()=>{};
 const btc={...h,key:'bithumb|KRW-ETH/BTC|BTC',market:'KRW-ETH/BTC',quote_currency:'BTC',symbol:'ETH',volume:0,avg_price:0,closed:true};
 const initial={status:'read',holdings:[h,btc],holding_count:1,closed_count:1,confirmed_exchange:'bithumb',holding_management_enabled:true};
 const state={snapshot:{local_holdings:initial}},listeners=new Set(),store={get:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);}};
 let resolve;const calls=[];
 const managementClient={read:async(p)=>p.market===btc.market?{...current,current:{volume:0,avg_price:0}}:current,change:async(p,mode)=>{
  calls.push({p,mode});if(mode==='preview')return {result:preview};return new Promise(r=>resolve=r);
 }};
 const page=createHoldingsWorkbench({store,managementClient,onHoldingsChanged:v=>{state.snapshot.local_holdings=v;}});
 page.mount(document.getElementById('root'));const view=document.querySelector('crypto-holdings-workbench').shadowRoot;
 const click=sel=>view.querySelector(sel).click();
 const input=(name,value)=>{const f=view.querySelector(`[data-manage-field="${name}"]`);f.value=value;f.dispatchEvent(new Event('input',{bubbles:true}));assert.equal(view.querySelector(`[data-manage-field="${name}"]`),f,'editing retains the live input node');};
 click('[data-manage-open="sell"]');await flush();input('price','1');input('fee','.1');click('[data-manage-action="all"]');
 for(const notify of listeners)notify(state,{type:'snapshot-live'});
 assert.equal(view.querySelector('[data-manage-field="volume"]').value,'10');assert.equal(view.querySelector('[data-manage-field="price"]').value,'1');
 const submit=()=>view.querySelector('#holding-manage-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
 submit();await flush();assert.equal(calls.length,1);assert.equal(calls[0].mode,'preview');assert.match(view.querySelector('.holding-change-preview').textContent,/10 → 0/);
 click('[data-manage-action="apply"]');click('[data-manage-action="apply"]');assert.equal(calls.length,2);
 resolve({result:preview,holdings:{...initial,holding_count:0,closed_count:2,holdings:[{...h,volume:0,avg_price:0,closed:true},btc]}});await flush();
 assert.equal(view.querySelector('#holding-manage-form'),null);assert.match(view.getElementById('holdings-list').textContent,/보유 종료 2개/);
 click(`[data-holding="${btc.key}"]`);click('[data-manage-open="buy"]');await flush();assert.match(view.querySelector('#holding-manage-form').textContent,/수수료 · BTC/);
 assert.match(view.querySelector('.holding-manage-editor').textContent,/다시 매수/);
 input('price','.03');input('volume','1');input('fee','0');submit();await flush();
 assert.equal(calls.at(-1).p.market,'KRW-ETH/BTC');assert.equal(calls.at(-1).p.quote_currency,'BTC');page.destroy();dom.window.close();
});
