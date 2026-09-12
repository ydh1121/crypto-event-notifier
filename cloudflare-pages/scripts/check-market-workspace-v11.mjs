import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const repoRead=path=>fs.readFileSync(new URL(`../../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const research=read('public/modules/pages/research.js');
const quotesService=read('public/modules/services/market-quotes.js');
const quotesApi=read('functions/api/market-quotes.ts');
const interaction=read('public/modules/styles/interaction-layout-v4.css');
const scoped=repoRead('b3_trader/scoped_paper_store.py');
const publisher=repoRead('b3_trader/cloudflare_snapshot_publisher.py');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V11 market workspace build marker exists',index.includes('2026.09.12-v5.1.0-market-workspace'));
check('market workspace assets remain cache-versioned',index.includes('/modules/main.js?v=')&&index.includes('/modules/styles/interaction-layout-v4.css?v=')&&main.includes("./pages/research.js?v="));
check('market quote client remains wired through research module',main.includes("./pages/research.js?v=")&&research.includes("getMarketQuotes}from'../services/market-quotes.js?v=1'"));

check('market list has exchange-style quote columns',research.includes('market-list-columns')&&research.includes('market-quote-row')&&research.includes('market-price-cell')&&research.includes('market-change-cell'));
check('selected instrument starts with ticker and current price',research.includes('market-quote-identity')&&research.includes('market-current-price')&&research.includes('data-research-live="price"'));
check('selected instrument exposes actual market change field',research.includes('quoteChangePct')&&research.includes('change_24h_pct')&&research.includes('data-research-live="market-change"'));
check('detail API is a valid market-change fallback',research.includes('signal.change_24h_pct')&&research.includes('latest.change_24h_pct'));
check('paper account return is semantically separated',research.includes('PAPER 수익률')&&!research.includes('data-research-live="return"'));
check('missing quote change is not replaced with paper performance',research.includes("return value===null?'—'")||research.includes("value===null?'—'"));

check('D1 quote endpoint requires a viewer session',quotesApi.includes('requireSession')&&quotesApi.includes("AUTH_REQUIRED"));
check('D1 quote endpoint reads existing market detail cache only',quotesApi.includes('FROM market_details')&&quotesApi.includes('WHERE exchange=? AND strategy=?')&&!quotesApi.includes('fetch('));
check('D1 quote endpoint extracts real market fields',quotesApi.includes('signal.price')&&quotesApi.includes('signal.change_24h_pct')&&quotesApi.includes('signal.turnover_24h'));
check('quote client caches bounded reads',quotesService.includes('/api/market-quotes?exchange=')&&quotesService.includes('now-hit.ts<15000')&&quotesService.includes('new Map'));
check('research hydrates list from quote cache',research.includes("getMarketQuotes}from'../services/market-quotes.js?v=1'")&&research.includes('quoteMap=new Map()')&&research.includes('cachedQuote(row)'));
check('snapshot refresh also refreshes quote cache',research.includes('function refreshSnapshot()')&&research.includes('loadQuotes();'));

check('market filter controls cannot visually collapse',interaction.includes('#researchFilters')&&interaction.includes('grid-template-columns:repeat(3,minmax(0,1fr))!important')&&interaction.includes('min-height:32px!important'));
check('market rail gives quote columns enough width',interaction.includes('grid-template-columns:minmax(340px,360px) minmax(0,1fr)!important'));
check('only market rows scroll while controls remain visible',interaction.includes('Exchange-style market rail')&&interaction.includes('overflow:hidden!important')&&interaction.includes('.research-master .master-list')&&interaction.includes('flex:1 1 auto!important')&&interaction.includes('overflow-y:auto!important'));
check('quote is visually dominant over decision scores',interaction.includes('.market-current-price')&&interaction.includes('font-size:clamp(36px,3.2vw,48px)!important')&&interaction.includes('grid-template-areas:"price conclusion vitals"'));
check('secondary research is after the trading workspace',interaction.includes('>.research-workspace{order:1!important')&&interaction.includes('>.decision-first-extra-research{order:3!important'));

check('scoped leaderboard selects real quote fields',scoped.includes('s.price,s.change_24h_pct,s.turnover_24h,s.liquidity_score'));
check('scoped leaderboard returns real quote fields',scoped.includes('"change_24h_pct": round(_num(row.get("change_24h_pct")), 4)')&&scoped.includes('"turnover_24h": round(_num(row.get("turnover_24h")), 2)')&&scoped.includes('"liquidity_score": round(_num(row.get("liquidity_score")), 2)'));
check('snapshot compact market preserves quote fields',publisher.includes('"change_24h_pct", "turnover_24h", "liquidity_score"'));

if(fail.length){console.error('MARKET_WORKSPACE_V11=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('MARKET_WORKSPACE_V11=PASS');
