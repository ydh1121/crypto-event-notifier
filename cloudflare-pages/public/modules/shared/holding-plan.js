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
  const budget=Math.max(0,Math.round(n(totalBudget)));
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

  const rawUnit=Math.floor(budget/candidates.length);
  const unit=rawUnit>=1000?Math.floor(rawUnit/1000)*1000:rawUnit;
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

export function buildProfitProtectionGuidance({holding=null,plan={}}={}){
  const avg=Math.max(0,n(holding?.avg_price)||n(plan?.position_avg_price));
  const current=Math.max(0,n(holding?.current_price)||n(plan?.current_price));
  const targetPrice=Math.max(0,n(plan?.target_price));
  const targetPct=Math.max(0,n(plan?.target_profit_pct));
  const trailArmPct=Math.max(0,n(plan?.trail_arm_pct));
  const trailGivebackPct=Math.max(0,n(plan?.trail_giveback_pct));
  const trailingStopPrice=Math.max(0,n(plan?.trailing_stop_price));
  const peakGainPct=n(plan?.peak_gain_pct);
  const firstProtectionPrice=avg>0&&trailArmPct>0?avg*(1+trailArmPct/100):0;
  const breakEvenPrice=avg;

  const stage1Reached=firstProtectionPrice>0&&current>=firstProtectionPrice;
  const stage2Reached=targetPrice>0&&current>=targetPrice;
  const trailingActive=trailingStopPrice>0;
  return{
    breakEvenPrice,current,targetPrice,targetPct,trailArmPct,trailGivebackPct,trailingStopPrice,peakGainPct,
    stages:[
      {
        key:'protect',label:'1차 수익보호',price:firstProtectionPrice,reached:stage1Reached,
        action:'수익이 생기기 시작한 구간입니다. 본전선 이상으로 보호 기준을 올릴지 검토합니다.'
      },
      {
        key:'target',label:'2차 목표가',price:targetPrice,reached:stage2Reached,
        action:'현재 PAPER의 동적 목표가입니다. 이 가격에 도달하면 가상전략은 매도 조건을 확인합니다.'
      },
      {
        key:'trail',label:'최종 고점보호',price:trailingStopPrice,reached:trailingActive,
        action:trailingActive?`현재 고점 기준 보호가격입니다. 고점에서 약 ${trailGivebackPct.toFixed(2)}% 밀리면 정리 조건을 확인합니다.`:`수익이 충분히 난 뒤 고점 추적 보호가 활성화됩니다. 활성 기준은 평균단가 대비 약 ${trailArmPct.toFixed(2)}% 상승입니다.`
      }
    ],
    note:'현재 PAPER는 분할매도 비중을 계산하지 않습니다. 임의의 30/30/40 같은 매도 비중은 만들지 않고 가격·보호 조건만 보여줍니다.'
  };
}
