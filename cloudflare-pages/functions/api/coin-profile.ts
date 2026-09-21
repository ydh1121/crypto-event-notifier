import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {sectorFor, sectorInfo, TAXONOMY_SOURCE_NOTE} from '../lib/coin-taxonomy';
import type {Env} from '../lib/types';

type CachedProfile = {
  exchange: string; market: string; provider: string; provider_id: string;
  korean_name: string; english_name: string; description_ko: string; description_en: string;
  categories_json: string; homepage: string; image_url: string; updated_at: number;
  business_summary_ko: string; business_summary_en: string; canonical_sector: string;
  tags_json: string; evidence_json: string; official_docs: string; whitepaper: string;
  source_code: string; community_json: string; research_status: string; summary_source: string;
  source_count: number; match_confidence: number; last_verified_at: number;
};

const THIRTY_DAYS = 30 * 86400;
const NINETY_DAYS = 90 * 86400;
function text(value: unknown): string { return String(value || '').trim(); }
function symbolOf(market: string): string { return market.toUpperCase().replace(/^KRW-/, '').replace(/^USDT-/, ''); }
function safeUrl(value: unknown): string { const raw=text(value); try { const url=new URL(raw); return url.protocol==='https:'||url.protocol==='http:'?url.toString():''; } catch { return ''; } }
function plain(value: unknown, limit=5000): string { return text(value).replace(/<br\s*\/?\s*>/gi,'\n').replace(/<[^>]+>/g,' ').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/[ \t]+/g,' ').replace(/\n\s+/g,'\n').trim().slice(0,limit); }
function shortBusiness(value: unknown, limit=520): string { const source=plain(value,3000); if(!source)return''; const pieces=source.split(/(?<=[.!?。！？])\s+/); let out=''; for(const piece of pieces){const next=(out+' '+piece.trim()).trim();if(next.length>limit)break;out=next;if(out.length>=180)break}return out||source.slice(0,limit); }
function stringArray(value: unknown): string[] { if(Array.isArray(value))return value.map(text).filter(Boolean).slice(0,40); try{const parsed=JSON.parse(text(value)||'[]');return Array.isArray(parsed)?parsed.map(text).filter(Boolean).slice(0,40):[]}catch{return[]} }
function jsonObjects(value: unknown): any[] { if(Array.isArray(value))return value.slice(0,16); try{const parsed=JSON.parse(text(value)||'[]');return Array.isArray(parsed)?parsed.slice(0,16):[]}catch{return[]} }
function normalized(value:string):string{return value.toLowerCase().replace(/[^a-z0-9가-힣]+/g,'')}

async function exchangeFallback(env:Env,exchange:string,market:string){
  const names=await exchangeMarketNames(exchange);const official=names.get(market);
  const detail=await env.DB.prepare(`SELECT json_extract(detail_json,'$.summary.name') AS detail_name,json_extract(detail_json,'$.summary.symbol') AS detail_symbol FROM market_details WHERE exchange=? AND market=? AND strategy='adaptive' LIMIT 1`).bind(exchange,market).first<Record<string,unknown>>();
  return{symbol:text(detail?.detail_symbol)||symbolOf(market),korean_name:text(official?.korean_name)||text(detail?.detail_name)||symbolOf(market),english_name:text(official?.english_name)||symbolOf(market)};
}

async function fromCoinGecko(symbol:string,englishName:string){
  const searchResponse=await fetch(`https://api.coingecko.com/api/v3/search?query=${encodeURIComponent(symbol)}`,{headers:{accept:'application/json','user-agent':'crypto-research-viewer/33'}});
  if(!searchResponse.ok)throw new Error(`CoinGecko search ${searchResponse.status}`);const search:any=await searchResponse.json();
  const candidates=Array.isArray(search?.coins)?search.coins.filter((row:any)=>text(row?.symbol).toUpperCase()===symbol.toUpperCase()):[];if(!candidates.length)throw new Error('CoinGecko match not found');
  const wanted=normalized(englishName);candidates.sort((a:any,b:any)=>{const am=wanted&&normalized(text(a?.name))===wanted?1:0,bm=wanted&&normalized(text(b?.name))===wanted?1:0;if(am!==bm)return bm-am;return Number(a?.market_cap_rank||999999)-Number(b?.market_cap_rank||999999)});
  const id=text(candidates[0]?.id);if(!id)throw new Error('CoinGecko id missing');
  const detailResponse=await fetch(`https://api.coingecko.com/api/v3/coins/${encodeURIComponent(id)}?localization=true&tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false`,{headers:{accept:'application/json','user-agent':'crypto-research-viewer/33'}});
  if(!detailResponse.ok)throw new Error(`CoinGecko detail ${detailResponse.status}`);const detail:any=await detailResponse.json();
  const links=Array.isArray(detail?.links?.homepage)?detail.links.homepage:[];const repos=detail?.links?.repos_url?.github||[];const communities=[detail?.links?.subreddit_url,detail?.links?.twitter_screen_name?`https://x.com/${detail.links.twitter_screen_name}`:'',detail?.links?.telegram_channel_identifier?`https://t.me/${detail.links.telegram_channel_identifier}`:''].map(safeUrl).filter(Boolean);
  return{provider:'coingecko',provider_id:id,english_name:text(detail?.name)||englishName,korean_name:text(detail?.localization?.ko),description_ko:plain(detail?.description?.ko),description_en:plain(detail?.description?.en),categories:stringArray(detail?.categories),homepage:safeUrl(links.find((item:unknown)=>safeUrl(item))||''),image_url:safeUrl(detail?.image?.small||detail?.image?.thumb||''),source_code:safeUrl(repos[0]||''),community:communities};
}

function payload(row:CachedProfile,symbol:string){
  const categories=stringArray(row.categories_json),tags=stringArray(row.tags_json),evidence=jsonObjects(row.evidence_json),community=stringArray(row.community_json);
  const sector=text(row.canonical_sector)||sectorFor(symbol,[...categories,...tags],`${row.business_summary_ko}\n${row.business_summary_en}\n${row.description_ko}\n${row.description_en}`);
  const hasKorean=Boolean(text(row.business_summary_ko)||text(row.description_ko));
  return{
    ok:true,exchange:row.exchange,market:row.market,symbol,
    korean_name:row.korean_name,english_name:row.english_name,
    description_ko:row.description_ko,
    description_en:hasKorean?row.description_en:'',
    business_summary_ko:row.business_summary_ko,business_summary_en:hasKorean?row.business_summary_en:'',
    categories,tags,homepage:row.homepage,image_url:row.image_url,official_docs:row.official_docs,
    whitepaper:row.whitepaper,source_code:row.source_code,community,evidence,provider:row.provider,
    provider_id:row.provider_id,updated_at:Number(row.updated_at||0),last_verified_at:Number(row.last_verified_at||0),
    research_status:row.research_status||'pending',summary_source:row.summary_source||'',source_count:Number(row.source_count||0),
    match_confidence:Number(row.match_confidence||0),canonical_sector:sector,sector_info:sectorInfo(sector),taxonomy_note:TAXONOMY_SOURCE_NOTE,
    korean_ready:hasKorean,
  };
}

function inheritedPeer(peer:CachedProfile,exchange:string,market:string,fallback:{korean_name:string;english_name:string}):CachedProfile{
  return{...peer,exchange,market,korean_name:fallback.korean_name||peer.korean_name,english_name:fallback.english_name||peer.english_name};
}

export const onRequestGet:PagesFunction<Env>=async({request,env})=>{
  try{await requireSession(env,request)}catch{return error(401,'AUTH_REQUIRED','로그인이 필요합니다.')}
  const url=new URL(request.url),exchange=url.searchParams.get('exchange')==='upbit'?'upbit':'bithumb',market=text(url.searchParams.get('market')).toUpperCase();
  if(!/^(KRW|USDT)-[A-Z0-9._-]{1,32}$/.test(market))return error(400,'INVALID_MARKET','코인 마켓 형식을 확인하세요.');
  const now=Math.floor(Date.now()/1000),fallback=await exchangeFallback(env,exchange,market);
  const cached=await env.DB.prepare('SELECT * FROM coin_profile_cache WHERE exchange=? AND market=?').bind(exchange,market).first<CachedProfile>();
  if(cached){
    const verified=Number(cached.last_verified_at||0),enriched=['verified','corroborated','single_source'].includes(cached.research_status||'');
    if(enriched&&verified&&now-verified<NINETY_DAYS&&Boolean(cached.business_summary_ko||cached.description_ko))return json(payload(cached,fallback.symbol));
    if(cached.provider==='coingecko'&&now-Number(cached.updated_at||0)<THIRTY_DAYS&&Boolean(cached.business_summary_ko||cached.description_ko))return json(payload(cached,fallback.symbol));
  }

  const peer=await env.DB.prepare(`SELECT * FROM coin_profile_cache WHERE market=? AND exchange<>? AND (business_summary_ko<>'' OR description_ko<>'') ORDER BY source_count DESC,last_verified_at DESC LIMIT 1`).bind(market,exchange).first<CachedProfile>();
  if(peer)return json(payload(inheritedPeer(peer,exchange,market,fallback),fallback.symbol));

  let profile:any=null;try{profile=await fromCoinGecko(fallback.symbol,fallback.english_name)}catch{profile=null}
  const categories=profile?.categories||[],descriptionKo=profile?.description_ko||'',descriptionEn=profile?.description_en||'',businessKo=shortBusiness(descriptionKo),businessEn=shortBusiness(descriptionEn),sector=sectorFor(fallback.symbol,categories,`${descriptionKo}\n${descriptionEn}`),evidence=profile?[{source:'coingecko',url:`https://www.coingecko.com/en/coins/${profile.provider_id}`,label:'CoinGecko metadata',language:'multi',weight:.82}]:[];
  const row:CachedProfile={exchange,market,provider:profile?.provider||'exchange',provider_id:profile?.provider_id||'',korean_name:profile?.korean_name||fallback.korean_name,english_name:profile?.english_name||fallback.english_name,description_ko:descriptionKo,description_en:descriptionEn,categories_json:JSON.stringify(categories),homepage:profile?.homepage||'',image_url:profile?.image_url||'',updated_at:now,business_summary_ko:businessKo,business_summary_en:businessEn,canonical_sector:sector,tags_json:'[]',evidence_json:JSON.stringify(evidence),official_docs:'',whitepaper:'',source_code:profile?.source_code||'',community_json:JSON.stringify(profile?.community||[]),research_status:profile?'single_source':'pending',summary_source:businessKo?'coingecko_ko':businessEn?'coingecko':'',source_count:profile?1:0,match_confidence:profile?.provider_id?.length?0.82:0,last_verified_at:profile?now:0};
  await env.DB.prepare(`INSERT INTO coin_profile_cache(exchange,market,provider,provider_id,korean_name,english_name,description_ko,description_en,categories_json,homepage,image_url,updated_at,business_summary_ko,business_summary_en,canonical_sector,tags_json,evidence_json,official_docs,whitepaper,source_code,community_json,research_status,summary_source,source_count,match_confidence,last_verified_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(exchange,market) DO UPDATE SET provider=excluded.provider,provider_id=excluded.provider_id,korean_name=excluded.korean_name,english_name=excluded.english_name,description_ko=excluded.description_ko,description_en=excluded.description_en,categories_json=excluded.categories_json,homepage=excluded.homepage,image_url=excluded.image_url,updated_at=excluded.updated_at,business_summary_ko=excluded.business_summary_ko,business_summary_en=excluded.business_summary_en,canonical_sector=excluded.canonical_sector,source_code=excluded.source_code,community_json=excluded.community_json,research_status=excluded.research_status,summary_source=excluded.summary_source,source_count=excluded.source_count,match_confidence=excluded.match_confidence,last_verified_at=excluded.last_verified_at`).bind(row.exchange,row.market,row.provider,row.provider_id,row.korean_name,row.english_name,row.description_ko,row.description_en,row.categories_json,row.homepage,row.image_url,row.updated_at,row.business_summary_ko,row.business_summary_en,row.canonical_sector,row.tags_json,row.evidence_json,row.official_docs,row.whitepaper,row.source_code,row.community_json,row.research_status,row.summary_source,row.source_count,row.match_confidence,row.last_verified_at).run();
  return json(payload(row,fallback.symbol));
};
