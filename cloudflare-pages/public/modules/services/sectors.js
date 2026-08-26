import{getJson}from'../core/http.js';
const cache=new Map();
const apiRange={"1h":"h1","6h":"h6","24h":"h24","7d":"d7"};
export async function getSectorSummary(exchange='bithumb',{range='24h',force=false}={}){
  const key=`${exchange}|${range}`,now=Date.now(),hit=cache.get(key);
  if(!force&&hit&&now-hit.ts<20000)return hit.value;
  const normalized=apiRange[range]||range;
  const value=await getJson(`/api/sector-summary?exchange=${encodeURIComponent(exchange)}&range=${encodeURIComponent(normalized)}`);
  cache.set(key,{ts:now,value});
  return value;
}
export function clearSectorSummary(){cache.clear()}
