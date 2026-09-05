export interface Env {
  DB: D1Database;
  INGEST_TOKEN: string;
  OWNER_BOOTSTRAP_TOKEN: string;
  SESSION_DAYS?: string;
}

export interface ViewerUser {
  id: string;
  email: string;
  display_name: string;
  role: 'owner' | 'viewer';
  can_view_holdings: number;
  disabled_at: number | null;
}

export interface SessionContext {
  user: ViewerUser;
  tokenHash: string;
}
