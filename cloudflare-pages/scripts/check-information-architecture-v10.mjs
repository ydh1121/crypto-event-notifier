import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const router=read('public/modules/core/router.js');
const shell=read('public/modules/styles/shell.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const viewport=read('public/modules/styles/viewport-first-v9.css');
const strategy=read('public/modules/pages/strategy.js');
const selectors=read('public/modules/shared/selectors.js');
const doc=read('docs/UX_INFORMATION_ARCHITECTURE_V10.md');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('scroll ownership build marker exists',index.includes('2026.09.12-v5.0.1-scroll-ownership'));
check('architecture document declares product decision loop',doc.includes('시장 파악 → 코인 판단 → 내 자산 확인 → 모의 실행 → 전략 평가 → 결과 회고'));
check('architecture document defines explicit scroll ownership',doc.includes('Scroll ownership is explicit')&&doc.includes('sticky bounded rail + document-flow detail'));

check('primary navigation follows six user goals',['홈','시장','자산','모의투자','전략','기록'].every(label=>index.includes(`>${label}</button>`)));
check('system is account-only, not primary navigation',!index.includes('data-route="system"')&&main.includes("userMenuBtn')?.addEventListener('click',()=>router.go('system'))"));
check('strategy is not parented under paper',!router.includes("strategy:'paper'"));
check('market secondary group remains coherent',main.includes("['research','코인']")&&main.includes("['dashboard-detail','시장현황']")&&main.includes("['sectors','테마']"));
check('paper and strategy secondary fusion is removed',!main.includes("paper:[['paper','모의투자']")&&!main.includes("strategy:[['paper','모의투자']"));

check('shell exposes one content width token',shell.includes('--content-max:1540px')&&shell.includes('width:min(var(--content-max),100%)'));
check('header and main share content padding token',shell.includes('--content-pad:28px')&&shell.includes('padding:0 var(--content-pad)')&&shell.includes('padding:22px var(--content-pad) 48px'));
check('all master detail workspaces share one rail geometry',interaction.includes('grid-template-columns:minmax(280px,300px) minmax(0,1fr)!important'));
check('desktop master rails are sticky and bounded',interaction.includes('@media(min-width:901px)')&&interaction.includes('position:sticky!important')&&interaction.includes('max-height:calc(100dvh - var(--shell-header-offset,112px) - 32px)!important')&&interaction.includes('overflow-y:auto!important'));
check('result detail uses document flow',interaction.includes('Detail content is read with the page')&&interaction.includes('max-height:none!important')&&interaction.includes('overflow-y:visible!important'));
check('mobile lists remain bounded and scrollable',interaction.includes('max-height:min(52dvh,520px)!important')&&interaction.includes('@media(max-width:900px)'));
check('viewport layer does not neutralize master rail scrolling',viewport.includes('Do not override canonical master-rail scrolling here')&&!viewport.includes('.research-master .master-list'));
check('horizontal overflow is reserved for data table',interaction.includes('.strategy-trade-table')&&interaction.includes('overflow-x:auto'));

check('selected coin current price is first-class identity',interaction.includes('grid-template-areas:"price conclusion vitals"')&&interaction.includes('font-size:clamp(30px,3vw,44px)!important'));
check('strategy exposes virtual trade evidence tab',strategy.includes("item('trades','가상매매 내역')")&&strategy.includes('data-strategy-v5-panel="trades"'));
check('strategy trade rows use experiment selector',strategy.includes('strategyTradeRows(store.get(),r.experiment_id)'));
check('strategy trade selector supports canonical contract',selectors.includes('strategyTradeRows')&&selectors.includes('lab.strategy_trades')&&selectors.includes('lab.trades')&&selectors.includes('lab.fills'));
check('missing trade ledger is explicit and not fabricated',strategy.includes('체결 원장이 아직 Snapshot에 제공되지 않습니다')&&strategy.includes('가상의 거래를 만들어 표시하지 않습니다'));
check('no new global V10 override stylesheet was added',!index.includes('v10.css')&&!index.includes('information-architecture-v10.css'));

if(fail.length){console.error('INFORMATION_ARCHITECTURE_V10=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('INFORMATION_ARCHITECTURE_V10=PASS');
