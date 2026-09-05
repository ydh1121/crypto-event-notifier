import {bearer, error, json} from '../lib/http';
import type {Env} from '../lib/types';

type IdentityRow = {
  exchange: string;
  market: string;
  provider: string;
  provider_id: string;
  korean_name: string;
  english_name: string;
  homepage: string;
  research_status: string;
  source_count: number;
  match_confidence: number;
  last_verified_at: number;
  evidence_json: string;
};

function clean(value: unknown): string { return String(value || '').trim(); }
function safeMarket(value: string): boolean { return /^(KRW|USDT)-[A-Z0-9._-]{1,32}$/.test(value); }
function evidence(value: unknown): unknown[] {
  try {
    const parsed = JSON.parse(clean(value) || '[]');
    return Array.isArray(parsed) ? parsed.slice(0, 12) : [];
  } catch {
    return [];
  }
}
function coinGeckoId(rows: unknown[]): string {
  for (const value of rows) {
    if (!value || typeof value !== 'object') continue;
    const row = value as Record<string, unknown>;
    if (clean(row.source).toLowerCase() !== 'coingecko') continue;
    const raw = clean(row.url);
    if (!raw) continue;
    try {
      const url = new URL(raw);
      const match = url.pathname.match(/\/coins\/([^/?#]+)/i);
      if (match?.[1]) return decodeURIComponent(match[1]);
    } catch {
      // Ignore malformed evidence URLs. Identity stays fail-closed below.
    }
  }
  return '';
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  if (!env.INGEST_TOKEN || bearer(request) !== env.INGEST_TOKEN) {
    return error(401, 'INGEST_REQUIRED', '로컬 연구 노드 인증이 필요합니다.');
  }
  const url = new URL(request.url);
  const exchange = clean(url.searchParams.get('exchange')).toLowerCase();
  const market = clean(url.searchParams.get('market')).toUpperCase();
  if (!['bithumb', 'upbit'].includes(exchange) || !safeMarket(market)) {
    return error(400, 'INVALID_MARKET', '거래소와 마켓 형식을 확인하세요.');
  }
  const row = await env.DB.prepare(
    `SELECT exchange,market,provider,provider_id,korean_name,english_name,homepage,
            research_status,source_count,match_confidence,last_verified_at,evidence_json
       FROM coin_profile_cache WHERE exchange=? AND market=? LIMIT 1`,
  ).bind(exchange, market).first<IdentityRow>();
  if (!row) return json({ok: true, found: false, exchange, market});

  const status = clean(row.research_status);
  const sourceCount = Number(row.source_count || 0);
  const confidence = Number(row.match_confidence || 0);
  const providerId = clean(row.provider_id);
  const homepage = clean(row.homepage);
  const evidenceRows = evidence(row.evidence_json);
  const coingeckoId = coinGeckoId(evidenceRows);
  const providerAnchorPresent = Boolean(providerId || coingeckoId);
  const verified = ['verified', 'corroborated'].includes(status)
    && sourceCount >= 2
    && confidence >= 0.8
    && providerAnchorPresent
    && Boolean(homepage);

  return json({
    ok: true,
    found: true,
    verified,
    exchange,
    market,
    identity: {
      symbol: market.replace(/^(KRW|USDT)-/, ''),
      korean_name: clean(row.korean_name),
      english_name: clean(row.english_name),
      provider: clean(row.provider),
      provider_id: providerId,
      coingecko_id: coingeckoId,
      homepage,
      match_confidence: confidence,
      last_verified_at: Number(row.last_verified_at || 0),
      research_status: status,
      source_count: sourceCount,
      evidence: evidenceRows,
    },
    gate: {
      research_status: status,
      source_count: sourceCount,
      match_confidence: confidence,
      provider_id_present: Boolean(providerId),
      coingecko_id_present: Boolean(coingeckoId),
      provider_anchor_present: providerAnchorPresent,
      homepage_present: Boolean(homepage),
    },
  });
};
