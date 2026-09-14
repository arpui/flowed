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
