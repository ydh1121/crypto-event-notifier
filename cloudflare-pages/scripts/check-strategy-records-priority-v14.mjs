import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const strategy=read('public/modules/pages/strategy.js');
const records=read('public/modules/pages/records.js');
const strategyCss=read('public/modules/styles/strategy-native-v5.css');
const recordsCss=read('public/modules/styles/records-system.css');
const audienceCss=read('public/modules/styles/records-audience.css');
const priorityCss=read('public/modules/styles/content-priority.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('current build marker exists',/meta name="crypto-viewer-build" content="[^"]+"/.test(index));
check('strategy stylesheet remains cache-versioned',/\/modules\/styles\/strategy-native-v5\.css\?v=[^'\"]+/.test(index));
check('records stylesheet remains cache-versioned',/\/modules\/styles\/records-system\.css\?v=[^'\"]+/.test(index));
check('records audience stylesheet remains cache-versioned',/\/modules\/styles\/records-audience\.css\?v=[^'\"]+/.test(index));
check('content priority stylesheet remains cache-versioned',/\/modules\/styles\/content-priority\.css\?v=[^'\"]+/.test(index));

check('strategy keeps experiment-specific trade evidence',strategy.includes('strategyTradeRows(store.get(),r.experiment_id)')&&strategy.includes('가상매매 내역'));
check('strategy primary summary keeps return before supporting evidence',strategy.includes('<small>전체 수익률</small>')&&strategy.indexOf('<small>전체 수익률</small>')<strategy.indexOf('<small>최대 하락폭</small>'));
check('strategy V14 hierarchy rules exist',strategyCss.includes('V14 strategy hierarchy')&&strategyCss.includes('grid-template-columns:repeat(10,minmax(0,1fr))!important'));
check('strategy return is visually dominant',strategyCss.includes('strategy-detail-kpis>span:first-child b{font-size:32px!important}'));
check('strategy drawdown is promoted as primary risk fact',strategyCss.includes('strategy-detail-kpis>span:nth-child(3) b{font-size:22px!important}'));
check('simple strategy rail suppresses descriptive noise',strategyCss.includes('html[data-reader-mode="simple"] #pageRoot[data-page-route="strategy"] .strategy-v5-item-copy small{display:none!important}'));

check('records still render chronological feed',records.includes('data-records-feed')&&records.includes('.sort((a,b)=>n(b.ts)-n(a.ts))'));
check('records retain user/system audience separation',records.includes('data-records-scope="user"')&&records.includes('data-records-scope="system"'));
check('records V14 hierarchy rules exist',recordsCss.includes('V14 records hierarchy')&&recordsCss.includes('grid-template-columns:minmax(0,1fr) minmax(280px,320px)!important'));
check('latest record is visually emphasized',recordsCss.includes('.record-item:first-child')&&recordsCss.includes('border-left:3px solid var(--accent)!important'));
check('records counters are compact support strip',recordsCss.includes('.records-kpis>.kpi')&&recordsCss.includes('background:transparent!important'));
check('records insight stays visible beside long feed on desktop',recordsCss.includes('.records-insight')&&recordsCss.includes('position:sticky!important'));
check('records audience switch is flat navigation',audienceCss.includes('V14 audience switch')&&audienceCss.includes('border-bottom:2px solid transparent!important')&&audienceCss.includes('background:transparent!important'));

check('legacy asset order rules are gone from content priority layer',!priorityCss.includes('#pageRoot[data-page-route="assets"]>.asset-kpis{order:')&&!priorityCss.includes('#pageRoot[data-page-route="assets"]>.asset-workspace{order:')&&!priorityCss.includes('#pageRoot[data-page-route="assets"]>.asset-history-panel{\n  order:'));
check('legacy asset order rules remain gone from canonical interaction layer',!interaction.includes('>.asset-workspace{order:2')&&!interaction.includes('>.asset-history-panel{order:3'));

if(fail.length){console.error('STRATEGY_RECORDS_PRIORITY_V14=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('STRATEGY_RECORDS_PRIORITY_V14=PASS');
