import {finite,calculatePlan,freshness} from './strategy-workbench-model.js';
import {tradingFeeProfile} from './trading-fees-v16.js';

export function holdingDraft(holding) {
  const profile=tradingFeeProfile(holding.exchange,holding.market);
  return {volume:String(holding.volume??''),average:String(holding.avg_price??''),
    fee:profile?String(profile.rate*100):'',slippage:'0',buys:[],sells:[],budget:'',origin:'manual',
    holdingRevision:[holding.updated_ts,holding.volume,holding.avg_price].join('|')};
}
export function holdingChanged(draft,holding) {
  return draft.holdingRevision!==[holding.updated_ts,holding.volume,holding.avg_price].join('|');
}
export function scopedStrategies(detail,holding) {
  const lab=detail?.data?.strategy_lab;
  if(!holding?.planning_available||detail?.exchange!==holding.exchange||detail?.market!==holding.market||
    lab?.exchange!==holding.exchange||lab?.market!==holding.market||!(lab?.version>=2))return [];
  return lab.experiments||[];
}
export function importAvailable(account,holding) {
  return Boolean(holding?.planning_available&&account?.reconciliation?.matches===true&&account.plan?.available&&
    !freshness(account.plan.source_ts).stale);
}
/** Only prices/relative allocations are transferred. PAPER cash, volume and
 * average must never become the user's actual starting position or budget. */
export function importHoldingPlan(draft,holding,account) {
  if(!importAvailable(account,holding))return {error:'최근 전략 기록과 계좌 대조를 확인하세요.'};
  if(holdingChanged(draft,holding))return {error:'보유정보가 바뀌었습니다. 최신 수량·평단을 먼저 불러오세요.'};
  const entries=account.plan.entries||[],budget=finite(draft.budget);
  if(entries.length&&(!(budget>0)||!Number.isSafeInteger(budget)))return {error:'분할 매수에 사용할 총예산을 원 단위로 입력하세요.'};
  const total=entries.reduce((sum,r)=>sum+(finite(r.amount_krw)||0),0);
  if(entries.length&&(!(total>0)||entries.some(r=>!(finite(r.amount_krw)>0)||!(finite(r.price)>0))))return {error:'전략의 분할 가격·비중을 확인하세요.'};
  let allocated=0;
  const next={...draft,buys:entries.map((r,i)=>{
    const amount=i===entries.length-1?budget-allocated:Math.floor(budget*r.amount_krw/total);
    allocated+=amount;return {price:String(r.price),amount:String(amount),basis:r.basis};
  }),sells:[],origin:'strategy'};
  if(next.buys.some(r=>!(Number(r.amount)>0)))return {error:'회차마다 1원 이상 배분되도록 예산을 늘리세요.'};
  const result=calculatePlan(next,{exchange:holding.exchange,market:holding.market});
  if(!result.valid)return {error:result.errors.join(' ')};
  const target=finite(account.plan.rules?.take_profit_pct);
  if(target!==null&&target>0&&result.afterBuyQuantity>0)
    next.sells=[{price:String(result.average*(1+target/100)),weight:'100'}];
  next.strategyLabel=account.label;
  return {draft:next};
}
export function buyAllocations(draft) {
  const amounts=(draft.buys||[]).map(r=>finite(r.amount));
  if(amounts.some(x=>x===null||x<=0))return [];
  const total=amounts.reduce((a,b)=>a+b,0);
  return total>0?amounts.map(amount=>amount/total*100):[];
}
