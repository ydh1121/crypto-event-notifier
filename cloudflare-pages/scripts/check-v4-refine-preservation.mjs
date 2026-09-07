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
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('v4 home remains active',main.includes("dashboard:()=>createHomePage"));
check('v4 market dashboard remains active',main.includes("'dashboard-detail':()=>createDashboardPage"));
check('v5 market replacement is absent',!main.includes('createMarketPage'));
check('all v4 functional pages remain wired',['createResearchPage','createAssetsPage','createPaperPage','createStrategyPage','createSectorsPage','createRecordsPage','createSystemPage'].every(value=>main.includes(value)));
check('coin market theme group remains',main.includes("['research','코인']")&&main.includes("['dashboard-detail','시장현황']")&&main.includes("['sectors','테마']"));
check('paper strategy group remains',main.includes("['paper','모의투자']")&&main.includes("['strategy','매매방법 비교']"));
check('v4 style stack remains',['mainstream-v4.css','layout-fixes-v4.css','theme-dark-v4.css','theme-dark-audit-v4.css','decision-workspace-v4.css'].every(value=>index.includes(value)));

check('research workspace remains',research.includes('research-workspace')&&research.includes('research-detail'));
check('research listing study remains',research.includes('listing-history-panel'));
check('research current decision remains',research.includes('decision-hero'));
check('research paper reference remains',research.includes('paper-inline'));
check('research btc eth context remains',research.includes('major-context'));
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

if(fail.length){console.error('V4_REFINE_PRESERVATION=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V4_REFINE_PRESERVATION=PASS');
