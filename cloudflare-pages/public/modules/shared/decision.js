const normalize=value=>String(value??'').trim().toUpperCase();

export const DECISION_FILTERS={
  all:{label:'전체',hint:'현재 거래소의 전체 연구 대상'},
  buy:{label:'매수 후보',hint:'시장 ≥ 65 · 진입 ≥ 68'},
  wait:{label:'눌림 대기',hint:'시장 ≥ 70 · 진입 < 50'},
  watch:{label:'관찰',hint:'실행 조건이 아직 섞여 있음'},
  risk:{label:'매수 금지',hint:'시장 < 50'},
  holding:{label:'PAPER 보유',hint:'현재 독립 PAPER 계좌에 포지션 보유'},
};

function strategyDecision(row){
  const action=normalize(row?.strategy_action);
  if(action==='BUY_CANDIDATE')return'buy';
  if(action==='WAIT_PULLBACK')return'wait';
  if(action==='RISK_OFF'||action==='ERROR')return'risk';
  if(action==='WATCH')return'watch';

  // Current AssetStrategy decision thresholds. Public snapshots from older
  // publishers may not contain strategy_action, so infer the same action from
  // the scores instead of guessing from execution-only trade_intent values.
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
  if(kind==='holding')return'보유 상태 관리 중';
  if(kind==='buy')return'매수 후보';
  if(kind==='wait')return'가격이 내려오길 기다림';
  if(kind==='risk')return'지금은 매수하지 않음';
  return'조금 더 지켜보기';
}

export function decisionMatches(row,filter='all'){
  if(filter==='all')return true;
  return decisionKind(row)===filter;
}

export function decisionCounts(rows=[]){
  const counts={all:0,buy:0,wait:0,watch:0,risk:0,holding:0};
  for(const row of rows){
    counts.all++;
    const kind=decisionKind(row);
    if(kind in counts)counts[kind]++;
  }
  return counts;
}

export function decisionEmptyMessage(filter='all',exchangeLabel='현재 거래소'){
  const info=DECISION_FILTERS[filter]||DECISION_FILTERS.all;
  if(filter==='all')return['조건에 맞는 코인이 없습니다.','검색어를 지우거나 데이터 갱신 상태를 확인하세요.'];
  return[
    `현재 최신 ${exchangeLabel} 판단에서 ‘${info.label}’ 0개입니다.`,
    `필터는 정상 적용 중입니다. 기준: ${info.hint}. 다음 연구 스캔에서 조건을 충족하면 자동 표시됩니다.`,
  ];
}
