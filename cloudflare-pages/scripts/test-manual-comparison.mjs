import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {manualComparisonHtml} from '../public/modules/shared/manual-comparison-view.js';
import {manualRecordsHtml} from '../public/modules/shared/holding-records-view.js';
import {updateHtml} from '../public/modules/shared/dom-patch.js';

const totals=()=>({closed:2,wins:1,open:1,invested_krw:3004,proceeds_krw:3067,realized_pnl_krw:63,return_pct:63/3004*100,mean_return_pct:8.1,worst_return_pct:-10,fees_krw:7});
const comparison=()=>({version:2,status:'ok',start:1791247000,end:1791247900,manual:totals(),paper:totals(),paper_carried_positions:1,witnesses_limit:20,
 manual_witnesses:[{entry_trade_id:'one',entry_ts:1791247000,exit_ts:1791247800,invested_krw:1004,proceeds_krw:1267,realized_pnl_krw:263}],paper_witnesses:[]});

test('completed cash amounts and weighted return stay legible while refresh retains detail DOM',()=>{
 const dom=new JSDOM('<main></main>');
 for(const name of ['window','document','Node','Element','HTMLElement','HTMLInputElement','HTMLTextAreaElement'])globalThis[name]=dom.window[name];
 const root=document.querySelector('main'),c=comparison();updateHtml(root,manualComparisonHtml(c,'공격적'));
 const table=root.querySelector('table');assert.equal(table.tHead.rows[0].cells.length,3);
 assert.match(table.textContent,/3,004원/);assert.match(table.textContent,/3,067원/);
 assert.match(table.textContent,/2.1%/);assert.doesNotMatch(table.textContent,/8.1%/);
 const detail=root.querySelector('details');detail.open=true;
 const amount=root.querySelector('[data-render-key="comparison-2"]');
 c.manual.realized_pnl_krw=64;updateHtml(root,manualComparisonHtml(c,'공격적'));
 assert.equal(root.querySelector('details'),detail);assert.equal(detail.open,true);
 assert.equal(root.querySelector('[data-render-key="comparison-2"]'),amount);
 assert.match(amount.textContent,/64원/);assert.match(root.textContent,/기간 전에 시작한 가상 매매 1회 제외/);
 dom.window.close();
});

test('no completed samples, unavailable PAPER and genuine zero results remain distinct',()=>{
 const c=comparison();c.paper=null;c.status='paper_incomplete';
 c.manual={...totals(),closed:0,wins:null,return_pct:null,invested_krw:null,proceeds_krw:null,realized_pnl_krw:null};
 let html=manualComparisonHtml(c);assert.match(html,/원장을 모두 읽지 못했습니다/);
 assert.match(html,/완료 0회/);assert.doesNotMatch(html,/>0%<|>0원</);
 c.paper=totals();c.status='ok';c.manual={...totals(),return_pct:0,realized_pnl_krw:0};
 html=manualComparisonHtml(c,'<script>');assert.match(html,/>0%<|>0원</);assert.doesNotMatch(html,/<script>/);
 assert.match(manualComparisonHtml({start:null}),/체결을 기록하면/);
});

test('individual execution distinguishes gross amount, paid fees and net cash',()=>{
 const trade={id:'one',ts:1791247000,side:'buy',price:'100',volume:'10',fee:'4',gross_krw:1000,net:1004,realized:null};
 const html=manualRecordsHtml({data:{plan:{draft:{buys:[],sells:[]},paper:{label:'공격적'}},records:[trade],summary:{trades:[trade],fees:4},comparison:comparison()},form:{side:'buy'}});
 assert.match(html,/체결 금액 \/ 수수료/);assert.match(html,/지급·수령액/);
 assert.match(html,/1,000원/);assert.match(html,/수수료 4원/);assert.match(html,/1,004원/);
});
