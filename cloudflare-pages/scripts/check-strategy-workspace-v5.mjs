import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const strategy=read('public/modules/pages/strategy.js');
const selectors=read('public/modules/shared/selectors.js');
const css=read('public/modules/styles/strategy-native-v5.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('native strategy stylesheet is loaded',index.includes('/modules/styles/strategy-native-v5.css?v=1'));
check('native strategy stylesheet loads before canonical interaction layer',index.indexOf('strategy-native-v5.css')<index.indexOf('interaction-layout-v4.css'));
check('temporary strategy DOM patch is not loaded',!index.includes('strategy-workspace-v5.js'));
check('main cache version is refreshed',index.includes('/modules/main.js?v=95'));
check('strategy module cache version is refreshed',main.includes("./pages/strategy.js?v=48"));
check('overview renders native master detail workspace',strategy.includes('data-strategy-workspace-v5="ready"')&&strategy.includes('strategy-v5-detail-shell'));
check('four local strategy evidence tabs exist',['summary','coins','trades','evidence'].every(value=>strategy.includes(`item('${value}'`)));
check('strategy rail is rendered as navigation items',strategy.includes('strategy-v5-strategy-item')&&strategy.includes('aria-current'));
check('strategy selection updates detail without rerendering whole overview',strategy.includes('setSelectedRailItem(key(chosen))')&&strategy.includes('renderOverviewDetails(chosen,criteria)'));
check('strategy uses document scroll instead of rail scroll restoration',!strategy.includes('overviewRailScroll')&&!strategy.includes('captureDetailScroll'));
check('deep tab promotes simple mode to detail',strategy.includes("[data-reader-mode=\"detail\"]")&&strategy.includes("value!=='summary'&&readerMode()==='simple'"));
check('mobile has explicit strategy list return',strategy.includes('data-strategy-v5-back')&&css.includes('.strategy-v5-back'));
check('strategy trade selector exists',selectors.includes('strategyTradeRows')&&selectors.includes('strategy_trades'));
check('strategy trade panel has explicit missing-data state',strategy.includes('체결 원장이 아직 Snapshot에 제공되지 않습니다'));
check('canonical workspace uses shared rail width',interaction.includes('grid-template-columns:minmax(280px,300px) minmax(0,1fr)!important'));
check('canonical layer removes nested detail viewport',interaction.includes('.strategy-v5-detail-panels')&&interaction.includes('overflow-y:visible!important'));
check('canonical layer removes sticky strategy detail shell',interaction.includes('.strategy-v5-detail-shell')&&interaction.includes('position:static!important'));
check('trade ledger allows horizontal table overflow only',interaction.includes('.strategy-trade-table')&&interaction.includes('overflow-x:auto'));
check('user-facing strategy copy removes Adaptive label',!strategy.includes('Adaptive'));

if(fail.length){console.error('STRATEGY_WORKSPACE_V5=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('STRATEGY_WORKSPACE_V5=PASS');
