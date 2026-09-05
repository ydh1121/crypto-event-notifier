import {createSession, sessionCookie} from '../../lib/auth';
import {hashPassword, sha256} from '../../lib/crypto';
import {error, json, readJson} from '../../lib/http';
import type {Env} from '../../lib/types';

interface Payload {token?: string; password?: string; display_name?: string}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  let payload: Payload;
  try { payload = await readJson<Payload>(request, 24_000); }
  catch { return error(400, 'INVALID_REQUEST', '입력값을 확인하세요.'); }
  const token = String(payload.token || '').trim();
  const password = String(payload.password || '');
  const displayName = String(payload.display_name || '').trim() || 'Viewer';
  if (!token) return error(422, 'INVITE_REQUIRED', '초대 정보가 없습니다.');
  if (password.length < 10 || password.length > 200) return error(422, 'WEAK_PASSWORD', '비밀번호는 10자 이상으로 설정하세요.');
  const tokenHash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  const invite = await env.DB.prepare(
    'SELECT token_hash,email,role,can_view_holdings,expires_at,used_at,revoked_at FROM invites WHERE token_hash=? LIMIT 1',
  ).bind(tokenHash).first<Record<string, unknown>>();
  if (!invite || invite.used_at || invite.revoked_at || Number(invite.expires_at || 0) <= now) {
    return error(410, 'INVITE_INVALID', '초대가 만료되었거나 이미 사용되었습니다.');
  }
  const existing = await env.DB.prepare('SELECT id FROM users WHERE email=? LIMIT 1').bind(String(invite.email)).first();
  if (existing) return error(409, 'USER_EXISTS', '이미 등록된 사용자입니다.');

  const {salt, hash} = await hashPassword(password);
  const userId = crypto.randomUUID();
  await env.DB.batch([
    env.DB.prepare(
      'INSERT INTO users(id,email,display_name,role,can_view_holdings,password_salt,password_hash,created_at) VALUES(?,?,?,?,?,?,?,?)',
    ).bind(userId, String(invite.email), displayName.slice(0, 80), 'viewer', Number(invite.can_view_holdings || 0), salt, hash, now),
    env.DB.prepare('UPDATE invites SET used_at=? WHERE token_hash=? AND used_at IS NULL').bind(now, tokenHash),
    env.DB.prepare('INSERT INTO audit_log(ts,actor_user_id,action,detail_json) VALUES(?,?,?,?)')
      .bind(now, userId, 'invite_activated', '{}'),
  ]);
  const sessionToken = await createSession(env, userId);
  return json(
    {ok: true, user: {id: userId, email: invite.email, display_name: displayName, role: 'viewer', can_view_holdings: Number(invite.can_view_holdings || 0)}},
    {headers: {'set-cookie': sessionCookie(sessionToken, env)}},
  );
};
