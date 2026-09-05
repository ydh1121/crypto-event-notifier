import {bearer,error,json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import type {Env} from '../lib/types';

type Row={exchange:string;market:string;korean_name:string;english_name:string;research_status:string;source_count:number;match_confidence:number;business_summary_ko:string;last_verified_at:number};
const clean=(v:unknown)=>String(v??'').trim();
const generic=new Set(['token','coin','network','protocol','finance','foundation','project','ecosystem','platform','labs','dao']);
function norm(v:unknown){return clean(v).toLowerCase().replace(/[^a-z0-9가-힣]+/g,'')}
function tokens(v:unknown){return clean(v).toLowerCase().match(/[a-z0-9]+/g)?.filter(x=>!generic.has(x))||[]}
function sameName(a:unknown,b:unknown){const x=norm(a),y=norm(b);if(!x||!y)return true;if(x===y)return true;if(x.length>=5&&y.length>=5&&(x.includes(y)||y.includes(x)))return true;const aa=new Set(tokens(a)),bb=new Set(tokens(b));if(!aa.size||!bb.size)return false;let hit=0;for(const t of aa)if(bb.has(t))hit++;return hit/Math.max(aa.size,bb.size)>=.8}

export const onRequestGet:PagesFunction<Env>=async({request,env})=>{
  if(!env.INGEST_TOKEN||bearer(request)!==env.INGEST_TOKEN)return error(401,'INGEST_REQUIRED','프로필 정합성 감사 인증이 필요합니다.');
  const query=(exchange:'bithumb'|'upbit')=>env.DB.prepare(`SELECT exchange,market,korean_name,english_name,research_status,source_count,match_confidence,business_summary_ko,last_verified_at FROM coin_profile_cache WHERE exchange=? ORDER BY market ASC LIMIT 1000`).bind(exchange).all<Row>();
  const [b,u,bNames,uNames]=await Promise.all([query('bithumb'),query('upbit'),exchangeMarketNames('bithumb'),exchangeMarketNames('upbit')]);
  const mismatches:any[]=[];const scopes={bithumb:b.results?.length||0,upbit:u.results?.length||0};
  for(const [rows,names] of [[b.results||[],bNames],[u.results||[],uNames]] as const){for(const row of rows){const official=names.get(clean(row.market).toUpperCase());if(!official?.english_name||sameName(row.english_name,official.english_name))continue;mismatches.push({exchange:row.exchange,market:row.market,korean_name:row.korean_name,cached_english_name:row.english_name,official_english_name:official.english_name,research_status:row.research_status,source_count:Number(row.source_count||0),match_confidence:Number(row.match_confidence||0),business_preview:clean(row.business_summary_ko).slice(0,180),last_verified_at:Number(row.last_verified_at||0)})}}
  const by_exchange={bithumb:mismatches.filter(x=>x.exchange==='bithumb').length,upbit:mismatches.filter(x=>x.exchange==='upbit').length};
  return json({ok:true,audited_at:Math.floor(Date.now()/1000),audit_scope:scopes,total:mismatches.length,by_exchange,rows:mismatches.slice(0,500)});
};
