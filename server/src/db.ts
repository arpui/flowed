// Fluent server — SQLite bridge.
// Reproduces the session/message/part schema the Fluent persistence hooks
// (accumulate-session.py / persist-session.py) read, so those hooks keep
// working unchanged. The DB lives at
//   ~/.flowed/<id>/sessions/sessions.db
// (legacy profiles: ~/.flowed/<id>/.opencode/opencode/opencode.db) — the same
// order `resolve_sessions_db` derives in persist-session.py.
//
// Only session / message / part are needed; Fluent never reads the other
// opencode tables (account, project, ...), so we omit them.

import { Database } from "bun:sqlite";

export type Role = "user" | "assistant" | "system";
export type PartType = "text" | "tool";

export interface SessionRow {
  id: string;
  slug: string;
  agent: string;
  title: string;
  model: string;
  time_created: number;
  time_updated: number;
  last_activity: number;
  metadata: string | null;
}

export interface MessageRow {
  id: string;
  session_id: string;
  time_created: number;
  time_updated: number;
  data: Record<string, unknown>;
}

export interface PartRow {
  id: string;
  message_id: string;
  session_id: string;
  time_created: number;
  time_updated: number;
  data: Record<string, unknown>;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS session (
  id text PRIMARY KEY,
  project_id text NOT NULL DEFAULT 'proj_math',
  workspace_id text,
  parent_id text,
  slug text NOT NULL,
  directory text NOT NULL DEFAULT '',
  path text,
  title text NOT NULL DEFAULT 'FlowMath',
  version text NOT NULL DEFAULT '0.0.0-local',
  share_url text,
  summary_additions integer,
  summary_deletions integer,
  summary_files integer,
  summary_diffs text,
  metadata text,
  cost real NOT NULL DEFAULT 0,
  tokens_input integer NOT NULL DEFAULT 0,
  tokens_output integer NOT NULL DEFAULT 0,
  tokens_reasoning integer NOT NULL DEFAULT 0,
  tokens_cache_read integer NOT NULL DEFAULT 0,
  tokens_cache_write integer NOT NULL DEFAULT 0,
  revert text,
  permission text,
  agent text,
  model text,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  last_activity integer NOT NULL,
  time_compacting integer,
  time_archived integer
);
CREATE INDEX IF NOT EXISTS session_project_idx ON session (project_id);
CREATE TABLE IF NOT EXISTS message (
  id text PRIMARY KEY,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
CREATE INDEX IF NOT EXISTS message_session_time_created_id_idx ON message (session_id, time_created, id);
CREATE TABLE IF NOT EXISTS part (
  id text PRIMARY KEY,
  message_id text NOT NULL,
  session_id text NOT NULL,
  time_created integer NOT NULL,
  time_updated integer NOT NULL,
  data text NOT NULL
);
CREATE INDEX IF NOT EXISTS part_message_id_id_idx ON part (message_id, id);
CREATE INDEX IF NOT EXISTS part_session_idx ON part (session_id);
`;

export class FluentDB {
  private db: Database;
  readonly path: string;

  constructor(path: string) {
    this.db = new Database(path, { create: true });
    this.path = path;
    this.db.exec("PRAGMA journal_mode = WAL;");
    this.db.exec(SCHEMA);
    this.migrate();
  }

  private migrate() {
    // Check if last_activity column exists
    const cols = this.db.prepare("PRAGMA table_info(session)").all() as Array<{name: string}>;
    const hasLastActivity = cols.some(c => c.name === "last_activity");
    if (!hasLastActivity) {
      console.log("[Fluent] Migrating: adding last_activity column to session table");
      this.db.exec("ALTER TABLE session ADD COLUMN last_activity INTEGER NOT NULL DEFAULT 0");
      // Backfill with time_updated for existing rows
      this.db.exec("UPDATE session SET last_activity = time_updated WHERE last_activity = 0");
    }
  }

  close() {
    this.db.close();
  }

  newId(prefix: string): string {
    // 24 hex chars from crypto, similar shape to opencode ids.
    const buf = new Uint8Array(12);
    crypto.getRandomValues(buf);
    return prefix + "_" + Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ---- session ------------------------------------------------------------

  private tableExists(name: string): boolean {
    const row = this.db
      .prepare("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?")
      .get(name);
    return !!row;
  }

  // opencode's real schema has session.project_id NOT NULL and a FK to
  // project(id). Sessions created via the web server live under the "global"
  // workspace project, so make sure that row exists when the table does.
  private ensureGlobalProject() {
    if (!this.tableExists("project")) return;
    this.db
      .prepare(
        `INSERT OR IGNORE INTO project (id, worktree, time_created, time_updated, sandboxes)
         VALUES ('global', 'global', ?, ?, '[]')`
      )
      .run(Date.now(), Date.now());
  }

  createSession(opts: {
    slug: string;
    agent: string;
    title?: string;
    model?: string;
  }): SessionRow {
    const now = Date.now();
    const id = this.newId("ses");
    const model =
      opts.model ??
      JSON.stringify({ id: "deep", providerID: "math-deep", variant: "default" });
    // Explicit NOT NULL columns (no reliance on table defaults): works against
    // both our fresh schema and an existing opencode.db.
    this.ensureGlobalProject();
    this.db
      .prepare(
        `INSERT INTO session
         (id, project_id, slug, directory, title, version, agent, model, time_created, time_updated, last_activity)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(id, "global", opts.slug, "", opts.title ?? "FlowMath", "0.0.0-local", opts.agent, model, now, now, now);
    return { id, slug: opts.slug, agent: opts.agent, title: opts.title ?? "FlowMath", model, time_created: now, time_updated: now, last_activity: now, metadata: null };
  }

  getSession(id: string): SessionRow | null {
    const row = this.db
      .prepare("SELECT * FROM session WHERE id = ?")
      .get(id) as Record<string, unknown> | null;
    return row ? this.rowToSession(row) : null;
  }

  private rowToSession(r: Record<string, unknown>): SessionRow {
    return {
      id: r.id as string,
      slug: r.slug as string,
      agent: r.agent as string,
      title: r.title as string,
      model: r.model as string,
      time_created: r.time_created as number,
      time_updated: r.time_updated as number,
      last_activity: (r.last_activity as number) ?? r.time_updated as number,
      metadata: (r.metadata as string) ?? null,
    };
  }

  /** Mirrors persist-session.find_session(latest=True, slug=...). */
  findLatestBySlug(slug: string): SessionRow | null {
    const row = this.db
      .prepare(
        `SELECT s.* FROM session s
         JOIN part p ON p.session_id = s.id
         WHERE json_extract(p.data, '$.type') = 'text'
           AND json_extract(p.data, '$.text') LIKE ?
           AND s.agent = 'learner'
         ORDER BY s.time_created DESC LIMIT 1`
      )
      .get(`%"${slug}"%`) as Record<string, unknown> | null;
    return row ? this.rowToSession(row) : null;
  }

  touchSession(id: string, time = Date.now()) {
    this.db.prepare("UPDATE session SET time_updated = ?, last_activity = ? WHERE id = ?").run(time, time, id);
  }

  /** Learner sessions that are inactive, not yet finalized, and recent enough.
   *
   *  Both bounds matter. Without the "not finalized" flag the sweeper re-runs
   *  Capa B for every past session on every tick; without the floor it would
   *  wake up the entire session history after a restart. The flag lives in the
   *  session row (not in session-draft.json, which only ever holds ONE session).
   */
  getStaleSessions(maxAgeMs: number, now = Date.now(), maxLookbackMs = 24 * 60 * 60 * 1000): SessionRow[] {
    const cutoff = now - maxAgeMs;
    const floor = now - maxLookbackMs;
    const rows = this.db
      .prepare(
        `SELECT * FROM session
         WHERE agent = 'learner'
         AND last_activity < ?
         AND last_activity > ?
         AND json_extract(COALESCE(metadata, '{}'), '$.capa_b_done') IS NULL
         ORDER BY last_activity ASC`
      )
      .all(cutoff, floor) as Record<string, unknown>[];
    return rows.map((r) => this.rowToSession(r));
  }

  /** Re-open a finalized session: it has new work that Capa B has not seen.
   *
   *  The marker was built to stop the sweeper re-running Capa B every minute
   *  over old sessions, and it does — permanently, which turned out to be too
   *  permanent. web/app.js keeps the session id in localStorage, so reopening
   *  the browser hours later resumes the SAME session; if that session had
   *  already been finalized, everything the learner did afterwards reached the
   *  databases through Capa A only and never got a summary, a results file or
   *  a review_results block. persist-session.py recomputes from the T0
   *  snapshot, so running it again over a longer session is safe by design. */
  reopenIfFinalized(id: string): boolean {
    const row = this.db
      .prepare(
        "SELECT json_extract(COALESCE(metadata, '{}'), '$.capa_b_done') AS done FROM session WHERE id = ?"
      )
      .get(id) as { done?: unknown } | undefined;
    if (!row || row.done === null || row.done === undefined) return false;
    this.db
      .prepare(
        "UPDATE session SET metadata = json_remove(COALESCE(metadata, '{}'), '$.capa_b_done') WHERE id = ?"
      )
      .run(id);
    return true;
  }

  /** Record that Capa B has run for this session (durable, per session). */
  markFinalized(id: string, time = Date.now()) {
    this.db
      .prepare(
        "UPDATE session SET metadata = json_set(COALESCE(metadata, '{}'), '$.capa_b_done', ?) WHERE id = ?"
      )
      .run(time, id);
  }

  // ---- message + part -----------------------------------------------------

  insertMessage(sessionId: string, data: Record<string, unknown>): MessageRow {
    const now = Date.now();
    const id = this.newId("msg");
    this.db
      .prepare(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)"
      )
      .run(id, sessionId, now, now, JSON.stringify(data));
    return { id, session_id: sessionId, time_created: now, time_updated: now, data };
  }

  insertPart(messageId: string, sessionId: string, data: Record<string, unknown>): PartRow {
    const now = Date.now();
    const id = this.newId("part");
    // Explicit id keeps RowID monotonic with insertion order (unused id gap is fine).
    this.db
      .prepare(
        "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)"
      )
      .run(id, messageId, sessionId, now, now, JSON.stringify(data));
    return { id, message_id: messageId, session_id: sessionId, time_created: now, time_updated: now, data };
  }

  /** Replace a part's payload — used to close a streamed text part with its
   *  final content, so the transcript on disk matches what the learner saw. */
  updatePart(id: string, data: Record<string, unknown>) {
    this.db
      .prepare("UPDATE part SET data = ?, time_updated = ? WHERE id = ?")
      .run(JSON.stringify(data), Date.now(), id);
  }

  /** All messages for a session, in insertion order (oldest first). */
  getMessages(sessionId: string): MessageRow[] {
    const rows = this.db
      .prepare("SELECT * FROM message WHERE session_id = ? ORDER BY time_created ASC, rowid ASC")
      .all(sessionId) as Record<string, unknown>[];
    return rows.map((r) => ({
      id: r.id as string,
      session_id: r.session_id as string,
      time_created: r.time_created as number,
      time_updated: r.time_updated as number,
      data: JSON.parse(r.data as string) as Record<string, unknown>,
    }));
  }

  getParts(messageId: string): PartRow[] {
    const rows = this.db
      .prepare("SELECT * FROM part WHERE message_id = ? ORDER BY rowid ASC")
      .all(messageId) as Record<string, unknown>[];
    return rows.map((r) => ({
      id: r.id as string,
      message_id: r.message_id as string,
      session_id: r.session_id as string,
      time_created: r.time_created as number,
      time_updated: r.time_updated as number,
      data: JSON.parse(r.data as string) as Record<string, unknown>,
    }));
  }

  getPartsForSession(sessionId: string): PartRow[] {
    const rows = this.db
      .prepare("SELECT * FROM part WHERE session_id = ? ORDER BY rowid ASC")
      .all(sessionId) as Record<string, unknown>[];
    return rows.map((r) => ({
      id: r.id as string,
      message_id: r.message_id as string,
      session_id: r.session_id as string,
      time_created: r.time_created as number,
      time_updated: r.time_updated as number,
      data: JSON.parse(r.data as string) as Record<string, unknown>,
    }));
  }

  /** Shape used by GET /session/{id}/message and the SSE part objects. */
  getMessageView(message: MessageRow): { info: Record<string, unknown>; parts: Record<string, unknown>[] } {
    const parts = this.getParts(message.id).map((p) => this.partToClient(p, message));
    return {
      info: this.messageToClient(message),
      parts,
    };
  }

  private messageToClient(m: MessageRow): Record<string, unknown> {
    return {
      id: m.id,
      sessionID: m.session_id,
      role: (m.data["role"] as string) ?? "assistant",
      time: { created: m.time_created },
      model: m.data["model"],
      tokens: m.data["tokens"],
    };
  }

  private partToClient(p: PartRow, parent: MessageRow): Record<string, unknown> {
    const d = p.data;
    const out: Record<string, unknown> = {
      id: p.id,
      sessionID: p.session_id,
      messageID: p.message_id,
      type: (d["type"] as string) ?? "text",
      role: (parent.data["role"] as string) ?? "assistant",
      time: { created: p.time_created },
    };
    if (d["type"] === "text") {
      out["text"] = d["text"];
    } else if (d["type"] === "tool") {
      out["tool"] = d["tool"];
      out["state"] = d["state"];
      out["callID"] = d["callID"];
    }
    return out;
  }
}
