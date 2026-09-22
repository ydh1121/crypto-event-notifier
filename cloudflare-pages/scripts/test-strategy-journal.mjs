import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {calculatePlan,importPlan,exactHolding,freshness,accountModel} from '../public/modules/shared/strategy-workbench-model.js';
import {replaceText} from '../public/modules/shared/mainstream-ui.js';
import {accountHtml,sourceHref} from '../public/modules/shared/strategy-workbench-view.js';
const dir=await mkdtemp(path.join(tmpdir(),'crypto-journal-'));
await build({entryPoints:[new URL('../functions/lib/strategy-journal.ts',import.meta.url).pathname],bundle:true,format:'esm',platform:'node',outfile:path.join(dir,'journal.mjs')});
const {journalPage,withoutJournalRows}=await import(pathToFileURL(path.join(dir,'journal.mjs')));
test.after(()=>rm(dir,{recursive:true,force:true}));
const lab={experiments:[{experiment_id:'bithumb|aggressive|v1',revision:'r1',cash_krw:10,journal:{total:125,complete:true,columns:['id','side'],rows:Array.from({length:125},(_,i)=>[i+1,i%2?'sell':'buy'])}}]};
test('complete journal pagination has no duplicates, loss, or other strategy fills',async()=>{
 const ids=[];let offset=0;
 while(offset!==null){const page=await journalPage(lab,'bithumb|aggressive|v1','r1',offset,30,()=>assert.fail());ids.push(...page.trades.map(t=>t.id));offset=page.next_offset;assert.equal(page.account.experiment_id,'bithumb|aggressive|v1');}
 assert.deepEqual(ids,Array.from({length:125},(_,i)=>125-i));assert.equal(new Set(ids).size,125);
});
test('polling revision changes cannot mix a new account with old journal pages',async()=>{
 await assert.rejects(journalPage(lab,'bithumb|aggressive|v1','old',30,30,()=>null),e=>e.code==='JOURNAL_CHANGED');
 await assert.rejects(journalPage(lab,'upbit|aggressive|v1','r1',0,30,()=>null),e=>e.code==='JOURNAL_UNAVAILABLE');
});
test('chunked pages cross boundaries with the same result as inline pages',async()=>{
 const split=structuredClone(lab),j=split.experiments[0].journal,rows=j.rows;delete j.rows;
 const keys=['a','b','c'].map(c=>'lab-journal:'+c.repeat(40));j.chunks=keys.map((strategy,i)=>({strategy,count:rows.slice(i*50,(i+1)*50).length}));
 const load=async key=>({kind:'strategy_lab_journal',experiment_id:'bithumb|aggressive|v1',columns:j.columns,rows:rows.slice(keys.indexOf(key)*50,(keys.indexOf(key)+1)*50)});
 const page=await journalPage(split,'bithumb|aggressive|v1','r1',20,100,load);
 assert.deepEqual(page.trades,(await journalPage(lab,'bithumb|aggressive|v1','r1',20,100,()=>null)).trades);
 await assert.rejects(journalPage(split,'bithumb|aggressive|v1','r1',0,30,()=>null),e=>e.code==='JOURNAL_INCOMPLETE');
 assert.equal(withoutJournalRows({strategy_lab:split}).strategy_lab.experiments[0].journal.rows,undefined);
});
test('fee-inclusive averaging and split sells conserve quantity and cash',()=>{
 const draft={volume:'10',average:'100',fee:'0.04',slippage:'0',buys:[{price:'80',amount:'800.32'}],sells:[{price:'120',weight:'30'},{price:'130',weight:'40'}]};
 const r=calculatePlan(draft);assert.equal(r.valid,true);assert.equal(r.afterBuyQuantity,20);assert.ok(Math.abs(r.average-90.016)<1e-10);assert.equal(r.remaining,6);
 assert.ok(Math.abs(r.net-(6*120+8*130)*.9996)<1e-9);assert.ok(Math.abs(r.realized-(r.net-14*r.average))<1e-9);assert.ok(Math.abs(r.fees-(.32+1760*.0004))<1e-9);
 draft.sells[1].weight='80';assert.equal(calculatePlan(draft).valid,false);draft.volume='';assert.equal(calculatePlan(draft).valid,false);
});
test('prior fees charged once; imported plan keeps paper assumptions',()=>{
 const a={volume:100,avg_price:10.004,plan:{fee_rate:.0004,slippage_rate:.0005,entries:[],exits:[{price:12,weight_pct:100}]}};
 const draft=importPlan(a),r=calculatePlan(draft);assert.equal(r.remaining,0);assert.equal(draft.fee,'0.04');assert.ok(Math.abs(r.realized-(100*12*.9995*.9996-100*10.004))<1e-8);
});
test('holding lookup never falls back to another exchange or quote',()=>{
 const rows=[{exchange:'upbit',market:'KRW-B3',volume:5},{exchange:'bithumb',market:'KRW-B3',quote_currency:'BTC',volume:10}];
 assert.equal(exactHolding(rows,'bithumb','KRW-B3'),null);assert.equal(exactHolding(rows,'upbit','KRW-B3').volume,5);
});
test('unknown/stale observations remain missing; scope and identifiers survive',()=>{
 assert.equal(freshness(null).stale,true);assert.equal(freshness(1,100000).stale,true);
 assert.equal(accountModel({exchange:'upbit',market:'KRW-B3'},'bithumb','KRW-B3','x'),null);
 const html=accountHtml({label:'DEXE',closed_trades:0,wins:0,win_rate_pct:null,volume:0});assert.ok(html.includes('완료 거래 없음'));assert.ok(html.includes('DEXE'));assert.ok(!html.includes('검증 30'));assert.equal(sourceHref('javascript:alert(1)'),'#');assert.equal(replaceText('DEXE KRW-DEXE'),'DEXE KRW-DEXE');assert.equal(replaceText('DEX 거래'),'분산형 거래소 거래');
});
