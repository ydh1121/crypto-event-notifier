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
  const row = await env.DB.prepare(
    'SELECT id,received_at,source_ts,public_json,private_json FROM snapshots ORDER BY id DESC LIMIT 1',
  ).first<Record<string, unknown>>();
  if (!row) return json({ok: true, snapshot: null, user: session.user});
  const publicSnapshot = parseJson(row.public_json);
  const canViewHoldings = session.user.role === 'owner' || Number(session.user.can_view_holdings) === 1;
  return json({
    ok: true,
    user: session.user,
    snapshot: {
      id: row.id,
      received_at: Number(row.received_at || 0),
      source_ts: Number(row.source_ts || 0),
      public: publicSnapshot,
      private: canViewHoldings ? parseJson(row.private_json) : {},
      private_visible: canViewHoldings,
    },
  });
};
