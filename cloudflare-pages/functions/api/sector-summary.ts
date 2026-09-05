import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {sectorFor, sectorInfo, TAXONOMY_SOURCE_NOTE} from '../lib/coin-taxonomy';
import type {Env} from '../lib/types';

type SectorRow = {
  exchange:string; market:string; symbol:string; name_ko:string; name_en:string;
  source_ts:number; received_at:number; turnover_24h:number; change_24h_pct:number;
  d1_pct:number|null; d2_pct:number|null; d3_pct:number|null; d4_pct:number|null; d5_pct:number|null;
  cum_1d_pct:number|null; cum_3d_pct:number|null; cum_5d_pct:number|null; cum_7d_pct:number|null; cum_30d_pct:number|null;
  lifecycle_state:string;
  opportunity_score:number; position_value_krw:number; categories:string[]; tags:string[];
  canonical_sector:string; research_status:string; business_summary_ko:string; business_summary_en:string;
  description_ko:string; description_en:string;
};
type SectorCoin = {
  market:string; symbol:string; name_ko:string; name_en:string; turnover_24h:number;
  change_24h_pct:number; d1_pct:number|null; d2_pct:number|null; d3_pct:number|null; d4_pct:number|null; d5_pct:number|null;
  cum_1d_pct:number|null; cum_3d_pct:number|null; cum_5d_pct:number|null; cum_7d_pct:number|null; cum_30d_pct:number|null;
  lifecycle_state:string; opportunity_score:number; profile_cached:boolean; research_status:string;
};
type SectorAggregate = {
  sector:string; market_count:number; turnover_24h:number; positive_turnover:number;
  weighted_change_sum:number; opportunity_sum:number; paper_position_krw:number; coins:SectorCoin[];
};

const RANGES:Record<string,number>={h1:3600,h6:21600,h24:86400,d7:604800};
const num=(value:unknown)=>{const out=Number(value||0);return Number.isFinite(out)?out:0};
const nullableNum=(value:unknown):number|null=>{if(value===null||value===undefined||value==='')return null;const out=Number(value);return Number.isFinite(out)?out:null};
const symbolOf=(market:string)=>String(market||'').toUpperCase().replace(/^KRW-/,'').replace(/^USDT-/,'');
const clamp=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
const round=(value:number,digits=2)=>{const p=10**digits;return Math.round(value*p)/p};
function parseList(value:unknown,max=40):string[]{try{const parsed=JSON.parse(String(value||'[]'));return Array.isArray(parsed)?parsed.map(item=>String(item||'').trim()).filter(Boolean).slice(0,max):[]}catch{return[]}}

export const onRequestGet:PagesFunction<Env>=async({request,env})=>{
  try{await requireSession(env,request)}catch{return error(401,'AUTH_REQUIRED','로그인이 필요합니다.')}
  const url=new URL(request.url);
  const exchange=url.searchParams.get('exchange')==='upbit'?'upbit':'bithumb';
  const rangeKey=String(url.searchParams.get('range')||'h24');
  const rangeSeconds=RANGES[rangeKey]||RANGES.h24;
  const now=Math.floor(Date.now()/1000);

  const [query,officialNames]=await Promise.all([
    env.DB.prepare(`SELECT md.exchange,md.market,md.source_ts,md.received_at,
      json_extract(md.detail_json,'$.summary.name') AS detail_name,
      json_extract(md.detail_json,'$.summary.symbol') AS detail_symbol,
      CAST(COALESCE(json_extract(md.detail_json,'$.signal.turnover_24h'),0) AS REAL) AS turnover_24h,
      CAST(COALESCE(json_extract(md.detail_json,'$.signal.change_24h_pct'),0) AS REAL) AS change_24h_pct,
      json_extract(md.detail_json,'$.return_windows.d1_pct') AS d1_pct,
      json_extract(md.detail_json,'$.return_windows.d2_pct') AS d2_pct,
      json_extract(md.detail_json,'$.return_windows.d3_pct') AS d3_pct,
      json_extract(md.detail_json,'$.return_windows.d4_pct') AS d4_pct,
      json_extract(md.detail_json,'$.return_windows.d5_pct') AS d5_pct,
      json_extract(md.detail_json,'$.return_windows.cum_1d_pct') AS cum_1d_pct,
      json_extract(md.detail_json,'$.return_windows.cum_3d_pct') AS cum_3d_pct,
      json_extract(md.detail_json,'$.return_windows.cum_5d_pct') AS cum_5d_pct,
      json_extract(md.detail_json,'$.return_windows.cum_7d_pct') AS cum_7d_pct,
      json_extract(md.detail_json,'$.return_windows.cum_30d_pct') AS cum_30d_pct,
      COALESCE(NULLIF(json_extract(md.detail_json,'$.lifecycle_state'),''),'NORMAL') AS lifecycle_state,
      CAST(COALESCE(json_extract(md.detail_json,'$.signal.opportunity_score'),json_extract(md.detail_json,'$.summary.opportunity_score'),0) AS REAL) AS opportunity_score,
      CAST(COALESCE(json_extract(md.detail_json,'$.summary.position_value_krw'),0) AS REAL) AS position_value_krw,
      COALESCE(NULLIF(cp.korean_name,''),NULLIF(peer.korean_name,''),'') AS cached_korean_name,
      COALESCE(NULLIF(cp.english_name,''),NULLIF(peer.english_name,''),'') AS cached_english_name,
      COALESCE(NULLIF(cp.categories_json,'[]'),NULLIF(peer.categories_json,'[]'),'[]') AS categories_json,
      COALESCE(NULLIF(cp.tags_json,'[]'),NULLIF(peer.tags_json,'[]'),'[]') AS tags_json,
      COALESCE(NULLIF(cp.canonical_sector,''),NULLIF(peer.canonical_sector,''),'') AS canonical_sector,
      CASE
        WHEN cp.research_status IN ('verified','corroborated','single_source') THEN cp.research_status
        WHEN peer.research_status IN ('verified','corroborated','single_source') THEN peer.research_status
        ELSE COALESCE(NULLIF(cp.research_status,''),NULLIF(peer.research_status,''),'pending')
      END AS research_status,
      COALESCE(NULLIF(cp.business_summary_ko,''),NULLIF(peer.business_summary_ko,''),'') AS business_summary_ko,
      COALESCE(NULLIF(cp.business_summary_en,''),NULLIF(peer.business_summary_en,''),'') AS business_summary_en,
      COALESCE(NULLIF(cp.description_ko,''),NULLIF(peer.description_ko,''),'') AS description_ko,
      COALESCE(NULLIF(cp.description_en,''),NULLIF(peer.description_en,''),'') AS description_en
      FROM market_details md
      LEFT JOIN coin_profile_cache cp ON cp.exchange=md.exchange AND cp.market=md.market
      LEFT JOIN coin_profile_cache peer ON peer.market=md.market AND peer.exchange<>md.exchange
      WHERE md.exchange=? AND md.strategy='adaptive'
      ORDER BY md.received_at DESC LIMIT 1200`).bind(exchange).all<Record<string,unknown>>(),
    exchangeMarketNames(exchange),
  ]);

  const rows:SectorRow[]=(query.results||[]).map(row=>{
    const market=String(row.market||'').toUpperCase();
    const official=officialNames.get(market);
    const symbol=String(row.detail_symbol||'').trim().toUpperCase()||symbolOf(market);
    return{
      exchange,market,symbol,
      name_ko:String(official?.korean_name||row.cached_korean_name||row.detail_name||symbol).trim(),
      name_en:String(official?.english_name||row.cached_english_name||symbol).trim(),
      source_ts:num(row.source_ts),received_at:num(row.received_at),
      turnover_24h:Math.max(0,num(row.turnover_24h)),change_24h_pct:num(row.change_24h_pct),
      d1_pct:nullableNum(row.d1_pct),d2_pct:nullableNum(row.d2_pct),d3_pct:nullableNum(row.d3_pct),
      d4_pct:nullableNum(row.d4_pct),d5_pct:nullableNum(row.d5_pct),
      cum_1d_pct:nullableNum(row.cum_1d_pct),cum_3d_pct:nullableNum(row.cum_3d_pct),
      cum_5d_pct:nullableNum(row.cum_5d_pct),cum_7d_pct:nullableNum(row.cum_7d_pct),cum_30d_pct:nullableNum(row.cum_30d_pct),
      lifecycle_state:String(row.lifecycle_state||'NORMAL').trim().toUpperCase(),
      opportunity_score:num(row.opportunity_score),position_value_krw:Math.max(0,num(row.position_value_krw)),
      categories:parseList(row.categories_json),tags:parseList(row.tags_json),
      canonical_sector:String(row.canonical_sector||'').trim(),research_status:String(row.research_status||'pending'),
      business_summary_ko:String(row.business_summary_ko||''),business_summary_en:String(row.business_summary_en||''),
      description_ko:String(row.description_ko||''),description_en:String(row.description_en||''),
    };
  }).filter(row=>row.market);

  const aggregates=new Map<string,SectorAggregate>();
  for(const row of rows){
    const evidenceText=`${row.business_summary_ko}\n${row.business_summary_en}\n${row.description_ko}\n${row.description_en}`;
    const sector=row.canonical_sector||sectorFor(row.symbol,[...row.categories,...row.tags],evidenceText);
    const current=aggregates.get(sector)||{sector,market_count:0,turnover_24h:0,positive_turnover:0,weighted_change_sum:0,opportunity_sum:0,paper_position_krw:0,coins:[]};
    current.market_count++;
    current.turnover_24h+=row.turnover_24h;
    if(row.change_24h_pct>0)current.positive_turnover+=row.turnover_24h;
    current.weighted_change_sum+=row.change_24h_pct*row.turnover_24h;
    current.opportunity_sum+=row.opportunity_score;
    current.paper_position_krw+=row.position_value_krw;
    const koreanReady=Boolean(row.business_summary_ko||row.description_ko);
    current.coins.push({
      market:row.market,symbol:row.symbol,name_ko:row.name_ko,name_en:row.name_en,
      turnover_24h:row.turnover_24h,change_24h_pct:row.change_24h_pct,
      d1_pct:row.d1_pct,d2_pct:row.d2_pct,d3_pct:row.d3_pct,d4_pct:row.d4_pct,d5_pct:row.d5_pct,
      cum_1d_pct:row.cum_1d_pct,cum_3d_pct:row.cum_3d_pct,cum_5d_pct:row.cum_5d_pct,
      cum_7d_pct:row.cum_7d_pct,cum_30d_pct:row.cum_30d_pct,
      lifecycle_state:row.lifecycle_state,opportunity_score:row.opportunity_score,
      profile_cached:koreanReady,research_status:row.research_status,
    });
    aggregates.set(sector,current);
  }

  const sectors=[...aggregates.values()].map(item=>{
    const positiveShare=item.turnover_24h>0?item.positive_turnover/item.turnover_24h*100:0;
    const weightedChange=item.turnover_24h>0?item.weighted_change_sum/item.turnover_24h:0;
    const info=sectorInfo(item.sector);
    return{
      sector:item.sector,sector_description:info.summary,sector_business:info.business,
      market_count:item.market_count,turnover_24h:round(item.turnover_24h,0),
      positive_turnover_share_pct:round(positiveShare,2),weighted_change_pct:round(weightedChange,3),
      flow_score:round(clamp((positiveShare-50)*2,-100,100),1),
      opportunity_avg:round(item.opportunity_sum/Math.max(1,item.market_count),1),
      paper_position_krw:round(item.paper_position_krw,0),
      coins:item.coins.sort((a,b)=>b.turnover_24h-a.turnover_24h),
    };
  }).sort((a,b)=>b.turnover_24h-a.turnover_24h);

  const totalTurnover=sectors.reduce((sum,row)=>sum+row.turnover_24h,0);
  const positiveTurnover=sectors.reduce((sum,row)=>sum+row.turnover_24h*row.positive_turnover_share_pct/100,0);
  const koreanReady=rows.filter(row=>Boolean(row.business_summary_ko||row.description_ko)).length;
  const researched=rows.filter(row=>Boolean(row.business_summary_ko||row.description_ko)&&!['pending','unresolved'].includes(row.research_status)).length;
  const unresolved=Math.max(0,rows.length-researched);
  const koreanMissing=Math.max(0,rows.length-koreanReady);
  const verificationPending=Math.max(0,koreanReady-researched);
  const lifecycleCounts=rows.reduce<Record<string,number>>((out,row)=>{out[row.lifecycle_state]=(out[row.lifecycle_state]||0)+1;return out},{});

  if(sectors.length){
    const latest=await env.DB.prepare('SELECT MAX(ts) AS ts FROM sector_history WHERE exchange=?').bind(exchange).first<{ts:number}>();
    if(!latest?.ts||now-Number(latest.ts)>=60){
      const statements:D1PreparedStatement[]=sectors.map(row=>env.DB.prepare(
        `INSERT INTO sector_history(exchange,sector,ts,turnover_24h,positive_turnover_share_pct,weighted_change_pct,opportunity_avg,market_count) VALUES(?,?,?,?,?,?,?,?)`,
      ).bind(exchange,row.sector,now,row.turnover_24h,row.positive_turnover_share_pct,row.weighted_change_pct,row.opportunity_avg,row.market_count));
      await env.DB.batch(statements);
      env.DB.prepare('DELETE FROM sector_history WHERE ts<?').bind(now-90*86400).run().catch(()=>undefined);
    }
  }

  const historyResult=await env.DB.prepare(
    `SELECT sector,ts,turnover_24h,positive_turnover_share_pct,weighted_change_pct,opportunity_avg,market_count FROM sector_history WHERE exchange=? AND ts>=? ORDER BY ts ASC LIMIT 4000`,
  ).bind(exchange,now-rangeSeconds).all<Record<string,unknown>>();
  const history=(historyResult.results||[]).map(row=>({
    sector:String(row.sector||''),ts:num(row.ts),turnover_24h:num(row.turnover_24h),
    positive_turnover_share_pct:num(row.positive_turnover_share_pct),weighted_change_pct:num(row.weighted_change_pct),
    opportunity_avg:num(row.opportunity_avg),market_count:num(row.market_count),
  }));

  return json({
    ok:true,exchange,range:rangeKey,updated_at:now,
    summary:{
      market_count:rows.length,sector_count:sectors.length,turnover_24h:round(totalTurnover,0),
      positive_turnover_share_pct:round(totalTurnover>0?positiveTurnover/totalTurnover*100:0,2),
      researched_count:researched,korean_ready_count:koreanReady,unresolved_count:unresolved,
      korean_missing_count:koreanMissing,verification_pending_count:verificationPending,
      lifecycle_counts:lifecycleCounts,
    },
    sectors,history,taxonomy_source:TAXONOMY_SOURCE_NOTE,
    methodology:'24시간 거래대금 중 상승 코인에 집중된 비율과 거래대금 가중 등락률을 대표 섹터별로 집계합니다. 프로젝트 프로필은 거래소와 무관한 자산 정보이므로 동일 KRW 종목의 빗썸·업비트 조사 결과를 교차 재사용하며, 한국어 사업 설명이 준비되고 검증 상태가 완료된 종목만 조사 완료 수치에 반영합니다.',
  });
};
