import{getJson}from'../core/http.js';
const cache=new Map();
export async function getCoinProfile(exchange='bithumb',market=''){
  const key=`${exchange}|${market}`;if(cache.has(key))return cache.get(key);
  const [value,integrity]=await Promise.all([
    getJson(`/api/coin-profile?exchange=${encodeURIComponent(exchange)}&market=${encodeURIComponent(market)}`),
    getJson(`/api/coin-profile-integrity?exchange=${encodeURIComponent(exchange)}&market=${encodeURIComponent(market)}`).catch(()=>null),
  ]);
  if(integrity?.status==='mismatch')return null;
  cache.set(key,value);return value;
}
export function clearCoinProfileCache(){cache.clear()}
