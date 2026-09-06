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
  [/feature/gi,'요약 정보'],
  [/source/gi,'자료'],
  [/raw candles?/gi,'원본 가격 기록'],
  [/compact/gi,'요약'],
  [/premium/gi,'가격 차이'],
  [/리서치/g,'코인 조사'],
  [/상장 프리미엄/g,'상장 직후 가격 차이'],
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
