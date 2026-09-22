import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const paperWorkbench=read('public/modules/pages/paper-workbench.js');
const router=read('public/modules/core/router.js');
const store=read('public/modules/core/store.js');
const live=read('public/modules/pages/live-trading.js');
const css=read('public/modules/styles/decision-workspace-v4.css');
const shell=read('public/modules/styles/shell.css');
const mainstream=read('public/modules/styles/mainstream-v4.css');
const layout=read('public/modules/styles/layout-fixes-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V22 build marker is active',index.includes('2026.09.21-v6.5.0-simplified-trading-v22'));
check('primary nav is simplified to four user destinations',
  ['data-route="live"','>실전매매</button>','data-route="paper"','>가상매매</button>','data-route="research"','>탐색</button>','data-route="records"','>기록</button>'].every(value=>index.includes(value))&&
  !index.includes('data-route="assets">자산</button>')&&
  !index.includes('data-route="strategy">전략</button>'));

check('live route is wired without deleting legacy pages',
  main.includes("createLiveTradingPage")&&main.includes("live:()=>createLiveTradingPage")&&
  ['createHomePage','createDashboardPage','createResearchPage','createAssetsPage','createPaperWorkbench','createStrategyPage','createSectorsPage','createRecordsPage','createSystemPage'].every(value=>main.includes(value))&&paperWorkbench.includes('createPaperPage')&&paperWorkbench.includes('openOverview'));

check('legacy capabilities stay reachable through secondary journeys',
  main.includes("live:[['live','실전매매'],['assets','자산(기존)']]")&&
  main.includes("paper:[['paper','가상매매'],['strategy','전략 비교']]")&&
  main.includes("research:[['research','코인 탐색'],['dashboard-detail','시장현황'],['sectors','테마']]"));

check('router carries simplified primary context',
  router.includes("'live'")&&router.includes("dashboard:'live'")&&router.includes("assets:'live'")&&router.includes("strategy:'paper'")&&
  router.includes("if(name==='live')return{exchange:ui.liveExchange,market:ui.liveMarket}")&&
  router.includes("if(to==='live')"));

check('store defaults and polling include live route',
  store.includes("route:'live'")&&store.includes("liveExchange:'bithumb'")&&store.includes("liveMarket:''")&&store.includes("liveCalculator:'average'")&&
  store.includes("new Set(['live','dashboard','research','assets','paper','strategy','records','system'])"));

check('live page reuses canonical real data and calculators',
  live.includes('rowsFor')&&live.includes('holdings')&&live.includes('strategyCoinRows')&&live.includes('strategyRows')&&
  live.includes('calculateAveraging')&&live.includes('buildHoldingPlanGuidance')&&live.includes('buildProfitProtectionGuidance')&&live.includes('getMarketDetail'));

check('dominant strategy is never invented from return ordering',
  live.includes('코인별 우세 전략을 확정할 projection이 아직 없습니다')&&
  live.includes('수익률만으로 한 전략을 임의 선택하지 않습니다')&&
  live.includes('우세 후보'));

check('recommendation rail stays explicitly pre-recommendation until evidence envelope exists',
  live.includes('상승 관찰 후보')&&live.includes('자동 추천으로 승격하지 않습니다'));

check('strategy plan exposes missing projection instead of fake values',
  live.includes('전략별 타점 미제공')&&live.includes('전략별 비중 미제공')&&live.includes('분할 비중 미제공')&&live.includes('projection 대기'));

check('averaging and profit calculators support split rows',
  live.includes('data-live-add-average')&&live.includes('data-live-add-profit')&&
  live.includes('rows.length>=8')&&live.includes('data-live-profit-pct')&&live.includes('data-live-average-amount'));

check('live page contains no order submission or holdings mutation action',
  !live.includes('/api/holding-mutations')&&!live.includes('submitOrder')&&!live.includes('placeOrder')&&!live.includes('실제 DB 반영'));

check('live polling path patches page-owned data without full route render',
  store.includes("'live'")&&live.includes("meta.type==='snapshot-live'")&&live.includes('refreshData()'));

check('V22 styling is route-scoped and avoids viewport-fixed clipping',
  css.includes('#pageRoot[data-page-route="live"] .live-context')&&
  css.includes('#pageRoot[data-page-route="live"] .live-layout')&&
  !css.includes('#pageRoot[data-page-route="live"] .live-candidates{height:calc')&&
  !css.includes('#pageRoot[data-page-route="live"] .live-candidates{max-height:calc'));

check('four-item compact navigation is consistent',
  shell.includes('grid-template-columns:repeat(4,minmax(0,1fr))')&&
  mainstream.includes('grid-template-columns:repeat(4,1fr)!important')&&
  layout.includes('.main-nav{grid-template-columns:repeat(4,minmax(0,1fr))!important}'));

if(fail.length){
  console.error('SIMPLIFIED_TRADING_V22=FAIL');
  for(const item of fail)console.error(`- ${item}`);
  process.exit(1);
}
console.log('SIMPLIFIED_TRADING_V22=PASS');
