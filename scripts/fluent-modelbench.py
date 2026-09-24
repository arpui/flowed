#!/usr/bin/env python3
"""Model bench: how well does a model do Fluent's own jobs?

See docs/MODELBENCH.md. Two roles, both built on the simulated A1 learner
(bench/learner-a1.md) — a child who has studied the A1 curriculum:

    learner   the model under test IS the learner: it answers the curriculum's
              own Check: examples. Score: % it gets right.
    generate  the model under test is the TUTOR: it writes one exercise per
              competence; a FIXED judge (the learner skill on the reference
              model) answers it. Fair = the judge reaches the tutor's answer.

    # a candidate on a test port (the production model stays on 12322)
    python3 scripts/fluent-modelbench.py learner  --url http://127.0.0.1:12330/v1/chat/completions --name gemma-12b
    python3 scripts/fluent-modelbench.py generate --url http://127.0.0.1:12330/v1/chat/completions --name gemma-12b
    python3 scripts/fluent-modelbench.py compare

Read-only: it never touches a profile or the app server.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("FLUENT_BENCH_OUT") or REPO / "results" / "modelbench")
SKILL = REPO / "bench" / "learner-a1.md"
BLANK = re.compile(r"_{3,}")

sys.path.insert(0, str(REPO / "hooks"))
import curriculum as cu  # noqa: E402


# ---- the model -------------------------------------------------------------

def default_url() -> str:
    port = os.environ.get("FLUENT_DEEP_PORT")
    if not port and (REPO / ".env").exists():
        m = re.search(r"^FLUENT_DEEP_PORT=(\d+)", (REPO / ".env").read_text(), re.M)
        port = m.group(1) if m else None
    return f"http://127.0.0.1:{port or 12322}/v1/chat/completions"


def chat(url: str, prompt: str, schema: dict, temperature: float, api_key: str = "",
         timeout: float = 180) -> tuple[dict | None, float, int]:
    """(parsed JSON or None, seconds, completion tokens)."""
    body = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 300,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}},
    }
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    t0 = time.time()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read().decode())
    dt = time.time() - t0
    tokens = int((raw.get("usage") or {}).get("completion_tokens") or 0)
    content = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    try:
        out = json.loads(content)
        return (out if isinstance(out, dict) else None), dt, tokens
    except ValueError:
        return None, dt, tokens


# ---- the same answer, written differently ----------------------------------

NUMBERS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
           "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]


def canon(a: str) -> str:
    a = str(a or "").strip().lower().replace("’", "'").replace("‘", "'")
    a = a.strip(" \t\"“”«».,;:!?")
    a = re.sub(r"\bo\s*'?\s*clock\b", "o'clock", a)
    a = re.sub(r"\bcan't\b|\bcan not\b", "cannot", a)
    a = re.sub(r"\bwon't\b", "will not", a)
    a = re.sub(r"n't\b", " not", a)
    a = re.sub(r"\b(i)'m\b", r"\1 am", a)
    a = re.sub(r"\b(you|we|they)'re\b", r"\1 are", a)
    a = re.sub(r"\b(he|she|it|there|what|where|who|how|that)'s\b", r"\1 is", a)
    if re.fullmatch(r"\d+", a) and int(a) < len(NUMBERS):
        a = NUMBERS[int(a)]
    return re.sub(r"\s+", " ", a).strip()


def matches(got: str, expected: list[str]) -> bool:
    return canon(got) in {canon(e) for e in expected}


# ---- the learner skill -----------------------------------------------------

def load_curriculum(path: str) -> dict:
    return cu.load_curriculum(REPO / path if not os.path.isabs(path) else path)


def describe(comp: dict) -> str:
    d = f'{comp["name"]} — {comp.get("can_do", "")}'.strip(" —")
    if comp.get("words"):
        d += f' (words: {", ".join(comp["words"])})'
    elif comp.get("forms"):
        d += f' (forms: {str(comp["forms"]).rstrip(". ")})'
    return d


def learner_prompt(cur: dict, comp: dict, card: str) -> str:
    skill = SKILL.read_text(encoding="utf-8").split("\n---\n", 1)[1]
    studied = "\n".join(f"- {describe(c)}" for c in cur["competencies"])
    return (skill.replace("<<studied>>", studied).replace("<<lesson>>", describe(comp))
            .replace("<<card>>", card))


LEARNER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string", "maxLength": 80}},
                  "required": ["answer"]}


def checks(cur: dict) -> list[tuple[dict, dict]]:
    """The curriculum's own closed examples, one gap each."""
    out = []
    for comp in cur["competencies"]:
        for ch in comp["checks"]:
            if ch["type"] not in ("Complete", "Meaning"):
                continue
            if ch["type"] == "Complete" and "," in ch["answer"]:
                continue  # several gaps in one card
            out.append((comp, ch))
    return out


def card_of(ch: dict) -> str:
    if ch["type"] == "Meaning":
        return f"**Meaning:** {ch['prompt']}\n**Word:** ___"
    return f"**Sentence:** {ch['prompt']}"


# ---- roles -----------------------------------------------------------------

def role_learner(a, cur: dict) -> dict:
    items = []
    for comp, ch in checks(cur):
        out, dt, tok = chat(a.url, learner_prompt(cur, comp, card_of(ch)), LEARNER_SCHEMA, 0, a.api_key)
        got = (out or {}).get("answer", "")
        alts = ch.get("alternatives") or [ch["answer"]]
        items.append({"competence": comp["id"], "card": card_of(ch), "expected": alts, "answer": got,
                      "json_ok": out is not None, "correct": out is not None and matches(got, alts),
                      "seconds": round(dt, 2), "tokens": tok})
        print(f"  {'✓' if items[-1]['correct'] else '✗'} {ch['prompt'][:60]:<62} → {got!r}", flush=True)
    return summarise("learner", items, ok_key="correct")


GEN_SCHEMA = {
    "type": "object",
    "properties": {"sentence": {"type": "string", "maxLength": 160},
                   "answer": {"type": "string", "maxLength": 40}},
    "required": ["sentence", "answer"],
}

GEN_PROMPT = (
    "You are an English tutor for a Catalan-speaking child at level A1. Write ONE short exercise for the lesson "
    "on: {lesson}.\n"
    "It has exactly one gap (___) and exactly one right answer for a learner who studied this lesson. "
    "{rule}Do not copy the examples below; write a new one.\n"
    "Examples of this lesson (do not reuse them): {examples}\n\n"
    "Reply as JSON: {{\"sentence\": \"...\", \"answer\": \"...\"}}"
)


def deterministic(ex: dict, comp: dict) -> str | None:
    """Why the exercise is not usable before anyone answers it, or None."""
    s, ans = ex.get("sentence", ""), ex.get("answer", "")
    if len(BLANK.findall(s)) != 1:
        return "no té exactament un buit"
    if not ans.strip():
        return "sense resposta"
    if re.search(rf"\b{re.escape(canon(ans))}\b", canon(BLANK.sub(" ", s))):
        return "la resposta ja surt a la frase"
    if comp.get("words"):
        if canon(ans) not in {canon(w) for w in comp["words"]}:
            return "la resposta no és de la llista"
        if not re.search(r"___+[^\n]*\([^()]{1,40}\)", s):
            return "vocabulari sense la paraula en català entre parèntesis"
    return None


def role_generate(a, cur: dict) -> dict:
    items = []
    for comp in cur["competencies"]:
        rule = ('Put the word in Catalan in brackets right after the gap, e.g. "The car is ___ (vermell).". '
                'The answer is one word from the list. ') if comp.get("words") else ""
        examples = "; ".join(c["prompt"] for c in comp["checks"][:2])
        for _ in range(a.per):
            prompt = GEN_PROMPT.format(lesson=describe(comp), rule=rule, examples=examples)
            ex, dt, tok = chat(a.url, prompt, GEN_SCHEMA, a.temperature, a.api_key)
            row = {"competence": comp["id"], "json_ok": ex is not None, "seconds": round(dt, 2), "tokens": tok,
                   **(ex or {})}
            why = deterministic(ex, comp) if ex else "no és JSON"
            row["rejected"] = why
            if not why:
                judged, _, _ = chat(a.judge_url, learner_prompt(cur, comp, f"**Sentence:** {ex['sentence']}"),
                                    LEARNER_SCHEMA, 0, a.judge_key)
                row["judge"] = (judged or {}).get("answer", "")
                row["fair"] = matches(row["judge"], [ex["answer"]])
            else:
                row["fair"] = False
            items.append(row)
            mark = "✓" if row["fair"] else "✗"
            print(f"  {mark} {comp['id']:<32} {str(row.get('sentence', ''))[:55]:<57} "
                  f"→ {row.get('answer', '')!r}" + (f"  [{why}]" if why else f"  jutge: {row.get('judge')!r}"),
                  flush=True)
    card = summarise("generate", items, ok_key="fair")
    good = [r for r in items if r["fair"]]
    card["variety"] = round(len({canon(r["sentence"]) for r in good}) / len(good), 2) if good else 0
    card["rejected_by"] = {}
    for r in items:
        if r["rejected"]:
            card["rejected_by"][r["rejected"]] = card["rejected_by"].get(r["rejected"], 0) + 1
    return card


def summarise(role: str, items: list[dict], ok_key: str) -> dict:
    n = len(items)
    secs = [i["seconds"] for i in items] or [0]
    tok = sum(i["tokens"] for i in items)
    return {"role": role, "n": n,
            "json_ok": round(sum(i["json_ok"] for i in items) / n, 3) if n else 0,
            "score": round(sum(bool(i[ok_key]) for i in items) / n, 3) if n else 0,
            "median_s": round(statistics.median(secs), 2),
            "tokens_per_s": round(tok / sum(secs), 1) if sum(secs) else 0,
            "items": items}


def save(a, card: dict) -> Path:
    d = OUT / a.name / datetime.now().strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    items = card.pop("items")
    (d / f"{card['role']}.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n",
                                              encoding="utf-8")
    meta = {"name": a.name, "url": a.url, "curriculum": a.curriculum, "date": datetime.now().isoformat(timespec="minutes"),
            **({"judge_url": a.judge_url, "temperature": a.temperature, "per": a.per} if card["role"] == "generate" else {})}
    (d / f"{card['role']}.json").write_text(json.dumps({**meta, **card}, indent=2, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
    return d



# ---- bank (fase 1: PLA-EXERCICIS-TANCATS.md) --------------------------------

BANK_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["complete", "choose", "meaning", "translate", "correct"]},
        "instruction": {"type": "string", "maxLength": 100},
        "sentence": {"type": "string", "maxLength": 160},
        "context": {"type": "string", "maxLength": 100},
        "answer": {"type": "string", "maxLength": 40},
        "also_accept": {"type": "array", "items": {"type": "string", "maxLength": 40}, "maxItems": 3},
        "options": {"type": "array", "items": {"type": "string", "maxLength": 20}, "maxItems": 4},
        "why": {"type": "string", "maxLength": 140},
    },
    "required": ["type", "instruction", "sentence", "answer", "why"],
}

BANK_PROMPT = (
    "You are an English tutor writing ONE exercise item for a bank, for a Catalan-speaking A1 child, lesson: "
    "{lesson}.\n"
    "Write a {kind} exercise. {rule}"
    "Do not copy the examples below; write a new sentence.\n"
    "Examples of this lesson (do not reuse them): {examples}\n\n"
    'Reply as JSON: {{"type": "{kind}", "instruction": "short task line", "sentence": "...", "context": "", '
    '"answer": "...", "also_accept": [], "options": [], "why": "one short sentence explaining the rule, for a '
    'child who got it wrong"}}'
)

PICTURE_RE = re.compile(r"\b(?:look at the (?:picture|photo|image|diagram)\b|describe what you see)", re.I)


def bank_kind_rule(kind: str, comp: dict) -> str:
    if kind == "meaning":
        return "It has no gap: instruction asks what an English word from the lesson means, answer is that word. "
    if kind == "translate":
        return "It has no gap: instruction asks for the English word for a Catalan word from the lesson. "
    if kind == "correct":
        return ("sentence is a WRONG sentence using this lesson's structure; answer is the FULL corrected "
                "sentence, differing from sentence in only a few words. ")
    if kind == "choose" and comp.get("words"):
        return ("Put the Catalan word in brackets right after the gap, e.g. \"The car is ___ (vermell).\". "
                "options are 2-4 words from the lesson's word list, answer is one of them. ")
    if kind == "choose":
        return "options are 2-4 short alternatives that could plausibly fill the gap; a clue in the sentence makes only answer correct. "
    if comp.get("words"):
        return ("Exactly one ___ gap. Put the Catalan word in brackets right after the gap, e.g. "
                "\"The car is ___ (vermell).\". answer is one word from the lesson's word list. ")
    return "Exactly one ___ gap; answer is the single word or short phrase that belongs there — never the verb that sits next to it. "


def bank_validate(item: dict | None, comp: dict, seen_sentences: set[str]) -> str | None:
    """V1-V11 of PLA-EXERCICIS-TANCATS.md. Returns the rejection reason, or None if it passes."""
    if not item:
        return "no és JSON"
    kind = item.get("type", "")
    sentence = str(item.get("sentence", ""))
    context = str(item.get("context", ""))
    answer = str(item.get("answer", ""))
    why = str(item.get("why", ""))
    is_vocab = bool(comp.get("words"))
    allowed = ("meaning", "complete", "translate") if is_vocab else ("complete", "choose", "correct")
    if kind not in allowed:
        return f"type {kind!r} no permès per aquesta competència (V1)"
    if not answer.strip():
        return "sense resposta"
    if kind in ("complete", "choose"):
        if len(BLANK.findall(sentence)) != 1:
            return "no té exactament un buit (V2)"
        # Strip any bracket hint ("___ (have) you got a pen?") before checking
        # for collision: the hint word is scaffolding for the learner, not
        # prose the answer would be "repeating" (2026-09-24, after V3
        # rejected a1.have_got's "Have" because the hint "(have)" contains it).
        sentence_no_hint = re.sub(r"\([^()]{1,40}\)", " ", sentence)
        rest = canon(BLANK.sub(" ", sentence_no_hint)) + " " + canon(context)
        if re.search(rf"\b{re.escape(canon(answer))}\b", rest):
            return "la resposta ja surt a la frase (V3)"
    if is_vocab and kind in ("meaning", "complete", "translate"):
        if canon(answer) not in {canon(w) for w in comp["words"]}:
            return "la resposta no és de Words (V4)"
        if kind == "complete" and not re.search(r"___+[^\n]*\([^()]{1,40}\)", sentence):
            return "vocabulari amb buit sense pista en català entre parèntesis (V5)"
        if kind == "complete":
            hint = re.search(r"___+[^\n]*\(([^()]{1,40})\)", sentence)
            if hint and canon(hint.group(1)) == canon(answer):
                return "la pista és la mateixa paraula anglesa, no una traducció (V5)"
    key = canon(sentence)
    if key in seen_sentences:
        return "frase repetida dins la competència (V6)"
    if PICTURE_RE.search(sentence) or PICTURE_RE.search(context):
        return "referència a una imatge (V7)"
    if kind == "correct":
        if canon(sentence) == canon(answer):
            return "la frase ja és correcta (V8)"
        wa, wb = canon(sentence).split(), canon(answer).split()
        if abs(len(wa) - len(wb)) > 4:
            return "correct: la resposta no és la mateixa frase corregida (V8)"
    if kind == "choose":
        opts = item.get("options") or []
        if not (2 <= len(opts) <= 4) or canon(answer) not in {canon(o) for o in opts}:
            return "choose: answer no és a options, o options fora de 2-4 (V9)"
    if not is_vocab:
        # V10 only makes sense as a literal-tag check when the sentence has no
        # bracket hint: a fixed-structure item ("___ she live in Madrid?") has
        # a fixed answer that IS one of the lesson's Tags. A bracket item
        # ("My brother ___ (play) football") asks for a MORPHOLOGICAL
        # transform of the bracket verb (play -> plays, not/like ->
        # doesn't like) — its answer is legitimately not a literal Tags word,
        # so V10 would reject correct answers ("opens", "explains") as often
        # as it would catch a real one ("can ride"). Left to authoring/review
        # for bracket items instead (2026-09-24, after V10 rejected "opens"
        # and "explains" for a1.present_simple).
        # Word-level overlap, not phrase-level substring: a multi-word tag
        # ("there is") legitimately shows up reordered ("Is there") or as a
        # sub-phrase ("good afternoon" -> "afternoon", "years old" -> "years",
        # "what time" -> "What") in a correct answer. Substring-of-the-whole-
        # tag matching rejected all of these as false positives (2026-09-24).
        has_bracket = bool(re.search(r"___+[^\n]*\([^()]{1,40}\)", sentence))
        tag_word_set: set[str] = set()
        for t in comp.get("tags", []):
            if t.startswith("#"):
                continue
            tag_word_set.update(canon(t).split())
        answer_word_set = set(canon(answer).split())
        if not has_bracket and tag_word_set and not (tag_word_set & answer_word_set):
            return "la resposta no conté cap paraula de Tags: — sembla el verb veí, no l'estructura (V10)"
    if not why.strip() or canon(why) == canon(sentence):
        return "sense why útil (V11)"
    return None


def role_bank(a, cur: dict) -> dict:
    comps = [c for c in cur["competencies"] if not a.competence or c["id"] == a.competence]
    if not comps:
        print(f"❌ competència {a.competence!r} no trobada")
        return {"role": "bank", "n": 0, "score": 0, "json_ok": 0, "median_s": 0, "tokens_per_s": 0, "items": []}
    all_items = []
    for comp in comps:
        is_vocab = bool(comp.get("words"))
        kinds = ["meaning", "complete", "translate"] if is_vocab else ["complete", "complete", "correct"]
        examples = "; ".join(c["prompt"] for c in comp["checks"][:2])
        accepted: list[dict] = []
        seen: set[str] = set()
        tried = 0
        secs = []
        while len(accepted) < a.count and tried < a.attempts:
            kind = kinds[tried % len(kinds)]
            rule = bank_kind_rule(kind, comp)
            prompt = BANK_PROMPT.format(lesson=describe(comp), kind=kind, rule=rule, examples=examples)
            ex, dt, tok = chat(a.url, prompt, BANK_SCHEMA, a.temperature, a.api_key)
            secs.append(dt)
            tried += 1
            why = bank_validate(ex, comp, seen)
            row = {"competence": comp["id"], "json_ok": ex is not None, "seconds": round(dt, 2), "tokens": tok,
                   "rejected": why, **(ex or {})}
            if why:
                row["fair"] = False
                all_items.append(row)
                print(f"  ✗ {comp['id']:<32} [{why}]", flush=True)
                continue
            judged, _, _ = chat(a.judge_url, learner_prompt(cur, comp, f"**Sentence:** {ex['sentence']}\n**Instruction:** {ex.get('instruction','')}"),
                                LEARNER_SCHEMA, 0, a.judge_key)
            got = (judged or {}).get("answer", "")
            fair = matches(got, [ex["answer"], *ex.get("also_accept", [])])
            row["judge"] = got
            row["fair"] = fair
            all_items.append(row)
            mark = "✓" if fair else "✗"
            print(f"  {mark} {comp['id']:<32} {str(ex.get('sentence',''))[:50]:<52} → {ex['answer']!r}"
                  + ("" if fair else f"  jutge: {got!r}"), flush=True)
            if fair:
                seen.add(canon(ex["sentence"]))
                accepted.append({
                    "id": f"{comp['id']}.{len(accepted) + 1:03d}",
                    "competence": comp["id"],
                    "type": ex["type"],
                    "instruction": ex.get("instruction", ""),
                    "sentence": ex["sentence"],
                    "context": ex.get("context", ""),
                    "answer": ex["answer"],
                    "also_accept": ex.get("also_accept", []),
                    "options": ex.get("options", []),
                    "why": ex.get("why", ""),
                    "status": "validated",
                    "source": f"{a.name} · {datetime.now().strftime('%Y-%m-%d')}",
                })
        bank_dir = REPO / "curriculum" / "bank" / Path(a.curriculum).stem
        bank_dir.mkdir(parents=True, exist_ok=True)
        out_path = bank_dir / f"{comp['id']}.json"
        out_path.write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  → {len(accepted)}/{a.count} ítems vàlids per a {comp['id']} ({tried} intents) → {out_path}")
    card = summarise("bank", all_items, ok_key="fair")
    return card


def cmd_bank(a) -> int:
    cur = load_curriculum(a.curriculum)
    print(f"{a.name} · bank · {a.url}")
    try:
        card = role_bank(a, cur)
    except (urllib.error.URLError, OSError) as e:
        print(f"❌ el model no respon ({e})")
        return 2
    if card["n"]:
        print(f"\ntotal: {card['score']:.0%} justos de {card['n']} intents · mediana {card['median_s']}s")
    return 0


def cmd_role(a) -> int:
    cur = load_curriculum(a.curriculum)
    print(f"{a.name} · {a.cmd} · {a.url}")
    try:
        card = role_learner(a, cur) if a.cmd == "learner" else role_generate(a, cur)
    except (urllib.error.URLError, OSError) as e:
        print(f"❌ el model no respon ({e})")
        return 2
    d = save(a, card)
    extra = (f" · varietat {card['variety']:.0%} · rebutjats {card['rejected_by']}" if a.cmd == "generate" else "")
    print(f"\n{a.name} · {a.cmd}: {card['score']:.0%} de {card['n']} · JSON {card['json_ok']:.0%} · "
          f"mediana {card['median_s']}s · {card['tokens_per_s']} tok/s{extra}\n→ {d}")
    return 0


def cmd_compare(a) -> int:
    rows = {}
    for f in sorted(OUT.glob("*/*/*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        rows.setdefault(c["name"], {})[c["role"]] = c  # the latest run of each role wins (sorted by date)
    if not rows:
        print(f"cap resultat a {OUT}")
        return 0
    pct = lambda v: f"{v:.0%}"
    print(f"{'model':<22}{'alumne':>9}{'tutor just':>12}{'varietat':>10}{'JSON':>7}{'mediana':>9}{'tok/s':>8}")
    for name, r in sorted(rows.items()):
        l, g = r.get("learner"), r.get("generate")
        done = [x for x in (l, g) if x]
        learner = pct(l["score"]) if l else "—"
        tutor = pct(g["score"]) if g else "—"
        variety = pct(g.get("variety", 0)) if g else "—"
        js = pct(min(x["json_ok"] for x in done))
        med = f"{max(x['median_s'] for x in done)}s"
        tps = done[0].get("tokens_per_s", 0)
        print(f"{name:<22}{learner:>9}{tutor:>12}{variety:>10}{js:>7}{med:>9}{tps:>8}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=default_url(), help="model sota prova (compatible OpenAI)")
    ap.add_argument("--api-key", default=os.environ.get("FLUENT_BENCH_KEY", ""))
    ap.add_argument("--name", default="qwen3-14b-q4")
    ap.add_argument("--curriculum", default="curriculum/en-A1.md")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("learner")
    g = sub.add_parser("generate")
    g.add_argument("--judge-url", default=default_url(), help="el jutge fix: per defecte, el model de producció")
    g.add_argument("--judge-key", default=os.environ.get("FLUENT_JUDGE_KEY", ""))
    g.add_argument("--per", type=int, default=2, help="exercicis per competència")
    g.add_argument("--temperature", type=float, default=0.7)
    sub.add_parser("compare")
    b = sub.add_parser("bank")
    b.add_argument("--judge-url", default=default_url(), help="el jutge fix: per defecte, el model de producció")
    b.add_argument("--judge-key", default=os.environ.get("FLUENT_JUDGE_KEY", ""))
    b.add_argument("--competence", default="", help="només aquesta competència; buit = totes")
    b.add_argument("--count", type=int, default=40, help="ítems vàlids per competència")
    b.add_argument("--attempts", type=int, default=120, help="intents màxims per competència")
    b.add_argument("--temperature", type=float, default=0.7)
    a = ap.parse_args()
    if a.cmd == "compare":
        return cmd_compare(a)
    if a.cmd == "bank":
        return cmd_bank(a)
    return cmd_role(a)


if __name__ == "__main__":
    sys.exit(main())
