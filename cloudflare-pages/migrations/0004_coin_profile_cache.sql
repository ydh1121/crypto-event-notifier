CREATE TABLE IF NOT EXISTS coin_profile_cache (
  exchange TEXT NOT NULL,
  market TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT '',
  provider_id TEXT NOT NULL DEFAULT '',
  korean_name TEXT NOT NULL DEFAULT '',
  english_name TEXT NOT NULL DEFAULT '',
  description_ko TEXT NOT NULL DEFAULT '',
  description_en TEXT NOT NULL DEFAULT '',
  categories_json TEXT NOT NULL DEFAULT '[]',
  homepage TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  updated_at INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(exchange, market)
);

CREATE INDEX IF NOT EXISTS idx_coin_profile_cache_updated
  ON coin_profile_cache(updated_at DESC);
