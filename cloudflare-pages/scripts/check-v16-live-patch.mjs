import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const store=read('public/modules/core/store.js');
const live=read('public/modules/shared/live-patch-v16.js');
const compact=read('public/modules/styles/compact-v16.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('current V16 build marker exists',/meta name="crypto-viewer-build" content="[^"]*v6\.[^"]*"/.test(index));
check('main entry remains cache-versioned',/\/modules\/main\.js\?v=[^'\"]+/.test(index));
check('compact live layer remains cache-versioned',/\/modules\/styles\/compact-v16\.css\?v=[^'\"]+/.test(index));
check('live patch module is cache-versioned and installed',/\.\/shared\/live-patch-v16\.js\?v=[^'\"]+/.test(main)&&main.includes('installLivePatchV16({store,root})'));
check('store separates later live snapshots from initial render',store.includes("patchOnly?'snapshot-live':'snapshot'")&&['dashboard','assets','paper','strategy'].every(route=>store.includes(`'${route}'`))&&store.includes('LIVE_PATCH_ROUTES=new Set('));
check('home uses patch-only live values',live.includes("route==='dashboard'")&&live.includes('patchHome(root,state)')&&live.includes('#homeCoinTable'));
check('assets use patch-only live values',live.includes("route==='assets'")&&live.includes('patchAssets(root,state)')&&live.includes('.asset-holdings-list'));
check('paper uses patch-only live values',live.includes("route==='paper'")&&live.includes('patchPaper(root,state)')&&live.includes('#paperList'));
check('strategy uses patch-only live values',live.includes("route==='strategy'")&&live.includes('patchStrategy(root,state)')&&live.includes('[data-strategy-key'));
check('live patch avoids page-wide innerHTML replacement',!live.includes('root.innerHTML='));
check('new rows are inserted as DOM nodes',live.includes("document.createElement('button')")&&live.includes('enter(node)'));
check('row insertion animation exists',compact.includes('.live-row-enter-v16,.live-enter')&&compact.includes('@keyframes v16RowEnter'));
check('numeric value tick exists',compact.includes('.live-value-tick-v16')&&compact.includes('@keyframes v16ValueTick'));
check('reduced-motion is respected',compact.includes('@media(prefers-reduced-motion:reduce)'));

if(fail.length){console.error('V16_LIVE_PATCH=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V16_LIVE_PATCH=PASS');
