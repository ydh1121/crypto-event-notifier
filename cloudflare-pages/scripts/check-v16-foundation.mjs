import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const index=read('public/index.html');
const main=read('public/modules/main.js');
const fees=read('public/modules/shared/trading-fees-v16.js');
const rails=read('public/modules/shared/rail-controls-v16.js');
const compact=read('public/modules/styles/compact-v16.css');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};

check('V16 build marker exists',index.includes('2026.09.17-v6.0.0-v16-foundation'));
check('V16 compact stylesheet loads after viewport layer',index.includes('/modules/styles/compact-v16.css?v=1')&&index.indexOf('viewport-first-v9.css')<index.indexOf('compact-v16.css'));
check('V16 rail control module is cache-versioned and installed',main.includes("./shared/rail-controls-v16.js?v=1")&&main.includes('installRailControlsV16({store})'));
check('Bithumb coupon fee is fixed at 0.04 percent',fees.includes('bithumb:0.0004')&&fees.includes("bithumb:'빗썸 쿠폰 0.04%'"));
check('Upbit KRW fee is fixed at 0.05 percent',fees.includes('upbit:0.0005')&&fees.includes("upbit:'업비트 KRW 0.05%'"));
check('fee utility exposes round trip totals',fees.includes('total_fee_krw')&&fees.includes('sell_net_krw')&&fees.includes('buy_total_krw'));
check('research rail offers ticker price 24h opportunity sorting',['티커','현재가','24h','기회'].every(value=>rails.includes(`label:'${value}'`)));
check('asset rail offers value price pnl volume sorting',['평가액','현재가','손익률','수량'].every(value=>rails.includes(`label:'${value}'`)));
check('research search blocks legacy selection-changing handler',rails.includes("document.addEventListener('input',onInputCapture,true)")&&rails.includes('event.stopPropagation()'));
check('research search filters existing rows without selecting them',rails.includes('row.hidden=!show')&&!rails.includes('researchMarket:'));
check('rail sort state persists independently',rails.includes('cryptoViewerRailSortV16')&&rails.includes('localStorage.setItem'));
check('rail overflow is explicitly contained',compact.includes('overflow-x:hidden!important')&&compact.includes('.market-quote-row')&&compact.includes('.asset-quote-row'));
check('long explanatory copy is suppressed',compact.includes('.strategy-context-line')&&compact.includes('.calculator-note')&&compact.includes('.records-live-note')&&compact.includes('display:none!important'));

if(fail.length){console.error('V16_FOUNDATION=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V16_FOUNDATION=PASS');
