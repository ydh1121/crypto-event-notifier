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
const clean = (value: unknown, fallback = '') => String(value ?? fallback).trim();

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

    await env.DB.prepare(
      `INSERT INTO market_details(detail_key,exchange,market,strategy,source_ts,received_at,detail_json)
       VALUES(?,?,?,?,?,?,?)
       ON CONFLICT(detail_key) DO UPDATE SET
         exchange=excluded.exchange,
         market=excluded.market,
         strategy=excluded.strategy,
         source_ts=excluded.source_ts,
         received_at=excluded.received_at,
         detail_json=excluded.detail_json`,
    ).bind(
      key,
      exchange,
      market,
      strategy,
      Number.isFinite(sourceTs) ? sourceTs : 0,
      now,
      detailJson,
    ).run();
    stored += 1;
  }

  if (!stored) return error(422, 'NO_VALID_DETAILS', '유효한 코인 상세 데이터가 없습니다.');
  return json({ok: true, stored, received_at: now});
};
