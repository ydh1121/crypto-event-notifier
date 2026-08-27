import {bearer, error, json, readJson} from '../lib/http';
import type {Env} from '../lib/types';

interface DetailItem {
  key?: string;
  exchange?: string;
  market?: string;
  strategy?: string;
  source_ts?: number;
  detail?: unknown;
}
interface Payload {details?: DetailItem[]}

const MAX_DETAILS = 40;
const EMERGENCY_SNAPSHOT_KEEP = 12;
const clean = (value: unknown, fallback = '') => String(value ?? fallback).trim();

function d1Text(exc: unknown): string {
  return String(exc instanceof Error ? exc.message : exc || '').toLowerCase();
}

function isStoragePressure(exc: unknown): boolean {
  const text = d1Text(exc);
  return text.includes('maximum db size') || text.includes('sqlite_full') ||
    text.includes('database or disk is full') || text.includes('storage limit');
}

function d1Failure(exc: unknown): Response {
  const text = d1Text(exc);
  if (text.includes('daily row write limit') || (text.includes('free tier') && text.includes('write limit'))) {
    return error(503, 'D1_WRITE_LIMIT', 'Cloudflare D1 일일 쓰기 한도에 도달했습니다. UTC 자정 이후 자동으로 다시 시도합니다.');
  }
  if (isStoragePressure(exc)) {
    return error(503, 'D1_STORAGE_LIMIT', 'Cloudflare D1 저장공간 한도 때문에 상세 데이터를 저장할 수 없습니다.');
  }
  if (text.includes('overloaded')) {
    return error(503, 'D1_OVERLOADED', 'Cloudflare D1이 일시적으로 과부하 상태입니다.');
  }
  return error(503, 'D1_WRITE_UNAVAILABLE', 'Cloudflare D1 상세 데이터 쓰기를 완료하지 못했습니다.');
}

async function relieveSnapshotPressure(env: Env): Promise<void> {
  await env.DB.prepare(
    `DELETE FROM snapshots
     WHERE id NOT IN (SELECT id FROM snapshots ORDER BY received_at DESC, id DESC LIMIT ?)`,
  ).bind(EMERGENCY_SNAPSHOT_KEEP).run();
}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  if (!env.INGEST_TOKEN || bearer(request) !== env.INGEST_TOKEN) {
    return error(401, 'INGEST_REQUIRED', '상세 연구 데이터 전송 인증이 필요합니다.');
  }

  let payload: Payload;
  try { payload = await readJson<Payload>(request, 1_900_000); }
  catch (exc) {
    return error(String(exc).includes('PAYLOAD_TOO_LARGE') ? 413 : 400, 'INVALID_MARKET_DETAILS', '상세 연구 데이터 형식을 확인하세요.');
  }

  const details = Array.isArray(payload.details) ? payload.details.slice(0, MAX_DETAILS) : [];
  if (!details.length) return error(422, 'DETAILS_REQUIRED', '저장할 코인 상세 데이터가 없습니다.');

  const now = Math.floor(Date.now() / 1000);
  let stored = 0;
  let written = 0;
  let unchanged = 0;
  let pressureRelieved = false;
  for (const item of details) {
    if (!item || typeof item !== 'object' || !item.detail || typeof item.detail !== 'object') continue;
    const exchange = clean(item.exchange, 'bithumb').toLowerCase();
    const market = clean(item.market).toUpperCase();
    const strategy = clean(item.strategy, 'adaptive').toLowerCase();
    if (!market || market.length > 80 || exchange.length > 40 || strategy.length > 60) continue;
    const key = clean(item.key, `${exchange}|${market}|${strategy}`);
    if (!key || key.length > 220) continue;
    const sourceTs = Number(item.source_ts || 0);
    const detailJson = JSON.stringify(item.detail);
    if (detailJson.length > 180_000) continue;

    const statement = () => env.DB.prepare(
      `INSERT INTO market_details(detail_key,exchange,market,strategy,source_ts,received_at,detail_json)
       VALUES(?,?,?,?,?,?,?)
       ON CONFLICT(detail_key) DO UPDATE SET
         source_ts=excluded.source_ts,
         received_at=excluded.received_at,
         detail_json=excluded.detail_json
       WHERE excluded.source_ts > market_details.source_ts
          OR excluded.detail_json <> market_details.detail_json`,
    ).bind(
      key,
      exchange,
      market,
      strategy,
      Number.isFinite(sourceTs) ? sourceTs : 0,
      now,
      detailJson,
    );

    let result;
    try {
      result = await statement().run();
    } catch (firstError) {
      if (!pressureRelieved && isStoragePressure(firstError)) {
        try {
          await relieveSnapshotPressure(env);
          pressureRelieved = true;
          result = await statement().run();
        } catch (recoveryError) {
          return d1Failure(recoveryError);
        }
      } else {
        return d1Failure(firstError);
      }
    }

    stored += 1;
    const changes = Number(result.meta.changes || 0);
    if (changes > 0) written += changes;
    else unchanged += 1;
  }

  if (!stored) return error(422, 'NO_VALID_DETAILS', '유효한 코인 상세 데이터가 없습니다.');
  return json({
    ok: true,
    stored,
    written,
    unchanged,
    received_at: now,
    pressure_recovery: pressureRelieved,
  });
};
