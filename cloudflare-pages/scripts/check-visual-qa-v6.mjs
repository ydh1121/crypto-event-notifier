import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const home=read('public/modules/pages/v4/home.js');
const css=read('public/modules/styles/visual-qa-v6.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('visual QA layer is loaded',index.includes('/modules/styles/visual-qa-v6.css?v=1'));
check('visual QA layer follows strategy native layer',index.indexOf('strategy-native-v5.css')<index.indexOf('visual-qa-v6.css'));
check('decision-first layer follows visual QA',index.indexOf('visual-qa-v6.css')<index.indexOf('decision-first-v7.css'));
check('canonical interaction layer supersedes visual QA geometry',index.indexOf('visual-qa-v6.css')<index.indexOf('interaction-layout-v4.css'));
check('main entry cache is refreshed',index.includes('/modules/main.js?v=93'));
check('home module cache is refreshed',main.includes("./pages/v4/home.js?v=2"));

check('wide dashboard uses viewport',css.includes('max-width:1540px!important'));
check('wide dashboard keeps reasonable side padding',css.includes('padding-left:28px!important')&&css.includes('padding-right:28px!important'));

check('home is distributed into overview columns',home.includes('home-dashboard-grid')&&home.includes('home-dashboard-column'));
check('home separates market and asset regions',home.includes('home-market-section')&&home.includes('home-assets-section'));
check('home separates coin and recent trade regions',home.includes('home-coins-section')&&home.includes('home-trades-section'));

check('V6 repaired desktop result panes',css.includes('#pageRoot[data-page-route="research"] .research-detail')&&css.includes('#pageRoot[data-page-route="assets"] .asset-detail')&&css.includes('#pageRoot[data-page-route="paper"] .paper-detail'));
check('canonical layer owns final result scrolling',interaction.includes('Result panes do not create')||interaction.includes('result panes do not create')||interaction.includes('max-height:none!important'));
check('asset budget input gets protected width',css.includes('.holding-budget-head')&&css.includes('minmax(220px,280px)!important'));

check('strategy legacy grid cannot rearrange V5 rail',css.includes('.strategy-row.strategy-v5-strategy-item:not(.columns)')&&css.includes('grid-template-columns:minmax(0,1fr)!important'));
check('strategy rail facts are explicitly two columns',css.includes('.strategy-v5-strategy-item>.strategy-v5-item-facts')&&css.includes('grid-template-columns:repeat(2,minmax(0,1fr))!important'));
check('strategy pseudo labels are neutralized',css.includes('.strategy-v5-item-facts>span::before')&&css.includes('content:none!important'));
check('strategy rail cannot horizontally overflow',css.includes('overflow-x:hidden!important'));

check('dark theme search surface is repaired',css.includes('html[data-theme="dark"] #pageRoot[data-page-route="sectors"] .sector-search')&&css.includes('background:var(--surface)!important'));
check('dark theme search input stays transparent',css.includes('html[data-theme="dark"] #pageRoot[data-page-route="sectors"] .sector-search input')&&css.includes('background:transparent!important'));

if(fail.length){console.error('VISUAL_QA_V6=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('VISUAL_QA_V6=PASS');
