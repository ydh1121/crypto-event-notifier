import{getJson}from'../core/http.js';
const cache=new Map();
export async function getCoinProfile(exchange='bithumb',market=''){
  const key=`${exchange}|${market}`;if(cache.has(key))return cache.get(key);
  const value=await getJson(`/api/coin-profile?exchange=${encodeURIComponent(exchange)}&market=${encodeURIComponent(market)}`);
  cache.set(key,value);return value;
}
export function clearCoinProfileCache(){cache.clear()}
