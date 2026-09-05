import {createSession, sessionCookie} from '../../lib/auth';
import {verifyPassword} from '../../lib/crypto';
import {error, json, normalizeEmail, readJson} from '../../lib/http';
import type {Env} from '../../lib/types';

interface Payload {email?: string; password?: string}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  let payload: Payload;
  try { payload = await readJson<Payload>(request, 16_000); }
  catch { return error(400, 'INVALID_REQUEST', '입력값을 확인하세요.'); }
  const email = normalizeEmail(payload.email);
  const password = String(payload.password || '');
  const user = await env.DB.prepare(
    'SELECT id,email,display_name,role,can_view_holdings,password_salt,password_hash,disabled_at FROM users WHERE email=? LIMIT 1',
  ).bind(email).first<Record<string, unknown>>();
  if (!user || user.disabled_at || !(await verifyPassword(password, String(user.password_salt || ''), String(user.password_hash || '')))) {
    return error(401, 'LOGIN_FAILED', '이메일 또는 비밀번호를 확인하세요.');
  }
  const token = await createSession(env, String(user.id));
  return json(
    {ok: true, user: {id: user.id, email: user.email, display_name: user.display_name, role: user.role, can_view_holdings: Number(user.can_view_holdings || 0)}},
    {headers: {'set-cookie': sessionCookie(token, env)}},
  );
};
