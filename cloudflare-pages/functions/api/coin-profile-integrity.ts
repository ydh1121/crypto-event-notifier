import {requireSession} from '../lib/auth';
import {error,json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {evaluateProfileIntegrity,knownProjects,type ProfileIntegrityRow} from '../lib/coin-profile-integrity';
import type {Env} from '../lib/types';

const clean=(value:unknown)=>String(value??'').trim();
export const onRequestGet:PagesFunction<Env>=async({request,env})=>{
  try{await requireSession(env,request)}catch{return error(401,'AUTH_REQUIRED','로그인이 필요합니다.')}
  const url=new URL(request.url),exchange=url.searchParams.get('exchange')==='upbit'?'upbit':'bithumb',market=clean(url.searchParams.get('market')).toUpperCase();
  if(!/^(KRW|USDT)-[A-Z0-9._-]{1,32}$/.test(market))return error(400,'INVALID_MARKET','코인 마켓 형식을 확인하세요.');
  const [row,bNames,uNames]=await Promise.all([
    env.DB.prepare(`SELECT exchange,market,korean_name,english_name,provider,provider_id,business_summary_ko,description_ko,description_en,homepage,evidence_json,research_status,source_count,match_confidence,last_verified_at FROM coin_profile_cache WHERE exchange=? AND market=?`).bind(exchange,market).first<ProfileIntegrityRow>(),
    exchangeMarketNames('bithumb'),exchangeMarketNames('upbit'),
  ]);
  if(!row)return json({ok:true,status:'unknown',reasons:[],foreign_projects:[]});
  const names=exchange==='upbit'?uNames:bNames,official=names.get(market),finding=evaluateProfileIntegrity(row,official,knownProjects(bNames,uNames));
  return json({ok:true,status:finding.reasons.length?'mismatch':'ok',reasons:finding.reasons,foreign_projects:finding.foreign_projects,official_english_name:official?.english_name||'',cached_english_name:row.english_name});
};
