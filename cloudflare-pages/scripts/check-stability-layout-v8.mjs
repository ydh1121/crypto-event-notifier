import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const router=read('public/modules/core/router.js');
const words=read('public/modules/shared/mainstream-ui.js');
const amount=read('public/modules/shared/amount-input-ux.js');
const dex=read('public/modules/pages/dex-launch-panel.js');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('current build preserves V8 baseline',index.includes('2026.09.11-v4.9.0-viewport-first'));
check('main cache refreshed',index.includes('/modules/main.js?v=94'));
check('canonical interaction layer loads last',index.includes('/modules/styles/interaction-layout-v4.css?v=3')&&index.indexOf('decision-first-v7.css')<index.indexOf('interaction-layout-v4.css'));
check('router cache refreshed',main.includes("./core/router.js?v=2"));
check('event driven amount ux loaded',main.includes("./shared/amount-input-ux.js?v=2"));
check('event driven text normalizer loaded',main.includes("./shared/mainstream-ui.js?v=2"));
check('event driven dex panel loaded',main.includes("./pages/dex-launch-panel.js?v=45"));
check('global click continuity crutch removed',!main.includes('installSamePageInteractionContinuity'));
check('main dispatches explicit UI refresh events',main.includes("new CustomEvent('ui:refresh'")&&main.includes('queueUiRefresh'));

check('text normalizer has no mutation observer',!words.includes('MutationObserver')&&words.includes("addEventListener('ui:refresh'"));
check('amount ux has no mutation observer',!amount.includes('MutationObserver')&&amount.includes("addEventListener('ui:refresh'")&&amount.includes("addEventListener('focusin'"));
check('dex panel has no mutation observer',!dex.includes('MutationObserver')&&dex.includes("addEventListener('ui:refresh'"));
check('same route click does not rerender whole page',router.includes('if(currentName===name){syncNav(name);onChange?.(name);return}')&&!router.includes('patchPreservingUi'));

check('only shell header is sticky by policy',interaction.includes('Only the shell header is sticky')&&interaction.includes('.app-header{')&&interaction.includes('z-index:100!important'));
check('result panes use document flow',interaction.includes('.strategy-v5-detail-panels')&&interaction.includes('max-height:none!important')&&interaction.includes('overflow:visible!important'));
check('canonical tabs are flat',interaction.includes('Canonical tab language')&&interaction.includes('border-bottom:2px solid transparent!important'));
check('segmented controls are separated',interaction.includes('Canonical selection controls')&&interaction.includes('gap:var(--ui-control-gap)!important')&&interaction.includes('border-radius:var(--ui-control-r)!important'));
check('action buttons share one geometry',interaction.includes('Canonical action buttons')&&interaction.includes('min-height:var(--ui-control-h)!important'));
check('desktop workspaces have protected gaps',interaction.includes('gap:28px!important'));
check('mobile stacks workspaces',interaction.includes('@media(max-width:900px)')&&interaction.includes('display:block!important'));

if(fail.length){console.error('STABILITY_LAYOUT_V8=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('STABILITY_LAYOUT_V8=PASS');
