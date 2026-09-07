import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const main=read('public/modules/main.js');
const research=read('public/modules/pages/research.js');
const assets=read('public/modules/pages/assets.js');
const paper=read('public/modules/pages/paper.js');
const strategy=read('public/modules/pages/strategy.js');
const sectors=read('public/modules/pages/sectors-v36.js');
const records=read('public/modules/pages/records.js');
const system=read('public/modules/pages/system.js');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('all nine routes remain registered',['dashboard','dashboard-detail','research','assets','paper','strategy','sectors','records','system'].every(route=>main.includes(route)));
check('auth and snapshot polling remain installed',main.includes('createAuth')&&main.includes('createSnapshotPoller'));
check('legacy interaction helpers remain installed',['installSectorImeGuard','installTableSortEnhancer','installSamePageInteractionContinuity','installAmountInputUx','installDexLaunchResearchPanel'].every(value=>main.includes(value)));

check('coin page keeps exchange search filter and detail',research.includes('data-research-exchange')&&research.includes('data-research-search')&&research.includes('data-research-filter')&&research.includes('research-workspace')&&research.includes('research-detail'));
check('coin page keeps market detail service',research.includes('getMarketDetail')&&research.includes('researchDeep'));
check('coin page keeps listing study',research.includes('listing-history-panel'));
check('coin page keeps btc eth context',research.includes('major-context'));

check('assets keep holdings workspace',assets.includes('asset-workspace')&&assets.includes('asset-master')&&assets.includes('asset-detail'));
check('assets keep average purchase tools',assets.includes('direct-average-panel')&&assets.includes('averaging-calculator'));
check('assets keep holding plan',assets.includes('holding-plan-panel'));
check('assets keep exchange comparison',assets.includes('asset-research-sides'));
check('assets keep history',assets.includes('asset-history-panel'));

check('paper keeps master detail flow',paper.includes('paper-workspace')&&paper.includes('paper-master')&&paper.includes('paper-detail'));
check('paper keeps current trade plan',paper.includes('trade-plan-panel')&&paper.includes('paperDeep'));
check('paper keeps exchange summary',paper.includes('exchange-paper-grid')&&paper.includes('paper-combined'));

check('strategy keeps strategy selector',strategy.includes('strategy-workspace')&&strategy.includes('strategy-table')&&strategy.includes('strategy-detail'));
check('strategy keeps coin breakdown',strategy.includes('strategyBreakdown')&&strategy.includes('strategy-coin-table'));
check('strategy keeps coin matrix',strategy.includes('strategyCoinMatrix')&&strategy.includes("if(tab==='matrix')"));
check('strategy keeps evidence charts',strategy.includes('strategyEvidence')&&strategy.includes('strategyEquityHistory'));
check('strategy keeps current paper benchmark',strategy.includes('paperPortfolioHistory')&&strategy.includes('combinedPaper'));

check('themes keep ranking and detail',sectors.includes('sector-rank')&&sectors.includes('sector-detail'));
check('themes keep coin table',sectors.includes('sector-coin-workspace'));
check('themes keep lifecycle and method evidence',sectors.includes('market-lifecycle')&&sectors.includes('sector-method'));

check('records keep user and internal scopes',records.includes("recordsScope==='system'")&&records.includes('records-scope-switch'));
check('records keep search strategy period filters',records.includes('data-records-search')&&records.includes('data-records-strategy')&&records.includes('data-records-period'));
check('records keep buy sell decision learning system events',['buy','sell','decision','learning','system'].every(value=>records.includes(`'${value}'`)));

check('system keeps operations and diagnostics',system.includes('operations-grid')&&system.includes('component-panel'));
check('system keeps account invitation',system.includes('invite'));

if(fail.length){console.error('V5_FEATURE_PRESERVATION=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V5_FEATURE_PRESERVATION=PASS');
