import fs from'node:fs';
const read=path=>fs.readFileSync(new URL(`../${path}`,import.meta.url),'utf8');
const files={
  shell:read('public/index.html'),
  home:read('public/modules/pages/v4/home.js'),
  market:read('public/modules/pages/v5/market.js'),
  ia:read('public/modules/shared/information-architecture-v5.js'),
};
const normalizer=read('public/modules/shared/mainstream-ui.js');
const fail=[];
const check=(name,value)=>{if(!value)fail.push(name)};
const banned=['READ ONLY','PAPER','Cloudflare','GitHub','SQLite','Profit Factor','NO RAW CANDLES','PHASE','백엔드','데이터 계약'];
for(const[name,text]of Object.entries(files))for(const word of banned)check(`${name} primary surface hides ${word}`,!text.includes(word));
const legacyTerms=['READ ONLY','PAPER','Profit Factor','NO RAW CANDLES','CEX','DEX','리서치','섹터','평단','물타기','익절','손절','진입','Cloudflare','GitHub','SQLite','Supervisor'];
for(const word of legacyTerms)check(`legacy normalizer covers ${word}`,normalizer.includes(`['${word}'`));
check('primary mode labels are Korean',files.ia.includes('>단타</button>')&&files.ia.includes('>스윙</button>')&&files.ia.includes('>적립식</button>'));
check('primary time labels are Korean',files.ia.includes('>15분</button>')&&files.ia.includes('>30분</button>')&&files.ia.includes('>1시간</button>')&&files.ia.includes('>4시간</button>')&&files.ia.includes('>일봉</button>')&&files.ia.includes('>주봉</button>'));
check('user-facing missing-data wording is plain Korean',files.ia.includes('아직 계산하지 않음')&&files.market.includes('아직 연결되지 않았습니다'));
if(fail.length){console.error('V5_VISIBLE_LANGUAGE=FAIL');for(const item of fail)console.error(`- ${item}`);process.exit(1)}
console.log('V5_VISIBLE_LANGUAGE=PASS');
