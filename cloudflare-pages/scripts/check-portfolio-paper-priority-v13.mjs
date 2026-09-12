import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const assets=read('public/modules/pages/assets.js');
const paper=read('public/modules/pages/paper.js');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V13 build marker exists',index.includes('2026.09.12-v5.2.0-portfolio-paper-priority'));
check('asset module remains cache-versioned',/\.\/pages\/assets\.js\?v=[^'\"]+/.test(main));
check('paper module remains cache-versioned',/\.\/pages\/paper\.js\?v=[^'\"]+/.test(main));
check('canonical interaction layer remains cache-versioned',/\/modules\/styles\/interaction-layout-v4\.css\?v=[^'\"]+/.test(index));

const workspacePos=assets.indexOf('<section class="asset-workspace">');
const historyCallPos=assets.indexOf('${renderHoldingsHistory()}');
check('asset source order is workspace before history',workspacePos>=0&&historyCallPos>workspacePos);
check('asset rail presents holdings before allocation',assets.indexOf('asset-holdings-list')>=0&&assets.indexOf('asset-holdings-list')<assets.indexOf('${renderAllocation(list,summary)}'));
check('asset holding rows expose current quote and pnl',assets.includes('asset-quote-row')&&assets.includes('${price(item.current_price)}')&&assets.includes('${pct(item.unrealized_pnl_pct)}'));
check('asset selected holding promotes current price',assets.includes('asset-position-hero')&&assets.includes('asset-current-price')&&assets.includes('${price(holding.current_price)}'));
const assetCurrent=assets.indexOf('<small>현재가</small>');
const assetAvg=assets.indexOf('<small>평균 매수가</small>');
const assetPnl=assets.indexOf('<small>평가손익</small>');
const assetPct=assets.indexOf('<small>손익률</small>');
check('asset simple facts are current avg pnl pct in order',assetCurrent>=0&&assetCurrent<assetAvg&&assetAvg<assetPnl&&assetPnl<assetPct);
check('asset visual order hack is removed',!interaction.includes('Asset source order is legacy')&&!interaction.includes('>.asset-workspace{order:2')&&!interaction.includes('>.asset-history-panel{order:3'));
check('asset history keeps spacing without order mutation',interaction.includes('Asset module now emits canonical source order')&&interaction.includes('>.asset-history-panel{margin-top:30px!important}'));

check('paper page is named by user goal',paper.includes("pageHead('모의투자'"));
check('paper list exposes position before cumulative return',paper.includes('paper-position-row')&&paper.includes("position=r.has_position?money(r.position_value_krw):'미보유'")&&paper.includes('${pct(r.return_pct)}'));
check('paper hero promotes current virtual position',paper.includes('paper-position-hero')&&paper.includes('paper-position-primary')&&paper.includes('현재 가상 포지션'));
const paperPosition=paper.indexOf('<small>현재 보유금액</small>');
const paperAvg=paper.indexOf('<small>평균 매수가</small>');
const paperUnreal=paper.indexOf('<small>미실현 손익</small>');
const paperCash=paper.indexOf('<small>남은 현금</small>');
const paperReturn=paper.indexOf('<small>누적 수익률</small>');
check('paper simple facts put live position before cumulative return',paperPosition>=0&&paperPosition<paperAvg&&paperAvg<paperUnreal&&paperUnreal<paperCash&&paperCash<paperReturn);
check('paper position hero has dominant visual rule',interaction.includes('.paper-position-primary>b')&&interaction.includes('font-size:clamp(28px,2.6vw,38px)!important'));
check('asset current price has dominant visual rule',interaction.includes('.asset-current-price')&&interaction.includes('font-size:clamp(32px,3vw,44px)!important'));

if(fail.length){console.error('PORTFOLIO_PAPER_PRIORITY_V13=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('PORTFOLIO_PAPER_PRIORITY_V13=PASS');
