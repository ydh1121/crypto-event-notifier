import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const strategy=read('public/modules/pages/strategy.js');
const css=read('public/modules/styles/strategy-native-v5.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('native strategy stylesheet is loaded',index.includes('/modules/styles/strategy-native-v5.css?v=1'));
check('native strategy stylesheet loads after interaction layout',index.indexOf('interaction-layout-v4.css')<index.indexOf('strategy-native-v5.css'));
check('temporary strategy DOM patch is not loaded',!index.includes('strategy-workspace-v5.js'));
check('main cache version is refreshed',index.includes('/modules/main.js?v=91'));
check('strategy module cache version is refreshed',main.includes("./pages/strategy.js?v=47"));
check('overview renders native master detail workspace',strategy.includes('data-strategy-workspace-v5="ready"')&&strategy.includes('strategy-v5-detail-shell'));
check('three local strategy detail tabs exist',['summary','coins','evidence'].every(value=>strategy.includes(`item('${value}'`)));
check('strategy rail is rendered as navigation items',strategy.includes('strategy-v5-strategy-item')&&strategy.includes('aria-current'));
check('strategy selection updates detail without rerendering whole overview',strategy.includes('setSelectedRailItem(key(chosen))')&&strategy.includes('renderOverviewDetails(chosen,criteria)'));
check('strategy rail scroll is preserved',strategy.includes('overviewRailScroll')&&strategy.includes('list.scrollTop=overviewRailScroll'));
check('detail tab scroll contexts are preserved',strategy.includes('detailScroll')&&strategy.includes('captureDetailScroll')&&strategy.includes('restoreDetailScroll'));
check('deep tab promotes simple mode to detail',strategy.includes("[data-reader-mode=\"detail\"]")&&strategy.includes("value!=='summary'&&readerMode()==='simple'"));
check('mobile has explicit strategy list return',strategy.includes('data-strategy-v5-back')&&css.includes('.strategy-v5-back'));
check('overview is master detail, not wide strategy table',css.includes('grid-template-columns:minmax(258px,286px) minmax(0,1fr)!important'));
check('strategy rail suppresses legacy pseudo-table labels',css.includes('.strategy-v5-strategy-item>span::before')&&css.includes('content:none!important'));
check('selected strategy has clear active rail',css.includes('border-left-color:var(--accent)!important'));
check('detail uses local tabs',css.includes('.strategy-v5-detail-tabs'));
check('detail uses one bounded desktop scroll area',css.includes('.strategy-v5-detail-panels')&&css.includes('overflow:auto!important'));
check('summary has one visually dominant metric',css.includes('.strategy-detail-kpis>span:first-child')&&css.includes('font-size:28px!important'));
check('coin detail restores a dense desktop table',css.includes('.strategy-breakdown-table .strategy-coin-row.columns')&&css.includes('min-width:820px!important'));
check('paper benchmark avoids six equal cards',css.includes('.strategy-paper-kpis>span:nth-child(1)')&&css.includes('grid-column:span 6!important'));
check('mobile stacks master and detail',css.includes('@media(max-width:900px)')&&css.includes('grid-template-columns:1fr!important'));
check('reduced motion is honored',css.includes('@media(prefers-reduced-motion:reduce)'));
check('user-facing strategy copy removes Adaptive label',!strategy.includes('Adaptive'));

if(fail.length){console.error('STRATEGY_WORKSPACE_V5=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('STRATEGY_WORKSPACE_V5=PASS');
