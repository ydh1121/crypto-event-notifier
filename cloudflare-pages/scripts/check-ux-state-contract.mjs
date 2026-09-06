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
const amountUx=read('public/modules/shared/amount-input-ux.js');
const rebuild=read('public/modules/styles/rebuild-v2.css');

check('sector owns its main-nav active state',index.includes('data-route="sectors"')&&!router.includes("sectors:'research'")&&!router.includes("sectors: 'research'"));
check('strategy route remains under performance workspace',router.includes("strategy:'paper'")||router.includes("strategy: 'paper'"));
check('strategy overview state is explicit',store.includes('strategyOverviewExperiment'));
check('strategy selection drives inline coin breakdown',strategy.includes('id="strategyBreakdown"')&&strategy.includes('renderBreakdown(chosen)')&&strategy.includes('data-strategy-coin-experiment="${esc(key(chosen))}"'));
check('separate strategy coin tab is retired',!strategy.includes('data-strategy-tab="coins"'));
check('strategy row selection rerenders full selected journey',/const row=e\.target\.closest\('\[data-strategy-key\]'\);[\s\S]{0,500}renderOverview\(/.test(strategy));
check('strategy overview status counts use displayed rows',strategy.includes('const states=rows.map(row=>candidateLabel(row,criteria)[1])'));
check('strategy breakdown sort and search are visible',strategy.includes('data-strategy-coin-sort')&&strategy.includes('data-strategy-breakdown-search'));
check('strategy matrix search is isolated from breakdown search',strategy.includes("matrixSearch=''")&&strategy.includes('data-strategy-matrix-search'));
check('paper has execution-strategy filter state',store.includes('paperStrategyFilter'));
check('paper has visible execution-strategy filter',paper.includes('data-paper-strategy'));
check('paper strategy filter uses execution row strategy',paper.includes('paperStrategy(store.get(),ex,r)'));
check('home detail link carries visible holding',home.includes('data-home-asset="${esc(row.market)}"'));
check('strategy hidden market handoff is scoped to matrix',router.includes("ui.strategyTab==='matrix'"));
check('assets route does not leak stale research exchange',router.includes("if(name==='assets')return{exchange:'',market:ui.assetMarket}"));
check('sector sort exposes pressed state',sectorTable.includes('aria-pressed='));
check('mobile primary nav exposes all items without hidden horizontal discovery',shell.includes('grid-template-columns:repeat(3,1fr)'));
check('performance journey labels are user-facing',main.includes("['paper','가상매매']")&&main.includes("['strategy','방법 비교']"));
check('averaging amount presets exceed one million',amountUx.includes("[100_000_000,'1억원']")&&amountUx.includes("[10_000_000,'1,000만원']"));
check('averaging amount input has no one-million cap',amountUx.includes("input.removeAttribute('max')")&&amountUx.includes("input.setAttribute('placeholder','예: 10000000')"));
check('amount presets trigger existing calculator input flow',amountUx.includes("dispatchEvent(new Event('input',{bubbles:true}))")&&main.includes('installAmountInputUx(root)'));

check('v2 shell stylesheet loaded',index.includes('/modules/styles/rebuild-v2.css?v=1'));
check('v2 home has no hero layout',home.includes('v2-status-strip')&&home.includes('v2-table')&&!home.includes('home-answer'));
check('v2 visible shell is Korean',index.includes('가상자산 상태판')&&index.includes('종류별 보기')&&index.includes('가상매매'));
check('v2 shell avoids gradient decoration',!rebuild.includes('linear-gradient')&&!rebuild.includes('radial-gradient'));
check('v2 shell avoids shadow decoration',rebuild.includes('box-shadow:none'));

if(fail.length){
  console.error('VIEWER_UX_STATE_CONTRACT=FAIL');
  for(const item of fail)console.error(`- ${item}`);
  process.exit(1);
}
console.log('VIEWER_UX_STATE_CONTRACT=PASS');
