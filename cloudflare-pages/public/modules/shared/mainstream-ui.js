const REPLACEMENTS=[
  ['READ ONLY PAPER','조회만 가능'],
  ['PAPER ONLY','모의투자만'],
  ['READ ONLY','조회만 가능'],
  ['Crypto Research','코인 현황'],
  ['GitHub Actions CI','자동 검사'],
  ['Profit Factor','손익비'],
  ['NO RAW CANDLES','원본 시세 제외'],
  ['exact contract','확인된 코인 주소'],
  ['primary pool','주요 거래쌍'],
  ['BUY_CANDIDATE','매수 관심'],
  ['PAPER','모의투자'],
  ['Adaptive','기본 방식'],
  ['adaptive','기본 방식'],
  ['COMPACT','요약'],
  ['리서치','코인 정보'],
  ['섹터','테마'],
  ['전략 비교','매매방법 비교'],
  ['전략','매매방법'],
  ['기회점수','종합 점수'],
  ['눌림 대기','가격 대기'],
  ['매수 금지','주의'],
  ['평단','평균 매수가'],
  ['물타기','추가매수'],
  ['익절','수익 실현'],
  ['손절','손실 제한'],
  ['진입','매수 시점'],
  ['Gate','검증 기준'],
  ['Supervisor','자동 점검'],
  ['Warehouse','분석 저장소'],
  ['SQLite','저장소'],
  ['Cloudflare','웹 서비스'],
  ['GitHub','코드 저장소'],
  ['Git ','코드 동기화 '],
  ['Viewer','조회 화면'],
  ['Drive','백업'],
  ['PID','실행 번호'],
  ['DEX','분산형 거래소'],
  ['CEX','일반 거래소'],
  ['feature','요약 정보'],
  ['accepted pool','확인된 거래쌍'],
  ['Launch','상장 전'],
];

function replaceText(value){
  let out=String(value??'');
  for(const[from,to]of REPLACEMENTS)out=out.split(from).join(to);
  return out;
}

function skipElement(element){
  return !element||['SCRIPT','STYLE','CODE','PRE','TEXTAREA','INPUT','SELECT'].includes(element.tagName)||element.closest?.('[data-raw-text]');
}

function translateTextNode(node){
  if(node.nodeType!==Node.TEXT_NODE||skipElement(node.parentElement))return;
  const next=replaceText(node.nodeValue);
  if(next!==node.nodeValue)node.nodeValue=next;
}

function translateElement(element){
  if(!(element instanceof Element)||skipElement(element))return;
  for(const attr of['placeholder','aria-label','title']){
    if(!element.hasAttribute(attr))continue;
    const value=element.getAttribute(attr),next=replaceText(value);
    if(next!==value)element.setAttribute(attr,next);
  }
  for(const node of element.childNodes)if(node.nodeType===Node.TEXT_NODE)translateTextNode(node);
}

function walk(root){
  if(root instanceof Element)translateElement(root);
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
  let node=walker.nextNode();
  while(node){
    if(node.nodeType===Node.TEXT_NODE)translateTextNode(node);
    else translateElement(node);
    node=walker.nextNode();
  }
}

export function installMainstreamUi(root=document.body){
  if(!root||root.dataset?.mainstreamUi==='1')return;
  if(root.dataset)root.dataset.mainstreamUi='1';
  walk(root);
  const observer=new MutationObserver(records=>{
    for(const record of records){
      if(record.type==='characterData')translateTextNode(record.target);
      for(const node of record.addedNodes){
        if(node.nodeType===Node.TEXT_NODE)translateTextNode(node);
        else if(node.nodeType===Node.ELEMENT_NODE)walk(node);
      }
    }
  });
  observer.observe(root,{childList:true,subtree:true,characterData:true});
}
