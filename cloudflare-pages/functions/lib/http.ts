export function json(data: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set('content-type', 'application/json; charset=utf-8');
  headers.set('cache-control', 'no-store');
  headers.set('x-content-type-options', 'nosniff');
  return new Response(JSON.stringify(data), {...init, headers});
}

export function error(status: number, code: string, message: string): Response {
  return json({ok: false, error: {code, message}}, {status});
}

export async function readJson<T = Record<string, unknown>>(request: Request, maxBytes = 2_000_000): Promise<T> {
  const declared = Number(request.headers.get('content-length') || 0);
  if (declared > maxBytes) throw new Error('PAYLOAD_TOO_LARGE');
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > maxBytes) throw new Error('PAYLOAD_TOO_LARGE');
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error('INVALID_JSON');
  }
}

export function bearer(request: Request): string {
  const value = request.headers.get('authorization') || '';
  return value.startsWith('Bearer ') ? value.slice(7).trim() : '';
}

export function normalizeEmail(value: unknown): string {
  return String(value || '').trim().toLowerCase();
}

export function validEmail(value: string): boolean {
  return value.length >= 3 && value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}
