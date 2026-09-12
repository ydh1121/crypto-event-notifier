import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const home=read('public/modules/pages/v4/home.js');
const layout=read('public/modules/styles/layout-fixes-v4.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('home module cache is refreshed',main.includes("./pages/v4/home.js?v=2.1"));
check('entry cache is refreshed for home hierarchy',index.includes('/modules/main.js?v=96.2'));
check('layout cache is refreshed for home quote columns',index.includes('/modules/styles/layout-fixes-v4.css?v=1.1'));
check('home reuses authenticated market quote cache',home.includes("getMarketQuotes}from'../../services/market-quotes.js?v=1'")&&home.includes("getMarketQuotes('bithumb')")&&home.includes("getMarketQuotes('upbit')"));
check('home coin table follows ticker price 24h decision hierarchy',home.includes('<span>코인</span><span>현재가</span><span>24h</span><span>판단</span>')&&home.includes('home-market-price')&&home.includes('home-market-change'));
check('home quote values fall back safely',home.includes('finite(cached?.price)??finite(row?.price)')&&home.includes('finite(cached?.change_24h_pct)??finite(row?.change_24h_pct)'));
check('home quote table has protected four-column geometry',layout.includes('.home-market-table .home-market-head')&&layout.includes('grid-template-columns:minmax(0,1.35fr) minmax(92px,.85fr) minmax(68px,.65fr) minmax(82px,.85fr)!important'));
check('compact home preserves ticker price and 24h while hiding lower priority decision',layout.includes('.home-market-table .home-market-head>span:nth-child(4)')&&layout.includes('display:none!important'));

if(fail.length){console.error('HOME_PRIORITY_V12=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('HOME_PRIORITY_V12=PASS');
