PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS holding_mutations (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  actor_user_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  claimed_at INTEGER,
  applied_at INTEGER,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','claimed','applied','rejected')),
  exchange TEXT NOT NULL CHECK (exchange IN ('bithumb','upbit')),
  market TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('set_holding','apply_averaging')),
  expected_revision REAL NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  result_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_holding_mutations_status_created
ON holding_mutations(status, created_at);

CREATE INDEX IF NOT EXISTS idx_holding_mutations_actor_created
ON holding_mutations(actor_user_id, created_at DESC);
