import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import type {Env} from '../lib/types';

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function parseJson(value: unknown): Record<string, unknown> {
  try {
    return record(JSON.parse(String(value || '{}')));
  } catch {
    return {};
  }
}

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  let session;
  try { session = await requireSession(env, request); }
  catch { return error(401, 'AUTH_REQUIRED', '로그인이 필요합니다.'); }

  const url = new URL(request.url);
  const exchange = String(url.searchParams.get('exchange') || 'bithumb').trim().toLowerCase();
  const strategy = String(url.searchParams.get('strategy') || 'adaptive').trim().toLowerCase();

  const result = await env.DB.prepare(
    `SELECT market,source_ts,received_at,detail_json
     FROM market_details
     WHERE exchange=? AND strategy=?
     ORDER BY market ASC
     LIMIT 1000`,
  ).bind(exchange, strategy).all<Record<string, unknown>>();

  const quotes = (result.results || []).map(row => {
    const detail = parseJson(row.detail_json);
    const signal = record(detail.signal);
    const summary = record(detail.summary);
    return {
      market: String(row.market || ''),
      price: num(signal.price) ?? num(summary.price),
      change_24h_pct: num(signal.change_24h_pct) ?? num(summary.change_24h_pct),
      turnover_24h: num(signal.turnover_24h) ?? num(summary.turnover_24h),
      liquidity_score: num(signal.liquidity_score) ?? num(summary.liquidity_score),
      source_ts: num(row.source_ts) ?? 0,
      received_at: num(row.received_at) ?? 0,
    };
  }).filter(row => row.market);

  return json({ok: true, user: session.user, exchange, strategy, quotes});
};
