import {bearer, error, json, readJson} from '../lib/http';
import type {Env} from '../lib/types';

interface AckPayload {
  id?: string;
  status?: 'applied' | 'rejected';
  result?: unknown;
  error_code?: string;
  error_message?: string;
}

function missingTable(exc: unknown): boolean {
  const text = String(exc instanceof Error ? exc.message : exc || '').toLowerCase();
  return text.includes('no such table') && text.includes('holding_mutations');
}

function authorized(env: Env, request: Request): boolean {
  return Boolean(env.INGEST_TOKEN) && bearer(request) === env.INGEST_TOKEN;
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  if (!authorized(env, request)) return error(401, 'INGEST_REQUIRED', '런타임 인증이 필요합니다.');
  const now = Math.floor(Date.now() / 1000);
  try {
    // A crashed consumer must not leave a mutation claimed forever.
    await env.DB.prepare(
      `UPDATE holding_mutations SET status='pending',claimed_at=NULL,updated_at=?
       WHERE status='claimed' AND claimed_at IS NOT NULL AND claimed_at < ?`,
    ).bind(now, now - 120).run();

    const row = await env.DB.prepare(
      `SELECT id,exchange,market,action,expected_revision,payload_json,created_at
       FROM holding_mutations WHERE status='pending' ORDER BY created_at ASC LIMIT 1`,
    ).first<Record<string, unknown>>();
    if (!row) return json({ok: true, mutation: null});

    await env.DB.prepare(
      `UPDATE holding_mutations SET status='claimed',claimed_at=?,updated_at=?
       WHERE id=? AND status='pending'`,
    ).bind(now, now, row.id).run();

    let payload: unknown = {};
    try { payload = JSON.parse(String(row.payload_json || '{}')); } catch {}
    return json({ok: true, mutation: {
      id: row.id,
      exchange: row.exchange,
      market: row.market,
      action: row.action,
      expected_revision: Number(row.expected_revision || 0),
      created_at: row.created_at,
      payload,
    }});
  } catch (exc) {
    if (missingTable(exc)) return error(503, 'MIGRATION_REQUIRED', '보유자산 반영 큐 마이그레이션이 필요합니다.');
    return error(503, 'MUTATION_CLAIM_UNAVAILABLE', '반영 요청을 가져올 수 없습니다.');
  }
};

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  if (!authorized(env, request)) return error(401, 'INGEST_REQUIRED', '런타임 인증이 필요합니다.');
  let body: AckPayload;
  try { body = await readJson<AckPayload>(request, 80_000); }
  catch { return error(400, 'INVALID_ACK', '반영 결과 형식을 확인하세요.'); }

  const id = String(body.id || '').trim();
  const status = body.status;
  if (!id || (status !== 'applied' && status !== 'rejected')) {
    return error(422, 'INVALID_ACK', '반영 결과 상태가 올바르지 않습니다.');
  }
  const now = Math.floor(Date.now() / 1000);
  const resultJson = JSON.stringify(body.result && typeof body.result === 'object' ? body.result : {});
  const errorCode = String(body.error_code || '').slice(0, 80);
  const errorMessage = String(body.error_message || '').slice(0, 300);

  try {
    const result = await env.DB.prepare(
      `UPDATE holding_mutations
       SET status=?,updated_at=?,applied_at=?,result_json=?,error_code=?,error_message=?
       WHERE id=? AND status='claimed'`,
    ).bind(status, now, now, resultJson, errorCode, errorMessage, id).run();
    if (!Number(result.meta.changes || 0)) return error(409, 'MUTATION_NOT_CLAIMED', '현재 처리 중인 요청이 아닙니다.');
    return json({ok: true, id, status, applied_at: now});
  } catch (exc) {
    if (missingTable(exc)) return error(503, 'MIGRATION_REQUIRED', '보유자산 반영 큐 마이그레이션이 필요합니다.');
    return error(503, 'MUTATION_ACK_UNAVAILABLE', '반영 결과를 저장할 수 없습니다.');
  }
};
