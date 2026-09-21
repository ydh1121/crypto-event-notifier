const META={
  NORMAL:{label:'',tone:'normal'},
  LISTING_ANNOUNCED:{label:'상장예정',tone:'new'},
  NEW_LISTING:{label:'신규',tone:'new'},
  CAUTION:{label:'유의',tone:'caution'},
  TERMINATION_SCHEDULED:{label:'거래종료 예정',tone:'terminated'},
  TERMINATED:{label:'거래종료',tone:'terminated'},
};

export function normalizeLifecycleState(value){
  const key=String(value||'NORMAL').trim().toUpperCase();
  return META[key]?key:'NORMAL';
}

export function lifecycleMeta(value){
  const state=normalizeLifecycleState(value),meta=META[state];
  return{state,label:meta.label,tone:meta.tone,className:`market-lifecycle-${meta.tone}`};
}

export function lifecycleNeedsAttention(value){
  return normalizeLifecycleState(value)!=='NORMAL';
}
