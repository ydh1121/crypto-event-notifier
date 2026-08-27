import {bearer, error, json, readJson} from '../lib/http';
import {sectorFor} from '../lib/coin-taxonomy';
import type {Env} from '../lib/types';

type EvidenceItem = {source?: unknown; url?: unknown; label?: unknown; language?: unknown; weight?: unknown};
type ProfileItem = {
  exchange?: unknown; market?: unknown; symbol?: unknown; provider?: unknown; provider_id?: unknown;
  korean_name?: unknown; english_name?: unknown; description_ko?: unknown; description_en?: unknown;
  business_summary_ko?: unknown; business_summary_en?: unknown; categories?: unknown; tags?: unknown;
  homepage?: unknown; image_url?: unknown; official_docs?: unknown; whitepaper?: unknown; source_code?: unknown;
  community?: unknown; evidence?: unknown; research_status?: unknown; summary_source?: unknown;
  source_count?: unknown; match_confidence?: unknown; verified_at?: unknown;
};
type Payload = {profiles?: ProfileItem[]};
type PreparedProfile = {market:string; statement:D1PreparedStatement};

const MAX_PROFILES = 24;
const STORE_CHUNK = 6;
const STATUS = new Set(['verified','corroborated','single_source','unresolved','pending']);
const clean = (value: unknown, limit = 4000) => String(value ?? '').trim().slice(0, limit);
const symbolOf = (market: string) => market.toUpperCase().replace(/^KRW-/, '').replace(/^USDT-/, '');
const finite = (value: unknown, fallback = 0) => { const out = Number(value); return Number.isFinite(out) ? out : fallback; };
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
function safeUrl(value: unknown): string {
  const raw = clean(value, 1200);
  if (!raw) return '';
  try { const url = new URL(raw); return url.protocol === 'https:' || url.protocol === 'http:' ? url.toString() : ''; }
  catch { return ''; }
}
function stringList(value: unknown, max = 40, itemLimit = 160): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    const text = clean(item, itemLimit);
    if (text && !out.includes(text)) out.push(text);
    if (out.length >= max) break;
  }
  return out;
}
function urlList(value: unknown, max = 16): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    const url = safeUrl(item);
    if (url && !out.includes(url)) out.push(url);
    if (out.length >= max) break;
  }
  return out;
}
function evidenceList(value: unknown): Array<{source:string;url:string;label:string;language:string;weight:number}> {
  if (!Array.isArray(value)) return [];
  const out: Array<{source:string;url:string;label:string;language:string;weight:number}> = [];
  for (const raw of value.slice(0, 16)) {
    if (!raw || typeof raw !== 'object') continue;
    const item = raw as EvidenceItem;
    const source = clean(item.source, 60).toLowerCase();
    const url = safeUrl(item.url);
    if (!source && !url) continue;
    out.push({source, url, label: clean(item.label, 180), language: clean(item.language, 40), weight: clamp(finite(item.weight), 0, 1)});
  }
  return out;
}

async function storePrepared(env:Env, prepared:PreparedProfile[]) {
  let stored = 0;
  const failedMarkets: string[] = [];
  for (let offset = 0; offset < prepared.length; offset += STORE_CHUNK) {
    const chunk = prepared.slice(offset, offset + STORE_CHUNK);
    try {
      const results = await env.DB.batch(chunk.map(item => item.statement));
      stored += results.length;
      continue;
    } catch {
      // A single malformed/temporarily failing row must not kill the other profiles.
    }
    for (const item of chunk) {
      try { await item.statement.run(); stored += 1; }
      catch { failedMarkets.push(item.market); }
    }
  }
  return {stored, failedMarkets};
}

export const onRequestPost: PagesFunction<Env> = async ({request, env}) => {
  if (!env.INGEST_TOKEN || bearer(request) !== env.INGEST_TOKEN) {
    return error(401, 'INGEST_REQUIRED', '코인 프로필 전송 인증이 필요합니다.');
  }
  let payload: Payload;
  try { payload = await readJson<Payload>(request, 1_900_000); }
  catch (exc) { return error(String(exc).includes('PAYLOAD_TOO_LARGE') ? 413 : 400, 'INVALID_PROFILE_BATCH', '코인 프로필 데이터 형식을 확인하세요.'); }
  const profiles = Array.isArray(payload.profiles) ? payload.profiles.slice(0, MAX_PROFILES) : [];
  if (!profiles.length) return error(422, 'PROFILES_REQUIRED', '저장할 코인 프로필이 없습니다.');

  const now = Math.floor(Date.now() / 1000);
  const prepared: PreparedProfile[] = [];
  const statusCounts: Record<string, number> = {};
  const rejectedMarkets: string[] = [];
  for (const raw of profiles) {
    if (!raw || typeof raw !== 'object') continue;
    const exchange = clean(raw.exchange, 20).toLowerCase() === 'upbit' ? 'upbit' : 'bithumb';
    const market = clean(raw.market, 60).toUpperCase();
    if (!/^(KRW|USDT)-[A-Z0-9._-]{1,32}$/.test(market)) continue;
    const symbol = clean(raw.symbol, 40).toUpperCase() || symbolOf(market);
    const categories = stringList(raw.categories);
    const tags = stringList(raw.tags);
    const descriptionKo = clean(raw.description_ko, 6000);
    const descriptionEn = clean(raw.description_en, 6000);
    const businessKo = clean(raw.business_summary_ko, 1400);
    const businessEn = clean(raw.business_summary_en, 1400);
    const evidence = evidenceList(raw.evidence);
    const community = urlList(raw.community);
    const statusRaw = clean(raw.research_status, 40).toLowerCase();
    const researchStatus = STATUS.has(statusRaw) ? statusRaw : (evidence.length >= 2 ? 'corroborated' : evidence.length ? 'single_source' : 'unresolved');
    const sector = sectorFor(symbol, [...categories, ...tags], `${businessKo}\n${businessEn}\n${descriptionKo}\n${descriptionEn}`);
    const confidence = clamp(finite(raw.match_confidence), 0, 1);
    const sourceCount = clamp(Math.round(finite(raw.source_count, evidence.length)), 0, 99);
    const verifiedAt = Math.round(finite(raw.verified_at, now));
    statusCounts[researchStatus] = (statusCounts[researchStatus] || 0) + 1;

    try {
      const statement = env.DB.prepare(
        `INSERT INTO coin_profile_cache(
          exchange,market,provider,provider_id,korean_name,english_name,description_ko,description_en,categories_json,homepage,image_url,updated_at,
          business_summary_ko,business_summary_en,canonical_sector,tags_json,evidence_json,official_docs,whitepaper,source_code,community_json,
          research_status,summary_source,source_count,match_confidence,last_verified_at
         ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
         ON CONFLICT(exchange,market) DO UPDATE SET
          provider=excluded.provider, provider_id=excluded.provider_id,
          korean_name=CASE WHEN excluded.korean_name<>'' THEN excluded.korean_name ELSE coin_profile_cache.korean_name END,
          english_name=CASE WHEN excluded.english_name<>'' THEN excluded.english_name ELSE coin_profile_cache.english_name END,
          description_ko=CASE WHEN excluded.description_ko<>'' THEN excluded.description_ko ELSE coin_profile_cache.description_ko END,
          description_en=CASE WHEN excluded.description_en<>'' THEN excluded.description_en ELSE coin_profile_cache.description_en END,
          categories_json=excluded.categories_json,
          homepage=CASE WHEN excluded.homepage<>'' THEN excluded.homepage ELSE coin_profile_cache.homepage END,
          image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE coin_profile_cache.image_url END,
          updated_at=excluded.updated_at,
          business_summary_ko=CASE WHEN excluded.business_summary_ko<>'' THEN excluded.business_summary_ko ELSE coin_profile_cache.business_summary_ko END,
          business_summary_en=CASE WHEN excluded.business_summary_en<>'' THEN excluded.business_summary_en ELSE coin_profile_cache.business_summary_en END,
          canonical_sector=excluded.canonical_sector, tags_json=excluded.tags_json, evidence_json=excluded.evidence_json,
          official_docs=CASE WHEN excluded.official_docs<>'' THEN excluded.official_docs ELSE coin_profile_cache.official_docs END,
          whitepaper=CASE WHEN excluded.whitepaper<>'' THEN excluded.whitepaper ELSE coin_profile_cache.whitepaper END,
          source_code=CASE WHEN excluded.source_code<>'' THEN excluded.source_code ELSE coin_profile_cache.source_code END,
          community_json=excluded.community_json, research_status=excluded.research_status, summary_source=excluded.summary_source,
          source_count=excluded.source_count, match_confidence=excluded.match_confidence, last_verified_at=excluded.last_verified_at`,
      ).bind(
        exchange, market, clean(raw.provider, 60), clean(raw.provider_id, 120), clean(raw.korean_name, 180), clean(raw.english_name, 180),
        descriptionKo, descriptionEn, JSON.stringify(categories), safeUrl(raw.homepage), safeUrl(raw.image_url), now,
        businessKo, businessEn, sector, JSON.stringify(tags), JSON.stringify(evidence), safeUrl(raw.official_docs), safeUrl(raw.whitepaper),
        safeUrl(raw.source_code), JSON.stringify(community), researchStatus, clean(raw.summary_source, 80), sourceCount, confidence, verifiedAt,
      );
      prepared.push({market, statement});
    } catch { rejectedMarkets.push(market); }
  }
  if (!prepared.length) return error(422, 'NO_VALID_PROFILES', '유효한 코인 프로필이 없습니다.');
  const result = await storePrepared(env, prepared);
  const failedMarkets = [...rejectedMarkets, ...result.failedMarkets];
  return json({
    ok: failedMarkets.length === 0,
    stored: result.stored,
    failed: failedMarkets.length,
    failed_markets: failedMarkets.slice(0, 8),
    received_at: now,
    research_status: statusCounts,
  });
};
