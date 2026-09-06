(function(){
  if(window.__seniorKoreanDashboard)return;
  window.__seniorKoreanDashboard=true;

  const MAP=[
    [/Crypto Auto Trader/gi,'가상자산 상태판'],
    [/PAPER CONTROL/gi,'가상매매 관리'],
    [/PAPER/gi,'가상매매'],
    [/Market pulse/gi,'시장 흐름'],
    [/System/gi,'프로그램'],
    [/Watchlist/gi,'살펴볼 코인'],
    [/Asset workspace/gi,'코인 상세'],
    [/Asset/gi,'코인'],
    [/Context/gi,'관련 시장'],
    [/Price/gi,'가격'],
    [/Scores/gi,'판단 점수'],
    [/Forward test/gi,'앞으로의 결과 확인'],
    [/Equity/gi,'평가금액'],
    [/By asset/gi,'코인별'],
    [/Interpretation/gi,'결과 설명'],
    [/Journal/gi,'기록'],
    [/Control/gi,'관리'],
    [/Strategy/gi,'매매 방식'],
    [/Telegram/gi,'매수 알림'],
    [/Backup\s*&\s*sync/gi,'백업과 동기화'],
    [/Backup/gi,'백업'],
    [/Sync/gi,'동기화'],
    [/Phone access/gi,'휴대폰 연결'],
    [/UI BUILD/gi,'화면 버전'],
    [/Deferred/gi,'나중에 할 기능'],
    [/GitHub/gi,'코드 보관소'],
    [/Google Drive/gi,'온라인 백업'],
    [/Drive/gi,'온라인 백업'],
    [/Cloudflare/gi,'외부 보안 연결'],
    [/Tailscale/gi,'다른 안전 연결'],
    [/HTTPS/gi,'보안 연결'],
    [/API/gi,'연결 기능'],
    [/Regime/gi,'시장 분위기'],
    [/Entry/gi,'매수 시점'],
    [/Kill switch/gi,'긴급 정지'],
    [/Kill 해제/gi,'긴급 정지 해제'],
    [/Kill/gi,'긴급 정지'],
    [/DD\b/gi,'하락폭'],
    [/bps\b/gi,'단계'],
    [/UI\b/gi,'화면'],
    [/DB\b/gi,'저장 기록'],
    [/AI\b/gi,'자동 분석'],
    [/Profile/gi,'판단 기준'],
    [/Phase\s*5/gi,'다음 단계'],
    [/Gate\s*Matrix/gi,'준비 상태'],
    [/Strategy\s*Lab/gi,'매매 방식 비교'],
    [/Adaptive/gi,'기본 매매 방식'],
    [/Photo-eBook/gi,'책처럼 넘기는'],
    [/Liquid/gi,'부드러운'],
    [/origin/gi,'원격 보관본'],
    [/token/gi,'연결 코드'],
    [/server/gi,'프로그램'],
    [/engine/gi,'자동 실행'],
    [/scan/gi,'확인'],
    [/snapshot/gi,'기록'],
    [/status/gi,'상태'],
    [/error/gi,'문제'],
    [/running/gi,'실행 중'],
    [/idle/gi,'대기'],
    [/success/gi,'성공'],
    [/failed?/gi,'실패'],
    [/warning/gi,'주의'],
    [/version/gi,'버전'],
    [/commit/gi,'저장 버전'],
    [/branch/gi,'작업 줄기'],
    [/repository/gi,'코드 보관소'],
    [/runtime/gi,'실행 설정'],
    [/local/gi,'이 컴퓨터'],
    [/remote/gi,'외부'],
    [/strategy/gi,'매매 방식'],
    [/risk/gi,'위험'],
    [/portfolio/gi,'보유 자산'],
    [/exposure/gi,'투입 금액'],
    [/spread/gi,'사고파는 가격 차이'],
    [/slippage/gi,'예상과 실제 가격 차이'],
    [/cooldown/gi,'다시 기다리는 시간'],
    [/drawdown/gi,'하락폭'],
    [/position/gi,'보유 상태'],
    [/entry/gi,'매수'],
    [/exit/gi,'매도'],
    [/buy candidate/gi,'매수 관심'],
    [/프로필/g,'판단 기준'],
    [/포지션/g,'보유 상태'],
    [/평단/g,'평균 매수가'],
    [/진입/g,'매수'],
    [/익절/g,'수익 실현'],
    [/손절/g,'손실 제한'],
    [/물타기/g,'추가 매수'],
    [/청산/g,'매도 완료'],
    [/유동성/g,'거래 활발함'],
    [/호가 불균형/g,'사고파는 주문 차이'],
    [/호가 균형/g,'사고파는 주문 균형'],
    [/호가/g,'현재 주문 가격'],
    [/스프레드/g,'사고파는 가격 차이'],
    [/슬리피지/g,'예상과 실제 가격 차이'],
    [/쿨다운/g,'다시 기다리는 시간'],
    [/리스크/g,'위험'],
    [/스캔/g,'확인'],
    [/스냅샷/g,'기록'],
    [/대시보드/g,'화면'],
    [/전략/g,'매매 방식'],
    [/섹터/g,'종류'],
  ];

  const EXACT=new Map([
    ['Crypto Auto Trader','가상자산 상태판'],
    ['코인 상태판','가상자산 상태판'],
    ['현재 상태','오늘 확인할 내용'],
    ['시장을 보고, 매수은 따로 판단합니다.','시장 분위기와 지금 살 시점을 함께 봅니다.'],
    ['감시 자산','살펴볼 코인'],
    ['자산 분석','코인 자세히 보기'],
    ['PAPER 성과','가상매매 결과'],
    ['활동 기록','최근 기록'],
    ['전략·리스크','매매 기준과 위험 제한'],
    ['신규 매수 일시정지','새 매수 잠시 멈추기'],
    ['재개','다시 시작'],
    ['긴급 정지 해제','긴급 정지 풀기'],
    ['백업 실행','지금 백업하기'],
    ['코드 보관소 동기화','변경사항 맞추기'],
    ['폰 외부 접속','휴대폰 연결'],
    ['로컬 자동 실행','이 컴퓨터의 자동 실행'],
    ['판단 근거 자세히 보기','왜 이렇게 판단했는지 보기'],
    ['PAPER 평가금액','가상매매 평가금액'],
    ['평가금액','현재 가상금액'],
    ['시장 국면','시장 분위기'],
    ['관련 시장','함께 볼 시장'],
    ['전략 기준과 운영 연결을 관리합니다. 실거래 자동 실행은 이 작업 범위에 포함하지 않습니다.','매수 기준과 프로그램 연결 상태를 관리합니다. 실제 돈으로 주문하지 않습니다.'],
  ]);

  function coinText(node){
    const el=node.parentElement;
    if(!el)return false;
    const raw=String(node.nodeValue||'').trim();
    if(!raw)return false;
    if(/^[A-Z0-9][A-Z0-9._/-]{1,14}$/.test(raw))return true;
    return Boolean(el.closest('.asset-title,.v2-asset-symbol,.demo-symbol-line,.demo-rank-name,.asset-select-label,.asset-chip,.market-code'));
  }

  function clean(value){
    let text=String(value??'');
    const trimmed=text.trim();
    if(EXACT.has(trimmed)&&trimmed===text)return EXACT.get(trimmed);
    for(const[pattern,replacement]of MAP)text=text.replace(pattern,replacement);
    return text;
  }

  function nodes(root){
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode(node){
      const parent=node.parentElement;
      if(!parent||parent.closest('script,style,noscript,code,pre'))return NodeFilter.FILTER_REJECT;
      return node.nodeValue?.trim()?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;
    }});
    const out=[];let node;while((node=walker.nextNode()))out.push(node);return out;
  }

  function polishText(root=document.body){
    if(!root)return;
    for(const node of nodes(root)){
      if(coinText(node))continue;
      const next=clean(node.nodeValue);
      if(next!==node.nodeValue)node.nodeValue=next;
    }
    const els=root.matches?.('*')?[root,...root.querySelectorAll('*')]:[...root.querySelectorAll('*')];
    for(const el of els){
      for(const attr of ['title','aria-label','placeholder']){
        if(!el.hasAttribute?.(attr))continue;
        const before=el.getAttribute(attr),after=clean(before);
        if(before!==after)el.setAttribute(attr,after);
      }
    }
  }

  function shell(){
    document.title='가상자산 상태판';
    const h=document.querySelector('.brand-row h1');if(h)h.textContent='가상자산 상태판';
    const labels={overview:'홈',assets:'코인',performance:'결과',activity:'기록',settings:'설정'};
    document.querySelectorAll('.view-tab[data-view]').forEach(btn=>{const label=labels[btn.dataset.view];if(!label)return;const span=btn.querySelector('span');if(span)span.textContent=label;else btn.textContent=label;btn.setAttribute('aria-label',label)});
  }

  function simplifySettings(){
    const build=document.querySelector('#staticUiBuild .panel-copy');
    if(build)build.textContent='현재 적용된 화면 구성을 확인합니다. 화면 변경은 가상매매 판단이나 저장 데이터에 영향을 주지 않습니다.';
    const buildPill=document.querySelector('#staticUiBuild .status-pill');if(buildPill)buildPill.textContent='현재 화면';
    const deferred=document.querySelector('.deferred-panel');
    const title=deferred?.querySelector('h3');if(title)title.textContent='실제 주문 기능';
    const p=deferred?.querySelector('.panel-copy');if(p)p.textContent='현재는 가상매매만 사용합니다. 실제 돈으로 주문하는 기능은 켜지지 않습니다.';
  }

  function install(){
    shell();simplifySettings();polishText();
    let queued=false;
    const observer=new MutationObserver(records=>{
      if(queued||!records.some(r=>r.type==='childList'||r.type==='characterData'))return;
      queued=true;
      requestAnimationFrame(()=>{queued=false;shell();simplifySettings();polishText()});
    });
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)requestAnimationFrame(()=>{shell();simplifySettings();polishText()})});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install,{once:true});else install();
})();
