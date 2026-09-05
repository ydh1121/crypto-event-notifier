CREATE INDEX IF NOT EXISTS idx_coin_profile_cache_market_peer
  ON coin_profile_cache(market, research_status, last_verified_at DESC);
