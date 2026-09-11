import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const research=read('public/modules/pages/research.js');
const css=read('public/modules/styles/decision-first-v7.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('decision-first stylesheet is loaded',index.includes('/modules/styles/decision-first-v7.css?v=1'));
check('decision-first stylesheet loads after visual QA',index.indexOf('visual-qa-v6.css')<index.indexOf('decision-first-v7.css'));
check('canonical interaction layer loads after decision-first',index.indexOf('decision-first-v7.css')<index.indexOf('interaction-layout-v4.css'));
check('main cache is refreshed for V8',index.includes('/modules/main.js?v=93'));
check('research module cache is refreshed',main.includes("./pages/research.js?v=42"));

check('inert decision lens is not installed',!main.includes('installCoinDecisionLens'));
check('research no longer exposes fake mode selector',!research.includes('data-decision-mode'));
check('research no longer exposes fake timeframe selector',!research.includes('data-decision-frame'));
check('research starts with one conclusion',research.includes('먼저 볼 것')&&research.includes('decision-first-conclusion'));
check('research exposes only three detail layers',['summary','plan','history'].every(value=>research.includes(`tabButton('${value}'`)));
check('secondary listing research is collapsed',research.includes('<details class="decision-first-extra-research">'));

check('coin selection updates detail without full page render',research.includes("selectListRow(market);renderDetail({refreshDetail:true})"));
check('filter updates list locally',research.includes('updateFilterState();const list=filteredRows();ensureSelected(list);renderList(list)'));
check('filter keeps current detail in place when selection survives',research.includes('else patchDetailLive();return'));
check('snapshot uses local refresh path',research.includes("if(m.type==='snapshot')refreshSnapshot()"));
check('snapshot live values patch in place',research.includes('function patchDetailLive()')&&research.includes('data-research-live="decision"')&&research.includes('data-research-live="price"'));
check('snapshot avoids unconditional detail rerender',research.includes("if(previousMarket!==ui().researchMarket||!patchDetailLive())renderDetail({refreshDetail:previousMarket!==ui().researchMarket})"));
check('cached detail prevents needless refetch',research.includes('if(cached&&!refreshDetail)return'));

check('V7 hides obsolete decision lens defensively',css.includes('.v4-refine-decision-lens')&&css.includes('display:none!important'));
check('primary conclusion has stronger visual hierarchy',css.includes('.decision-first-conclusion h3')&&css.includes('font-size:clamp(28px,3vw,42px)'));
check('detail navigation is flat tabs not pill cards',css.includes('.decision-first-tabs button')&&css.includes('border-radius:0!important'));
check('simple mode hides secondary charts',css.includes('html[data-reader-mode="simple"]')&&css.includes('.decision-first-secondary-chart'));

if(fail.length){console.error('DECISION_FIRST_V7=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('DECISION_FIRST_V7=PASS');
