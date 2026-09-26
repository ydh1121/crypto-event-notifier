import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createHoldingRegistration} from '../public/modules/shared/holding-registration.js';
import {createHoldingsWorkbench} from '../public/modules/pages/holdings-workbench.js';
import {createHoldingRegistrationClient} from '../public/modules/services/holding-registration.js';

test('retry preserves request ID and inputs; changed payload gets a new identity',async()=>{
 const calls=[];let fail=true,added=0;
 const session=createHoldingRegistration({client:{async add(p){calls.push(p);if(fail)throw Error('연결 실패');return {holding_key:'saved'};}},changed:()=>{},onAdded:()=>added++});
 session.open('bithumb');await session.save();assert.equal(calls.length,0);
 for(const [key,value] of Object.entries({symbol:' xrp ',volume:'10',avg_price:'200'}))session.input(key,value);
 await session.save();assert.equal(session.state.form.volume,'10');assert.equal(session.state.open,true);
 await session.save();assert.equal(calls[0].request_id,calls[1].request_id);
 session.input('volume','20');fail=false;await session.save();
 assert.notEqual(calls[2].request_id,calls[1].request_id);assert.equal(added,1);
 assert.equal(calls[2].symbol,'XRP');assert.equal(session.state.open,false);
});

test('client obtains local token and posts only the explicit registration',async()=>{
 const old=globalThis.fetch,calls=[];
 globalThis.fetch=async(path,options)=>{calls.push([path,options]);return {ok:true,json:async()=>options.method?{holding_key:'saved'}:{csrf_token:'local-only'}};};
 try{
  const body={request_id:'same-retry-id',symbol:'XRP'};
  assert.equal((await createHoldingRegistrationClient().add(body)).holding_key,'saved');
  assert.equal(calls.length,2);assert.equal(calls[1][1].headers['X-Planning-Token'],'local-only');
  assert.deepEqual(JSON.parse(calls[1][1].body),body);
 }finally{globalThis.fetch=old;}
});

test('empty portfolio can add, polling preserves fields, saved holding becomes selected',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
 for(const name of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element','Document','DocumentFragment','Event'])globalThis[name]=dom.window[name];
 globalThis.CSS={escape:v=>String(v)};globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);window.scrollTo=()=>{};
 const holdings={status:'read',holdings:[],holding_count:0,closed_count:0,confirmed_exchange:'bithumb',holding_registration_enabled:true};
 const state={snapshot:{local_holdings:holdings}},listeners=new Set(),store={get:()=>state,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn);}};
 const added={key:'bithumb|KRW-XRP|KRW',exchange:'bithumb',market:'KRW-XRP',symbol:'XRP',quote_currency:'KRW',volume:3,avg_price:100,valid:true,closed:false};
 let calls=0,resolve;
 const registrationClient={add:async()=>{calls++;return new Promise(r=>resolve=r);}};
 const page=createHoldingsWorkbench({store,registrationClient,onHoldingsChanged:value=>{state.snapshot.local_holdings=value;}});
 page.mount(document.getElementById('root'));const view=document.querySelector('crypto-holdings-workbench').shadowRoot;
 const flush=()=>new Promise(r=>setTimeout(r,10));
 view.querySelector('[data-action="open-holding-add"]').click();
 assert.equal(view.querySelector('[data-add-holding="exchange"]').value,'bithumb');
 assert.equal(view.querySelector('[data-add-holding="exchange"]').disabled,true);
 function input(name,value){const f=view.querySelector(`[data-add-holding="${name}"]`);f.value=value;f.dispatchEvent(new Event('input',{bubbles:true}));}
 input('symbol','XRP');input('volume','3');input('avg_price','100');
 for(const notify of listeners)notify(state,{type:'snapshot-live'});
 assert.equal(view.querySelector('[data-add-holding="symbol"]').value,'XRP');
 assert.equal(view.querySelector('[data-add-holding="avg_price"]').value,'100');
 input('quote_currency','BTC');assert.match(view.querySelector('[data-add-holding="avg_price"]').parentElement.textContent,/BTC/);
 input('quote_currency','KRW');
 const submit=()=>view.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
 submit();submit();assert.equal(calls,1);assert.equal(view.querySelector('fieldset').disabled,true);
 resolve({holding_key:added.key,holdings:{...holdings,holding_count:1,holdings:[added]}});await flush();
 assert.equal(view.querySelector(`[data-holding="${added.key}"]`).getAttribute('aria-pressed'),'true');
 assert.match(view.getElementById('holding-detail').textContent,/XRP/);
 assert.equal(view.querySelector('form'),null);
 page.destroy();dom.window.close();
});
