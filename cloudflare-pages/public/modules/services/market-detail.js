import{getJson}from'../core/http.js';
const cache=new Map();
export async function getMarketDetail(exchange,market,{force=false}={}){
  const key=`${exchange}|${market}|adaptive`,now=Date.now(),hit=cache.get(key);
  if(!force&&hit&&now-hit.ts<20000)return hit.value;
  const body=await getJson(`/api/market-detail?exchange=${encodeURIComponent(exchange)}&strategy=adaptive&market=${encodeURIComponent(market)}`);
  const value=body.detail||null;cache.set(key,{ts:now,value});return value;
}
export function clearMarketDetail(exchange,market){cache.delete(`${exchange}|${market}|adaptive`)}
