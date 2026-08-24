import {json} from '../lib/http';
import type {Env} from '../lib/types';

export const onRequestGet: PagesFunction<Env> = async ({env}) => {
  const row = await env.DB.prepare('SELECT received_at,source_ts FROM snapshots ORDER BY id DESC LIMIT 1')
    .first<{received_at: number; source_ts: number}>();
  const now = Math.floor(Date.now() / 1000);
  return json({
    ok: true,
    service: 'crypto-auto-trader-viewer',
    paper_only: true,
    has_snapshot: Boolean(row),
    last_received_at: Number(row?.received_at || 0),
    age_seconds: row ? Math.max(0, now - Number(row.received_at || 0)) : null,
  });
};
