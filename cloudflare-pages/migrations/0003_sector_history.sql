CREATE TABLE IF NOT EXISTS sector_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exchange TEXT NOT NULL,
  sector TEXT NOT NULL,
  ts INTEGER NOT NULL,
  turnover_24h REAL NOT NULL DEFAULT 0,
  positive_turnover_share_pct REAL NOT NULL DEFAULT 0,
  weighted_change_pct REAL NOT NULL DEFAULT 0,
  opportunity_avg REAL NOT NULL DEFAULT 0,
  market_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sector_history_exchange_ts
ON sector_history(exchange, ts DESC);

CREATE INDEX IF NOT EXISTS idx_sector_history_exchange_sector_ts
ON sector_history(exchange, sector, ts DESC);
