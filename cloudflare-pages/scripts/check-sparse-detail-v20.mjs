import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const paper=read('public/modules/styles/paper.css');
const strategy=read('public/modules/styles/strategy-native-v5.css');
const viewport=read('public/modules/styles/viewport-first-v9.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V20 sparse-detail cache lineage is active',
  index.includes('/modules/styles/paper.css?v=7')&&
  index.includes('/modules/styles/strategy-native-v5.css?v=3'));

check('PAPER workspace follows content height',
  paper.includes('.paper-workspace{display:grid;grid-template-columns:360px minmax(0,1fr);gap:14px;align-items:start}')&&
  !paper.includes('.paper-workspace{display:grid;grid-template-columns:360px minmax(0,1fr);gap:14px;min-height:calc(100vh - 265px)}'));

check('PAPER master is bounded without forcing detail height',
  paper.includes('top:calc(var(--shell-header-offset,112px) + 8px);height:auto;max-height:calc(100dvh - var(--shell-header-offset,112px) - 32px)')&&
  paper.includes('#paperList{overflow:auto;height:auto;max-height:calc(100dvh - var(--shell-header-offset,112px) - 84px)')&&
  !paper.includes('height:calc(100vh - 110px)'));

check('Strategy detail shell is content-height driven',
  strategy.includes('top:calc(var(--shell-header-offset,112px) + 8px)!important')&&
  strategy.includes('display:block!important')&&
  strategy.includes('min-height:0!important')&&
  strategy.includes('max-height:none!important')&&
  strategy.includes('overflow:visible!important')&&
  !strategy.includes('min-height:440px!important'));

check('Strategy local panels do not create a second scroll container',
  strategy.includes('.strategy-v5-detail-panels{')&&
  strategy.includes('overflow:visible!important')&&
  strategy.includes('overscroll-behavior:auto!important')&&
  strategy.includes('scrollbar-gutter:auto!important'));

check('Viewport contract still protects document-flow result panes',
  viewport.includes('height:auto!important')&&
  viewport.includes('max-height:none!important')&&
  viewport.includes('overflow-y:visible!important'));

if(fail.length){
  console.error('SPARSE_DETAIL_V20=FAIL');
  for(const item of fail)console.error(`- ${item}`);
  process.exit(1);
}
console.log('SPARSE_DETAIL_V20=PASS');
