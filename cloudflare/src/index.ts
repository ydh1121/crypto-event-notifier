import { Container, getContainer } from "@cloudflare/containers";

interface Env {
  B3_TRADER: DurableObjectNamespace<B3TraderContainer>;
  ADMIN_TOKEN?: string;
}

type Checkpoint = Record<string, unknown>;

export class B3TraderContainer extends Container<Env> {
  defaultPort = 8080;
  requiredPorts = [8080];
  sleepAfter = "10m";
  enableInternet = true;
  pingEndpoint = "localhost/ready";

  private ensureSchema() {
    this.ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        captured_at INTEGER NOT NULL,
        snapshot_ts REAL,
        payload_json TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_checkpoints_captured_at
        ON checkpoints(captured_at);
    `);
  }

  async captureCheckpoint(): Promise<Checkpoint> {
    if (!this.ctx.container.running) {
      await this.startAndWaitForPorts();
    }

    const response = await this.containerFetch("/checkpoint");
    if (!response.ok) {
      throw new Error(`container checkpoint failed: ${response.status}`);
    }

    const checkpoint = (await response.json()) as Checkpoint;
    const lastSnapshot = checkpoint["last_snapshot"] as
      | Record<string, unknown>
      | null
      | undefined;
    const snapshotTs =
      lastSnapshot && typeof lastSnapshot["ts"] === "number"
        ? (lastSnapshot["ts"] as number)
        : null;

    this.ensureSchema();
    const capturedAt = Date.now();
    this.ctx.storage.sql.exec(
      `INSERT INTO checkpoints(captured_at, snapshot_ts, payload_json)
       VALUES (?, ?, ?)`,
      capturedAt,
      snapshotTs,
      JSON.stringify(checkpoint),
    );

    const cutoff = capturedAt - 7 * 24 * 60 * 60 * 1000;
    this.ctx.storage.sql.exec(
      "DELETE FROM checkpoints WHERE captured_at < ?",
      cutoff,
    );

    return checkpoint;
  }

  async latestCheckpoint(): Promise<Checkpoint | null> {
    this.ensureSchema();
    const rows = [
      ...this.ctx.storage.sql.exec(
        `SELECT captured_at, snapshot_ts, payload_json
         FROM checkpoints
         ORDER BY id DESC
         LIMIT 1`,
      ),
    ];
    if (rows.length === 0) return null;

    const row = rows[0] as {
      captured_at: number;
      snapshot_ts: number | null;
      payload_json: string;
    };
    return {
      captured_at: row.captured_at,
      snapshot_ts: row.snapshot_ts,
      checkpoint: JSON.parse(row.payload_json),
    };
  }

  async checkpointHistory(limit = 60): Promise<Checkpoint[]> {
    this.ensureSchema();
    const safeLimit = Math.max(1, Math.min(1440, Math.floor(limit)));
    const rows = [
      ...this.ctx.storage.sql.exec(
        `SELECT captured_at, snapshot_ts, payload_json
         FROM checkpoints
         ORDER BY id DESC
         LIMIT ?`,
        safeLimit,
      ),
    ];

    return rows.map((raw) => {
      const row = raw as {
        captured_at: number;
        snapshot_ts: number | null;
        payload_json: string;
      };
      return {
        captured_at: row.captured_at,
        snapshot_ts: row.snapshot_ts,
        checkpoint: JSON.parse(row.payload_json),
      };
    });
  }
}

function authorized(request: Request, env: Env): boolean {
  if (!env.ADMIN_TOKEN) return false;
  const header = request.headers.get("Authorization");
  return header === `Bearer ${env.ADMIN_TOKEN}`;
}

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function trader(env: Env) {
  return getContainer<B3TraderContainer>(env.B3_TRADER, "b3-singleton");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const instance = trader(env);

    if (url.pathname === "/health" || url.pathname === "/ready") {
      return instance.fetch(request);
    }

    if (!authorized(request, env)) {
      return json({ ok: false, error: "unauthorized" }, 401);
    }

    if (url.pathname === "/status") {
      return json(await instance.latestCheckpoint());
    }

    if (url.pathname === "/history") {
      const limit = Number(url.searchParams.get("limit") ?? "60");
      return json(await instance.checkpointHistory(limit));
    }

    if (url.pathname === "/capture" && request.method === "POST") {
      return json(await instance.captureCheckpoint());
    }

    return json({ ok: false, error: "not_found" }, 404);
  },

  async scheduled(
    _controller: ScheduledController,
    env: Env,
    ctx: ExecutionContext,
  ): Promise<void> {
    ctx.waitUntil(
      trader(env)
        .captureCheckpoint()
        .catch((error) => console.error("checkpoint capture failed", error)),
    );
  },
} satisfies ExportedHandler<Env>;
