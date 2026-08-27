import {bearer, error, json, readJson} from '../lib/http';
import type {Env} from '../lib/types';

interface Payload {source_ts?: number; public?: unknown; private?: unknown}

// The viewer only reads the latest snapshot. Keeping hundreds of ~1MB snapshots
// can push D1 close to its storage limit and then the INSERT fails before the
// old post-insert cleanup can run. Keep a small recovery window instead.
const SNAPSHOT_RETENTION = 24;

async function pruneBeforeInsert(env: Env): Promise<void> {
  const keepBeforeInsert = Math.max(1, SNAPSHOT_RETENTION - 1);
  await env.DB.prepare(
    `DELETE FROM snapshots
     WHERE id NOT IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT ?)`,
  ).bind(keepBeforeInsert).run();
}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  if (!env.INGEST_TOKEN || bearer(request) !== env.INGEST_TOKEN) {
    return error(401, 'INGEST_REQUIRED', '스냅샷 전송 인증이 필요합니다.');
  }
  let payload: Payload;
  try { payload = await readJson<Payload>(request, 1_900_000); }
  catch (exc) {
    return error(String(exc).includes('PAYLOAD_TOO_LARGE') ? 413 : 400, 'INVALID_SNAPSHOT', '스냅샷 형식을 확인하세요.');
  }
  if (!payload.public || typeof payload.public !== 'object') {
    return error(422, 'PUBLIC_SNAPSHOT_REQUIRED', '조회용 공개 스냅샷이 필요합니다.');
  }
  const sourceTs = Number(payload.source_ts || 0);
  const publicJson = JSON.stringify(payload.public);
  const privateJson = payload.private && typeof payload.private === 'object' ? JSON.stringify(payload.private) : '{}';
  const now = Math.floor(Date.now() / 1000);

  // Critical ordering: free reusable D1 pages before attempting the large row.
  // The old implementation inserted first and could become permanently stuck
  // at storage pressure because the cleanup statement was never reached.
  await pruneBeforeInsert(env);

  const result = await env.DB.prepare(
    'INSERT INTO snapshots(received_at,source_ts,public_json,private_json) VALUES(?,?,?,?)',
  ).bind(now, Number.isFinite(sourceTs) ? sourceTs : 0, publicJson, privateJson).run();

  return json({
    ok: true,
    id: result.meta.last_row_id,
    received_at: now,
    source_ts: sourceTs,
    retention: SNAPSHOT_RETENTION,
  });
};
