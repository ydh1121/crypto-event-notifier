import fs from 'node:fs';
import path from 'node:path';

const ROOT=path.resolve(process.cwd());
const read=rel=>fs.readFileSync(path.join(ROOT,rel),'utf8');
const fail=message=>{console.error(`senior-korean-contract: ${message}`);process.exitCode=1};
const requireText=(text,needle,label)=>{if(!text.includes(needle))fail(`${label}: missing ${needle}`)};

const publicIndex=read('public/index.html');
const main=read('public/modules/main.js');
const publicGuard=read('public/modules/shared/senior-korean.js');
const publicSystemGuard=read('public/modules/shared/senior-korean-system.js');
const publicCss=read('public/modules/styles/senior-korean.css');
const publicSystemCss=read('public/modules/styles/senior-korean-system.css');
const localIndex=read('../dashboard/index.html');
const localGuard=read('../dashboard/senior-korean.js');
const localCss=read('../dashboard/senior-korean.css');

for(const route of ['dashboard','dashboard-detail','research','assets','paper','strategy','sectors','records','system']){
  requireText(main,`${route}:`, 'public route preservation');
}
for(const id of ['authView','loginForm','bootstrapForm','inviteForm','mainNav','readerModeControl','systemStatusBtn','userMenuBtn','logoutBtn','pageRoot']){
  requireText(publicIndex,`id="${id}"`,'public function entry preservation');
}
for(const route of ['dashboard','research','sectors','assets','paper','records']){
  requireText(publicIndex,`data-route="${route}"`,'public navigation preservation');
}
for(const id of [
  'pauseBtn','resumeBtn','killBtn','resetKillBtn','addAssetForm','tickerInput','assetSelect','priceChart','scoreChart',
  'performanceGrid','equityChart','marketPerformance','performanceNote','refreshActivity','fillsList','eventsList','runtimeConfigForm',
  'telegramSettings','telegramTest','backupNow','syncNow','phoneAccessBody','systemDetail','settingsDialog','connectionForm','telegramDialog','telegramForm'
]){
  requireText(localIndex,`id="${id}"`,'local function entry preservation');
}
for(const script of ['app.js','plain-language.js','portfolio-tools.js','ux-stability.js','navigation-v3.js','demo-research.js','research-capital.js','research-components.js','phase5-gates.js','strategy-lab-local.js','senior-korean.js']){
  requireText(localIndex,script,'local script preservation');
}
for(const asset of ['senior-korean.css','senior-korean-system.css','senior-korean.js','senior-korean-system.js']){
  requireText(publicIndex,asset,'public presentation layer');
}

const visibleStatic=text=>text
  .replace(/<!--[\s\S]*?-->/g,' ')
  .replace(/<script\b[\s\S]*?<\/script>/gi,' ')
  .replace(/<style\b[\s\S]*?<\/style>/gi,' ')
  .replace(/<[^>]+>/g,' ')
  .replace(/&[^;]+;/g,' ')
  .replace(/\b(?:BTC|ETH|XRP|SEI|SOL|KRW-SOL)\b/g,' ')
  .replace(/\s+/g,' ')
  .trim();
for(const [label,text] of [['public index',publicIndex],['local index',localIndex]]){
  const visible=visibleStatic(text);
  if(/[A-Za-z]/.test(visible)){
    const sample=visible.match(/.{0,35}[A-Za-z][A-Za-z0-9 ./_-]{0,35}/)?.[0]||'unknown';
    fail(`${label}: visible Latin text remains near "${sample}"`);
  }
}

for(const token of ['PAPER','Adaptive','GitHub','Cloudflare','SQLite','Parquet','Regime','Entry','Strategy','Telegram','Backup','System','DEX','OHLCV']){
  const covered=publicGuard.includes(token)||publicSystemGuard.includes(token);
  if(!covered)fail(`public guard does not cover ${token}`);
}
for(const token of ['PAPER','GitHub','Cloudflare','Regime','Entry','Strategy','Telegram','Backup','System','Kill switch']){
  if(!localGuard.includes(token))fail(`local guard does not cover ${token}`);
}
for(const token of ['전략','섹터','포지션','평단','진입','익절','손절','물타기','유동성','호가','스프레드','슬리피지','리스크']){
  const covered=publicGuard.includes(token)||publicSystemGuard.includes(token)||localGuard.includes(token);
  if(!covered)fail(`plain-Korean guard does not cover ${token}`);
}

for(const [label,css] of [['public senior css',publicCss],['public system css',publicSystemCss],['local senior css',localCss]]){
  if(/linear-gradient|radial-gradient|conic-gradient/i.test(css))fail(`${label}: gradient detected`);
}
requireText(publicSystemCss,'.technical-detail-row','technical detail hiding');
requireText(publicCss,'prefers-reduced-motion','public reduced-motion support');
requireText(localCss,'prefers-reduced-motion','local reduced-motion support');

if(!process.exitCode)console.log('senior-korean-contract: PASS');
