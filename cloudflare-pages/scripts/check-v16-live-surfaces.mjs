import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const store=read('public/modules/core/store.js');
const patch=read('public/modules/shared/live-patch-remaining-v16.js');
const compact=read('public/modules/styles/compact-v16.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V16A3 build marker exists',index.includes('2026.09.17-v6.2.0-v16-live-surfaces'));
check('main entry is refreshed',index.includes('/modules/main.js?v=96.6'));
check('compact layer is refreshed',index.includes('/modules/styles/compact-v16.css?v=3'));
check('remaining live patch is installed',main.includes("./shared/live-patch-remaining-v16.js?v=1")&&main.includes('installRemainingLivePatchV16({store,root})'));
check('research records system use live snapshot channel',['research','records','system'].every(route=>store.includes(`'${route}'`)));
check('research list is reconciled without page replacement',patch.includes('function patchResearch')&&patch.includes('createResearchRow')&&patch.includes('[data-research-market')&&!patch.includes('root.innerHTML='));
check('research live quotes keep D1 hydration',patch.includes('getMarketQuotes')&&patch.includes('refreshResearchQuotes'));
check('records feed is reconciled by stable keys',patch.includes('function patchRecords')&&patch.includes('recordKey')&&patch.includes('[data-record-key]')&&patch.includes('feed.prepend(node)'));
check('system telemetry is patched in place',patch.includes('function patchSystem')&&patch.includes('patchCard(cards[0]')&&patch.includes("setByLabel(list,'Supervisor'"));
check('remaining patch does not replace whole page',!patch.includes('root.innerHTML='));
check('remaining new rows use insertion motion',patch.includes('enter(node)'));
check('dashboard and system explanatory prose is suppressed',compact.includes('.pulse-guide')&&compact.includes('.operation-card>p')&&compact.includes('.strategy-validity>p'));
check('sector methodology prose is suppressed while business profile remains',compact.includes('.sector-method')&&!compact.includes('.coin-profile-business p'));

if(fail.length){console.error('V16_LIVE_SURFACES=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V16_LIVE_SURFACES=PASS');
