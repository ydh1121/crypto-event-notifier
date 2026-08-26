import{getJson}from'../core/http.js';
const cache=new Map();
export async function getSectorSummary(exchange='bithumb',{range='h24',force=false}={}){
  const key=`${exchange}|${range}`,now=Date.now(),hit=cache.get(key);
  if(!force&&hit&&now-hit.ts<20000)return hit.value;
  const value=await getJson(`/api/sector-summary?exchange=${encodeURIComponent(exchange)}&range=${encodeURIComponent(range)}`);
  cache.set(key,{ts:now,value});
  return value;
}
export function clearSectorSummary(){cache.clear()}
