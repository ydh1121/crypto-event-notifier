CREATE TABLE IF NOT EXISTS market_details (
  detail_key TEXT PRIMARY KEY,
  exchange TEXT NOT NULL,
  market TEXT NOT NULL,
  strategy TEXT NOT NULL,
  source_ts REAL NOT NULL DEFAULT 0,
  received_at INTEGER NOT NULL,
  detail_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_details_identity
  ON market_details(exchange, market, strategy);

CREATE INDEX IF NOT EXISTS idx_market_details_received
  ON market_details(received_at DESC);

CREATE INDEX IF NOT EXISTS idx_market_details_market
  ON market_details(market, received_at DESC);
