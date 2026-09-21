import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const dashboard=read('public/modules/styles/dashboard.css');
const sectorsCss=read('public/modules/styles/sectors.css');
const sectors=read('public/modules/pages/sectors-v36.js');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V19 cache lineage is active',
  index.includes('/modules/styles/dashboard.css?v=4')&&
  index.includes('/modules/styles/sectors.css?v=3')&&
  index.includes('modules/main.js?v=100.0')&&
  main.includes("sectors-v36.js?v=47"));

check('market dashboard has one primary overview path',
  dashboard.includes('grid-template-areas:"market asset" "market paper"')&&
  dashboard.includes('.dashboard-overview-grid>.market-overview{grid-area:market')&&
  dashboard.includes('.dashboard-overview-grid>.asset-overview{grid-area:asset')&&
  dashboard.includes('.dashboard-overview-grid>.paper-overview{grid-area:paper'));

check('watch list is primary over sector and strategy supports',
  dashboard.includes('.dashboard-intel-grid>.watch-panel{grid-column:1;grid-row:1/3')&&
  dashboard.includes('.dashboard-intel-grid>.sector-dashboard{grid-column:2;grid-row:1')&&
  dashboard.includes('.dashboard-intel-grid>.strategy-validity{grid-column:2;grid-row:2'));

check('theme summary is a fact strip not four detached cards',
  sectorsCss.includes('.sector-summary-grid{')&&
  sectorsCss.includes('gap:0;')&&
  sectorsCss.includes('.sector-summary-grid>div{')&&
  sectorsCss.includes('border-right:1px solid var(--line)'));

check('theme coin workspace no longer keeps a permanent third rail',
  sectorsCss.includes('.sector-coin-workspace{')&&
  sectorsCss.includes('grid-template-columns:minmax(0,1fr)')&&
  sectorsCss.includes('.sector-coin-disclosure{')&&
  sectorsCss.includes('.sector-coin-disclosure .sector-coin-profile{')&&
  sectorsCss.includes('position:static;'));

check('project evidence is progressive and native',
  sectors.includes('<details class="sector-coin-disclosure">')&&
  sectors.includes('data-sector-profile-label')&&
  sectors.includes("disclosure.open=true")&&
  sectors.includes('id="sectorCoinProfile"')&&
  sectors.includes('id="sectorCoinTable"')&&
  sectors.includes('data-sector-research'));

if(fail.length){
  console.error('PAGE_HIERARCHY_V19=FAIL');
  for(const item of fail)console.error(`- ${item}`);
  process.exit(1);
}
console.log('PAGE_HIERARCHY_V19=PASS');
