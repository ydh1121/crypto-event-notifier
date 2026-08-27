import {bearer,error,json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {evaluateProfileIntegrity,knownProjects,type ProfileIntegrityRow} from '../lib/coin-profile-integrity';
import type {Env} from '../lib/types';

type AuditRow=ProfileIntegrityRow&{canonical_sector:string};
const clean=(value:unknown)=>String(value??'').trim();
const num=(value:unknown)=>{const n=Number(value||0);return Number.isFinite(n)?n:0};
const query=(env:Env,exchange:'bithumb'|'upbit')=>env.DB.prepare(`SELECT exchange,market,korean_name,english_name,provider,provider_id,substr(COALESCE(business_summary_ko,''),1,700) AS business_summary_ko,substr(COALESCE(description_ko,''),1,700) AS description_ko,substr(COALESCE(description_en,''),1,700) AS description_en,homepage,substr(COALESCE(evidence_json,''),1,1600) AS evidence_json,research_status,canonical_sector,source_count,match_confidence,last_verified_at FROM coin_profile_cache WHERE exchange=? ORDER BY market ASC LIMIT 1000`).bind(exchange).all<AuditRow>();

function qualityReasons(row:AuditRow){
  const reasons:string[]=[];
  if(!clean(row.business_summary_ko)&&!clean(row.description_ko))reasons.push('korean_missing');
  if(['pending','unresolved',''].includes(clean(row.research_status)))reasons.push('research_unresolved');
  if(!clean(row.canonical_sector)||clean(row.canonical_sector)==='미분류 검토')reasons.push('sector_unresolved');
  if(num(row.source_count)<2)reasons.push('weak_evidence');
  if(num(row.match_confidence)<.8)reasons.push('low_match_confidence');
  return reasons;
}

export const onRequestGet:PagesFunction<Env>=async({request,env})=>{
  if(!env.INGEST_TOKEN||bearer(request)!==env.INGEST_TOKEN)return error(401,'INGEST_REQUIRED','프로필 내용 정합성 감사 인증이 필요합니다.');
  const [bRows,uRows,bNames,uNames]=await Promise.all([query(env,'bithumb'),query(env,'upbit'),exchangeMarketNames('bithumb'),exchangeMarketNames('upbit')]);
  const known=knownProjects(bNames,uNames),rows:any[]=[];const reasonCounts:Record<string,number>={};
  let identityTotal=0,incompleteTotal=0,readyTotal=0;
  const audits=[{exchange:'bithumb' as const,items:bRows.results||[],names:bNames},{exchange:'upbit' as const,items:uRows.results||[],names:uNames}];
  for(const audit of audits){
    const cached=new Map(audit.items.map(row=>[clean(row.market).toUpperCase(),row]));
    for(const official of audit.names.values()){
      const market=clean(official.market).toUpperCase(),row=cached.get(market);
      if(!row){
        reasonCounts.profile_missing=(reasonCounts.profile_missing||0)+1;incompleteTotal++;
        rows.push({exchange:audit.exchange,market,korean_name:official.korean_name,official_english_name:official.english_name,cached_english_name:'',research_status:'missing',source_count:0,match_confidence:0,reasons:['profile_missing'],foreign_projects:[],business_preview:'',homepage:'',provider:'',provider_id:'',last_verified_at:0});
        continue;
      }
      const integrity=evaluateProfileIntegrity(row,official,known),quality=qualityReasons(row),reasons=[...new Set([...integrity.reasons,...quality])];
      if(!reasons.length){readyTotal++;continue}
      const hasIdentity=integrity.reasons.length>0;if(hasIdentity)identityTotal++;if(quality.length)incompleteTotal++;
      for(const reason of reasons)reasonCounts[reason]=(reasonCounts[reason]||0)+1;
      rows.push({exchange:audit.exchange,market:row.market,korean_name:official.korean_name||row.korean_name,official_english_name:official.english_name||'',cached_english_name:row.english_name,research_status:row.research_status,canonical_sector:row.canonical_sector,source_count:num(row.source_count),match_confidence:num(row.match_confidence),reasons,foreign_projects:integrity.foreign_projects,business_preview:clean(row.business_summary_ko||row.description_ko||row.description_en).slice(0,240),homepage:clean(row.homepage),provider:clean(row.provider),provider_id:clean(row.provider_id),last_verified_at:num(row.last_verified_at)});
    }
  }
  const severity=(row:any)=>row.reasons.includes('profile_missing')?1000:row.reasons.includes('content_foreign_identity')?900:row.reasons.includes('cached_name_mismatch')?880:row.reasons.includes('content_lead_name_mismatch')?850:row.reasons.includes('korean_missing')?700:row.reasons.includes('research_unresolved')?650:row.reasons.includes('sector_unresolved')?500:row.reasons.includes('weak_evidence')?300:100;
  rows.sort((a,b)=>severity(b)-severity(a)||clean(a.exchange).localeCompare(clean(b.exchange))||clean(a.market).localeCompare(clean(b.market)));
  const byExchange={bithumb:rows.filter(x=>x.exchange==='bithumb').length,upbit:rows.filter(x=>x.exchange==='upbit').length};
  return json({ok:true,audited_at:Math.floor(Date.now()/1000),market_scope:{bithumb:bNames.size,upbit:uNames.size},cached_scope:{bithumb:bRows.results?.length||0,upbit:uRows.results?.length||0},ready_total:readyTotal,total:rows.length,identity_total:identityTotal,incomplete_total:incompleteTotal,by_exchange:byExchange,reasons:reasonCounts,rows:rows.slice(0,120),rows_truncated:rows.length>120});
};