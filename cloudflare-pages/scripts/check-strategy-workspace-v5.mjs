import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const js=read('public/modules/shared/strategy-workspace-v5.js');
const css=read('public/modules/styles/strategy-workspace-v5.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('strategy workspace style is loaded',index.includes('/modules/styles/strategy-workspace-v5.css?v=1'));
check('strategy workspace style loads after interaction layout',index.indexOf('interaction-layout-v4.css')<index.indexOf('strategy-workspace-v5.css'));
check('strategy workspace module is loaded',index.includes('/modules/shared/strategy-workspace-v5.js?v=1'));
check('existing main entry remains',index.includes('/modules/main.js?v=88'));
check('three local strategy detail tabs exist',['summary','coins','evidence'].every(value=>js.includes(`data-strategy-v5-tab=\"${value}\"`)));
check('strategy selection rail preserves its scroll',js.includes('savedRailScroll')&&js.includes('list.scrollTop=savedRailScroll'));
check('strategy click does not get intercepted',js.includes("closest('[data-strategy-key]')")&&!js.includes("strategy.stopPropagation"));
check('deep tab promotes simple mode to detail',js.includes('openDetailModeForDeepTab')&&js.includes("[data-reader-mode=\"detail\"]"));
check('mobile has explicit strategy list return',js.includes('data-strategy-v5-back')&&css.includes('.strategy-v5-back'));
check('overview becomes master detail workspace',css.includes('grid-template-columns:minmax(250px,292px) minmax(0,1fr)!important'));
check('strategy rail is navigation not wide table',css.includes('.strategy-v5-strategy-item')&&css.includes('min-width:0!important'));
check('selected strategy has a clear active rail',css.includes('border-left-color:var(--accent)!important'));
check('detail uses local tabs',css.includes('.strategy-v5-detail-tabs'));
check('detail uses one bounded desktop scroll area',css.includes('.strategy-v5-detail-panels')&&css.includes('overflow:auto'));
check('metric cards are flattened into hierarchy',css.includes('.strategy-detail-kpis>span:first-child')&&css.includes('font-size:28px!important'));
check('mobile stacks master and detail',css.includes('@media(max-width:900px)')&&css.includes('grid-template-columns:1fr!important'));
check('reduced motion is honored',css.includes('@media(prefers-reduced-motion:reduce)'));

if(fail.length){console.error('STRATEGY_WORKSPACE_V5=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('STRATEGY_WORKSPACE_V5=PASS');
