import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const handoff=read('public/modules/shared/viewport-handoff-v4.js');
const css=read('public/modules/styles/viewport-first-v9.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V9 build marker exists',index.includes('2026.09.11-v4.9.0-viewport-first'));
check('main cache refreshed',index.includes('/modules/main.js?v=94'));
check('viewport-first css loads last',index.includes('/modules/styles/viewport-first-v9.css?v=1')&&index.indexOf('interaction-layout-v4.css')<index.indexOf('viewport-first-v9.css'));
check('viewport handoff cache refreshed',main.includes("./shared/viewport-handoff-v4.js?v=3"));

check('1024-class header uses two rows',css.includes('@media(max-width:1180px) and (min-width:901px)')&&css.includes('grid-template-areas:"brand tools" "nav nav"!important'));
check('compact desktop navigation keeps six direct destinations',css.includes('grid-template-columns:repeat(6,minmax(0,1fr))!important'));
check('mobile navigation returns to three columns',css.includes('@media(max-width:620px)')&&css.includes('grid-template-columns:repeat(3,minmax(0,1fr))!important'));
check('selection rails have viewport budgets',css.includes('max-height:min(50dvh,var(--viewport-rail-max))!important')&&css.includes('max-height:min(36dvh,350px)!important'));
check('short desktop displays have tighter budgets',css.includes('@media(min-width:901px) and (max-height:760px)'));
check('arrival targets use live shell offset',css.includes('scroll-margin-top:calc(var(--shell-header-offset) + 12px)!important'));

check('compact click targets cover four core workspaces',['data-research-market','data-asset-market','data-paper-market','data-strategy-key'].every(value=>handoff.includes(value)));
check('compact result has explicit return context',handoff.includes('viewport-return-bar')&&handoff.includes('data-viewport-back')&&handoff.includes('returnToSource'));
check('header offset is measured from rendered shell',handoff.includes("document.querySelector('.app-header')")&&handoff.includes("setProperty('--shell-header-offset'"));
check('compact handoff does not use mutation observer',!handoff.includes('MutationObserver'));
check('resize refreshes measured shell geometry',handoff.includes("window.addEventListener('resize',resize")&&handoff.includes("window.removeEventListener('resize',resize)"));

if(fail.length){console.error('VIEWPORT_FIRST_V9=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('VIEWPORT_FIRST_V9=PASS');
