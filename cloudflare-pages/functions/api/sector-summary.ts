import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import type {Env} from '../lib/types';

type SectorRow = {
  exchange: string;
  market: string;
  source_ts: number;
  received_at: number;
  turnover_24h: number;
  change_24h_pct: number;
  opportunity_score: number;
  position_value_krw: number;
};

type SectorAggregate = {
  sector: string;
  market_count: number;
  turnover_24h: number;
  positive_turnover: number;
  weighted_change_sum: number;
  opportunity_sum: number;
  paper_position_krw: number;
  coins: Array<{market: string; symbol: string; turnover_24h: number; change_24h_pct: number; opportunity_score: number}>;
};

const RANGES: Record<string, number> = {h1: 3600, h6: 21600, h24: 86400, d7: 604800};

const groups: Record<string, Set<string>> = {
  '메이저': new Set(['BTC','ETH']),
  '레이어1': new Set(['SOL','ADA','AVAX','SUI','APT','SEI','NEAR','TON','HBAR','ICP','ATOM','DOT','ALGO','KAS','EGLD','INJ','CELO','XTZ','MINA']),
  '레이어2': new Set(['ARB','OP','STRK','ZK','MNT','METIS','POL','IMX']),
  '디파이': new Set(['UNI','AAVE','CRV','COMP','MKR','SKY','SNX','LDO','JTO','JUP','PENDLE','ENA','RUNE','SUSHI','1INCH','DYDX','CAKE','GMX','BAL','CVX']),
  'AI·데이터': new Set(['FET','TAO','RENDER','RNDR','GRT','WLD','IO','ATH','ARKM','VIRTUAL','AIXBT','AKT','NMR','OCEAN']),
  '게임·메타버스': new Set(['SAND','MANA','AXS','GALA','BEAM','PIXEL','MAGIC','RON','ILV','YGG','PORTAL']),
  '밈': new Set(['DOGE','SHIB','PEPE','BONK','FLOKI','TRUMP','PENGU','WIF','BRETT','MOG','POPCAT','BOME','MEW','TURBO','NEIRO']),
  'RWA': new Set(['ONDO','OM','POLYX','CFG','XDC','RIO','MPL']),
  '결제·송금': new Set(['XRP','XLM','LTC','BCH','XEC','DASH']),
  '인프라·오라클': new Set(['LINK','PYTH','API3','TIA','FIL','AR','STORJ','ANKR','QNT','IOTA','IOTX','WAVES']),
  '프라이버시': new Set(['XMR','ZEC','ROSE','SCRT']),
  'NFT': new Set(['BLUR','LOOKS','APE','NFT','SUPER']),
  '거래소·유틸리티': new Set(['BNB','CRO','OKB','GT','KCS','LEO','BGB']),
};

function num(value: unknown): number {
  const out = Number(value || 0);
  return Number.isFinite(out) ? out : 0;
}

function symbolOf(market: string): string {
  return String(market || '').toUpperCase().replace(/^KRW-/, '').replace(/^USDT-/, '');
}

function sectorOf(market: string): string {
  const symbol = symbolOf(market);
  for (const [sector, symbols] of Object.entries(groups)) if (symbols.has(symbol)) return sector;
  return '기타';
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function round(value: number, digits = 2): number {
  const p = 10 ** digits;
  return Math.round(value * p) / p;
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  try { await requireSession(env, request); }
  catch { return error(401, 'AUTH_REQUIRED', '로그인이 필요합니다.'); }

  const url = new URL(request.url);
  const exchange = url.searchParams.get('exchange') === 'upbit' ? 'upbit' : 'bithumb';
  const rangeKey = String(url.searchParams.get('range') || 'h24');
  const rangeSeconds = RANGES[rangeKey] || RANGES.h24;
  const now = Math.floor(Date.now() / 1000);

  const query = await env.DB.prepare(
    `SELECT exchange, market, source_ts, received_at,
      CAST(COALESCE(json_extract(detail_json,'$.signal.turnover_24h'),0) AS REAL) AS turnover_24h,
      CAST(COALESCE(json_extract(detail_json,'$.signal.change_24h_pct'),0) AS REAL) AS change_24h_pct,
      CAST(COALESCE(json_extract(detail_json,'$.signal.opportunity_score'),json_extract(detail_json,'$.summary.opportunity_score'),0) AS REAL) AS opportunity_score,
      CAST(COALESCE(json_extract(detail_json,'$.summary.position_value_krw'),0) AS REAL) AS position_value_krw
     FROM market_details
     WHERE exchange=? AND strategy='adaptive'
     ORDER BY received_at DESC
     LIMIT 900`,
  ).bind(exchange).all<Record<string, unknown>>();

  const rows: SectorRow[] = (query.results || []).map(row => ({
    exchange,
    market: String(row.market || ''),
    source_ts: num(row.source_ts),
    received_at: num(row.received_at),
    turnover_24h: Math.max(0, num(row.turnover_24h)),
    change_24h_pct: num(row.change_24h_pct),
    opportunity_score: num(row.opportunity_score),
    position_value_krw: Math.max(0, num(row.position_value_krw)),
  })).filter(row => row.market);

  const aggregates = new Map<string, SectorAggregate>();
  for (const row of rows) {
    const sector = sectorOf(row.market);
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
      symbol: symbolOf(row.market),
      turnover_24h: row.turnover_24h,
      change_24h_pct: row.change_24h_pct,
      opportunity_score: row.opportunity_score,
    });
    aggregates.set(sector, current);
  }

  const sectors = [...aggregates.values()].map(item => {
    const positiveShare = item.turnover_24h > 0 ? item.positive_turnover / item.turnover_24h * 100 : 0;
    const weightedChange = item.turnover_24h > 0 ? item.weighted_change_sum / item.turnover_24h : 0;
    return {
      sector: item.sector,
      market_count: item.market_count,
      turnover_24h: round(item.turnover_24h, 0),
      positive_turnover_share_pct: round(positiveShare, 2),
      weighted_change_pct: round(weightedChange, 3),
      flow_score: round(clamp((positiveShare - 50) * 2, -100, 100), 1),
      opportunity_avg: round(item.opportunity_sum / Math.max(1, item.market_count), 1),
      paper_position_krw: round(item.paper_position_krw, 0),
      coins: item.coins.sort((a, b) => b.turnover_24h - a.turnover_24h).slice(0, 14),
    };
  }).sort((a, b) => b.turnover_24h - a.turnover_24h);

  const totalTurnover = sectors.reduce((sum, row) => sum + row.turnover_24h, 0);
  const positiveTurnover = sectors.reduce((sum, row) => sum + row.turnover_24h * row.positive_turnover_share_pct / 100, 0);

  if (sectors.length) {
    const latest = await env.DB.prepare(
      'SELECT MAX(ts) AS ts FROM sector_history WHERE exchange=?',
    ).bind(exchange).first<{ts: number}>();
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
    methodology: '24시간 거래대금 중 상승 코인에 집중된 비율과 거래대금 가중 등락률을 섹터별로 집계합니다. 순입출금액이 아니라 거래 집중도 지표입니다.',
  });
};
