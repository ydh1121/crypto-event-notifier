import {bearer, error, json} from '../lib/http';
import type {Env} from '../lib/types';

type BacklogRow = {
  exchange: string;
  market: string;
  korean_name: string;
  english_name: string;
  research_status: string;
  canonical_sector: string;
  source_count: number;
  match_confidence: number;
  updated_at: number;
  last_verified_at: number;
  has_korean: number;
};

type CountRow = {count?: number};

const clean = (value: unknown) => String(value ?? '').trim();
const num = (value: unknown) => {
  const out = Number(value || 0);
  return Number.isFinite(out) ? out : 0;
};

function reasons(row: BacklogRow): string[] {
  const out: string[] = [];
  if (!Number(row.has_korean || 0)) out.push('korean_missing');
  if (['pending', 'unresolved'].includes(clean(row.research_status))) out.push('research_unresolved');
  if (!clean(row.canonical_sector) || clean(row.canonical_sector) === '미분류 검토') out.push('sector_unresolved');
  if (num(row.source_count) < 2) out.push('weak_evidence');
  if (num(row.match_confidence) < 0.8) out.push('low_match_confidence');
  return out;
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  if (!env.INGEST_TOKEN || bearer(request) !== env.INGEST_TOKEN) {
    return error(401, 'INGEST_REQUIRED', '정밀 재조사 큐 인증이 필요합니다.');
  }

  const url = new URL(request.url);
  const requested = Math.max(1, Math.min(80, Math.floor(num(url.searchParams.get('limit')) || 48)));
  const now = Math.floor(Date.now() / 1000);
  const fastCutoff = now - 15 * 60;
  const sectorCutoff = now - 60 * 60;
  const qualityCutoff = now - 6 * 60 * 60;
  const perExchange = Math.max(1, Math.ceil(requested / 2));

  const eligibleWhere = `(
        ((business_summary_ko='' AND description_ko='') AND updated_at<=?)
        OR (research_status IN ('pending','unresolved') AND updated_at<=?)
        OR ((canonical_sector='' OR canonical_sector='미분류 검토') AND updated_at<=?)
        OR (source_count<2 AND updated_at<=?)
        OR (match_confidence<0.8 AND updated_at<=?)
      )`;

  const qualityWhere = `(
        (business_summary_ko='' AND description_ko='')
        OR research_status IN ('pending','unresolved')
        OR canonical_sector='' OR canonical_sector='미분류 검토'
        OR source_count<2
        OR match_confidence<0.8
      )`;

  const queryExchange = (exchange: 'bithumb' | 'upbit') => env.DB.prepare(
    `SELECT exchange,market,korean_name,english_name,research_status,canonical_sector,
            source_count,match_confidence,updated_at,last_verified_at,
            CASE WHEN business_summary_ko<>'' OR description_ko<>'' THEN 1 ELSE 0 END AS has_korean
       FROM coin_profile_cache
      WHERE exchange=? AND ${eligibleWhere}
      ORDER BY
        CASE
          WHEN business_summary_ko='' AND description_ko='' THEN 500
          WHEN research_status IN ('pending','unresolved') THEN 400
          WHEN canonical_sector='' OR canonical_sector='미분류 검토' THEN 300
          WHEN source_count<2 THEN 200
          WHEN match_confidence<0.8 THEN 100
          ELSE 0
        END DESC,
        updated_at ASC,
        market ASC
      LIMIT ?`,
  ).bind(exchange, fastCutoff, fastCutoff, sectorCutoff, qualityCutoff, qualityCutoff, perExchange).all<BacklogRow>();

  const countEligible = (exchange: 'bithumb' | 'upbit') => env.DB.prepare(
    `SELECT COUNT(*) AS count FROM coin_profile_cache WHERE exchange=? AND ${eligibleWhere}`,
  ).bind(exchange, fastCutoff, fastCutoff, sectorCutoff, qualityCutoff, qualityCutoff).first<CountRow>();

  const countQuality = (exchange: 'bithumb' | 'upbit') => env.DB.prepare(
    `SELECT COUNT(*) AS count FROM coin_profile_cache WHERE exchange=? AND ${qualityWhere}`,
  ).bind(exchange).first<CountRow>();

  const [
    bithumbResult,
    upbitResult,
    bithumbEligible,
    upbitEligible,
    bithumbQuality,
    upbitQuality,
  ] = await Promise.all([
    queryExchange('bithumb'),
    queryExchange('upbit'),
    countEligible('bithumb'),
    countEligible('upbit'),
    countQuality('bithumb'),
    countQuality('upbit'),
  ]);

  // Preserve exchange fairness with a round-robin merge before applying the
  // caller's total limit. A single exchange with an older/larger backlog must
  // never starve precision research on the other exchange (the old global LIMIT
  // could return 48/0 even when both exchanges had eligible work).
  const queues = [bithumbResult.results || [], upbitResult.results || []];
  const balanced: BacklogRow[] = [];
  for (let offset = 0; balanced.length < requested; offset += 1) {
    let added = false;
    for (const queue of queues) {
      const row = queue[offset];
      if (!row || balanced.length >= requested) continue;
      balanced.push(row);
      added = true;
    }
    if (!added) break;
  }

  const rows = balanced.map(row => ({
    exchange: clean(row.exchange) === 'upbit' ? 'upbit' : 'bithumb',
    market: clean(row.market).toUpperCase(),
    korean_name: clean(row.korean_name),
    english_name: clean(row.english_name),
    research_status: clean(row.research_status) || 'pending',
    canonical_sector: clean(row.canonical_sector),
    source_count: Math.max(0, Math.round(num(row.source_count))),
    match_confidence: Math.max(0, Math.min(1, num(row.match_confidence))),
    updated_at: Math.round(num(row.updated_at)),
    last_verified_at: Math.round(num(row.last_verified_at)),
    reasons: reasons(row),
  })).filter(row => /^(KRW|USDT)-[A-Z0-9._-]{1,32}$/.test(row.market));

  const returnedByExchange = {
    bithumb: rows.filter(row => row.exchange === 'bithumb').length,
    upbit: rows.filter(row => row.exchange === 'upbit').length,
  };
  const eligibleByExchange = {
    bithumb: Math.max(0, Math.round(num(bithumbEligible?.count))),
    upbit: Math.max(0, Math.round(num(upbitEligible?.count))),
  };
  const qualityPendingByExchange = {
    bithumb: Math.max(0, Math.round(num(bithumbQuality?.count))),
    upbit: Math.max(0, Math.round(num(upbitQuality?.count))),
  };
  const cooldownByExchange = {
    bithumb: Math.max(0, qualityPendingByExchange.bithumb - eligibleByExchange.bithumb),
    upbit: Math.max(0, qualityPendingByExchange.upbit - eligibleByExchange.upbit),
  };

  const reasonCounts: Record<string, number> = {};
  for (const row of rows) {
    for (const reason of row.reasons) reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
  }

  return json({
    ok: true,
    generated_at: now,
    rows,
    by_exchange: returnedByExchange,
    returned_by_exchange: returnedByExchange,
    eligible_by_exchange: eligibleByExchange,
    quality_pending_by_exchange: qualityPendingByExchange,
    cooldown_by_exchange: cooldownByExchange,
    reasons: reasonCounts,
  });
};
