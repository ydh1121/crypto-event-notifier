import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const home=read('public/modules/pages/v4/home.js');
const ia=read('public/modules/shared/information-architecture-v5.js');
const drilldown=read('public/modules/shared/strategy-drilldown-v4.js');
const market=read('public/modules/pages/v5/market.js');
const css=read('public/modules/styles/information-architecture-v5.css');
const polish=read('public/modules/styles/polish-v5.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('v5 styles load after v4 decision workspace',index.includes('information-architecture-v5.css')&&index.includes('polish-v5.css')&&index.indexOf('decision-workspace-v4.css')<index.indexOf('information-architecture-v5.css')&&index.indexOf('information-architecture-v5.css')<index.indexOf('polish-v5.css'));
check('market route uses dedicated v5 page',main.includes('createMarketPage')&&main.includes("'dashboard-detail':()=>createMarketPage"));
check('all functional routes remain wired',['createResearchPage','createAssetsPage','createPaperPage','createStrategyPage','createSectorsPage','createRecordsPage','createSystemPage'].every(value=>main.includes(value)));
check('information architecture receives viewer state',main.includes('installInformationArchitectureV5({root,store})'));
check('coin market theme navigation remains grouped',main.includes("['research','코인']")&&main.includes("['dashboard-detail','시장현황']")&&main.includes("['sectors','테마']"));
check('secondary navigation is prominent',css.includes(".journey-nav::before{content:'보기'")&&css.includes('min-width:116px!important')&&css.includes('font-size:16px!important'));
check('secondary navigation stays visible on mobile',css.includes('grid-template-columns:repeat(3,minmax(0,1fr))!important'));

check('home has decision-first priority',home.includes('오늘 볼 순서')&&home.includes('1 · 먼저 볼 코인')&&home.includes('2 · 내 자산 확인')&&home.includes('3 · 모의투자 검증'));
check('home keeps existing functional sections',["sectionHead('시장현황'","sectionHead('코인'","sectionHead('내 자산'","sectionHead('최근 거래'"].every(value=>home.includes(value)));
check('home focus has responsive styling',polish.includes('.v5-home-focus>div{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))')&&polish.includes('.v5-home-focus>div{grid-template-columns:1fr}'));
check('legacy chip rows wrap instead of side scroll',polish.includes('#pageRoot .subnav,#pageRoot .chip-row,#pageRoot .sector-filter-chips{overflow-x:visible!important')&&polish.includes('flex-wrap:wrap!important'));

check('coin decision modes exist',ia.includes('data-v5-mode="short"')&&ia.includes('data-v5-mode="swing"')&&ia.includes('data-v5-mode="dca"'));
check('six timeframes exist',['15m','30m','1h','4h','1d','1w'].every(value=>ia.includes(`data-v5-timeframe="${value}"`)));
check('missing calculations are explicit',ia.includes('아직 계산하지 않음')&&ia.includes('가격을 임의로 만들어 표시하지 않습니다'));
check('accumulation suitability criteria exist',['프로젝트 존속 가능성','실제 사업·이용 실적','주요 투자사·재무 지원','사업성','개발·운영 지속성','공급 구조와 장기 부담'].every(value=>ia.includes(value)));
check('decision lens avoids developer wording',!ia.includes('백엔드')&&!ia.includes('API')&&!ia.includes('Cloudflare'));
check('coin detail is grouped into current evidence records',ia.includes("label:'현재 계산'")&&ia.includes("label:'판단 근거'")&&ia.includes("label:'기록'"));
check('assets are grouped by decision calculator exchange',ia.includes("label:'관리 판단'")&&ia.includes("label:'추가매수 계산'")&&ia.includes("label:'거래소 비교'"));
check('paper is grouped into plan history records',ia.includes("label:'현재 매매계획'")&&ia.includes("label:'성적 흐름'")&&ia.includes("label:'최근 기록'"));
check('strategy evidence is tabbed',ia.includes("label:'코인별 성과'")&&ia.includes("label:'성적·검증'"));
check('sector detail is tabbed',ia.includes("label:'테마 코인'")&&ia.includes("label:'흐름'"));

check('strategy selector has no horizontal scrolling',css.includes('#pageRoot[data-page-route="strategy"] .strategy-table{max-height:none!important;max-width:100%!important;overflow:visible!important'));
check('strategy coin table has no horizontal scrolling',css.includes('#pageRoot[data-page-route="strategy"] .strategy-breakdown-table{max-height:none!important;max-width:100%!important;overflow:visible!important'));
check('v5 owned tables cannot force page side scroll',polish.includes('overflow-x:visible!important')&&polish.includes('strategy-breakdown-table')&&polish.includes('v5-market-mover-table'));
check('strategy coin metrics stay visible',['확정 손익','보유 손익','최대 하락','완료 거래','승률','상태'].every(value=>css.includes(`content:'${value}'`)));
check('strategy drilldown carries context',drilldown.includes('researchSourceStrategyExperiment')&&drilldown.includes('researchSourceStrategyLabel')&&drilldown.includes('researchDecisionMode'));
check('strategy drilldown still targets research',drilldown.includes('researchMarket:market')&&drilldown.includes("navigate('research')"));

check('market page separates major coins exchanges and movers',market.includes('비트코인 · 이더리움')&&market.includes('거래소별 시장 상태')&&market.includes('변동이 큰 코인'));
check('market page links coin rows to detail',market.includes('data-v5-market')&&market.includes("navigate?.('research')"));
check('external-event reaction is not fabricated',market.includes('대외 이벤트 반응')&&market.includes('충분히 누적한 뒤 실제 계산값만'));
check('market page avoids internal phase wording',!market.includes('PHASE')&&!market.includes('백엔드')&&!market.includes('데이터 계약'));
check('market layout is responsive',css.includes('.v5-market-status>div{grid-template-columns:1fr}')&&css.includes('.v5-market-majors>div{grid-template-columns:1fr}'));
check('v5 dark mode has explicit coverage',css.includes('html[data-theme="dark"] .journey-nav')&&css.includes('html[data-theme="dark"] .v5-lens-status')&&polish.includes('html[data-theme="dark"] .v5-home-focus button'));

if(fail.length){console.error('INFORMATION_ARCHITECTURE_V5_CONTRACT=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('INFORMATION_ARCHITECTURE_V5_CONTRACT=PASS');
