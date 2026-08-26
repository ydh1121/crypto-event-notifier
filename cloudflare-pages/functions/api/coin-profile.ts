import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import {exchangeMarketNames} from '../lib/exchange-market-names';
import {sectorFor, sectorInfo, TAXONOMY_SOURCE_NOTE} from '../lib/coin-taxonomy';
import type {Env} from '../lib/types';

type CachedProfile = {
  exchange: string;
  market: string;
  provider: string;
  provider_id: string;
  korean_name: string;
  english_name: string;
  description_ko: string;
  description_en: string;
  categories_json: string;
  homepage: string;
  image_url: string;
  updated_at: number;
};

const THIRTY_DAYS = 30 * 86400;
const ONE_DAY = 86400;

function text(value: unknown): string { return String(value || '').trim(); }
function symbolOf(market: string): string { return market.toUpperCase().replace(/^KRW-/, '').replace(/^USDT-/, ''); }
function safeUrl(value: unknown): string {
  const raw = text(value);
  try { const url = new URL(raw); return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : ''; }
  catch { return ''; }
}
function plain(value: unknown, limit = 1400): string {
  return text(value)
    .replace(/<br\s*\/?\s*>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/[ \t]+/g, ' ').replace(/\n\s+/g, '\n').trim().slice(0, limit);
}
function categories(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(text).filter(Boolean).slice(0, 24);
  try { const parsed = JSON.parse(text(value) || '[]'); return Array.isArray(parsed) ? parsed.map(text).filter(Boolean).slice(0, 24) : []; }
  catch { return []; }
}
function normalized(value: string): string { return value.toLowerCase().replace(/[^a-z0-9가-힣]+/g, ''); }

async function exchangeFallback(env: Env, exchange: string, market: string) {
  const names = await exchangeMarketNames(exchange);
  const official = names.get(market);
  const detail = await env.DB.prepare(
    `SELECT json_extract(detail_json,'$.summary.name') AS detail_name,
            json_extract(detail_json,'$.summary.symbol') AS detail_symbol
     FROM market_details WHERE exchange=? AND market=? AND strategy='adaptive' LIMIT 1`,
  ).bind(exchange, market).first<Record<string, unknown>>();
  return {
    symbol: text(detail?.detail_symbol) || symbolOf(market),
    korean_name: text(official?.korean_name) || text(detail?.detail_name) || symbolOf(market),
    english_name: text(official?.english_name) || symbolOf(market),
  };
}

async function fromCoinGecko(symbol: string, englishName: string) {
  const searchResponse = await fetch(`https://api.coingecko.com/api/v3/search?query=${encodeURIComponent(symbol)}`, {
    headers: {accept: 'application/json', 'user-agent': 'crypto-research-viewer/31'},
  });
  if (!searchResponse.ok) throw new Error(`CoinGecko search ${searchResponse.status}`);
  const search: any = await searchResponse.json();
  const candidates = Array.isArray(search?.coins) ? search.coins.filter((row: any) => text(row?.symbol).toUpperCase() === symbol.toUpperCase()) : [];
  if (!candidates.length) throw new Error('CoinGecko match not found');
  const wanted = normalized(englishName);
  candidates.sort((a: any, b: any) => {
    const aName = normalized(text(a?.name)), bName = normalized(text(b?.name));
    const aMatch = wanted && aName === wanted ? 1 : 0, bMatch = wanted && bName === wanted ? 1 : 0;
    if (aMatch !== bMatch) return bMatch - aMatch;
    const ar = Number(a?.market_cap_rank || 999999), br = Number(b?.market_cap_rank || 999999);
    return ar - br;
  });
  const id = text(candidates[0]?.id);
  if (!id) throw new Error('CoinGecko id missing');
  const detailResponse = await fetch(
    `https://api.coingecko.com/api/v3/coins/${encodeURIComponent(id)}?localization=true&tickers=false&market_data=false&community_data=false&developer_data=false&sparkline=false`,
    {headers: {accept: 'application/json', 'user-agent': 'crypto-research-viewer/31'}},
  );
  if (!detailResponse.ok) throw new Error(`CoinGecko detail ${detailResponse.status}`);
  const detail: any = await detailResponse.json();
  const links = Array.isArray(detail?.links?.homepage) ? detail.links.homepage : [];
  return {
    provider: 'coingecko', provider_id: id,
    english_name: text(detail?.name) || englishName,
    korean_name: text(detail?.localization?.ko),
    description_ko: plain(detail?.description?.ko),
    description_en: plain(detail?.description?.en),
    categories: categories(detail?.categories),
    homepage: safeUrl(links.find((item: unknown) => safeUrl(item)) || ''),
    image_url: safeUrl(detail?.image?.small || detail?.image?.thumb || ''),
  };
}

function payload(row: CachedProfile, symbol: string) {
  const cats = categories(row.categories_json);
  const sector = sectorFor(symbol, cats);
  return {
    ok: true,
    exchange: row.exchange,
    market: row.market,
    symbol,
    korean_name: row.korean_name,
    english_name: row.english_name,
    description_ko: row.description_ko,
    description_en: row.description_en,
    categories: cats,
    homepage: row.homepage,
    image_url: row.image_url,
    provider: row.provider,
    provider_id: row.provider_id,
    updated_at: Number(row.updated_at || 0),
    canonical_sector: sector,
    sector_info: sectorInfo(sector),
    taxonomy_note: TAXONOMY_SOURCE_NOTE,
  };
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  try { await requireSession(env, request); }
  catch { return error(401, 'AUTH_REQUIRED', '로그인이 필요합니다.'); }

  const url = new URL(request.url);
  const exchange = url.searchParams.get('exchange') === 'upbit' ? 'upbit' : 'bithumb';
  const market = text(url.searchParams.get('market')).toUpperCase();
  if (!/^(KRW|USDT)-[A-Z0-9._-]{1,32}$/.test(market)) return error(400, 'INVALID_MARKET', '코인 마켓 형식을 확인하세요.');
  const now = Math.floor(Date.now() / 1000);
  const fallback = await exchangeFallback(env, exchange, market);

  const cached = await env.DB.prepare('SELECT * FROM coin_profile_cache WHERE exchange=? AND market=?')
    .bind(exchange, market).first<CachedProfile>();
  if (cached) {
    const ttl = cached.provider === 'coingecko' ? THIRTY_DAYS : ONE_DAY;
    if (now - Number(cached.updated_at || 0) < ttl) return json(payload(cached, fallback.symbol));
  }

  let profile: any = null;
  try { profile = await fromCoinGecko(fallback.symbol, fallback.english_name); }
  catch { profile = null; }
  const row: CachedProfile = {
    exchange, market,
    provider: profile?.provider || 'exchange',
    provider_id: profile?.provider_id || '',
    korean_name: profile?.korean_name || fallback.korean_name,
    english_name: profile?.english_name || fallback.english_name,
    description_ko: profile?.description_ko || '',
    description_en: profile?.description_en || '',
    categories_json: JSON.stringify(profile?.categories || []),
    homepage: profile?.homepage || '',
    image_url: profile?.image_url || '',
    updated_at: now,
  };
  await env.DB.prepare(
    `INSERT INTO coin_profile_cache(exchange,market,provider,provider_id,korean_name,english_name,description_ko,description_en,categories_json,homepage,image_url,updated_at)
     VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(exchange,market) DO UPDATE SET provider=excluded.provider,provider_id=excluded.provider_id,korean_name=excluded.korean_name,
       english_name=excluded.english_name,description_ko=excluded.description_ko,description_en=excluded.description_en,
       categories_json=excluded.categories_json,homepage=excluded.homepage,image_url=excluded.image_url,updated_at=excluded.updated_at`,
  ).bind(row.exchange,row.market,row.provider,row.provider_id,row.korean_name,row.english_name,row.description_ko,row.description_en,row.categories_json,row.homepage,row.image_url,row.updated_at).run();
  return json(payload(row, fallback.symbol));
};
