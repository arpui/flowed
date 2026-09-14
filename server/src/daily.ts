// Fluent server — what the learner has done TODAY.
//
// The progress counter used to be per session, and the session is an accident
// of the browser tab: close it, come back after lunch, back to zero. Everything
// else in this system is daily — the streak, the spaced-repetition queue, the
// database rollups — so the counter is daily too, and pausing costs nothing.
//
// Two numbers per day, in one small file per day under <profile>/.daily/:
//   graded — every answer the tutor scored, wherever it came from (free play
//            included). This is the "✏️ 15 🤩" number.
//   lesson — answers given inside the guided Lesson. This is what empties the
//            badge on the 🎓 button.
//
// Kept free of Bun imports so server/test/*.test.ts can exercise it under node.

import fs from "node:fs";
import path from "node:path";

export interface DailyCounts {
  date: string;
  graded: number;
  lesson: number;
}

export function today(now = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function dailyFile(dataDir: string, date: string): string {
  return path.join(dataDir, ".daily", `${date}.json`);
}

export function readDaily(dataDir: string, date = today()): DailyCounts {
  try {
    const raw = JSON.parse(fs.readFileSync(dailyFile(dataDir, date), "utf8")) as Partial<DailyCounts>;
    const n = (v: unknown) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Math.floor(Number(v)) : 0);
    return { date, graded: n(raw.graded), lesson: n(raw.lesson) };
  } catch {
    return { date, graded: 0, lesson: 0 };
  }
}

/** Add to today's counts and return the new totals. Best-effort: a counter that
 *  fails to write must never cost the learner their answer. */
/**
 * Today's lesson plan, FROZEN when the day's first lesson turn happens.
 *
 * Recomputing it from the live queue every time was wrong twice over. The total
 * shrinks as reviews get answered (they stop being due), so the badge moved for
 * the wrong reason; and leaving the lesson for Speaking and coming back left the
 * tutor with no idea what it had already covered, so it restarted at exercise 1
 * — and the sixth question, the one that was never asked, still counted as done.
 *
 * A plan is a thing you make once and then work through.
 */
export interface LessonPlan {
  date: string;
  total: number;
  done: number;
  /** Review item ids consumed, when the tutor declares them. */
  covered: string[];
  slot: string | null;
  slot_done: boolean;
}

function planFile(dataDir: string, date: string): string {
  return path.join(dataDir, ".daily", `lesson-${date}.json`);
}

export function readPlan(dataDir: string, date = today()): LessonPlan | null {
  try {
    const raw = JSON.parse(fs.readFileSync(planFile(dataDir, date), "utf8")) as Partial<LessonPlan>;
    if (raw.date !== date || !Number.isFinite(Number(raw.total))) return null;
    return {
      date,
      total: Math.max(0, Math.floor(Number(raw.total))),
      done: Math.max(0, Math.floor(Number(raw.done) || 0)),
      covered: Array.isArray(raw.covered) ? raw.covered.map(String) : [],
      slot: typeof raw.slot === "string" ? raw.slot : null,
      slot_done: raw.slot_done === true,
    };
  } catch {
    return null;
  }
}

export function writePlan(dataDir: string, plan: LessonPlan): LessonPlan {
  try {
    const file = planFile(dataDir, plan.date);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(plan, null, 2) + "\n", "utf8");
  } catch {
    /* best-effort */
  }
  return plan;
}

/** Lessons completed, ever. Drives the every-third-lesson skill slot. */
export interface LessonTally {
  completed: number;
  /** The day the current lesson was last credited, so it counts once. */
  credited_on?: string;
}

function tallyFile(dataDir: string): string {
  return path.join(dataDir, ".daily", "lessons.json");
}

export function readTally(dataDir: string): LessonTally {
  try {
    const raw = JSON.parse(fs.readFileSync(tallyFile(dataDir), "utf8")) as Partial<LessonTally>;
    const n = Number(raw.completed);
    return {
      completed: Number.isFinite(n) && n > 0 ? Math.floor(n) : 0,
      credited_on: typeof raw.credited_on === "string" ? raw.credited_on : undefined,
    };
  } catch {
    return { completed: 0 };
  }
}

/** Credit one finished Lesson, at most once per day. */
export function creditLesson(dataDir: string, date = today()): LessonTally {
  const current = readTally(dataDir);
  if (current.credited_on === date) return current;
  const next: LessonTally = { completed: current.completed + 1, credited_on: date };
  try {
    const file = tallyFile(dataDir);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(next) + "\n", "utf8");
  } catch {
    /* best-effort */
  }
  return next;
}

export function bumpDaily(
  dataDir: string,
  delta: { graded?: number; lesson?: number },
  date = today()
): DailyCounts {
  const current = readDaily(dataDir, date);
  const next: DailyCounts = {
    date,
    graded: Math.max(0, current.graded + (delta.graded ?? 0)),
    lesson: Math.max(0, current.lesson + (delta.lesson ?? 0)),
  };
  try {
    const file = dailyFile(dataDir, date);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(next) + "\n", "utf8");
  } catch {
    /* the count is a nicety; the answer is not */
  }
  return next;
}
