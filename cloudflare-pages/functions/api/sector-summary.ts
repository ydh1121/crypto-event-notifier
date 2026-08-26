import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {sectorFor, sectorInfo, TAXONOMY_SOURCE_NOTE} from '../lib/coin-taxonomy';
import type {Env} from '../lib/types';

type SectorRow = {
  exchange: string;
  market: string;
  symbol: string;
  name_ko: string;
  name_en: string;
  source_ts: number;
  received_at: number;
  turnover_24h: number;
  change_24h_pct: number;
  opportunity_score: number;
  position_value_krw: number;
  categories: string[];
};

type SectorCoin = {
  market: string;
  symbol: string;
  name_ko: string;
  name_en: string;
  turnover_24h: number;
  change_24h_pct: number;
  opportunity_score: number;
  profile_cached: boolean;
};

type SectorAggregate = {
  sector: string;
  market_count: number;
  turnover_24h: number;
  positive_turnover: number;
  weighted_change_sum: number;
  opportunity_sum: number;
  paper_position_krw: number;
  coins: SectorCoin[];
};

const RANGES: Record<string, number> = {h1: 3600, h6: 21600, h24: 86400, d7: 604800};

function num(value: unknown): number {
  const out = Number(value || 0);
  return Number.isFinite(out) ? out : 0;
}
function symbolOf(market: string): string { return String(market || '').toUpperCase().replace(/^KRW-/, '').replace(/^USDT-/, ''); }
function clamp(value: number, min: number, max: number): number { return Math.max(min, Math.min(max, value)); }
function round(value: number, digits = 2): number { const p = 10 ** digits; return Math.round(value * p) / p; }
function parseCategories(value: unknown): string[] {
  try {
    const parsed = JSON.parse(String(value || '[]'));
    return Array.isArray(parsed) ? parsed.map(item => String(item || '').trim()).filter(Boolean).slice(0, 24) : [];
  } catch { return []; }
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  try { await requireSession(env, request); }
  catch { return error(401, 'AUTH_REQUIRED', '로그인이 필요합니다.'); }

  const url = new URL(request.url);
  const exchange = url.searchParams.get('exchange') === 'upbit' ? 'upbit' : 'bithumb';
  const rangeKey = String(url.searchParams.get('range') || 'h24');
  const rangeSeconds = RANGES[rangeKey] || RANGES.h24;
  const now = Math.floor(Date.now() / 1000);

  const [query, officialNames] = await Promise.all([
    env.DB.prepare(
      `SELECT md.exchange, md.market, md.source_ts, md.received_at,
        json_extract(md.detail_json,'$.summary.name') AS detail_name,
        json_extract(md.detail_json,'$.summary.symbol') AS detail_symbol,
        CAST(COALESCE(json_extract(md.detail_json,'$.signal.turnover_24h'),0) AS REAL) AS turnover_24h,
        CAST(COALESCE(json_extract(md.detail_json,'$.signal.change_24h_pct'),0) AS REAL) AS change_24h_pct,
        CAST(COALESCE(json_extract(md.detail_json,'$.signal.opportunity_score'),json_extract(md.detail_json,'$.summary.opportunity_score'),0) AS REAL) AS opportunity_score,
        CAST(COALESCE(json_extract(md.detail_json,'$.summary.position_value_krw'),0) AS REAL) AS position_value_krw,
        COALESCE(cp.korean_name,'') AS cached_korean_name,
        COALESCE(cp.english_name,'') AS cached_english_name,
        COALESCE(cp.categories_json,'[]') AS categories_json
       FROM market_details md
       LEFT JOIN coin_profile_cache cp ON cp.exchange=md.exchange AND cp.market=md.market
       WHERE md.exchange=? AND md.strategy='adaptive'
       ORDER BY md.received_at DESC
       LIMIT 1200`,
    ).bind(exchange).all<Record<string, unknown>>(),
    exchangeMarketNames(exchange),
  ]);

  const rows: SectorRow[] = (query.results || []).map(row => {
    const market = String(row.market || '').toUpperCase();
    const official = officialNames.get(market);
    const symbol = String(row.detail_symbol || '').trim().toUpperCase() || symbolOf(market);
    return {
      exchange,
      market,
      symbol,
      name_ko: String(official?.korean_name || row.cached_korean_name || row.detail_name || symbol).trim(),
      name_en: String(official?.english_name || row.cached_english_name || symbol).trim(),
      source_ts: num(row.source_ts),
      received_at: num(row.received_at),
      turnover_24h: Math.max(0, num(row.turnover_24h)),
      change_24h_pct: num(row.change_24h_pct),
      opportunity_score: num(row.opportunity_score),
      position_value_krw: Math.max(0, num(row.position_value_krw)),
      categories: parseCategories(row.categories_json),
    };
  }).filter(row => row.market);

  const aggregates = new Map<string, SectorAggregate>();
  for (const row of rows) {
    const sector = sectorFor(row.symbol, row.categories);
    const current = aggregates.get(sector) || {
      sector, market_count: 0, turnover_24h: 0, positive_turnover: 0, weighted_change_sum: 0,
      opportunity_sum: 0, paper_position_krw: 0, coins: [],
    };
    current.market_count += 1;
    current.turnover_24h += row.turnover_24h;
    if (row.change_24h_pct > 0) current.positive_turnover += row.turnover_24h;
    current.weighted_change_sum += row.change_24h_pct * row.turnover_24h;
    current.opportunity_sum += row.opportunity_score;
    current.paper_position_krw += row.position_value_krw;
    current.coins.push({
      market: row.market,
      symbol: row.symbol,
      name_ko: row.name_ko,
      name_en: row.name_en,
      turnover_24h: row.turnover_24h,
      change_24h_pct: row.change_24h_pct,
      opportunity_score: row.opportunity_score,
      profile_cached: row.categories.length > 0,
    });
    aggregates.set(sector, current);
  }

  const sectors = [...aggregates.values()].map(item => {
    const positiveShare = item.turnover_24h > 0 ? item.positive_turnover / item.turnover_24h * 100 : 0;
    const weightedChange = item.turnover_24h > 0 ? item.weighted_change_sum / item.turnover_24h : 0;
    const info = sectorInfo(item.sector);
    return {
      sector: item.sector,
      sector_description: info.summary,
      sector_business: info.business,
      market_count: item.market_count,
      turnover_24h: round(item.turnover_24h, 0),
      positive_turnover_share_pct: round(positiveShare, 2),
      weighted_change_pct: round(weightedChange, 3),
      flow_score: round(clamp((positiveShare - 50) * 2, -100, 100), 1),
      opportunity_avg: round(item.opportunity_sum / Math.max(1, item.market_count), 1),
      paper_position_krw: round(item.paper_position_krw, 0),
      coins: item.coins.sort((a, b) => b.turnover_24h - a.turnover_24h),
    };
  }).sort((a, b) => b.turnover_24h - a.turnover_24h);

  const totalTurnover = sectors.reduce((sum, row) => sum + row.turnover_24h, 0);
  const positiveTurnover = sectors.reduce((sum, row) => sum + row.turnover_24h * row.positive_turnover_share_pct / 100, 0);

  if (sectors.length) {
    const latest = await env.DB.prepare('SELECT MAX(ts) AS ts FROM sector_history WHERE exchange=?').bind(exchange).first<{ts: number}>();
    if (!latest?.ts || now - Number(latest.ts) >= 60) {
      const statements: D1PreparedStatement[] = sectors.map(row => env.DB.prepare(
        `INSERT INTO sector_history(exchange,sector,ts,turnover_24h,positive_turnover_share_pct,weighted_change_pct,opportunity_avg,market_count)
         VALUES(?,?,?,?,?,?,?,?)`,
      ).bind(exchange, row.sector, now, row.turnover_24h, row.positive_turnover_share_pct, row.weighted_change_pct, row.opportunity_avg, row.market_count));
      await env.DB.batch(statements);
      env.DB.prepare('DELETE FROM sector_history WHERE ts<?').bind(now - 90 * 86400).run().catch(() => undefined);
    }
  }

  const historyResult = await env.DB.prepare(
    `SELECT sector,ts,turnover_24h,positive_turnover_share_pct,weighted_change_pct,opportunity_avg,market_count
     FROM sector_history WHERE exchange=? AND ts>=? ORDER BY ts ASC LIMIT 4000`,
  ).bind(exchange, now - rangeSeconds).all<Record<string, unknown>>();

  const history = (historyResult.results || []).map(row => ({
    sector: String(row.sector || ''),
    ts: num(row.ts),
    turnover_24h: num(row.turnover_24h),
    positive_turnover_share_pct: num(row.positive_turnover_share_pct),
    weighted_change_pct: num(row.weighted_change_pct),
    opportunity_avg: num(row.opportunity_avg),
    market_count: num(row.market_count),
  }));

  return json({
    ok: true,
    exchange,
    range: rangeKey,
    updated_at: now,
    summary: {
      market_count: rows.length,
      sector_count: sectors.length,
      turnover_24h: round(totalTurnover, 0),
      positive_turnover_share_pct: round(totalTurnover > 0 ? positiveTurnover / totalTurnover * 100 : 0, 2),
    },
    sectors,
    history,
    taxonomy_source: TAXONOMY_SOURCE_NOTE,
    methodology: '24시간 거래대금 중 상승 코인에 집중된 비율과 거래대금 가중 등락률을 대표 섹터별로 집계합니다. 순입출금액이 아니라 거래 집중도 지표이며, 외부 메타데이터가 있는 코인은 다음 조회부터 대표 섹터 정규화에 반영됩니다.',
  });
};
