const encoder = new TextEncoder();
const PBKDF2_ITERATIONS = 100_000;

function base64Url(bytes: Uint8Array): string {
  let binary = '';
  for (const value of bytes) binary += String.fromCharCode(value);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function fromBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

export function randomToken(bytes = 32): string {
  const value = new Uint8Array(bytes);
  crypto.getRandomValues(value);
  return base64Url(value);
}

export async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(value));
  return base64Url(new Uint8Array(digest));
}

export async function hashPassword(password: string, salt?: string): Promise<{salt: string; hash: string}> {
  const actualSalt = salt || randomToken(18);
  const key = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits']);
  const saltBytes = fromBase64Url(actualSalt);
  const bits = await crypto.subtle.deriveBits(
    {name: 'PBKDF2', hash: 'SHA-256', salt: saltBytes, iterations: PBKDF2_ITERATIONS},
    key,
    256,
  );
  return {salt: actualSalt, hash: base64Url(new Uint8Array(bits))};
}

export async function verifyPassword(password: string, salt: string, expectedHash: string): Promise<boolean> {
  const actual = (await hashPassword(password, salt)).hash;
  if (actual.length !== expectedHash.length) return false;
  let diff = 0;
  for (let index = 0; index < actual.length; index += 1) diff |= actual.charCodeAt(index) ^ expectedHash.charCodeAt(index);
  return diff === 0;
}
