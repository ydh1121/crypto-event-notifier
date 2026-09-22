import {journalPage, JournalError, withoutJournalRows} from '../lib/strategy-journal';
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

  const data = parseJson(row.detail_json);
  const experiment = url.searchParams.get('experiment');
  if (experiment) {
    const offset = Number(url.searchParams.get('offset') || 0);
    const limit = Number(url.searchParams.get('limit') || 30);
    if (strategy !== 'adaptive' || !Number.isSafeInteger(offset) || offset < 0 ||
        !Number.isSafeInteger(limit) || limit < 1 || limit > 100) return error(422, 'INVALID_PAGE', '조회 범위를 확인하세요.');
    try {
      const journal = await journalPage((data.strategy_lab || {}) as Record<string, any>, experiment,
        url.searchParams.get('revision') || '', offset, limit, async chunkStrategy => {
          const chunk = await env.DB.prepare('SELECT detail_json FROM market_details WHERE exchange=? AND market=? AND strategy=? LIMIT 1')
            .bind(exchange, market, chunkStrategy).first<Record<string, unknown>>();
          return chunk ? parseJson(chunk.detail_json) : null;
        });
      return json({ok: true, exchange, market, journal});
    } catch (exc) {
      if (exc instanceof JournalError) return error(exc.status, exc.code,
        exc.code === 'JOURNAL_CHANGED' ? '계좌가 갱신되었습니다. 첫 페이지부터 다시 불러오세요.' : '체결 내역 전송을 기다리고 있습니다.');
      throw exc;
    }
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
      data: withoutJournalRows(data),
    },
  });
};
