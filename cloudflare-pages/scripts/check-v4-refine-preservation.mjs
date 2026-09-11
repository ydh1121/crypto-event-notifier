import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const research=read('public/modules/pages/research.js');
const dashboard=read('public/modules/pages/dashboard.js');
const assets=read('public/modules/pages/assets.js');
const paper=read('public/modules/pages/paper.js');
const strategy=read('public/modules/pages/strategy.js');
const sectors=read('public/modules/pages/sectors-v36.js');
const records=read('public/modules/pages/records.js');
const system=read('public/modules/pages/system.js');
const drilldown=read('public/modules/shared/strategy-drilldown-v4.js');
const viewport=read('public/modules/shared/viewport-handoff-v4.js');
const css=read('public/modules/styles/v4-refine-v1.css');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('v4 home remains active',main.includes("dashboard:()=>createHomePage"));
check('v4 market dashboard remains active',main.includes("'dashboard-detail':()=>createDashboardPage"));
check('v5 market replacement is absent',!main.includes('createMarketPage'));
check('all v4 functional pages remain wired',['createResearchPage','createAssetsPage','createPaperPage','createStrategyPage','createSectorsPage','createRecordsPage','createSystemPage'].every(value=>main.includes(value)));
check('coin market theme group remains',main.includes("['research','코인']")&&main.includes("['dashboard-detail','시장현황']")&&main.includes("['sectors','테마']"));
check('paper strategy group remains',main.includes("['paper','모의투자']")&&main.includes("['strategy','매매방법 비교']"));
check('v4 style stack remains',['mainstream-v4.css','layout-fixes-v4.css','theme-dark-v4.css','theme-dark-audit-v4.css','decision-workspace-v4.css'].every(value=>index.includes(value)));
check('refine layer remains after v4',index.includes('v4-refine-v1.css')&&index.indexOf('decision-workspace-v4.css')<index.indexOf('v4-refine-v1.css'));
check('canonical interaction layer loads last',index.includes('interaction-layout-v4.css?v=3')&&index.indexOf('decision-first-v7.css')<index.indexOf('interaction-layout-v4.css'));

check('research workspace remains',research.includes('research-workspace')&&research.includes('research-detail'));
check('research listing study remains',research.includes('listing-history-panel'));
check('research current decision remains',research.includes('decision-first-conclusion'));
check('research paper reference remains',research.includes('PAPER 참고'));
check('research btc eth context remains',research.includes('BTC 흐름')&&research.includes('코인 vs BTC·ETH'));
check('research current trade plan remains',research.includes('trade_plan'));
check('research charts and records remain',research.includes('history-stack')&&research.includes('detail-columns'));

check('market dashboard keeps overview cards',dashboard.includes('dashboard'));
check('assets tools remain',assets.includes('asset-workspace')&&assets.includes('holding-plan-panel')&&assets.includes('direct-average-panel')&&assets.includes('averaging-calculator')&&assets.includes('asset-research-sides'));
check('paper master detail remains',paper.includes('paper-workspace')&&paper.includes('paper-detail')&&paper.includes('trade-plan-panel'));
check('strategy workspace remains',strategy.includes('strategy-workspace')&&strategy.includes('strategy-table')&&strategy.includes('strategy-detail'));
check('strategy breakdown remains',strategy.includes('strategyBreakdown')&&strategy.includes('strategy-coin-table'));
check('strategy evidence remains',strategy.includes('strategyEvidence'));
check('themes remain',sectors.includes('sector-layout')&&sectors.includes('sector-rank')&&sectors.includes('sector-detail')&&sectors.includes('sector-coin-workspace'));
check('records remain',records.includes('records'));
check('system remains',system.includes('operations-grid')&&system.includes('component-panel'));

check('obsolete decision lens is not installed',!main.includes('installCoinDecisionLens'));
check('strategy context is carried to coin detail',drilldown.includes('researchSourceStrategyExperiment')&&drilldown.includes('researchSourceStrategyLabel'));
check('strategy coin click lands on requested decision result',drilldown.includes("viewport:handoff")&&drilldown.includes("selector:'#researchDetail'")&&drilldown.includes('force:true'));
check('viewport handoff is installed from main entry',main.includes('installViewportHandoff')&&main.includes("./shared/viewport-handoff-v4.js?v=3"));
check('compact list selections reveal their detail result',['[data-research-market]','#researchDetail','[data-asset-market]','#assetDetail','[data-paper-market]','#paperDetail','[data-strategy-key]','#strategyDetail'].every(value=>viewport.includes(value)));
check('paper summary action reveals the newly selected tab result',viewport.includes(".paper-next [data-paper-tab]")&&viewport.includes("reveal('#paperBody',{force:true})"));
check('viewport handoff retries after synchronous rerenders',viewport.includes('retries=6')&&viewport.includes('remaining-=1')&&viewport.includes('if(remaining>0)attempt()'));
check('viewport handoff settles after continuity restoration',viewport.includes('requestAnimationFrame(()=>{')&&viewport.includes('settled=root.querySelector(selector)')&&viewport.includes('settle:true'));
check('viewport handoff respects compact displays and reduced motion',viewport.includes('(max-width: 900px)')&&viewport.includes('prefers-reduced-motion: reduce'));
check('viewport handoff is event driven without mutation observer',!viewport.includes('MutationObserver')&&viewport.includes("root.addEventListener('click',click)"));
check('reader mode deliberate rerender preserves current viewport',main.includes('patchPreservingUi')&&main.includes("'.strategy-table'"));
check('main cache version is refreshed',index.includes('/modules/main.js?v=94'));

check('coin page prioritizes workspace before historical panels',interaction.includes('Page order: primary workspace')&&interaction.includes('>.research-workspace{order:1'));
check('asset page prioritizes selection and detail before long history',interaction.includes('>.asset-workspace{order:2')&&interaction.includes('>.asset-history-panel{order:3'));
check('desktop research selection and result share one viewport',interaction.includes('grid-template-columns:minmax(270px,315px) minmax(0,1fr)!important'));
check('desktop asset selection and result share one viewport',interaction.includes('grid-template-columns:minmax(280px,330px) minmax(0,1fr)!important'));
check('paper controls reserve control gaps',interaction.includes('.paper-toolbar')&&interaction.includes('gap:var(--ui-control-gap)!important'));
check('desktop strategy keeps list and selected result together',interaction.includes('grid-template-columns:minmax(270px,310px) minmax(0,1fr)!important'));
check('result panes do not become nested viewports',interaction.includes('.strategy-v5-detail-panels')&&interaction.includes('overflow:visible!important'));
check('stacked displays bound selection rails before handoff',interaction.includes('max-height:44dvh!important'));
check('detail destinations account for sticky shell',interaction.includes('#researchDetail,#assetDetail,#paperDetail,#strategyDetail,#paperBody,#strategyBody'));

check('secondary nav is centered and more visible',css.includes('.journey-nav{justify-content:center!important')&&css.includes('min-width:132px!important'));
check('all strategy metrics are explicitly restored',css.includes('.strategy-row>span')&&css.includes('display:block!important')&&css.includes("content:'손익비'")&&css.includes("content:'승률'")&&css.includes("content:'검증'"));
check('all coin breakdown metrics are explicitly restored',['실현손익','미실현','하락폭','완료 거래','승률','상태'].every(value=>css.includes(`content:'${value}'`)));

if(fail.length){console.error('V4_REFINE_PRESERVATION=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V4_REFINE_PRESERVATION=PASS');
