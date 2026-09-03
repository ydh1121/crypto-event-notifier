import fs from 'node:fs';
import path from 'node:path';

const root=process.cwd();
const read=file=>fs.readFileSync(path.join(root,file),'utf8');
const fail=[];
function check(name,ok){if(!ok)fail.push(name)}

const router=read('public/modules/core/router.js');
const store=read('public/modules/core/store.js');
const main=read('public/modules/main.js');
const index=read('public/index.html');
const home=read('public/modules/pages/home.js');
const paper=read('public/modules/pages/paper.js');
const strategy=read('public/modules/pages/strategy.js');
const sectorTable=read('public/modules/pages/sector-coin-table.js');
const shell=read('public/modules/styles/shell.css');

check('sector owns its main-nav active state',index.includes('data-route="sectors"')&&!router.includes("sectors:'research'")&&!router.includes("sectors: 'research'"));
check('strategy route remains under performance workspace',router.includes("strategy:'paper'")||router.includes("strategy: 'paper'"));
check('strategy overview state is explicit',store.includes('strategyOverviewExperiment'));
check('strategy coin-performance state is separate',store.includes('strategyCoinExperiment'));
check('strategy coin tab has visible experiment selector',strategy.includes('data-strategy-coin-experiment'));
check('strategy coin tab does not use hidden overview selection',strategy.includes('ensureCoinExperiment')&&!/function coinPerformance\([^)]*\)[\s\S]{0,240}ensureOverviewSelected/.test(strategy));
check('strategy coin sort is explicit',store.includes('strategyCoinSort')&&strategy.includes('data-strategy-coin-sort'));
check('paper has execution-strategy filter state',store.includes('paperStrategyFilter'));
check('paper has visible execution-strategy filter',paper.includes('data-paper-strategy'));
check('paper strategy filter uses execution row strategy',paper.includes('paperStrategy(store.get(),ex,r)'));
check('home detail link carries visible holding',home.includes('data-home-asset="${esc(market)}"'));
check('strategy hidden market handoff is scoped to matrix',router.includes("ui.strategyTab==='matrix'"));
check('assets route does not leak stale research exchange',router.includes("if(name==='assets')return{exchange:'',market:ui.assetMarket}"));
check('sector sort exposes pressed state',sectorTable.includes('aria-pressed='));
check('mobile primary nav exposes all items without hidden horizontal discovery',shell.includes('grid-template-columns:repeat(3,1fr)'));
check('performance journey labels are user-facing',main.includes("['paper','가상매매']")&&main.includes("['strategy','전략 비교']"));

if(fail.length){
  console.error('VIEWER_UX_STATE_CONTRACT=FAIL');
  for(const item of fail)console.error(`- ${item}`);
  process.exit(1);
}
console.log('VIEWER_UX_STATE_CONTRACT=PASS');
