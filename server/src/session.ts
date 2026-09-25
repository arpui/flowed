// Fluent server — session lifecycle.
// Thin layer over FluentDB that exposes the shapes the web UI expects.

import type { FluentDB, SessionRow } from "./db";

export interface SessionService {
  create(title: string): SessionRow;
  get(id: string): SessionRow | null;
  /** list of {info, parts} for the UI's message history endpoint. */
  history(id: string, limit?: number): Array<{ info: Record<string, unknown>; parts: Record<string, unknown>[] }>;
}

export function makeSessionService(db: FluentDB): SessionService {
  return {
    create(title: string): SessionRow {
      return db.createSession({ slug: "fluent", agent: "learner", title: title || "Fluent" });
    },
    get(id: string): SessionRow | null {
      return db.getSession(id);
    },
    history(id: string, limit = 200): Array<{ info: Record<string, unknown>; parts: Record<string, unknown>[] }> {
      const messages = db.getMessages(id);
      const list = limit > 0 ? messages.slice(-limit) : messages;
      return list.map((m) => db.getMessageView(m));
    },
  };
}

/** Whether a stored session can be picked up again by the web client.
 *  `bootMs` is when this server process started: a session whose last turn is
 *  older ran under the previous process, and its exercise state (the card on
 *  screen, the practice, the skill) lived only in that process's memory.
 *  Resuming it showed the pending question, but the answer was not graded —
 *  the server no longer knew the question and moved on to a new one
 *  (2026-09-25, after a restart). Such a session is not resumed; the sweeper
 *  closes it and writes its summary like any idle session. */
export function resumeState(
  row: { last_activity?: number; metadata?: string | null },
  now: number,
  bootMs: number,
  idleLimitMs: number,
): { finalized: boolean; idle_ms: number; restarted: boolean; resumable: boolean; reason: string } {
  let finalized = false;
  try {
    finalized = JSON.parse(row.metadata || "{}").capa_b_done != null;
  } catch {
    /* malformed metadata is not a reason to strand the learner */
  }
  const idleMs = Math.max(0, now - (row.last_activity || 0));
  const stale = idleMs > idleLimitMs;
  const restarted = (row.last_activity || 0) < bootMs;
  return {
    finalized,
    idle_ms: idleMs,
    restarted,
    resumable: !finalized && !stale && !restarted,
    reason: finalized ? "finalized" : stale ? "idle" : restarted ? "restart" : "ok",
  };
}
