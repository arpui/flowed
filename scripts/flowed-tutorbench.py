#!/usr/bin/env python3
"""Tutor bench: is a model good enough for the open practices, and how good?

Since the bank (2026-09-24) the model only runs Speaking, Writing and Reading.
This drives those three through the REAL server, over HTTP as the browser does,
with a fixed learner — the same answers for every model — and measures:

  sufficiency (rates; the verdict needs >= 90 % in each)
    ok         no LLM/HTTP error in the reply
    saved      the answer reached <profile>/.records (the model's tool call, or
               the server's own record when the model forgot — both count)
    graded     a score, in the text (N/10) or in math_record_answer
    shown      the score is on screen: she sees how she did (27B, 2026-09-27:
               graded in the tool call, then only "Waiting for your answer!")
    continues  next question/task, an explicit retry, or "ready" (Reading's
               text) — 2026-09-27, 27B on Speaking: "Take your time — a short
               answer is fine!" and nothing after it
    clean      no template braces ({❌}), menu, re-greeting or non-Latin script
               (14B, 2026-09-27: a Chinese word inside an English text)
  quality
    catches    an answer with a planted error: the fix appears in the reply
    consistent the score in math_record_answer = the score shown to her
  and seconds per turn. Each reply is kept in the .json and the .md.

  The learner's answers are fixed, so they do not always fit the question
  asked; a tutor that lowers the score for an off-topic answer is right. That is
  why there is no "a good answer must score >= 7" check (it penalised both
  models for doing their job — first version, 2026-09-27).

    # the server must be up on a TEST profile, talking to the model under test
    scripts/flowed-web.sh --app --port 4199 test-en
    python3 scripts/flowed-tutorbench.py run --port 4199 --name qwen3-27b test-en
    python3 scripts/flowed-tutorbench.py run --port 4199 --name qwen3-14b test-en --repeat 3
    python3 scripts/flowed-tutorbench.py compare

It writes to the profile (it answers exercises), so only test*/demo*/e2e*.
Results: results/tutorbench/<name>-<time>.json (+ .md transcript).
See docs/MODELBENCH.md.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import statistics
import sys
import time
import urllib.error
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("FLOWED_BENCH_OUT") or REPO / "results" / "tutorbench")
sys.path.insert(0, str(REPO / "hooks"))
from main_paths import profiles_root  # noqa: E402


def _e2e():
    spec = importlib.util.spec_from_file_location("flowed_e2e", REPO / "scripts" / "flowed-e2e.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E2E = _e2e()

# The learner. kind: good (fair expected), error (catches expected, `fix` must
# appear in the correction), free (only sufficiency: the right answer depends on
# what the tutor asked).
# The learner, per DOMAIN (0.6: one core, two domains). The command sent is the
# domain's own name (`fluent-*` for language, `math-*` for math), as the web
# sends it — a language profile pressing `math-speaking` opens Math Talk, and
# the first 0.6 run measured language chit-chat against it (2026-10-08).
# kind: good (fair expected), error (catches expected, `fix` must appear in the
# correction), free (only sufficiency: the right answer depends on the task).
CONTINUE_CA = r"problema\s*\d+|pregunta\s*\d+|tasca|escriu|a sota|\"?yes\"? o \"?no\"?|\?\s*$"
PRACTICES_BY_DOMAIN = {
    "language": {
        "fluent-speaking": {
            "next": re.compile(r"question\s*\d+", re.I),
            "answers": [
                ("good", "I'm fine, thanks. I am at home with my family today.", None),
                ("error", "Yesterday I go to the park with my friends.", "went"),
                ("free", "Fine, thanks", None),
                ("error", "My sister have two cats and one dog.", "has"),
                ("good", "I like pizza and I play football on Saturdays.", None),
            ],
        },
        "fluent-writing": {
            "next": re.compile(r"writing exercise|keep going|rewrite|new task|next task|\?\s*$", re.I),
            "answers": [
                ("error", "My name is Anna. I has a small dog. He are very funny and we play in the garden.", "has"),
                ("good", "My name is Tom. I live in a small town with my parents. I like music and I play the guitar.", None),
            ],
        },
        "fluent-reading": {
            "next": re.compile(r"question\s*\d+|reading text|true or false|\?\s*$", re.I | re.M),
            "answers": [("free", "It is about a family.", None), ("free", "Yes.", None), ("free", "I don't know.", None)],
        },
    },
    "math": {
        "math-speaking": {
            "next": re.compile(CONTINUE_CA + r"|question\s*\d+", re.I | re.M),
            "answers": [
                ("good", "Per fer 25 × 4 penso que quatre vegades 25 són 100, perquè 4 quarts fan una unitat.", None),
                ("error", "Per sumar 1/2 + 1/3 sumo els numeradors i els denominadors: 2/5.", "5/6"),
                ("free", "No ho sé.", None),
                ("error", "Per multiplicar per 10 afegeixo un zero, també amb decimals: 2,5 × 10 = 2,50.", "25"),
                ("good", "Primer faig el parèntesi i després la multiplicació, perquè té prioritat sobre la suma.", None),
            ],
        },
        "math-writing": {
            "next": re.compile(CONTINUE_CA, re.I | re.M),
            "answers": [
                ("error", "3(x + 2) = 3x + 2, perquè multiplico el 3 per la x i deixo el 2.", "3x + 6"),
                ("good", "Per resoldre 2x + 3 = 11 resto 3 als dos costats: 2x = 8. Després divideixo per 2: x = 4. "
                         "Comprovo: 2·4 + 3 = 11.", None),
            ],
        },
        "math-reading": {
            "next": re.compile(CONTINUE_CA, re.I | re.M),
            "answers": [("free", "24 × 2,5 = 60. Resultat: 60 kg.", None), ("free", "no", None),
                        ("free", "No ho sé.", None)],
        },
    },
}
# Every practice of every domain, by its command name (the judge looks a row up here).
ALL_PRACTICES = {k: v for d in PRACTICES_BY_DOMAIN.values() for k, v in d.items()}
PRACTICES = ALL_PRACTICES
RECORD_TOOLS = {"math_record_answer", "fluent_record_answer"}

# The tutor's own yes/no offer ("Vols que aquestes claus entrin a la cua de
# repàs? Escriu \"yes\" o \"no\".") — what the learner types next answers
# THAT, not an exercise: nothing to grade or record (2026-10-08, math-reading:
# "No ho sé" landed on the offer and was counted as an unsaved answer).
YESNO_OFFER = re.compile(r'"?yes"?\s*(?:o|or|/)\s*"?no"?', re.I)
LLM_ERR = re.compile(r"LLM HTTP|TemplateError|Unable to connect|⚠️", re.I)
SCORE_RE = re.compile(r"score[^0-9\n]{0,20}(\d{1,2})\s*/\s*10", re.I)
ANY_SCORE = re.compile(r"\b(\d{1,2})\s*/\s*10\b")
RETRY = re.compile(r"prova-ho (?:una altra vegada|de nou)|torna-ho a provar|un altre cop|try again|once more|one more time|type \*{0,2}.?ready|when you('| a)re ready|your turn|\bwrite \d|\*\*question:?\*\*|type a, b|type your answer", re.I)
NON_LATIN = re.compile(r"[\u0400-\u04ff\u0590-\u06ff\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def record_of(outcome) -> dict | None:
    for p in (outcome or {}).get("parts") or []:
        if p.get("type") == "tool" and p.get("tool") in RECORD_TOOLS:
            return ((p.get("state") or {}).get("input")) or {}
    return None


def text_score(text: str) -> int | None:
    m = SCORE_RE.search(text) or ANY_SCORE.search(text)
    return int(m.group(1)) if m else None


def ends_with_next(text: str, rx: re.Pattern) -> bool:
    tail = text.strip()[-600:]
    return bool(rx.search(tail) or RETRY.search(tail)) or tail.rstrip("*_ \n").endswith("?")


def judge(practice: str, step: str, text: str, err: str, tool_score, rights: str, fix: str | None) -> dict:
    spec = PRACTICES[practice]
    shown = text_score(text)
    row = {"ok": not err and not LLM_ERR.search(text) and bool(text),
           "continues": ends_with_next(text, spec["next"]),
           "clean": not E2E.BRACE.search(text) and not E2E.MENU_RE.search(text) and not NON_LATIN.search(text)
                    and (step == "start" or not E2E.GREETING_RE.search(text))}
    if step not in ("start", "offer"):
        row["score"] = tool_score if isinstance(tool_score, (int, float)) else shown
        row["graded"] = row["score"] is not None
        row["shown"] = shown is not None
        if isinstance(tool_score, (int, float)) and shown is not None:
            row["consistent"] = int(tool_score) == shown
        if step == "error" and fix:
            row["catches"] = fix in (rights + " " + text).lower()
    return row


def turn(fn, *args):
    t0 = time.time()
    try:
        out = fn(*args)
        err = ""
    except urllib.error.HTTPError as e:
        out, err = None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 — a bench reports, it does not crash
        out, err = None, str(e)[:200]
    return out, round(time.time() - t0, 1), err


def records_count(prof: Path, sid: str) -> int:
    f = prof / ".records" / f"{sid}.jsonl"
    try:
        return sum(1 for l in f.read_text(encoding="utf-8").splitlines() if l.strip())
    except OSError:
        return 0


def run_once(cli, prof: Path, practice: str, spec: dict, transcript: list[str]) -> list[dict]:
    rows = []
    sid = cli.new_session()
    out, secs, err = turn(cli.command, sid, practice)
    text = E2E.tutor_text(out)
    transcript.append(f"## {practice}\n\n**[button]** ({secs}s)\n\n{text or err}\n")
    rows.append({"practice": practice, "step": "start", "secs": secs, "text": text or err, "sid": sid,
                 **judge(practice, "start", text, err, None, "", None)})
    prev = text
    for kind, answer, fix in spec["answers"]:
        if YESNO_OFFER.search((prev or "")[-300:]):
            kind, fix = "offer", None
        before = records_count(prof, sid)
        out, secs, err = turn(cli.say, sid, answer)
        text = E2E.tutor_text(out)
        rec = record_of(out) or {}
        rights = " ".join(str(c.get("right", "")) for c in rec.get("corrections") or [])
        row = {"practice": practice, "step": kind, "answer": answer, "secs": secs, "text": text or err, "sid": sid,
               "tool_score": rec.get("score"),
               **judge(practice, kind, text, err, rec.get("score"), rights, fix)}
        if kind != "offer":
            for _ in range(20):  # the server may write the record just after replying
                if records_count(prof, sid) > before:
                    break
                time.sleep(0.5)
            row["saved"] = records_count(prof, sid) > before
        prev = text
        rows.append(row)
        transcript.append(f"**Learner:** {answer}\n\n**Tutor** ({secs}s, score {row.get('score')}):\n\n{text or err}\n")
    return rows


def rate(rows: list[dict], key: str) -> tuple[int, int]:
    have = [r[key] for r in rows if key in r]
    return sum(1 for v in have if v), len(have)


def join_metrics(prof: Path, rows: list[dict]) -> None:
    """The server's own per-turn numbers (<profile>/.metrics/turns.jsonl), in
    order, onto the bench's rows of the same session: tokens in and out, and
    how long the model itself took (vs the wall time the learner waited)."""
    f = prof / ".metrics" / "turns.jsonl"
    try:
        lines = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return
    by: dict[str, list] = {}
    for m in lines:
        by.setdefault(m.get("session_id"), []).append(m)
    seen: dict[str, int] = {}
    for r in rows:
        sid = r.get("sid")
        i = seen.get(sid, 0)
        seen[sid] = i + 1
        ms = by.get(sid) or []
        if i < len(ms):
            m = ms[i]
            r["prompt_tokens"] = m.get("prompt_tokens")
            r["completion_tokens"] = m.get("completion_tokens")
            r["model_s"] = round((m.get("model_ms") or 0) / 1000, 1)
            r["roundtrips"] = m.get("roundtrips")


def pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    v = sorted(vals)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 1)


def timing(rows: list[dict]) -> dict:
    """Seconds the learner waits, per practice and per kind of turn, plus the
    model's throughput. Only comparable on the same GPU (railab 4090 vs llvm
    4060 Ti is not a model comparison)."""
    def block(rs: list[dict]) -> dict:
        secs = [r["secs"] for r in rs if r.get("secs") is not None]
        out = {"n": len(secs), "median": pct(secs, 0.5), "p90": pct(secs, 0.9), "max": max(secs) if secs else None}
        gen = [(r["completion_tokens"], r["model_s"]) for r in rs
               if r.get("completion_tokens") and r.get("model_s")]
        if gen:
            out["tok_s"] = round(sum(c for c, _ in gen) / sum(t for _, t in gen), 1)
            out["prompt_tokens_median"] = pct([r["prompt_tokens"] for r in rs if r.get("prompt_tokens")], 0.5)
            out["completion_tokens_median"] = pct([c for c, _ in gen], 0.5)
        return out
    t = {"all": block(rows), "button": block([r for r in rows if r["step"] == "start"]),
         "answer": block([r for r in rows if r["step"] != "start"])}
    for p in dict.fromkeys(r["practice"] for r in rows):
        t[p.split("-")[-1]] = block([r for r in rows if r["practice"] == p])
    return t


GATES = ("ok", "saved", "graded", "shown", "continues", "clean")
QUALITY = ("catches", "consistent")


def summary(rows: list[dict]) -> dict:
    s = {k: rate(rows, k) for k in GATES + QUALITY}
    secs = [r["secs"] for r in rows]
    s["secs_median"] = round(statistics.median(secs), 1) if secs else None
    s["timing"] = timing(rows)
    s["per_practice"] = {p: {k: rate([r for r in rows if r["practice"] == p], k) for k in GATES + QUALITY}
                         for p in dict.fromkeys(r["practice"] for r in rows)}
    s["sufficient"] = all(n == 0 or ok / n >= 0.9 for ok, n in (s[k] for k in GATES))
    s["failures"] = [{"practice": r["practice"], "step": r["step"], "failed": [k for k in GATES if k in r and not r[k]],
                      "tail": (r.get("text") or "")[-200:]}
                     for r in rows if any(k in r and not r[k] for k in GATES)]
    return s


def fmt(k: tuple[int, int]) -> str:
    return f"{k[0]}/{k[1]}" if k[1] else "—"


def cmd_run(a) -> int:
    prof = Path(a.dir).expanduser() if a.dir else profiles_root() / a.profile
    if not re.match(r"^(test|demo|e2e)", prof.name):
        print(f"error: {prof.name} is not a test profile (test*/demo*/e2e*) — the bench answers exercises", file=sys.stderr)
        return 2
    # 2026-09-28: e2e-bench2 was created with new-user.sh but never filled in
    # (flowed-profile.py) — every field still "{YOUR_NAME}", "{LANGUAGE_YOU_WANT_TO_LEARN}".
    # The 27B spent its turns asking for them; the 14B made up Dutch. Neither run
    # measured the tutor. Refuse before the first turn instead.
    try:
        learner = json.loads((prof / "learner-profile.json").read_text(encoding="utf-8")).get("learner", {})
    except (OSError, ValueError):
        learner = {}
    unset = [k for k in ("name", "native_language", "target_language", "current_level")
             if not learner.get(k) or str(learner.get(k)).strip().startswith("{")]
    if unset:
        print(f"error: {prof.name} is not set up ({', '.join(unset)} still empty or a placeholder).\n"
              f"  python3 scripts/flowed-profile.py {prof.name} --name Test --native Catalan --target English "
              f"--level A1 --goal A2", file=sys.stderr)
        return 2
    pw = prof / ".web-password"
    password = a.password or "".join((pw if pw.exists() else profiles_root() / ".web-password-default").read_text().split())
    cli = E2E.Client(a.port, password, a.timeout)
    try:
        health = cli._call("/api/global/health")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"error: the server on port {a.port} refuses {prof.name}'s password — it is running another\n"
                  f"  profile (a web left from an earlier run?). Restart it with this one:\n"
                  f"  scripts/flowed-web.sh --stop --port {a.port}\n"
                  f"  scripts/flowed-web.sh --app --port {a.port} {prof.name}", file=sys.stderr)
        else:
            print(f"error: the server on port {a.port} answers {e.code}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"error: no server on port {a.port}: {e}\n  scripts/flowed-web.sh --app --port {a.port} {prof.name}", file=sys.stderr)
        return 2
    try:
        sys.path.insert(0, str(REPO / "hooks"))
        import domain as dom_mod  # noqa: PLC0415  (same rule as the server: explicit field, then level scale)
        domain = dom_mod.domain_for_profile(json.loads((prof / "learner-profile.json").read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        domain = "math"
    practices = dict(PRACTICES_BY_DOMAIN.get(domain) or PRACTICES_BY_DOMAIN["math"])
    try:  # only the open practices the domain runs (config/domain.json, 2026-10-08)
        allowed = json.loads((REPO / "config" / "domain.json").read_text(encoding="utf-8"))["domains"][domain].get("open_practices")
        if isinstance(allowed, list):
            practices = {k: v for k, v in practices.items() if k.split("-")[-1] in allowed}
    except (OSError, ValueError, KeyError):
        pass
    if not practices:
        print(f"  domini {domain}: cap pràctica oberta activa (config/domain.json) — res a provar")
        return 0
    print(f"  domini {domain}: {', '.join(practices)}", flush=True)
    rows, transcript = [], []
    for i in range(a.repeat):
        for practice, spec in practices.items():
            if a.only and practice.split("-")[-1] not in a.only:
                continue
            print(f"  [{i + 1}/{a.repeat}] {practice} …", flush=True)
            rows += run_once(cli, prof, practice, spec, transcript)
    join_metrics(prof, rows)
    s = summary(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    base = OUT / f"{a.name}-{stamp}"
    base.with_suffix(".json").write_text(json.dumps(
        {"name": a.name, "domain": domain, "when": stamp, "host": a.host or os.uname().nodename, "port": a.port, "profile": prof.name, "repeat": a.repeat,
         "server": health.get("version"), "summary": s, "rows": rows}, indent=1, ensure_ascii=False))
    base.with_suffix(".md").write_text(f"# {a.name} — {stamp}\n\n" + "\n---\n\n".join(transcript), encoding="utf-8")
    print(f"\n{a.name}: {'SUFICIENT' if s['sufficient'] else 'NO SUFICIENT'}")
    for k in GATES + QUALITY:
        print(f"  {k:10s} {fmt(s[k])}")
    print_timing(s["timing"])
    print(f"  → {base.with_suffix('.json')}\n  → {base.with_suffix('.md')} (transcripció)")
    return 0


def cmd_rescore(a) -> int:
    """Re-judge a run from its .md transcript (for runs made before a check
    changed). `saved` cannot be judged from text: check .records by hand."""
    for f in a.files:
        md = Path(f).with_suffix(".md").read_text(encoding="utf-8")
        d = json.loads(Path(f).with_suffix(".json").read_text(encoding="utf-8"))
        chunks = re.split(r"\n---\n\n(?=## math-|\*\*Learner:\*\*)", md.split("\n\n", 1)[1])
        if len(chunks) != len(d["rows"]):
            print(f"{f}: {len(chunks)} blocs per {len(d['rows'])} torns — no es pot alinear", file=sys.stderr)
            continue
        rows = []
        for old, ch in zip(d["rows"], chunks):
            m = re.search(r"\):\n\n(.*)$", ch, re.S) if old["step"] != "start" else re.search(r"s\)\n\n(.*)$", ch, re.S)
            text = (m.group(1) if m else ch).strip()
            fix = next((x for k, ans, x in PRACTICES[old["practice"]]["answers"] if ans == old.get("answer")), None)
            tool = old["tool_score"] if "tool_score" in old else (old.get("score") if old.get("graded") else None)  # v1: only the tool's score
            rows.append({k: old[k] for k in ("practice", "step", "secs") if k in old}
                        | ({"answer": old["answer"]} if "answer" in old else {})
                        | {"text": text, "tool_score": tool}
                        | judge(old["practice"], old["step"], text, "", tool, "", fix)
                        | {k: old[k] for k in ("saved", "sid", "prompt_tokens", "completion_tokens", "model_s", "roundtrips")
                           if k in old})
        d["rows"], d["summary"], d["rescored"] = rows, summary(rows), True
        d["summary"]["timing"] = timing(rows)
        out = Path(f).with_suffix(".json")
        out.write_text(json.dumps(d, indent=1, ensure_ascii=False))
        s = d["summary"]
        print(f"{d['name']}: {'SUFICIENT' if s['sufficient'] else 'NO SUFICIENT'}  "
              + " · ".join(f"{k} {fmt(s[k])}" for k in GATES + QUALITY if k != "saved"))
    return 0


def print_timing(t: dict) -> None:
    print("  temps (s que espera l'alumne)   mediana   p90   màx   tok/s  prompt")
    for k in ("button", "answer", "speaking", "writing", "reading", "all"):
        b = t.get(k) or {}
        if not b.get("n"):
            continue
        print(f"    {k:28s} {b['median']!s:>7} {b['p90']!s:>5} {b['max']!s:>5} {b.get('tok_s', '—')!s:>7}"
              f"  {b.get('prompt_tokens_median', '—')!s:>6}")


def cmd_compare(a) -> int:
    latest: dict[str, dict] = {}
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text())
        latest[d["name"]] = d
    if not latest:
        print("(cap resultat encara)")
        return 0
    keys = GATES + QUALITY
    print(f"{'model':18s} {'suf.':5s} " + " ".join(f"{k:>9s}" for k in keys))
    for n, d in latest.items():
        s = d["summary"]
        print(f"{n:18s} {'sí' if s['sufficient'] else 'no':5s} " + " ".join(f"{fmt(s[k]):>9s}" for k in keys))
    print(f"\n{'temps (s)':18s} {'GPU/host':12s} {'botó med':>9s} {'resp med':>9s} {'resp p90':>9s} {'màx':>6s} {'tok/s':>6s}")
    for n, d in latest.items():
        t = d["summary"].get("timing") or timing(d["rows"])
        b, r = t.get("button", {}), t.get("answer", {})
        print(f"{n:18s} {str(d.get('host', '?')):12s} {b.get('median')!s:>9} {r.get('median')!s:>9} {r.get('p90')!s:>9}"
              f" {t.get('all', {}).get('max')!s:>6} {r.get('tok_s', '—')!s:>6}")
    print("  (el temps només compara models a la mateixa màquina/GPU)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("profile", nargs="?", default="test-en")
    r.add_argument("--dir")
    r.add_argument("--port", type=int, default=4199)
    r.add_argument("--name", required=True, help="label for the model under test, e.g. qwen3-27b")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--only", nargs="*", help="speaking / writing / reading")
    r.add_argument("--timeout", type=int, default=300)
    r.add_argument("--password")
    r.add_argument("--host", help="label for the machine/GPU, e.g. llvm-4060ti (default: hostname)")
    sub.add_parser("compare")
    rs = sub.add_parser("rescore")
    rs.add_argument("files", nargs="+", help="results/tutorbench/<name>-<time>.json")
    a = ap.parse_args()
    return {"run": cmd_run, "compare": cmd_compare, "rescore": cmd_rescore}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
