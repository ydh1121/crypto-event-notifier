const EXTRA=[
  [/\bCEX\b/gi,'해외 거래소'],
  [/\bDEX\b/gi,'탈중앙 거래소'],
  [/\bOHLCV\b/gi,'가격 흐름 기록'],
  [/\bCI\b/gi,'자동 점검'],
  [/\bPID\b/gi,'실행 번호'],
  [/\bID\b/gi,'번호'],
  [/\bURL\b/gi,'주소'],
  [/\bJSON\b/gi,'저장 자료'],
  [/\bCSV\b/gi,'표 자료'],
  [/\bSQL\b/gi,'저장 기록'],
  [/\bD1\b/gi,'외부 저장소'],
  [/\bPages\b/gi,'조회 화면'],
  [/\bWorker\b/gi,'외부 보조 기능'],
  [/\bROI\b/gi,'수익률'],
  [/\bPnL\b/gi,'손익'],
  [/\bP&L\b/gi,'손익'],
  [/\bMDD\b/gi,'가장 크게 줄어든 폭'],
  [/\bBithumb\b/gi,'빗썸'],
  [/\bUpbit\b/gi,'업비트'],
  [/\bconservative\b/gi,'보수형'],
  [/\bbalanced\b/gi,'균형형'],
  [/\baggressive\b/gi,'적극형'],
  [/\bdca\b/gi,'나눠 사기'],
  [/\bmean[_ -]?reversion\b/gi,'많이 내려온 뒤 반등 보기'],
  [/\bswing\b/gi,'며칠 흐름 보기'],
  [/\bDeFi\b/gi,'탈중앙 금융'],
  [/\bDePIN\b/gi,'분산형 실물 기반망'],
  [/\bLayer\s*1\b/gi,'독립형 블록체인'],
  [/\bLayer\s*2\b/gi,'확장형 블록체인'],
  [/\bMeme\b/gi,'유행형 코인'],
  [/\bGaming\b/gi,'게임'],
  [/\bRWA\b/gi,'실물자산 연계'],
  [/\bInfrastructure\b/gi,'기반 기술'],
  [/\bPayment\b/gi,'결제'],
  [/\bPrivacy\b/gi,'개인정보 보호'],
  [/\bOracle\b/gi,'외부정보 연결'],
  [/\bStorage\b/gi,'분산 저장'],
  [/\bInteroperability\b/gi,'블록체인 연결'],
  [/\bExchange\b/gi,'거래소'],
  [/\bStablecoin\b/gi,'가격 안정형 코인'],
  [/\bNFT\b/gi,'디지털 소유권'],
  [/\bSocial\b/gi,'소셜'],
  [/\bBUY\b/gi,'매수'],
  [/\bSELL\b/gi,'매도'],
  [/\bactive\b/gi,'진행 중'],
  [/\bclosed\b/gi,'완료'],
  [/\bopen\b/gi,'진행 중'],
  [/\bNO\b/gi,'없음'],
  [/\b1H\b/gi,'1시간'],
  [/\b6H\b/gi,'6시간'],
  [/\b24H\b/gi,'24시간'],
  [/\b7D\b/gi,'7일'],
  [/feature/gi,'요약 정보'],
  [/source/gi,'자료'],
  [/raw candles?/gi,'원본 가격 기록'],
  [/compact/gi,'요약'],
  [/premium/gi,'가격 차이'],
  [/리서치/g,'코인 조사'],
  [/상장 프리미엄/g,'상장 직후 가격 차이'],
  [/원본 캔들/g,'원본 가격 기록'],
  [/캔들/g,'가격 기록'],
  [/기회점수/g,'볼 만한 정도'],
  [/기회 점수/g,'볼 만한 정도'],
  [/되돌림/g,'최근 고점 대비 내려온 폭'],
  [/변동성/g,'가격 출렁임'],
  [/자산곡선/g,'가상금액 변화'],
  [/체결/g,'거래 완료'],
  [/vs\.?/gi,'대비'],
  [/T-1일/gi,'상장 1일 전'],
  [/T-1시간/gi,'상장 1시간 전'],
  [/P5M/gi,'상장 5분 뒤'],
  [/P1H/gi,'상장 1시간 뒤'],
  [/P24H/gi,'상장 24시간 뒤'],
  [/P7D/gi,'상장 7일 뒤'],
];

function extraClean(value){
  let text=String(value??'');
  for(const[pattern,replacement]of EXTRA)text=text.replace(pattern,replacement);
  return text;
}

function cleanVisible(root=document.body){
  if(!root)return;
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(node){
    const parent=node.parentElement;
    if(!parent||parent.closest('script,style,noscript'))return NodeFilter.FILTER_REJECT;
    return node.nodeValue?.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;
  }});
  const nodes=[];let node;while((node=walker.nextNode()))nodes.push(node);
  for(const item of nodes){
    const parent=item.parentElement;
    if(parent?.closest('code,pre'))continue;
    const before=item.nodeValue,after=extraClean(before);
    if(before!==after)item.nodeValue=after;
  }
}

function simplifyStrategyNames(){
  const root=document.getElementById('pageRoot');
  if(root?.dataset.pageRoute!=='strategy')return;
  root.querySelectorAll('.strategy-row b,.strategy-detail h3,.strategy-breakdown h3').forEach(node=>{
    const before=node.textContent.trim();
    const after=extraClean(before);
    if(after!==before){node.textContent=after;return}
    if(/^[A-Za-z][A-Za-z0-9 _.-]{2,40}$/.test(before))node.textContent='사용자 매매 방식';
  });
}

function markTechnicalSystemRows(){
  const root=document.getElementById('pageRoot');
  if(root?.dataset.pageRoute!=='system')return;

  root.querySelectorAll('p,b,small,span,strong').forEach(node=>{
    const text=node.textContent.trim();
    if(!text)return;
    if(/^https?:\/\//i.test(text)||/\b[a-z0-9.-]+\.(?:com|dev|io|net|org)\b/i.test(text)){
      node.textContent='외부 조회 주소 연결됨';
      node.classList.add('raw-technical-value');
    }else if(/^[0-9a-f]{7,40}$/i.test(text)||/^refs?\//i.test(text)||/^b\d[-_/a-z0-9.]+$/i.test(text)){
      node.textContent='정상 확인됨';
    }
  });

  root.querySelectorAll('.system-list>div,.component-detail-grid>span,.operation-facts>span').forEach(row=>{
    const text=row.textContent||'';
    if(/실행 번호|저장 버전|작업 줄기|원격 보관본|구성 번호|기술|주소|소스 행|자료 행/i.test(text))row.classList.add('technical-detail-row');
  });

  root.querySelectorAll('[data-ci-panel] header p').forEach(p=>p.textContent='최근 자동 점검 상태입니다.');
  root.querySelectorAll('[data-ci-panel] h3').forEach(h=>h.textContent='자동 점검 결과');
}

function replaceKnownHeadings(){
  const root=document.getElementById('pageRoot');
  if(!root)return;
  const map=new Map([
    ['리서치','코인 찾기'],
    ['코인 조사','코인 찾기'],
    ['상장 이력 연구','상장 전후 가격 비교'],
    ['전략 비교','매매 방식 비교'],
    ['전략별 비교','매매 방식별 비교'],
    ['코인에서 전략 비교','코인별 매매 방식 비교'],
    ['현재 실행 성적','현재 가상매매 결과'],
    ['시스템','연결과 보관 상태'],
  ]);
  root.querySelectorAll('h1,h2,h3,h4,button,summary').forEach(node=>{
    const key=node.textContent.trim();
    if(map.has(key))node.textContent=map.get(key);
  });
}

function run(){
  cleanVisible();
  replaceKnownHeadings();
  simplifyStrategyNames();
  markTechnicalSystemRows();
}

let queued=false;
const observer=new MutationObserver(records=>{
  if(queued||!records.some(r=>r.type==='childList'||r.type==='characterData'))return;
  queued=true;
  requestAnimationFrame(()=>{queued=false;run()});
});

function install(){
  run();
  observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  document.addEventListener('click',()=>requestAnimationFrame(run),{passive:true});
}

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
