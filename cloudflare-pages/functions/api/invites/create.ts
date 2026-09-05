import {requireOwner} from '../../lib/auth';
import {randomToken, sha256} from '../../lib/crypto';
import {error, json, normalizeEmail, readJson, validEmail} from '../../lib/http';
import type {Env} from '../../lib/types';

interface Payload {email?: string; can_view_holdings?: boolean; expires_days?: number}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  let owner;
  try { owner = await requireOwner(env, request); }
  catch { return error(403, 'OWNER_REQUIRED', '관리자만 사용자를 추가할 수 있습니다.'); }
  let payload: Payload;
  try { payload = await readJson<Payload>(request, 16_000); }
  catch { return error(400, 'INVALID_REQUEST', '입력값을 확인하세요.'); }
  const email = normalizeEmail(payload.email);
  if (!validEmail(email)) return error(422, 'INVALID_EMAIL', '이메일 형식을 확인하세요.');
  const existing = await env.DB.prepare('SELECT id FROM users WHERE email=? LIMIT 1').bind(email).first();
  if (existing) return error(409, 'USER_EXISTS', '이미 등록된 사용자입니다.');

  const token = randomToken(32);
  const tokenHash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  const days = Math.max(1, Math.min(30, Number(payload.expires_days || 7)));
  const expiresAt = now + days * 86400;
  await env.DB.prepare(
    'INSERT INTO invites(token_hash,email,role,can_view_holdings,created_by,created_at,expires_at) VALUES(?,?,?,?,?,?,?)',
  ).bind(tokenHash, email, 'viewer', payload.can_view_holdings ? 1 : 0, owner.user.id, now, expiresAt).run();
  await env.DB.prepare('INSERT INTO audit_log(ts,actor_user_id,action,detail_json) VALUES(?,?,?,?)')
    .bind(now, owner.user.id, 'invite_created', JSON.stringify({email, can_view_holdings: Boolean(payload.can_view_holdings)})).run();
  return json({ok: true, invite: {email, token, expires_at: expiresAt, can_view_holdings: Boolean(payload.can_view_holdings)}});
};
