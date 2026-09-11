import{getJson}from'../core/http.js';
const cache=new Map();
export async function getMarketQuotes(exchange,{force=false}={}){
  const ex=String(exchange||'bithumb').toLowerCase(),now=Date.now(),hit=cache.get(ex);
  if(!force&&hit&&now-hit.ts<15000)return hit.value;
  const body=await getJson(`/api/market-quotes?exchange=${encodeURIComponent(ex)}&strategy=adaptive`);
  const rows=Array.isArray(body?.quotes)?body.quotes:[];
  const value=new Map(rows.filter(row=>row?.market).map(row=>[String(row.market),row]));
  cache.set(ex,{ts:now,value});
  return value;
}
export function clearMarketQuotes(exchange){cache.delete(String(exchange||'bithumb').toLowerCase())}
