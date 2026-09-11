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
check('market dashboard remains active',main.includes("'dashboard-detail':()=>createDashboardPage"));
check('all functional pages remain wired',['createResearchPage','createAssetsPage','createPaperPage','createStrategyPage','createSectorsPage','createRecordsPage','createSystemPage'].every(value=>main.includes(value)));
check('market secondary group remains',main.includes("['research','코인']")&&main.includes("['dashboard-detail','시장현황']")&&main.includes("['sectors','테마']"));
check('paper and strategy are no longer fused into secondary navigation',!main.includes("paper:[['paper','모의투자']")&&!main.includes("strategy:[['paper','모의투자']"));
check('v4 style stack remains',['mainstream-v4.css','layout-fixes-v4.css','theme-dark-v4.css','theme-dark-audit-v4.css','decision-workspace-v4.css'].every(value=>index.includes(value)));
check('refine layer remains after v4',index.includes('v4-refine-v1.css')&&index.indexOf('decision-workspace-v4.css')<index.indexOf('v4-refine-v1.css'));
check('canonical interaction layer is refreshed',index.includes('interaction-layout-v4.css?v=6')&&index.indexOf('decision-first-v7.css')<index.indexOf('interaction-layout-v4.css'));

check('research workspace remains',research.includes('research-workspace')&&research.includes('research-detail'));
check('research market quote list is first class',research.includes('market-list-columns')&&research.includes('market-quote-row')&&research.includes('market-current-price'));
check('research listing study remains',research.includes('listing-history-panel'));
check('research current decision remains',research.includes('decision-first-conclusion'));
check('research current trade plan remains',research.includes('trade_plan'));
check('market dashboard remains',dashboard.includes('dashboard'));
check('assets tools remain',assets.includes('asset-workspace')&&assets.includes('holding-plan-panel')&&assets.includes('direct-average-panel')&&assets.includes('averaging-calculator'));
check('paper master detail remains',paper.includes('paper-workspace')&&paper.includes('paper-detail')&&paper.includes('trade-plan-panel'));
check('strategy workspace remains',strategy.includes('strategy-workspace')&&strategy.includes('strategy-table')&&strategy.includes('strategy-detail'));
check('strategy breakdown remains',strategy.includes('strategyBreakdown')&&strategy.includes('strategy-coin-table'));
check('strategy evidence remains',strategy.includes('strategyEvidence'));
check('strategy virtual trade evidence exists',strategy.includes('strategyTrades')&&strategy.includes('가상매매 내역'));
check('themes remain',sectors.includes('sector-layout')&&sectors.includes('sector-rank')&&sectors.includes('sector-detail'));
check('records remain',records.includes('records'));
check('system remains',system.includes('operations-grid')&&system.includes('component-panel'));

check('obsolete decision lens is not installed',!main.includes('installCoinDecisionLens'));
check('strategy context is carried to coin detail',drilldown.includes('researchSourceStrategyExperiment')&&drilldown.includes('researchSourceStrategyLabel'));
check('strategy coin click lands on requested decision result',drilldown.includes("viewport:handoff")&&drilldown.includes("selector:'#researchDetail'")&&drilldown.includes('force:true'));
check('viewport handoff remains event driven',main.includes('installViewportHandoff')&&!viewport.includes('MutationObserver')&&viewport.includes("root.addEventListener('click',click)"));
check('compact selections still reveal detail',['[data-research-market]','#researchDetail','[data-asset-market]','#assetDetail','[data-paper-market]','#paperDetail','[data-strategy-key]','#strategyDetail'].every(value=>viewport.includes(value)));
check('paper action reveals body',viewport.includes(".paper-next [data-paper-tab]")&&viewport.includes("reveal('#paperBody',{force:true})"));
check('main cache version is refreshed',index.includes('/modules/main.js?v=96'));

check('non-market workspaces keep shared rail geometry',interaction.includes('grid-template-columns:minmax(280px,300px) minmax(0,1fr)!important'));
check('market workspace receives quote-capable rail width',interaction.includes('grid-template-columns:minmax(340px,360px) minmax(0,1fr)!important'));
check('research controls remain fixed while market rows scroll',interaction.includes('Exchange-style market rail')&&interaction.includes('.research-master .master-list')&&interaction.includes('flex:1 1 auto!important')&&interaction.includes('overflow-y:auto!important'));
check('result detail remains document flow',interaction.includes('Detail content is read with the page')&&interaction.includes('.strategy-v5-detail-panels')&&interaction.includes('overflow-y:visible!important'));
check('coin current price is promoted',interaction.includes('grid-template-areas:"price conclusion vitals"')&&interaction.includes('.market-current-price'));
check('secondary research follows primary workspace',interaction.includes('>.decision-first-extra-research{order:3!important'));
check('paper controls reserve control gaps',interaction.includes('.paper-toolbar')&&interaction.includes('gap:var(--ui-control-gap)!important'));
check('detail destinations account for sticky shell',interaction.includes('#researchDetail,#assetDetail,#paperDetail,#strategyDetail,#strategyBody'));

check('secondary nav legacy visual rules remain available',css.includes('.journey-nav{justify-content:center!important'));
check('strategy metric labels remain available',css.includes('.strategy-row>span')&&css.includes('display:block!important'));

if(fail.length){console.error('V4_REFINE_PRESERVATION=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V4_REFINE_PRESERVATION=PASS');
