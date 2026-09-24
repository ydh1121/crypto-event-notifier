import {tradingCost, holdingQuoteCurrency} from './trading-fees-v16.js';

export function finite(value) { return value===null||value===undefined||value===''||!Number.isFinite(Number(value)) ? null : Number(value); }
export function freshness(sourceTs, now=Date.now()/1000) {
  const value=finite(sourceTs);
  if(!value || value>now+60) return {stale:true,label:'기준 시각 확인 필요'};
  const seconds=Math.max(0,now-value);
  return {stale:seconds>1200,label:seconds>1200?'갱신 지연':'최근 수집',seconds};
}
export function exactHolding(holdings, exchange, market) {
  return holdings.find(h=>h.market===market && String(h.exchange||'').toLowerCase()===exchange &&
    String(h.quote_currency||holdingQuoteCurrency(h.market)).toUpperCase()===holdingQuoteCurrency(market)) || null;
}
export function accountModel(detail, exchange, market, experiment) {
  if(detail?.exchange!==exchange || detail?.market!==market) return null;
  const lab=detail.data?.strategy_lab;
  if(!(lab?.version>=2) || lab?.exchange!==exchange || lab?.market!==market) return null;
  return (lab.experiments||[]).find(e=>e.experiment_id===experiment) || null;
}
export function importPlan(account) {
  const plan=account?.plan;
  return {volume:String(account?.volume??''),average:String(account?.avg_price??''),
    fee:String((plan?.fee_rate??0.0004)*100),slippage:String((plan?.slippage_rate??0.0005)*100),
    buys:(plan?.entries||[]).map(r=>({price:String(r.price),amount:String(r.amount_krw),basis:r.basis})),
    sells:(plan?.exits||[]).map(r=>({price:String(r.price),weight:String(r.weight_pct)}))};
}
/** Fee-inclusive buy budgets; sale percentages refer to the post-buy holding, not a shrinking remainder. */
export function calculatePlan(draft, {exchange='bithumb',market='KRW-B3'}={}) {
  let quantity=finite(draft.volume), average=finite(draft.average);
  const feePct=finite(draft.fee), slipPct=finite(draft.slippage);
  const errors=[];
  if(quantity===null||quantity<0||average===null||average<0||(quantity>0&&average===0)) errors.push('보유수량과 평단을 확인하세요.');
  if(feePct===null||feePct<0||feePct>=100||slipPct===null||slipPct<0||slipPct>=100) errors.push('수수료와 체결 차이를 확인하세요.');
  if(errors.length) return {valid:false,errors};
  const fee=feePct/100, slip=slipPct/100;
  let cost=quantity*average, buyTotal=0, fees=0;
  const buyStages=[],sellStages=[];
  for(const [i,row] of (draft.buys||[]).entries()) {
    if(row.price===''&&row.amount==='') continue;
    const price=finite(row.price),amount=finite(row.amount);
    if(price===null||price<=0||amount===null||amount<=0) { errors.push(`${i+1}차 매수가와 금액을 확인하세요.`); continue; }
    const fill=price*(1+slip),gross=amount/(1+fee);
    // Use the canonical fee/cost owner with the explicitly editable paper fee assumption.
    const charge=tradingCost({buyGross:gross,exchange,market,rate:fee});
    const bought=gross/fill;
    quantity+=bought;cost+=charge.buy_total;buyTotal+=charge.buy_total;fees+=charge.buy_fee;
    buyStages.push({quantity,average:cost/quantity,fee:charge.buy_fee,bought,amount:charge.buy_total});
  }
  const afterBuyQuantity=quantity,afterBuyAverage=quantity>0?cost/quantity:0;
  let realized=0,net=0,totalWeight=0;
  for(const [i,row] of (draft.sells||[]).entries()) {
    if(row.price===''&&row.weight==='') continue;
    const price=finite(row.price),weight=finite(row.weight);
    if(price===null||price<=0||weight===null||weight<=0||weight>100) { errors.push(`${i+1}차 익절가와 비중을 확인하세요.`);continue; }
    totalWeight+=weight;
    if(totalWeight>100+1e-9) { errors.push('익절 비중의 합계는 100% 이하여야 합니다.');break; }
    // An explicitly complete sale consumes the exact remaining quantity;
    // multiplying by 100 / 100 can otherwise leave floating-point dust.
    const sold=totalWeight===100?quantity:Math.min(quantity,afterBuyQuantity*weight/100), gross=sold*price*(1-slip);
    const charge=tradingCost({sellGross:gross,exchange,market,rate:fee});
    const pnl=charge.sell_net-sold*afterBuyAverage;
    quantity-=sold;cost-=sold*afterBuyAverage;fees+=charge.sell_fee;realized+=pnl;net+=charge.sell_net;
    sellStages.push({sold,net:charge.sell_net,realized:pnl,fee:charge.sell_fee,remaining:Math.max(0,quantity)});
  }
  return {valid:!errors.length,errors,buyStages,sellStages,average:afterBuyAverage,afterBuyQuantity,
    remaining:Math.max(0,quantity),remainingCost:Math.max(0,cost),realized,net,buyTotal,fees};
}
export function relativeSeries(memory) {
  return (Array.isArray(memory)?memory:[]).map(r=>{
    const coin=finite(r.asset_return_pct),btc=finite(r.btc_return_pct),eth=finite(r.eth_return_pct);
    return {ts:r.signal_ts||r.ts,coin,btc,eth,vsBtc:coin!==null&&btc!==null?coin-btc:null,vsEth:coin!==null&&eth!==null?coin-eth:null};
  });
}
