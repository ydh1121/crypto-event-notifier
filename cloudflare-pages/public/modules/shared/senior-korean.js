const ROOT=document.documentElement;
const MAP=[
  [/Crypto Research/gi,'가상자산 연구실'],
  [/READ\s*ONLY\s*[·-]?\s*PAPER/gi,'조회 전용 · 가상매매'],
  [/READ\s*ONLY/gi,'조회 전용'],
  [/FIRST\s*SETUP/gi,'처음 설정'],
  [/INVITE/gi,'초대'],
  [/PAPER/gi,'가상매매'],
  [/Adaptive/gi,'기본 매매 방식'],
  [/Strategy\s*Lab/gi,'매매 방식 비교'],
  [/Forward\s*test/gi,'앞으로의 결과 확인'],
  [/Phase\s*5/gi,'다음 단계'],
  [/Gate\s*Matrix/gi,'준비 상태'],
  [/GitHub\s*Actions\s*CI/gi,'자동 점검 결과'],
  [/GitHub/gi,'코드 보관소'],
  [/Cloudflare/gi,'외부 보안 연결'],
  [/Google\s*Drive/gi,'온라인 백업'],
  [/Drive/gi,'온라인 백업'],
  [/SQLite/gi,'저장 기록'],
  [/Parquet(?:\/ZSTD)?/gi,'분석 보관 자료'],
  [/Warehouse/gi,'분석 보관함'],
  [/Viewer/gi,'조회 화면'],
  [/Snapshot/gi,'최근 기록'],
  [/Health/gi,'정상 여부'],
  [/Remote\s*access/gi,'외부 연결'],
  [/Tailscale/gi,'다른 안전 연결'],
  [/HTTPS/gi,'보안 연결'],
  [/API/gi,'연결 기능'],
  [/BUY_CANDIDATE/gi,'매수 관심 알림'],
  [/Bot\s*\/\s*Chat/gi,'알림 연결'],
  [/Bot\s*token/gi,'알림 비밀키'],
  [/Chat\s*ID/gi,'알림 대상 정보'],
  [/rclone/gi,'온라인 백업 도구'],
  [/DEX/gi,'탈중앙 거래소'],
  [/OHLCV/gi,'가격 흐름 기록'],
  [/UI\s*BUILD/gi,'화면 버전'],
  [/\bUI\b/gi,'화면'],
  [/\bDB\b/gi,'저장 기록'],
  [/\bAI\b/gi,'자동 분석'],
  [/\bSystem\b/gi,'프로그램'],
  [/\bMarket\s*pulse\b/gi,'시장 흐름'],
  [/\bMarket\b/gi,'시장'],
  [/\bRegime\b/gi,'시장 분위기'],
  [/\bEntry\b/gi,'매수 시점'],
  [/\bStrategy\b/gi,'매매 방식'],
  [/\bControl\b/gi,'관리'],
  [/\bJournal\b/gi,'기록'],
  [/\bEquity\b/gi,'평가금액'],
  [/\bTelegram\b/gi,'매수 알림'],
  [/\bBackup\b/gi,'백업'],
  [/\bSync\b/gi,'동기화'],
  [/\bLocal\b/gi,'이 컴퓨터'],
  [/\bOwner\b/gi,'관리자'],
  [/\bPASS\b/gi,'통과'],
  [/\bFAIL\b/gi,'실패'],
  [/\bunknown\b/gi,'확인 중'],
  [/\boffline\b/gi,'연결 끊김'],
  [/\brunning\b/gi,'실행 중'],
  [/\bhealthy\b/gi,'정상'],
  [/\bdegraded\b/gi,'확인 필요'],
  [/\bstarting\b/gi,'시작 중'],
  [/\bstopped\b/gi,'중지'],
  [/\bidle\b/gi,'대기'],
  [/\bsuccess\b/gi,'성공'],
  [/\berror\b/gi,'문제'],
  [/\bworkflow\b/gi,'자동 점검'],
  [/\bcomponent\b/gi,'기능'],
  [/\bsource\b/gi,'원본'],
  [/\bprofile\b/gi,'기준'],
  [/\bportfolio\b/gi,'보유 자산'],
  [/\bv(?=\d)/g,'버전 '],
  [/전략 비교/g,'매매 방식 비교'],
  [/실행 전략/g,'현재 매매 방식'],
  [/전략 기준/g,'매매 기준'],
  [/전략 참고/g,'매매 참고'],
  [/전략의/g,'매매 방식의'],
  [/전략상/g,'매매 방식상'],
  [/전략 실험/g,'매매 방식 시험'],
  [/전략/g,'매매 방식'],
  [/섹터별/g,'종류별'],
  [/섹터/g,'종류'],
  [/대시보드/g,'화면'],
  [/포지션/g,'보유 상태'],
  [/평단/g,'평균 매수가'],
  [/평균 진입가/g,'평균 매수가'],
  [/진입가/g,'매수가'],
  [/미진입/g,'아직 사지 않음'],
  [/진입 기준/g,'매수 기준'],
  [/진입 비중/g,'매수 비중'],
  [/진입/g,'매수'],
  [/익절/g,'수익 실현'],
  [/손절/g,'손실 제한'],
  [/물타기/g,'추가 매수'],
  [/미실현 손익/g,'현재 손익'],
  [/실현 손익/g,'확정 손익'],
  [/최대낙폭/g,'가장 크게 줄어든 폭'],
  [/최대 낙폭/g,'가장 크게 줄어든 폭'],
  [/최대 하락폭/g,'가장 크게 줄어든 폭'],
  [/유동성/g,'거래 활발함'],
  [/호가 불균형/g,'사고파는 주문 차이'],
  [/호가 균형/g,'사고파는 주문 균형'],
  [/호가/g,'현재 주문 가격'],
  [/스프레드/g,'사고파는 가격 차이'],
  [/슬리피지/g,'예상과 실제 가격 차이'],
  [/쿨다운/g,'다시 기다리는 시간'],
  [/리스크/g,'위험'],
  [/청산/g,'매도 완료'],
  [/스캔/g,'확인'],
  [/스냅샷/g,'기록'],
  [/게이트/g,'검증 항목'],
  [/노출/g,'투입 금액'],
  [/사이드카/g,'보조 기능'],
  [/프로필/g,'기준'],
  [/워크플로/g,'자동 점검'],
  [/커밋/g,'저장 버전'],
  [/브랜치/g,'작업 줄기'],
  [/풀\/리셋\/푸시/gi,'가져오기·되돌리기·올리기'],
  [/풀\b/gi,'가져오기'],
  [/리셋/gi,'되돌리기'],
  [/푸시/gi,'올리기'],
];

const PHRASES=new Map([
  ['지금 어떤 코인을 볼까?','지금 먼저 볼 코인'],
  ['내 코인은 괜찮을까?','내 코인 상태'],
  ['이 매매 방식은 잘하고 있나?','가상매매 결과'],
  ['오늘 뭐가 바뀌었나?','최근 변화'],
  ['조금 더 자세히 보고 싶다면','더 보고 싶은 내용'],
  ['전략 비교','매매 방식 비교'],
  ['상세 현황','자세한 현황'],
  ['시스템','연결과 보관 상태'],
  ['자산','내 코인'],
  ['가상매매 성적','가상매매 결과'],
  ['PAPER 평가액','가상매매 금액'],
  ['전체 스캔','전체 확인'],
  ['코인별 1,000만원 가상매매','코인마다 같은 금액으로 가상매매'],
  ['전체 코인 자동매매 연구','전체 코인 가상매매 비교'],
  ['프로그램 상태','실행 상태'],
]);

function cleanText(value){
  let text=String(value??'');
  const exact=PHRASES.get(text.trim());
  if(exact&&text.trim()===text)return exact;
  for(const[pattern,replacement]of MAP)text=text.replace(pattern,replacement);
  return text;
}

function textNodes(root){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(node){
    const parent=node.parentElement;
    if(!parent||parent.closest('script,style,noscript,code,pre'))return NodeFilter.FILTER_REJECT;
    return node.nodeValue?.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;
  }});
  const nodes=[];let node;while((node=walker.nextNode()))nodes.push(node);return nodes;
}

function polishNode(root=document.body){
  if(!root)return;
  for(const node of textNodes(root)){
    const next=cleanText(node.nodeValue);
    if(next!==node.nodeValue)node.nodeValue=next;
  }
  const elements=root.matches?.('*')?[root,...root.querySelectorAll('*')]:[...root.querySelectorAll('*')];
  for(const el of elements){
    for(const name of ['title','aria-label','placeholder']){
      if(!el.hasAttribute?.(name))continue;
      const before=el.getAttribute(name),after=cleanText(before);
      if(before!==after)el.setAttribute(name,after);
    }
  }
}

function simplifyShell(){
  document.title='가상자산 연구실';
  const brand=document.querySelector('.brand strong');if(brand)brand.textContent='가상자산 연구실';
  const sub=document.querySelector('.brand span');if(sub)sub.textContent='조회 전용 · 가상매매';
  const labels={dashboard:'홈',research:'코인 찾기',sectors:'종류별 보기',assets:'내 코인',paper:'가상매매',records:'기록'};
  document.querySelectorAll('#mainNav [data-route]').forEach(button=>{if(labels[button.dataset.route])button.textContent=labels[button.dataset.route]});
  const simple=document.querySelector('[data-reader-mode="simple"]');if(simple)simple.textContent='간단히 보기';
  const detail=document.querySelector('[data-reader-mode="detail"]');if(detail)detail.textContent='자세히 보기';
}

function simplifyHome(){
  document.querySelectorAll('.home-panel header>div>span').forEach(node=>node.setAttribute('aria-hidden','true'));
  const replacements={
    '지금 어떤 코인을 볼까?':'지금 먼저 볼 코인',
    '내 코인은 괜찮을까?':'내 코인 상태',
    '이 매매 방식은 잘하고 있나?':'가상매매 결과',
    '오늘 뭐가 바뀌었나?':'최근 변화',
    '조금 더 자세히 보고 싶다면':'더 보고 싶은 내용',
  };
  document.querySelectorAll('.home-panel h3,.home-more h3').forEach(node=>{const value=node.textContent.trim();if(replacements[value])node.textContent=replacements[value]});
}

function simplifySystem(){
  if(document.querySelector('[data-page-route="system"]'))return;
  const route=document.getElementById('pageRoot')?.dataset.pageRoute;
  if(route!=='system')return;
  document.querySelectorAll('.operation-primary b,.operation-primary small').forEach(node=>{
    const text=node.textContent.trim();
    if(/^[0-9a-f]{7,40}$/i.test(text)||/^refs?\//i.test(text)||/^[\w.-]+\/[\w.-]+$/.test(text))node.textContent='정상 확인됨';
  });
  document.querySelectorAll('.system-list>div,.component-detail-grid>span,.operation-facts>span').forEach(row=>{
    const label=row.querySelector('span,small')?.textContent||'';
    if(/PID|revision|origin|ID|소스 행/i.test(label))row.classList.add('technical-detail-row');
  });
}

function polish(){
  simplifyShell();
  polishNode(document.body);
  simplifyHome();
  simplifySystem();
  ROOT.dataset.seniorKorean='ready';
}

let queued=false;
const observer=new MutationObserver(records=>{
  if(queued)return;
  if(!records.some(record=>record.type==='childList'||record.type==='characterData'))return;
  queued=true;
  requestAnimationFrame(()=>{queued=false;polish()});
});

function install(){
  polish();
  observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  document.addEventListener('click',()=>requestAnimationFrame(polish),{passive:true});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)requestAnimationFrame(polish)});
}

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
