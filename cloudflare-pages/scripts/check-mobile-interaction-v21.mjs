import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const shell=read('public/modules/styles/shell.css');
const tokens=read('public/modules/styles/tokens.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const viewport=read('public/modules/styles/viewport-first-v9.css');
const continuity=read('public/modules/shared/ui-continuity.js');
const main=read('public/modules/main.js');
const store=read('public/modules/core/store.js');
const live=read('public/modules/shared/live-patch-v16.js');
const remaining=read('public/modules/shared/live-patch-remaining-v16.js');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V21 mobile asset cache lineage is active',
  index.includes('/modules/styles/shell.css?v=7')&&
  index.includes('/modules/styles/interaction-layout-v4.css?v=9'));

check('viewport preserves native zoom and safe-area capability',
  index.includes('width=device-width,initial-scale=1,viewport-fit=cover')&&
  !index.includes('user-scalable=no')&&
  !index.includes('maximum-scale=1'));

check('shell owns all four safe-area edges',
  shell.includes('env(safe-area-inset-left)')&&
  shell.includes('env(safe-area-inset-right)')&&
  shell.includes('env(safe-area-inset-top)')&&
  shell.includes('env(safe-area-inset-bottom)')&&
  shell.includes('min-height:100dvh'));

check('compact global nav is 360-safe and touch-sized',
  shell.includes('grid-template-columns:repeat(3,minmax(0,1fr))')&&
  shell.includes('min-height:var(--control-touch-h)')&&
  shell.includes('text-overflow:ellipsis'));

check('compact high-frequency controls use canonical touch height',
  interaction.includes('.main-nav button,.segmented button,.reader-mode-control button,.chip-row button,.theme-toggle{min-height:var(--control-touch-h)!important}')&&
  interaction.includes('.auth-theme-toggle{top:max(10px,env(safe-area-inset-top))!important;right:max(10px,env(safe-area-inset-right))!important;min-height:var(--control-touch-h)!important}'));

check('compact journey rail respects notch side insets',
  interaction.includes('padding-left:max(var(--content-pad-mobile,12px),env(safe-area-inset-left))!important')&&
  interaction.includes('padding-right:max(var(--content-pad-mobile,12px),env(safe-area-inset-right))!important'));

check('iOS focus zoom prevention remains capability based',
  tokens.includes('@media(pointer:coarse){input,textarea,select{font-size:16px}}')&&
  tokens.includes('touch-action:manipulation'));

check('mobile return handoff keeps minimum touch geometry',
  viewport.includes('.viewport-return-bar')&&
  viewport.includes('min-height:44px'));

check('continuity restores focus selection and scroll without browser jumps',
  continuity.includes('focus({preventScroll:true})')&&
  continuity.includes('setSelectionRange')&&
  continuity.includes('window.scrollTo(snapshot.window.x,snapshot.window.y)')&&
  continuity.includes('captureScrollableAncestors'));

check('main render path preserves bounded UI continuity',
  main.includes("import{patchPreservingUi}from'./shared/ui-continuity.js")&&
  main.includes("scrollSelectors:['[data-preserve-scroll]','.master-list','.asset-holdings-list','#paperList','.strategy-table']"));

check('polling patches do not route through full render',
  live.includes("meta.type!=='snapshot-live'")&&
  remaining.includes("meta.type!=='snapshot-live'")&&
  !live.includes('router.render')&&
  !remaining.includes('router.render'));

check('selection search filter state stays durable in viewer store',
  store.includes("const STORAGE_KEY='cryptoViewerUiV6'")&&
  ['paperSearch','paperFilter','paperSort','strategyCoinSearch','strategyCoinSort','recordsSearch','recordsFilter','sectorCoinMarket'].every(key=>store.includes(key)));

if(fail.length){
  console.error('MOBILE_INTERACTION_V21=FAIL');
  for(const item of fail)console.error(`- ${item}`);
  process.exit(1);
}
console.log('MOBILE_INTERACTION_V21=PASS');
