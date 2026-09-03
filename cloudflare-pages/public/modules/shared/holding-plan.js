import{n}from'./format.js';

const ACTIVE_BUY_INTENTS=new Set(['buy','explore','idle_explore','add']);

export function buildHoldingPlanGuidance({row=null,plan={}}={}){
  const intent=String(row?.trade_intent||'waiting').toLowerCase();
  const nextPrice=n(plan?.next_add_price)||n(plan?.expected_entry_price)||n(row?.price);
  const total=Math.max(0,Math.round(n(plan?.expected_total_entries)));
  const completed=Math.max(0,Math.round(n(plan?.completed_entries)));
  const remaining=Math.max(0,Math.round(n(plan?.remaining_entries)||(total-completed)));
  const stopPrice=n(plan?.hard_stop_price);
  const targetPrice=n(plan?.target_price);
  const suggestedWeightPct=Math.max(0,n(plan?.suggested_weight_pct)||n(row?.suggested_weight_pct));
  const addStepPct=Math.max(0,n(plan?.add_step_pct));
  const cooldownSeconds=Math.max(0,n(plan?.cooldown_remaining_seconds));

  let status='지금은 대기';
  let tone='neutral';
  let detail='다음 가격에 도달하더라도 시장 상태와 매수 조건을 다시 확인합니다.';

  if(intent==='sell'){
    status='추가매수 중단';
    tone='negative';
    detail='현재 가상전략은 매도 조건을 보고 있습니다. 물타기보다 위험 관리 확인이 먼저입니다.';
  }else if(intent==='add'){
    status='추가매수 검토';
    tone='positive';
    detail='현재 가상전략이 추가매수 조건을 보고 있습니다. 가격 도달만으로 자동 매수하지는 않습니다.';
  }else if(ACTIVE_BUY_INTENTS.has(intent)){
    status='매수 조건 확인';
    tone='positive';
    detail='현재 가상전략에 매수 조건이 잡혀 있습니다. 실제 보유분 추가매수는 아래 참고 가격과 중단선을 함께 봅니다.';
  }else if(intent==='analysis_error'){
    status='판단 데이터 대기';
    tone='neutral';
    detail='현재 분석값을 확정하지 못했습니다. 새 데이터가 들어올 때까지 추가매수 판단을 미룹니다.';
  }else if(remaining===0&&total>0){
    status='추가 분할 없음';
    tone='neutral';
    detail='현재 가상전략 기준 예정된 분할 횟수를 모두 사용했습니다. 추가매수보다 위험 기준을 먼저 확인합니다.';
  }

  return{
    intent,status,tone,detail,nextPrice,totalEntries:total,completedEntries:completed,remainingEntries:remaining,
    stopPrice,targetPrice,suggestedWeightPct,addStepPct,cooldownSeconds,
    note:String(plan?.plan_note||'가격 하나만으로 주문하지 않고 시장 상태를 함께 다시 확인합니다.')
  };
}

export function buildHoldingBudgetSchedule({row=null,plan={},totalBudget=0}={}){
  const guide=buildHoldingPlanGuidance({row,plan});
  const budget=Math.max(0,n(totalBudget));
  const remaining=Math.min(8,guide.remainingEntries);
  const firstPrice=Math.max(0,guide.nextPrice);
  const step=Math.max(0,guide.addStepPct)/100;
  if(!budget||!remaining||!firstPrice)return{rows:[],budget,remainingEntries:remaining,allocatedBudget:0,unallocatedBudget:budget,usesEstimatedPrices:false};

  const candidates=[];
  for(let index=0;index<remaining;index+=1){
    const estimatedPrice=index===0?firstPrice:firstPrice*Math.pow(Math.max(0.01,1-step),index);
    if(guide.stopPrice>0&&estimatedPrice<=guide.stopPrice)break;
    candidates.push({round:index+1,price:estimatedPrice,priceSource:index===0?'paper_next':'estimated_step'});
  }
  if(!candidates.length)return{rows:[],budget,remainingEntries:remaining,allocatedBudget:0,unallocatedBudget:budget,usesEstimatedPrices:false};

  const unit=Math.floor(budget/candidates.length/1000)*1000;
  let allocated=0;
  const rows=candidates.map((candidate,index)=>{
    const amount=index===candidates.length-1?Math.max(0,budget-allocated):unit;
    allocated+=amount;
    return{...candidate,amount_krw:amount};
  });
  return{
    rows,budget,remainingEntries:remaining,allocatedBudget:allocated,unallocatedBudget:Math.max(0,budget-allocated),
    usesEstimatedPrices:rows.some(item=>item.priceSource==='estimated_step')
  };
}
