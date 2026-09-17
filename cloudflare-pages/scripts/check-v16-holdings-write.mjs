import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html'),main=read('public/modules/main.js'),ui=read('public/modules/shared/holdings-write-v16.js'),fees=read('public/modules/shared/trading-fees-v16.js'),service=read('public/modules/services/holding-mutations-v16.js'),ownerApi=read('functions/api/holding-mutations.ts'),runtimeApi=read('functions/api/holding-mutations-runtime.ts'),migration=read('migrations/0007_holding_mutations.sql');
const consumer=fs.readFileSync(new URL('../../b3_trader/holding_mutation_consumer.py',import.meta.url),'utf8');
const checks=[
 ['V16B build marker',/crypto-viewer-build" content="[^"]*v16b-holdings-write/.test(index)],
 ['holdings write stylesheet',/holdings-write-v16\.css\?v=1/.test(index)],
 ['main cache refreshed',/main\.js\?v=96\.7/.test(index)],
 ['holdings writer imported',/holdings-write-v16\.js\?v=1/.test(main)],
 ['holdings writer installed',/installHoldingsWriteV16\(\{store,root\}\)/.test(main)],
 ['Bithumb fixed fee',fees.includes('bithumb:0.0004')&&ownerApi.includes('bithumb: 0.0004')&&consumer.includes('"bithumb": 0.0004')],
 ['Upbit fixed fee',fees.includes('upbit:0.0005')&&ownerApi.includes('upbit: 0.0005')&&consumer.includes('"upbit": 0.0005')],
 ['owner only mutation',ownerApi.includes('requireOwner(env, request)')],
 ['client fee ignored',ownerApi.includes('Client fee fields are intentionally ignored')],
 ['idempotency queue',migration.includes('idempotency_key TEXT NOT NULL UNIQUE')&&service.includes('idempotency_key')&&ownerApi.includes('IDEMPOTENCY_CONFLICT')],
 ['local receipt makes ACK retry idempotent',consumer.includes('holding_mutation_receipts')&&consumer.includes('SELECT result_json FROM holding_mutation_receipts')&&consumer.includes('INSERT INTO holding_mutation_receipts')],
 ['optimistic revision is mandatory',migration.includes('expected_revision REAL NOT NULL')&&ownerApi.includes('expectedRevision <= 0')&&consumer.includes('REVISION_CONFLICT')],
 ['queue status lifecycle',migration.includes("'pending','claimed','applied','rejected'")],
 ['trusted runtime auth',runtimeApi.includes('bearer(request) === env.INGEST_TOKEN')],
 ['stale claim recovery',runtimeApi.includes("status='claimed'")&&runtimeApi.includes('now - 120')],
 ['claim compare-and-set is checked',runtimeApi.includes('claim.meta.changes')&&runtimeApi.includes('Another trusted consumer won')],
 ['migration is explicit',migration.includes('CREATE TABLE IF NOT EXISTS holding_mutations')&&!ownerApi.includes('CREATE TABLE')&&!runtimeApi.includes('CREATE TABLE')],
 ['canonical local sqlite update',consumer.includes('UPDATE manual_holdings SET volume=?,avg_price=?,updated_ts=?')],
 ['current exchange preserved',consumer.includes('EXCHANGE_CONFLICT')&&ui.includes('const holdingExchange=holding=>')&&!ui.includes("holding.exchange||'bithumb'")],
 ['selected averaging rounds',ui.includes('data-avg-actual-apply')&&ui.includes('data-apply-selected-rounds')&&consumer.includes('apply_averaging')],
 ['actual holding edit',ui.includes('data-holding-edit-volume')&&ui.includes('data-holding-edit-avg')&&ui.includes('data-save-holding')],
 ['take profit target',ui.includes('data-take-profit-price')],
 ['take profit recalculates after edit',ui.includes("event.target.matches('[data-take-profit-price]')")&&ui.includes('setTimeout(rerender,0)')],
 ['calculator row replacement restores controls',ui.includes("[data-add-avg-row],[data-add-recommended-row],[data-reset-avg],[data-remove-avg]")],
 ['scenario values',ui.includes('시나리오 총 수수료')&&ui.includes('최종 수령액')&&ui.includes('순수익률')],
 ['canonical confirmation gate',ui.includes('DB 적용됨 · 스냅샷 확인중')&&ui.includes("?'적용됨':")],
 ['consumer not auto-started from frontend',!main.includes('holding_mutation_consumer')],
];
const failed=checks.filter(([,ok])=>!ok);if(failed.length){console.error('V16_HOLDINGS_WRITE=FAIL');for(const[name]of failed)console.error(`- ${name}`);process.exit(1)}console.log('V16_HOLDINGS_WRITE=PASS');
