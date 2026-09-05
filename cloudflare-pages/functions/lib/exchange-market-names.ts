export type ExchangeMarketName = {
  market: string;
  korean_name: string;
  english_name: string;
};

type CacheEntry = {expires: number; value: Map<string, ExchangeMarketName>};
const cache = new Map<string, CacheEntry>();
const TTL_MS = 10 * 60 * 1000;

function endpoint(exchange: string): string {
  return exchange === 'upbit'
    ? 'https://api.upbit.com/v1/market/all?is_details=false'
    : 'https://api.bithumb.com/v1/market/all?isDetails=false';
}

export async function exchangeMarketNames(exchangeRaw: string): Promise<Map<string, ExchangeMarketName>> {
  const exchange = exchangeRaw === 'upbit' ? 'upbit' : 'bithumb';
  const now = Date.now();
  const hit = cache.get(exchange);
  if (hit && hit.expires > now) return hit.value;
  const value = new Map<string, ExchangeMarketName>();
  try {
    const response = await fetch(endpoint(exchange), {headers: {accept: 'application/json'}});
    if (!response.ok) throw new Error(`market names ${response.status}`);
    const rows: unknown = await response.json();
    if (Array.isArray(rows)) {
      for (const raw of rows) {
        if (!raw || typeof raw !== 'object') continue;
        const row = raw as Record<string, unknown>;
        const market = String(row.market || '').toUpperCase();
        if (!market) continue;
        value.set(market, {
          market,
          korean_name: String(row.korean_name || '').trim(),
          english_name: String(row.english_name || '').trim(),
        });
      }
    }
  } catch {
    // Names are enrichment only. The viewer falls back to the published market detail name.
  }
  cache.set(exchange, {expires: now + TTL_MS, value});
  return value;
}
