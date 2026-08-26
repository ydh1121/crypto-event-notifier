ALTER TABLE coin_profile_cache ADD COLUMN business_summary_ko TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN business_summary_en TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN canonical_sector TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE coin_profile_cache ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE coin_profile_cache ADD COLUMN official_docs TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN whitepaper TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN source_code TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN community_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE coin_profile_cache ADD COLUMN research_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE coin_profile_cache ADD COLUMN summary_source TEXT NOT NULL DEFAULT '';
ALTER TABLE coin_profile_cache ADD COLUMN source_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE coin_profile_cache ADD COLUMN match_confidence REAL NOT NULL DEFAULT 0;
ALTER TABLE coin_profile_cache ADD COLUMN last_verified_at INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_coin_profile_cache_research_status
  ON coin_profile_cache(research_status, last_verified_at DESC);
CREATE INDEX IF NOT EXISTS idx_coin_profile_cache_sector
  ON coin_profile_cache(canonical_sector, last_verified_at DESC);
