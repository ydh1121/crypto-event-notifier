import {hashPassword} from '../../lib/crypto';
import {bearer, error, json, normalizeEmail, readJson, validEmail} from '../../lib/http';
import type {Env} from '../../lib/types';

interface Payload {email?: string; password?: string; display_name?: string}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  if (!env.OWNER_BOOTSTRAP_TOKEN || bearer(request) !== env.OWNER_BOOTSTRAP_TOKEN) {
    return error(401, 'BOOTSTRAP_REQUIRED', '첫 관리자 생성 키가 맞지 않습니다.');
  }
  const existing = await env.DB.prepare("SELECT id FROM users WHERE role='owner' LIMIT 1").first();
  if (existing) return error(409, 'OWNER_EXISTS', '관리자 계정이 이미 만들어져 있습니다.');

  let payload: Payload;
  try { payload = await readJson<Payload>(request, 16_000); }
  catch { return error(400, 'INVALID_REQUEST', '입력값을 확인하세요.'); }
  const email = normalizeEmail(payload.email);
  const password = String(payload.password || '');
  const displayName = String(payload.display_name || '').trim() || 'Owner';
  if (!validEmail(email)) return error(422, 'INVALID_EMAIL', '이메일 형식을 확인하세요.');
  if (password.length < 10 || password.length > 200) return error(422, 'WEAK_PASSWORD', '비밀번호는 10자 이상으로 설정하세요.');

  const {salt, hash} = await hashPassword(password);
  const id = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    'INSERT INTO users(id,email,display_name,role,can_view_holdings,password_salt,password_hash,created_at) VALUES(?,?,?,?,?,?,?,?)',
  ).bind(id, email, displayName.slice(0, 80), 'owner', 1, salt, hash, now).run();
  await env.DB.prepare('INSERT INTO audit_log(ts,actor_user_id,action,detail_json) VALUES(?,?,?,?)')
    .bind(now, id, 'owner_bootstrap', '{}').run();
  return json({ok: true, user: {id, email, display_name: displayName, role: 'owner'}});
};
