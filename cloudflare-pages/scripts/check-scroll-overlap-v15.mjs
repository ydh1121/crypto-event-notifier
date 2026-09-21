import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const viewport=read('public/modules/styles/viewport-first-v9.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('current build marker exists',/meta name="crypto-viewer-build" content="[^"]+"/.test(index));
check('viewport stylesheet remains versioned and final',/\/modules\/styles\/viewport-first-v9\.css\?v=[^'\"]+/.test(index)&&index.indexOf('interaction-layout-v4.css')<index.indexOf('viewport-first-v9.css'));
check('V15 clipping hardening rules exist',viewport.includes('V15 clipping / scroll-ownership hardening'));
check('detail surfaces fully clear inherited overflow axes',viewport.includes('overflow:visible!important')&&viewport.includes('overflow-x:visible!important')&&viewport.includes('overflow-y:visible!important'));
check('strategy detail shell expands with document',viewport.includes('#pageRoot[data-page-route="strategy"] .strategy-v5-detail-shell')&&viewport.includes('max-height:none!important'));
check('strategy matrix detail no longer owns vertical viewport',viewport.includes('#pageRoot[data-page-route="strategy"] .strategy-matrix-detail')&&viewport.includes('position:static!important'));
check('horizontal strategy evidence keeps deliberate x scroll',viewport.includes('.strategy-breakdown-table')&&viewport.includes('.strategy-trade-table')&&viewport.includes('overflow-x:auto!important'));
check('page head controls may wrap instead of clipping',viewport.includes('.page-head-meta{flex-wrap:wrap!important}'));
check('header controls can shrink without hiding neighboring actions',viewport.includes('.header-tools>button')&&viewport.includes('flex:0 1 auto!important'));
check('records toolbar compresses to two columns before mobile',viewport.includes('@media(max-width:900px)')&&viewport.includes('grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important'));
check('records toolbar becomes one column on narrow mobile',viewport.includes('@media(max-width:620px)')&&viewport.includes('grid-template-columns:minmax(0,1fr)!important'));
check('canonical master rails keep bounded independent scrolling',interaction.includes('A master-detail screen needs the selectable rail')&&interaction.includes('overflow-y:auto!important')&&interaction.includes('max-height:calc(100dvh - var(--shell-header-offset,112px) - 32px)!important'));

if(fail.length){console.error('SCROLL_OVERLAP_V15=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('SCROLL_OVERLAP_V15=PASS');
