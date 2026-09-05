import {randomToken, sha256} from './crypto';
import type {Env, SessionContext, ViewerUser} from './types';

const COOKIE_NAME = 'cat_session';
const DEFAULT_SESSION_DAYS = 30;

function cookieValue(request: Request, name: string): string {
  const raw = request.headers.get('cookie') || '';
  for (const part of raw.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return '';
}

function sessionSeconds(env: Env): number {
  const days = Math.max(1, Math.min(90, Number(env.SESSION_DAYS || DEFAULT_SESSION_DAYS)));
  return Math.floor(days * 86400);
}

export function sessionCookie(token: string, env: Env): string {
  return `${COOKIE_NAME}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${sessionSeconds(env)}`;
}

export function clearSessionCookie(): string {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

export async function createSession(env: Env, userId: string): Promise<string> {
  const token = randomToken(32);
  const tokenHash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = now + sessionSeconds(env);
  await env.DB.prepare(
    'INSERT INTO sessions(token_hash,user_id,created_at,last_seen_at,expires_at) VALUES(?,?,?,?,?)',
  ).bind(tokenHash, userId, now, now, expiresAt).run();
  return token;
}

export async function getSession(env: Env, request: Request): Promise<SessionContext | null> {
  const token = cookieValue(request, COOKIE_NAME);
  if (!token) return null;
  const tokenHash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  const row = await env.DB.prepare(
    `SELECT u.id,u.email,u.display_name,u.role,u.can_view_holdings,u.disabled_at,s.expires_at
     FROM sessions s JOIN users u ON u.id=s.user_id
     WHERE s.token_hash=? LIMIT 1`,
  ).bind(tokenHash).first<ViewerUser & {expires_at: number}>();
  if (!row || row.disabled_at || Number(row.expires_at) <= now) {
    await env.DB.prepare('DELETE FROM sessions WHERE token_hash=?').bind(tokenHash).run();
    return null;
  }
  env.DB.prepare('UPDATE sessions SET last_seen_at=? WHERE token_hash=?').bind(now, tokenHash).run().catch(() => undefined);
  return {
    tokenHash,
    user: {
      id: row.id,
      email: row.email,
      display_name: row.display_name,
      role: row.role,
      can_view_holdings: Number(row.can_view_holdings || 0),
      disabled_at: row.disabled_at ?? null,
    },
  };
}

export async function deleteSession(env: Env, request: Request): Promise<void> {
  const token = cookieValue(request, COOKIE_NAME);
  if (!token) return;
  await env.DB.prepare('DELETE FROM sessions WHERE token_hash=?').bind(await sha256(token)).run();
}

export async function requireSession(env: Env, request: Request): Promise<SessionContext> {
  const session = await getSession(env, request);
  if (!session) throw new Error('AUTH_REQUIRED');
  return session;
}

export async function requireOwner(env: Env, request: Request): Promise<SessionContext> {
  const session = await requireSession(env, request);
  if (session.user.role !== 'owner') throw new Error('OWNER_REQUIRED');
  return session;
}
