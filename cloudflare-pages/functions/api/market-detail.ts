import {requireSession} from '../lib/auth';
import {error, json} from '../lib/http';
import type {Env} from '../lib/types';

function parseJson(value: unknown): Record<string, unknown> {
  try {
    const parsed = JSON.parse(String(value || '{}'));
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  let session;
  try { session = await requireSession(env, request); }
  catch { return error(401, 'AUTH_REQUIRED', '로그인이 필요합니다.'); }

  const url = new URL(request.url);
  const exchange = String(url.searchParams.get('exchange') || 'bithumb').trim().toLowerCase();
  const market = String(url.searchParams.get('market') || '').trim().toUpperCase();
  const strategy = String(url.searchParams.get('strategy') || 'adaptive').trim().toLowerCase();
  if (!market) return error(422, 'MARKET_REQUIRED', '코인을 선택하세요.');

  const row = await env.DB.prepare(
    `SELECT detail_key,exchange,market,strategy,source_ts,received_at,detail_json
     FROM market_details
     WHERE exchange=? AND market=? AND strategy=?
     LIMIT 1`,
  ).bind(exchange, market, strategy).first<Record<string, unknown>>();

  if (!row) {
    return json({ok: true, detail: null, exchange, market, strategy, user: session.user});
  }

  return json({
    ok: true,
    user: session.user,
    detail: {
      key: row.detail_key,
      exchange: row.exchange,
      market: row.market,
      strategy: row.strategy,
      source_ts: Number(row.source_ts || 0),
      received_at: Number(row.received_at || 0),
      data: parseJson(row.detail_json),
    },
  });
};
