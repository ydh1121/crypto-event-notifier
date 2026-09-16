export const TRADING_FEE_RATES=Object.freeze({bithumb:0.0004,upbit:0.0005});
export const TRADING_FEE_LABELS=Object.freeze({bithumb:'빗썸 쿠폰 0.04%',upbit:'업비트 KRW 0.05%'});
export function normalizeFeeExchange(value){return String(value||'').toLowerCase()==='upbit'?'upbit':'bithumb'}
export function tradingFeeRate(exchange){return TRADING_FEE_RATES[normalizeFeeExchange(exchange)]}
export function tradingFeeLabel(exchange){return TRADING_FEE_LABELS[normalizeFeeExchange(exchange)]}
export function tradingFee(amount,exchange){const value=Math.max(0,Number(amount)||0);return value*tradingFeeRate(exchange)}
export function tradingCost({buyGross=0,sellGross=0,exchange='bithumb'}={}){const buy=Math.max(0,Number(buyGross)||0),sell=Math.max(0,Number(sellGross)||0),buyFee=tradingFee(buy,exchange),sellFee=tradingFee(sell,exchange);return{exchange:normalizeFeeExchange(exchange),rate:tradingFeeRate(exchange),buy_fee_krw:buyFee,sell_fee_krw:sellFee,total_fee_krw:buyFee+sellFee,buy_total_krw:buy+buyFee,sell_net_krw:sell-sellFee}}
