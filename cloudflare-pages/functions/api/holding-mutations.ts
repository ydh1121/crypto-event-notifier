import {requireOwner} from '../lib/auth';
import {error, json, readJson} from '../lib/http';
import type {Env} from '../lib/types';

type Exchange = 'bithumb' | 'upbit';
type Action = 'set_holding' | 'apply_averaging';

interface AveragingRound {price?: number; amount_krw?: number}
interface CreatePayload {
  idempotency_key?: string;
  exchange?: string;
  market?: string;
  action?: string;
  expected_revision?: number;
  volume?: number;
  avg_price?: number;
  rounds?: AveragingRound[];
}

function quoteCurrency(market: string): string {
  const pair = market.split("-", 2)[1] || "";
  return pair.includes("/") ? (pair.split("/", 2)[1] || "KRW") : "KRW";
}
function feeProfile(exchange: Exchange, market: string): {rate: number; policy: string} | null {
  const quote = quoteCurrency(market);
  if (exchange === "bithumb" && quote === "BTC") return {rate: 0, policy: "bithumb_btc_free"};
  if (exchange === "bithumb" && quote === "KRW") return {rate: 0.0004, policy: "bithumb_coupon_0.04pct"};
  if (exchange === "upbit" && quote === "KRW") return {rate: 0.0005, policy: "upbit_krw_0.05pct"};
  return null;
}

function missingTable(exc: unknown): boolean {
  const text = String(exc instanceof Error ? exc.message : exc || '').toLowerCase();
  return text.includes('no such table') && text.includes('holding_mutations');
}

function cleanExchange(value: unknown): Exchange | null {
  const exchange = String(value || '').trim().toLowerCase();
  return exchange === 'bithumb' || exchange === 'upbit' ? exchange : null;
}

function cleanMarket(value: unknown): string {
  const market = String(value || '').trim().toUpperCase();
  return /^KRW-[A-Z0-9]+(?:\/[A-Z0-9]+)?$/.test(market) ? market : '';
}

function cleanFinite(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function publicRow(row: Record<string, unknown>) {
  let result: unknown = {};
  try { result = JSON.parse(String(row.result_json || '{}')); } catch {}
  return {
    id: row.id,
    created_at: row.created_at,
    updated_at: row.updated_at,
    applied_at: row.applied_at,
    status: row.status,
    exchange: row.exchange,
    market: row.market,
    action: row.action,
    expected_revision: row.expected_revision,
    result,
    error_code: row.error_code || '',
    error_message: row.error_message || '',
  };
}

export const onRequestGet: PagesFunction<Env> = async ({request, env}) => {
  let session;
  try { session = await requireOwner(env, request); }
  catch (exc) {
    return error(String(exc).includes('OWNER_REQUIRED') ? 403 : 401, 'OWNER_REQUIRED', '관리자 권한이 필요합니다.');
  }
  const id = new URL(request.url).searchParams.get('id') || '';
  try {
    if (id) {
      const row = await env.DB.prepare(
        `SELECT id,created_at,updated_at,applied_at,status,exchange,market,action,expected_revision,
                result_json,error_code,error_message
         FROM holding_mutations WHERE id=? AND actor_user_id=? LIMIT 1`,
      ).bind(id, session.user.id).first<Record<string, unknown>>();
      if (!row) return error(404, 'MUTATION_NOT_FOUND', '반영 요청을 찾을 수 없습니다.');
      return json({ok: true, mutation: publicRow(row)});
    }
    const rows = await env.DB.prepare(
      `SELECT id,created_at,updated_at,applied_at,status,exchange,market,action,expected_revision,
              result_json,error_code,error_message
       FROM holding_mutations WHERE actor_user_id=? ORDER BY created_at DESC LIMIT 20`,
    ).bind(session.user.id).all<Record<string, unknown>>();
    return json({ok: true, mutations: (rows.results || []).map(publicRow)});
  } catch (exc) {
    if (missingTable(exc)) return error(503, 'MIGRATION_REQUIRED', '보유자산 반영 큐 마이그레이션이 필요합니다.');
    return error(503, 'MUTATION_READ_UNAVAILABLE', '반영 요청 상태를 읽을 수 없습니다.');
  }
};

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  let session;
  try { session = await requireOwner(env, request); }
  catch (exc) {
    return error(String(exc).includes('OWNER_REQUIRED') ? 403 : 401, 'OWNER_REQUIRED', '관리자 권한이 필요합니다.');
  }

  let body: CreatePayload;
  try { body = await readJson<CreatePayload>(request, 40_000); }
  catch { return error(400, 'INVALID_REQUEST', '반영 요청 형식을 확인하세요.'); }

  const exchange = cleanExchange(body.exchange);
  const market = cleanMarket(body.market);
  const action = String(body.action || '') as Action;
  const expectedRevision = cleanFinite(body.expected_revision);
  const idempotencyKey = String(body.idempotency_key || request.headers.get('x-idempotency-key') || '').trim();

  if (!exchange || !market || !['set_holding', 'apply_averaging'].includes(action)) {
    return error(422, 'INVALID_HOLDING_MUTATION', '거래소·코인·반영 종류를 확인하세요.');
  }
  const fee = feeProfile(exchange, market);
  if (!fee) return error(422, 'UNSUPPORTED_EXCHANGE_MARKET', '현재 지원하지 않는 거래소·마켓 조합입니다.');
  if (action === 'apply_averaging' && quoteCurrency(market) !== 'KRW') {
    return error(422, 'QUOTE_AWARE_AVERAGING_REQUIRED', 'BTC 마켓 물타기 실제 반영은 BTC 단위 계산기 전환 후 지원합니다.');
  }
  if (expectedRevision === null || expectedRevision <= 0) {
    return error(422, 'REVISION_REQUIRED', '현재 보유정보 revision이 필요합니다.');
  }
  if (idempotencyKey.length < 8 || idempotencyKey.length > 120) {
    return error(422, 'IDEMPOTENCY_REQUIRED', '중복 방지 키가 필요합니다.');
  }

  let payload: Record<string, unknown>;
  if (action === 'set_holding') {
    const volume = cleanFinite(body.volume);
    const avgPrice = cleanFinite(body.avg_price);
    if (volume === null || avgPrice === null || volume < 0 || avgPrice < 0 || (volume > 0 && avgPrice <= 0)) {
      return error(422, 'INVALID_HOLDING_VALUES', '보유수량은 0 이상이어야 하며, 보유 중인 자산의 평단은 0보다 커야 합니다.');
    }
    payload = {volume, avg_price: volume === 0 ? 0 : avgPrice};
  } else {
    const rounds = (Array.isArray(body.rounds) ? body.rounds : []).slice(0, 20).map((row, index) => ({
      round: index + 1,
      price: cleanFinite(row?.price),
      amount_krw: cleanFinite(row?.amount_krw),
    })).filter(row => row.price !== null && row.amount_krw !== null && row.price! > 0 && row.amount_krw! > 0);
    if (!rounds.length) return error(422, 'AVERAGING_ROUNDS_REQUIRED', '실제 반영할 물타기 회차를 선택하세요.');
    payload = {rounds};
  }

  // Fee is server-owned. Client fee fields are intentionally ignored.
  payload.fee_rate = fee.rate;
  payload.fee_policy = fee.policy;
  payload.quote_currency = quoteCurrency(market);

  const now = Math.floor(Date.now() / 1000);
  const id = crypto.randomUUID();
  try {
    const existing = await env.DB.prepare(
      `SELECT id,actor_user_id,created_at,updated_at,applied_at,status,exchange,market,action,expected_revision,
              result_json,error_code,error_message
       FROM holding_mutations WHERE idempotency_key=? LIMIT 1`,
    ).bind(idempotencyKey).first<Record<string, unknown>>();
    if (existing) {
      if (String(existing.actor_user_id || '') !== session.user.id) {
        return error(409, 'IDEMPOTENCY_CONFLICT', '다른 요청에서 사용된 중복 방지 키입니다.');
      }
      return json({ok: true, deduplicated: true, mutation: publicRow(existing)});
    }

    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO holding_mutations(
          id,idempotency_key,actor_user_id,created_at,updated_at,status,exchange,market,action,
          expected_revision,payload_json,result_json,error_code,error_message
        ) VALUES(?,?,?,?,?,'pending',?,?,?,?,?,'{}','','')`,
      ).bind(
        id, idempotencyKey, session.user.id, now, now, exchange, market, action,
        expectedRevision, JSON.stringify(payload),
      ),
      env.DB.prepare(
        `INSERT INTO audit_log(ts,actor_user_id,action,detail_json) VALUES(?,?,?,?)`,
      ).bind(now, session.user.id, 'holding_mutation_queued', JSON.stringify({id, exchange, market, action})),
    ]);

    return json({ok: true, deduplicated: false, mutation: {
      id, created_at: now, updated_at: now, applied_at: null, status: 'pending', exchange, market,
      action, expected_revision: expectedRevision, result: {}, error_code: '', error_message: '',
    }}, {status: 202});
  } catch (exc) {
    if (missingTable(exc)) return error(503, 'MIGRATION_REQUIRED', '보유자산 반영 큐 마이그레이션이 필요합니다.');
    return error(503, 'MUTATION_QUEUE_UNAVAILABLE', '보유자산 반영 요청을 저장할 수 없습니다.');
  }
};
