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
  if(!(holding?.planning_available||holding?.recording_available)||detail?.exchange!==holding.exchange||detail?.market!==holding.market||
    lab?.exchange!==holding.exchange||lab?.market!==holding.market||!(lab?.version>=2))return [];
  return lab.experiments||[];
}
export function importAvailable(account,holding) {
  return Boolean(holding?.planning_available&&account?.reconciliation?.matches===true&&account.plan?.available&&
    !freshness(account.plan.source_ts).stale);
}
/** Only prices/relative allocations are transferred. PAPER cash, volume and
 * average must never become the user's actual starting position or budget. */
export function importHoldingPlan(draft,holding,account,{part='both'}={}) {
  if(!importAvailable(account,holding))return {error:'최근 전략 기록과 계좌 대조를 확인하세요.'};
  if(holdingChanged(draft,holding))return {error:'보유정보가 바뀌었습니다. 최신 수량·평단을 먼저 불러오세요.'};
  if(!['buy','sell','both'].includes(part))return {error:'불러올 계획을 선택하세요.'};
  const entries=part==='sell'?[]:account.plan.entries||[],budget=finite(draft.budget);
  if(part==='buy'&&!entries.length)return {error:'현재 전략은 진입 가격을 제시하지 않았습니다.'};
  if(entries.length&&(!(budget>0)||!Number.isSafeInteger(budget)))return {error:'분할 매수에 사용할 총예산을 원 단위로 입력하세요.'};
  const total=entries.reduce((sum,r)=>sum+(finite(r.amount_krw)||0),0);
  if(entries.length&&(!(total>0)||entries.some(r=>!(finite(r.amount_krw)>0)||!(finite(r.price)>0))))return {error:'전략의 분할 가격·비중을 확인하세요.'};
  let allocated=0;
  const next={...draft,buys:part==='sell'?draft.buys.map(r=>({...r})):entries.map((r,i)=>{
    const amount=i===entries.length-1?budget-allocated:Math.floor(budget*r.amount_krw/total);
    allocated+=amount;return {price:String(r.price),amount:String(amount),basis:r.basis};
  }),sells:[],origin:'strategy'};
  if(next.buys.some(r=>!(Number(r.amount)>0)))return {error:'회차마다 1원 이상 배분되도록 예산을 늘리세요.'};
  const result=calculatePlan(next,{exchange:holding.exchange,market:holding.market});
  if(!result.valid)return {error:result.errors.join(' ')};
  const target=finite(account.plan.rules?.take_profit_pct);
  if(part==='buy')next.sells=draft.sells.map(r=>({...r}));
  else if(target!==null&&target>0&&result.afterBuyQuantity>0)
    next.sells=[{price:String(result.average*(1+target/100)),weight:'100'}];
  else return {error:'적용할 익절 비율과 보유수량을 확인하세요.'};
  next.strategyLabel=account.label;
  return {draft:next};
}
export function holdingTarget(holding,account) {
  const average=finite(holding?.avg_price),pct=finite(account?.plan?.rules?.take_profit_pct);
  if(!importAvailable(account,holding)||!(average>0)||!(pct>0))return null;
  const price=average*(1+pct/100),current=finite(holding.current_price);
  return {price,pct,distance:current>0&&!freshness(holding.price_ts).stale?(current/price-1)*100:null};
}
export function buyAllocations(draft) {
  const amounts=(draft.buys||[]).map(r=>finite(r.amount));
  if(amounts.some(x=>x===null||x<=0))return [];
  const total=amounts.reduce((a,b)=>a+b,0);
  return total>0?amounts.map(amount=>amount/total*100):[];
}
