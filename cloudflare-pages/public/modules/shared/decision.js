const normalize=value=>String(value??'').trim().toUpperCase();

export const DECISION_FILTERS={
  all:{label:'전체',hint:'전체 코인'},
  buy:{label:'지금 볼 코인',hint:'현재 조건이 가장 좋은 코인'},
  wait:{label:'가격 기다리기',hint:'조금 더 기다려 볼 코인'},
  watch:{label:'계속 보기',hint:'아직 방향이 뚜렷하지 않은 코인'},
  risk:{label:'지금은 조심',hint:'지금은 서두르지 않는 편이 나은 코인'},
  holding:{label:'가상매매 보유',hint:'가상매매에서 현재 들고 있는 코인'},
};

function strategyDecision(row){
  const action=normalize(row?.strategy_action);
  if(action==='BUY_CANDIDATE')return'buy';
  if(action==='WAIT_PULLBACK')return'wait';
  if(action==='RISK_OFF'||action==='ERROR')return'risk';
  if(action==='WATCH')return'watch';
  const regime=Number(row?.regime_score||0),entry=Number(row?.entry_score||0);
  if(regime>=65&&entry>=68)return'buy';
  if(regime<50)return'risk';
  if(regime>=70&&entry<50)return'wait';
  return'watch';
}

export function decisionKind(row){
  if(row?.has_position)return'holding';
  return strategyDecision(row);
}

export function decisionLabel(row){
  const kind=decisionKind(row);
  if(kind==='holding')return'가상매매에서 보유 중';
  if(kind==='buy')return'지금 살펴볼 때';
  if(kind==='wait')return'가격을 더 기다리기';
  if(kind==='risk')return'지금은 조심하기';
  return'계속 지켜보기';
}

export function decisionMatches(row,filter='all'){
  if(filter==='all')return true;
  return decisionKind(row)===filter;
}

export function decisionCounts(rows=[]){
  const counts={all:0,buy:0,wait:0,watch:0,risk:0,holding:0};
  for(const row of rows){counts.all++;const kind=decisionKind(row);if(kind in counts)counts[kind]++}
  return counts;
}

export function decisionEmptyMessage(filter='all',exchangeLabel='현재 거래소'){
  const info=DECISION_FILTERS[filter]||DECISION_FILTERS.all;
  if(filter==='all')return['조건에 맞는 코인이 없습니다.','검색어를 지우거나 잠시 뒤 다시 확인하세요.'];
  return[`현재 ${exchangeLabel}에서 ‘${info.label}’에 해당하는 코인이 없습니다.`,`새 자료가 들어오면 자동으로 다시 분류됩니다.`];
}
