import {bearer,error,json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {evaluateProfileIntegrity,knownProjects,type ProfileIntegrityRow} from '../lib/coin-profile-integrity';
import type {Env} from '../lib/types';

const clean=(value:unknown)=>String(value??'').trim();
const query=(env:Env,exchange:'bithumb'|'upbit')=>env.DB.prepare(`SELECT exchange,market,korean_name,english_name,provider,provider_id,substr(COALESCE(business_summary_ko,''),1,700) AS business_summary_ko,substr(COALESCE(description_ko,''),1,700) AS description_ko,substr(COALESCE(description_en,''),1,700) AS description_en,homepage,substr(COALESCE(evidence_json,''),1,1600) AS evidence_json,research_status,source_count,match_confidence,last_verified_at FROM coin_profile_cache WHERE exchange=? ORDER BY market ASC LIMIT 1000`).bind(exchange).all<ProfileIntegrityRow>();

export const onRequestGet:PagesFunction<Env>=async({request,env})=>{
  if(!env.INGEST_TOKEN||bearer(request)!==env.INGEST_TOKEN)return error(401,'INGEST_REQUIRED','프로필 내용 정합성 감사 인증이 필요합니다.');
  const [bRows,uRows,bNames,uNames]=await Promise.all([query(env,'bithumb'),query(env,'upbit'),exchangeMarketNames('bithumb'),exchangeMarketNames('upbit')]);
  const known=knownProjects(bNames,uNames),rows:any[]=[];const reasonCounts:Record<string,number>={};
  for(const [items,names] of [[bRows.results||[],bNames],[uRows.results||[],uNames]] as const){for(const row of items){const official=names.get(clean(row.market).toUpperCase()),finding=evaluateProfileIntegrity(row,official,known);if(!finding.reasons.length)continue;for(const reason of finding.reasons)reasonCounts[reason]=(reasonCounts[reason]||0)+1;rows.push({exchange:row.exchange,market:row.market,korean_name:official?.korean_name||row.korean_name,official_english_name:official?.english_name||'',cached_english_name:row.english_name,research_status:row.research_status,source_count:Number(row.source_count||0),match_confidence:Number(row.match_confidence||0),reasons:finding.reasons,foreign_projects:finding.foreign_projects,business_preview:clean(row.business_summary_ko||row.description_ko||row.description_en).slice(0,240),homepage:clean(row.homepage),provider:clean(row.provider),provider_id:clean(row.provider_id),last_verified_at:Number(row.last_verified_at||0)})}}
  return json({ok:true,audited_at:Math.floor(Date.now()/1000),audit_scope:{bithumb:bRows.results?.length||0,upbit:uRows.results?.length||0},total:rows.length,by_exchange:{bithumb:rows.filter(x=>x.exchange==='bithumb').length,upbit:rows.filter(x=>x.exchange==='upbit').length},reasons:reasonCounts,rows:rows.slice(0,500)});
};
