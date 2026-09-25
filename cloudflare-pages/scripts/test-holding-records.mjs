import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {createHoldingRecordsSession,koreanTimestamp} from '../public/modules/shared/holding-records-session.js';
import {createManualPlanningClient} from '../public/modules/services/manual-planning.js';
import {createHoldingsWorkbench} from '../public/modules/pages/holdings-workbench.js';

const flush=()=>new Promise(r=>setTimeout(r,20));
const scope={exchange:'bithumb',market:'KRW-B3',experiment:'bithumb|aggressive|v1'};
const draft=()=>({volume:'10',average:'100',fee:'0.04',slippage:'0',budget:'900',holdingRevision:'1|10|100',origin:'manual',buys:[{price:'80',amount:'800'}],sells:[{price:'120',weight:'100'}]});
const empty=()=>({plan:null,plan_revision:0,ledger_revision:0,records:[],summary:{volume:0,average:null,realized:0,fees:0,trades:[]},comparison:{start:null,end:null,manual:{closed:0,wins:0,mean_return_pct:null},paper:null}});
const saved=(value=draft(),revision=1)=>({...empty(),plan_revision:revision,plan:{revision,saved_at:Date.now()/1000,draft:value,paper:{label:'공격적'}}});

test('late restore never overwrites edits and explicit reload restores the saved version',async()=>{
 let finish;const restored=[];
 const session=createHoldingRecordsSession({client:{read:()=>new Promise(r=>finish=r)},restore:(...x)=>restored.push(x),changed:()=>{}});
 session.ensure('a',scope);session.edit('a');finish(saved());await flush();
 assert.equal(restored.length,0);assert.equal(session.get('a').dirty,true);
 const loading=session.read('a',true);finish(saved());await loading;
 assert.equal(restored[0][1].buys[0].amount,'800');assert.equal(session.get('a').dirty,false);
 session.destroy();
});
test('retry reuses the operation id and edits during save remain dirty',async()=>{
 const calls=[];let fail=true,finish;
 const session=createHoldingRecordsSession({client:{read:async()=>empty(),write:async(...args)=>{
  calls.push(args);if(fail)throw Error('offline');return new Promise(r=>finish=r);
 }},restore:()=>{},changed:()=>{}});
 session.ensure('a',scope);await flush();session.edit('a');
 await session.write('a','save',draft());assert.equal(session.get('a').error,'offline');
 fail=false;const saving=session.write('a','save',draft());await flush();session.edit('a');finish(saved());await saving;
 assert.equal(calls[0][2].request_id,calls[1][2].request_id);assert.equal(session.get('a').dirty,true);
 session.destroy();
});
test('manual execution carries exact saved plan version and explicit Korean timestamp',async()=>{
 const calls=[];const session=createHoldingRecordsSession({client:{read:async()=>saved(draft(),4),write:async(...args)=>{calls.push(args);return saved(draft(),4);}},restore:()=>{},changed:()=>{}});
 session.ensure('a',scope);await flush();
 for(const [k,v] of Object.entries({side:'buy',ts:'2026-09-25T17:00:00',price:'100',volume:'2',fee:'0',stage:'buy:0'}))session.input('a',k,v);
 await session.write('a','fill');
 assert.deepEqual(calls[0][0],scope);assert.equal(calls[0][2].plan_revision,4);
 assert.equal(calls[0][2].fill.ts,Date.parse('2026-09-25T08:00:00Z')/1000);
 assert.equal(calls[0][2].fill.fee,'0');assert.equal(session.get('a').form.price,'');
 assert.equal(koreanTimestamp(''),null);session.destroy();
});
test('service sends JSON and server token only to the local planning route',async()=>{
 const original=globalThis.fetch,requests=[];
 globalThis.fetch=async(...args)=>{requests.push(args);return {ok:true,json:async()=>({...empty(),csrf_token:'local-token'})};};
 try{const client=createManualPlanningClient();await client.read(scope);await client.write(scope,'save',{expected_revision:0,draft:draft(),request_id:'id'});
 assert.match(requests[0][0],/^\/api\/manual-planning\?/);
 assert.equal(requests[1][1].headers['X-Planning-Token'],'local-token');
 assert.equal(JSON.parse(requests[1][1].body).experiment,scope.experiment);
 }finally{globalThis.fetch=original;}
});

test('workbench saves and restores on remount, scopes plans, retains changed holdings and manual inputs',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'http://127.0.0.1:8766/',pretendToBeVisual:true});
 for(const name of ['window','document','HTMLElement','HTMLInputElement','HTMLTextAreaElement','Node','Element','Document','DocumentFragment','Event'])globalThis[name]=dom.window[name];
 globalThis.CSS={escape:v=>String(v)};globalThis.requestAnimationFrame=fn=>setTimeout(fn,0);window.scrollTo=()=>{};
 const holdings=['bithumb','upbit'].map(exchange=>({key:`${exchange}|KRW-B3|KRW`,exchange,market:'KRW-B3',quote_currency:'KRW',symbol:'B3',volume:10,avg_price:100,updated_ts:1,planning_available:true,valid:true,closed:false,current_price:120,price_ts:Date.now()/1000}));
 const data={status:'read',planning_enabled:true,holdings,holding_count:2};
 const listeners=new Set(),store={get:()=>({snapshot:{local_holdings:data}}),subscribe:f=>{listeners.add(f);return()=>listeners.delete(f);}};
 const memory=new Map(),calls=[];let fail=false;
 const client={read:async s=>structuredClone(memory.get(JSON.stringify(s))||empty()),write:async(s,action,p)=>{
   calls.push({s,action,p});if(fail)throw Error('다른 창에서 기록이 바뀌었습니다.');
   const next=action==='save'?saved(p.draft,p.expected_revision+1):memory.get(JSON.stringify(s));
   memory.set(JSON.stringify(s),structuredClone(next));return structuredClone(next);
 }};
 globalThis.fetch=async path=>{const p=new URL(path,'http://127.0.0.1:8766').searchParams,exchange=p.get('exchange'),market=p.get('market');return {ok:true,json:async()=>({detail:{exchange,market,data:{strategy_lab:{version:2,exchange,market,experiments:[{experiment_id:`${exchange}|aggressive|v1`,label:'공격적',style:'aggressive',return_pct:3,reconciliation:{matches:true},plan:{available:true,source_ts:Date.now()/1000,rules:{take_profit_pct:14},entries:[]}}]}}}})};};
 let page;const mount=()=>{page=createHoldingsWorkbench({store,manualClient:client});page.mount(document.getElementById('root'));};
 const shadow=()=>document.getElementById('root').firstElementChild.shadowRoot;
 const click=selector=>{const node=shadow().querySelector(selector);assert.ok(node,selector);node.click();};
 const input=(selector,value)=>{const node=shadow().querySelector(selector);assert.ok(node,selector);node.value=value;node.dispatchEvent(new Event('input',{bubbles:true}));return node;};
 try{
   mount();await flush();await flush();
   input('[data-draft="budget"]','1234');click('[data-action="add-sell"]');input('[data-sell-price="0"]','120');input('[data-sell-weight="0"]','100');
   click('[data-action="save-holding-plan"]');await flush();assert.match(shadow().querySelector('#holding-save-state').textContent,/저장됨/);
   page.destroy();holdings[0]={...holdings[0],volume:20,updated_ts:2};mount();await flush();await flush();
   assert.equal(shadow().querySelector('[data-draft="budget"]').value,'1234');assert.equal(shadow().querySelector('[data-draft="volume"]').value,'10');
   assert.match(shadow().textContent,/보유정보가 갱신/);
   click('[data-holding="upbit|KRW-B3|KRW"]');await flush();await flush();assert.equal(shadow().querySelector('[data-draft="budget"]').value,'');
   click('[data-holding="bithumb|KRW-B3|KRW"]');await flush();click('[data-holding-panel="records"]');
   input('[data-record-field="price"]','125');const q=input('[data-record-field="volume"]','2');q.focus();input('[data-record-field="fee"]','0');
   for(const f of listeners)f(null,{type:'snapshot-live'});await flush();
   assert.equal(shadow().querySelector('[data-record-field="price"]').value,'125');
   fail=true;click('[data-action="record-manual-fill"]');await flush();
   assert.match(shadow().textContent,/다른 창에서 기록/);assert.equal(shadow().querySelector('[data-record-field="volume"]').value,'2');
   assert.equal(calls.at(-1).p.plan_revision,1);assert.equal(calls.at(-1).s.exchange,'bithumb');
   holdings[0]={...holdings[0],volume:0,closed:true,planning_available:false,recording_available:true};data.closed_count=1;
   for(const f of listeners)f(null,{type:'snapshot-live'});await flush();
   assert.equal(shadow().querySelector('#holding-records').hidden,false);
   assert.match(shadow().querySelector('#holdings-list').textContent,/매도 완료 1개/);
   assert.equal(shadow().querySelector('[data-action="save-holding-plan"]'),null);
   input('[data-record-field="price"]','126');assert.equal(shadow().querySelector('[data-record-field="price"]').value,'126');
   click('[data-holding="upbit|KRW-B3|KRW"]');await flush();
   click('[data-holding="bithumb|KRW-B3|KRW"]');await flush();
   assert.equal(shadow().querySelector('#holding-records').hidden,false);
   assert.equal(shadow().querySelector('[data-record-field="price"]').value,'126');
   page.destroy();data.holdings=[holdings[0]];mount();await flush();await flush();
   assert.equal(shadow().querySelector('#holding-records').hidden,false);
   assert.match(shadow().querySelector('#holding-save-state').textContent,/저장됨/);
 }finally{page?.destroy();dom.window.close();}
});
