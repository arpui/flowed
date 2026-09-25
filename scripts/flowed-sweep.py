#!/usr/bin/env python3
"""Run the end-to-end tests across sampling settings, and write down the result.

The question this answers is the one that cannot be answered by looking: does
raising the temperature stop the tutor repeating itself, and what does it cost
in format compliance? Both move at once, both are stochastic, and a single run
of either proves nothing.

So: for each setting, restart the app with that sampling, check that the app
really is running it, seed the profile, run the scenarios N times each, and
record everything under results/sweep-<stamp>/ — one directory per setting, a
run log per execution, and a summary.csv at the top with the numbers side by
side.

The sampling reaches the app through FLOWED_MODELS_FILE (a models file per
setting, written next to its results). It is NOT written to config/fluent.json:
config/fluent-models.json is a layer that sits above it, and it pins
`temperature`, so a temperature written to fluent.json was silently ignored —
every "temp06" ran at 0.2. Whatever the layers do, the sweep now asks the
running app (/api/global/health) what it will send, and refuses to run a
setting the app is not actually using.

    python3 scripts/flowed-sweep.py --port 4103 \\
        --setting "base:" \\
        --setting "warm:temperature=0.6,presence_penalty=0.4" \\
        --setting "warm+rep:temperature=0.6,presence_penalty=0.4,repeat_last_n=512"

    python3 scripts/flowed-sweep.py --port 4103 --repeat 3 --scenario wander --scenario full

Touches no repo configuration: only a test profile, the app instance on --port
(stopped on exit) and the files under results/. The model is not started here
(scripts/flowed-bench.sh does that) and is never reloaded: the sampling knobs
travel in every request. Refuses any other profile.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from main_paths import profiles_root  # noqa: E402  (where the profiles live)

REPO = Path(__file__).resolve().parent.parent
SCRATCH = re.compile(r"^(test|demo|e2e)", re.I)
KNOBS = ("temperature", "top_p", "top_k", "presence_penalty",
         "frequency_penalty", "repeat_penalty", "repeat_last_n")


def parse_setting(text: str) -> tuple[str, dict[str, float]]:
    """"name:temperature=0.6,presence_penalty=0.4" → ("name", {...})"""
    name, _, rest = text.partition(":")
    knobs: dict[str, float] = {}
    for part in filter(None, (p.strip() for p in rest.split(","))):
        k, _, v = part.partition("=")
        k = k.strip()
        if k not in KNOBS:
            raise SystemExit(f"❌ paràmetre desconegut: {k}. Permesos: {', '.join(KNOBS)}")
        knobs[k] = float(v)
    return (name.strip() or "sense-nom"), knobs


# The app reads camelCase from a models file (index.ts loadModels); the
# knob names the sweep and the health endpoint use are snake_case.
MODELS_FILE_KEYS = {
    "temperature": "temperature", "top_p": "topP", "top_k": "topK",
    "presence_penalty": "presencePenalty", "frequency_penalty": "frequencyPenalty",
    "repeat_penalty": "repeatPenalty", "repeat_last_n": "repeatLastN",
}
INT_KNOBS = ("top_k", "repeat_last_n")
BASE_TEMPERATURE = 0.2


def wanted_sampling(knobs: dict[str, float]) -> dict[str, float]:
    """What a setting asks for. The base is not "whatever the files say": it is
    temperature 0.2 and nothing else, so it means the same on every machine."""
    want: dict[str, float] = {"temperature": BASE_TEMPERATURE}
    for k, v in knobs.items():
        want[k] = int(v) if k in INT_KNOBS else v
    return want


def write_models_file(knobs: dict[str, float], path: Path) -> Path:
    """The setting as a models file, for FLOWED_MODELS_FILE.

    That layer wins over config/fluent.json AND over config/fluent-models.json,
    so the setting cannot be shadowed by a file someone forgot about — and no
    repo file has to be edited and put back."""
    deep = {MODELS_FILE_KEYS[k]: v for k, v in wanted_sampling(knobs).items()}
    path.write_text(json.dumps({"deep": deep}, indent=2) + "\n", encoding="utf-8")
    return path.resolve()


def effective_sampling(port: int, prof: Path, wait: float = 30.0) -> dict | None:
    """What the RUNNING app says it will send to the model, or None if it does
    not answer. This is the app's own view (health.sampling), the last hop we
    can see from outside; llama.cpp honours per-request knobs by contract."""
    try:
        pw = (prof / ".web-password").read_text(encoding="utf-8").strip()
    except OSError:
        pw = ""
    token = base64.b64encode(f"opencode:{pw}".encode()).decode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/global/health",
                                 headers={"Authorization": f"Basic {token}"})
    deadline = time.time() + wait
    while True:
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode("utf-8")).get("sampling") or {}
        except Exception:  # noqa: BLE001 - not up yet, wrong password, anything
            if time.time() > deadline:
                return None
            time.sleep(1)


def sampling_problems(knobs: dict[str, float], got: dict) -> list[str]:
    """Differences between what was asked and what the app reports.

    A knob nobody asked for must be absent (top_p aside: it always has a
    default), otherwise "base" would silently be base plus whatever a config
    layer happens to carry."""
    want = wanted_sampling(knobs)
    out: list[str] = []
    for k in KNOBS:
        w, g = want.get(k), got.get(k)
        if w is None:
            if g is not None and k != "top_p":
                out.append(f"{k}: el servidor porta {g} i no s'ha demanat")
        elif g is None or abs(float(g) - float(w)) > 1e-9:
            out.append(f"{k}: demanat {w}, el servidor porta {g}")
    return out


def profile_state(prof: Path, since: float | None = None) -> dict:
    """Enough of the profile to see whether a run destroyed it.

    A T0 snapshot keyed on a recycled session number rolled a real profile from
    twelve spaced-repetition items back to two, and nothing failed while it
    happened. Any run that leaves the queue smaller than it found it is a
    finding, whatever the checks say — so the numbers go in the record instead
    of being asked for afterwards.
    """
    out: dict = {}
    try:
        sr = json.loads((prof / "spaced-repetition.json").read_text(encoding="utf-8"))
        items = sr.get("items") or {}
        out["items"] = len(items)
        # The server's own definition (dueItemIds in pacing.ts): due_date <= today.
        # `review_queue.today` is a cache that has been out of step with it, and
        # the gate below must agree with what the tutor will actually be given.
        today = date.today().isoformat()
        out["due_today"] = sum(
            1 for v in items.values()
            if isinstance(v, dict) and isinstance(v.get("due_date"), str)
            and v["due_date"] <= today)
        out["queue_today"] = len(sr.get("review_queue", {}).get("today") or [])
        out["item_ids"] = sorted(items)[:20]
    except Exception as e:
        out["items_error"] = str(e)
    try:
        mis = json.loads((prof / "mistakes-db.json").read_text(encoding="utf-8"))
        pats = mis.get("error_patterns") or {}
        out["patterns"] = len(pats)
        out["healed"] = sum(1 for v in pats.values() if (v.get("mastery_level") or 0) >= 4)
    except Exception as e:
        out["patterns_error"] = str(e)
    try:
        # Every repeat, not just the last one. `--repeat 3` restores the profile
        # between runs and archives each run's records under a dotted name, so
        # counting `*.jsonl` reported ONE run of three — and a sweep whose first
        # two runs wrote item_ids looked like a total failure because the third
        # did not. Anything written since this scenario started counts.
        here = prof / ".records"
        recs = [f for f in list(here.iterdir()) + list((here / "_archive").iterdir()
                                                       if (here / "_archive").is_dir() else [])
                if f.is_file() and ".jsonl" in f.name
                and (since is None or f.stat().st_mtime >= since)]
        lines = [l for f in recs for l in f.read_text().splitlines() if l.strip()]
        out["records"] = len(lines)
        out["records_with_item_id"] = sum(1 for l in lines if json.loads(l).get("item_id"))
        out["records_runs"] = len(recs)
    except Exception:
        out["records"] = 0
    try:
        out["t0_snapshots"] = len(list((prof / ".update-state").glob("*.json")))
    except Exception:
        pass
    return out


def sh(cmd: list[str], out: Path | None = None, timeout: int = 1800,
       echo: bool = False, prefix: str = "    ",
       env: dict[str, str] | None = None) -> int:
    """Run a step, write its output to a log, and — when it is the long one —
    show it as it happens.

    Capturing everything and saying nothing until the child exits makes a
    five-minute run indistinguishable from a hang. It was: "sembla q s'ha
    penjat". A test harness that cannot be told apart from a broken one is not
    finished.
    """
    started = time.time()
    lines: list[str] = []
    proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            env={**os.environ, **env} if env else None)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if echo:
                print(f"{prefix}{line.rstrip()}", flush=True)
            if timeout and time.time() - started > timeout:
                proc.kill()
                lines.append(f"\n[avortat: més de {timeout}s]\n")
                break
        proc.wait(timeout=30)
    except Exception as e:  # noqa: BLE001 - a step that dies must not kill the sweep
        proc.kill()
        lines.append(f"\n[error: {e}]\n")
    if out:
        out.write_text("".join(lines), encoding="utf-8")
    return proc.returncode if proc.returncode is not None else 1


SUMMARY = re.compile(r"^\s*(✅|⚠️|❌)\s+(.+?)(?:\s+—\s+falla (\d+)/(\d+))?\s*$")
UNGRADED = re.compile(r"execucions sense cap qualificació: (\d+) de (\d+)")
GUARDS = re.compile(r"el guard del servidor ha actuat (\d+) cop\(s\) en total")


DEEP_DOWN = re.compile(r"^\s*model:\s+deep\b.*NOT RUNNING", re.M)


def deep_model_down(start_log: str) -> bool:
    """Is the DEEP model down, according to flowed-web.sh's start log?

    That script prints one line per model — deep AND face — and face is off by
    design (FLOWED_FACE_ENABLED=0), so its "NOT RUNNING" is the normal state.
    A bare substring test on the whole log aborted a bench whose deep model
    was up ("model: deep — OK") because of the face line under it."""
    return bool(DEEP_DOWN.search(start_log))


def read_result(text: str) -> dict:
    """The aggregate lines of a --repeat run, as numbers."""
    checks: dict[str, tuple[int, int]] = {}
    inside = False
    for line in text.splitlines():
        if line.startswith("=== resum de"):
            inside = True
            continue
        if not inside:
            continue
        m = SUMMARY.match(line)
        if m:
            label = m.group(2).strip()
            fails = int(m.group(3) or 0)
            total = int(m.group(4) or 0) or 1
            checks[label] = (fails, total)
    g = GUARDS.search(text)
    u = UNGRADED.search(text)
    return {"checks": checks, "guards": int(g.group(1)) if g else -1,
            "ungraded": int(u.group(1)) if u else 0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("profile", nargs="?", default="test-en")
    ap.add_argument("--port", type=int, default=4103)
    ap.add_argument("--setting", action="append", default=[],
                    help='"nom:clau=valor,clau=valor". Repetible. Sense --setting, només la base')
    ap.add_argument("--scenario", action="append", default=[],
                    help="escenari a córrer; repetible (per defecte: wander)")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--test-mode", choices=("pass", "fail"), default="pass", dest="test_mode",
                    help="escenari ladder: la prova de nivell es contesta bé (pass) o tot malament (fail)")
    ap.add_argument("--stop-before-test", action="store_true", dest="stop_before_test",
                    help="escenari ladder: para just abans de la prova de nivell (perfil a punt, "
                         "no certificat) perquè la facis tu mateix a la web")
    ap.add_argument("--span", type=int, default=0,
                    help="dies de l'escenari curriculum (per defecte els del bench: 5); no és --days, que són els de la sembra")
    # A lesson is 6 exercises (LESSON_MINIMUM in pacing.ts). With fewer items due
    # the rest come from the weak patterns, and the seeded ones are three sentences
    # about articles, spelling and capitals: the bench asked the tutor for six
    # different exercises out of three concepts and then counted every look-alike
    # as a repeat. Six due items = six distinct things to ask.
    ap.add_argument("--due", type=int, default=6,
                    help="ítems per repassar avui (per defecte 6 = una lliçó sencera)")
    ap.add_argument("--out", help="directori de resultats (per defecte results/sweep-<data>)")
    args = ap.parse_args()

    if not SCRATCH.match(args.profile):
        print(f"❌ només en perfils de proves, no en {args.profile}", file=sys.stderr)
        return 2
    settings = [parse_setting(t) for t in (args.setting or ["base:"])]
    prof_dir = profiles_root() / args.profile
    scenarios = args.scenario or ["wander"]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_root = Path(args.out).expanduser() if args.out else REPO / "results" / f"sweep-{stamp}"
    out_root.mkdir(parents=True, exist_ok=True)
    print(f"resultats a {out_root}\n")

    rows: list[dict] = []
    all_checks: dict[tuple[str, str], dict[str, tuple[int, int]]] = {}
    try:
        for name, knobs in settings:
            print(f"{'=' * 24} {name} {'=' * 24}")
            print("  " + (", ".join(f"{k}={v}" for k, v in knobs.items()) or "per defecte"))
            d = out_root / name
            d.mkdir(exist_ok=True)
            (d / "knobs.json").write_text(json.dumps(knobs, indent=2) + "\n", encoding="utf-8")
            models_file = write_models_file(knobs, d / "models.json")

            # The app reads its sampling once, when it starts, so a setting that
            # is not restarted into is a setting that was never tested. The
            # setting travels in FLOWED_MODELS_FILE (see the module docstring).
            sh([str(REPO / "scripts" / "flowed-web.sh"), "--stop", "--port", str(args.port)],
               d / "00-stop.log", timeout=120)
            rc = sh([str(REPO / "scripts" / "flowed-web.sh"), "--app", "--port", str(args.port),
                     args.profile], d / "01-start.log", timeout=300,
               env={"FLOWED_MODELS_FILE": str(models_file)})
            if rc != 0:
                print(f"  ❌ el servidor no ha arrencat (mira {d / '01-start.log'})")
                continue
            # NOT the model: this reboots the APP, which reads config/fluent.json
            # once at boot. llama.cpp has to be up already and stays up — the
            # sampling knobs travel in the body of every request
            # (temperature / top_p / presence_penalty / frequency_penalty /
            # repeat_last_n, see llm.ts), so testing a setting never needs the
            # model reloaded. The old wording here said "waiting for the model
            # to load", which was simply wrong and read as if the bench started it.
            print("    esperant que l'app aixequi (el model ja ha d'estar amunt)…", flush=True)
            time.sleep(12)
            # A server that came up with the model down answers every turn with
            # nothing, instantly: six executions in 18 seconds, 0 records, 0
            # guard events, and ten checks red — a picture identical to a total
            # collapse of the tutor. The evidence was in 01-start.log all along
            # ("model: deep — NOT RUNNING"), which is exactly the kind of thing
            # nobody reads while a bench is running.
            if deep_model_down((d / "01-start.log").read_text(encoding="utf-8", errors="ignore")):
                print("  ❌ el model deep NO corre (mira la línia «model: deep — NOT RUNNING» a "
                      f"{d / '01-start.log'})")
                print("     arrenca'l amb scripts/flowed-start.sh --models-only i torna-hi;")
                print("     sense model, cada torn torna buit a l'instant i TOTES les "
                      "comprovacions de qualificació surten vermelles.")
                break

            # What the app SAYS it will send, against what was asked. On
            # 2026-09-19 config/fluent-models.json (a layer above fluent.json)
            # pinned temperature 0.2, so every "temp06" ran at 0.2 and the
            # tables compared noise with noise — with nothing on screen to say
            # so. The check costs one request; a wrong setting costs a bench.
            got = effective_sampling(args.port, prof_dir)
            if got is None:
                print("  ❌ no puc llegir el mostreig del servidor (/api/global/health) — "
                      "no corro aquest setting")
                continue
            problems = sampling_problems(knobs, got)
            if problems:
                print("  ❌ el mostreig efectiu NO és el demanat — no corro aquest setting:")
                for prob in problems:
                    print(f"     · {prob}")
                continue
            print("  mostreig efectiu: " + ", ".join(f"{k}={v}" for k, v in got.items()))

            for scen in scenarios:
                print(f"  escenari {scen} ×{args.repeat}…")
                seed_log = d / f"02-seed-{scen}.log"
                rc_seed = sh([sys.executable, str(REPO / "scripts" / "flowed-seed.py"),
                              args.profile, "--days", str(args.days), "--due", str(args.due)],
                             seed_log)
                before = profile_state(prof_dir)
                # A seed that died is not a detail: the executions that follow
                # run on whatever the last sweep left behind and report their
                # numbers as if the profile had been prepared. That happened on
                # 2026-09-19 — three executions on a stale profile with nothing
                # due, read as a collapse of the tutor.
                # The curriculum scenario blanks the queue itself: nothing has to be due.
                if rc_seed != 0 or (not before.get("due_today") and scen not in ("curriculum", "ladder")):
                    print(f"  ❌ la sembra ha fallat (codi {rc_seed}, "
                          f"{before.get('due_today', 0)} per repassar) — mira {seed_log}")
                    print("     no corro l'escenari: mesuraria un perfil que no s'ha preparat")
                    continue
                log = d / f"03-{scen}.log"
                t_scen = time.time()
                started = t_scen
                sh([sys.executable, "-u", str(REPO / "scripts" / "flowed-e2e.py"), args.profile,
                    "--port", str(args.port), "--scenario", scen,
                    "--repeat", str(args.repeat), "--summary",
                    *(["--days", str(args.span)] if args.span and scen in ("curriculum", "ladder") else []),
                    *(["--test-mode", args.test_mode] if scen == "ladder" else []),
                    *(["--stop-before-test"] if scen == "ladder" and args.stop_before_test else []),
                    "--transcript", str(d / f"transcript-{scen}.md")], log, echo=True,
                   # five lessons in a row per execution: the default half hour
                   # would kill the run before the second repeat.
                   timeout=(4 * 3600 if scen in ("days", "curriculum", "ladder") else 1800))
                print(f"    ({time.time() - t_scen:.0f}s)")
                after = profile_state(prof_dir, since=started)
                (d / f"04-profile-{scen}.json").write_text(
                    json.dumps({"abans": before, "despres": after}, indent=2, ensure_ascii=False)
                    + "\n", encoding="utf-8")
                lost = before.get("items", 0) - after.get("items", 0)
                if lost > 0 and scen not in ("curriculum", "ladder"):   # (that scenario blanks the queue on purpose)
                    print(f"    ⚠ la cua ha PERDUT {lost} ítems "
                          f"({before.get('items')} → {after.get('items')})")
                else:
                    print(f"    cua {before.get('items')} → {after.get('items')} ítems · "
                          f"{after.get('records', 0)} registres en "
                          f"{after.get('records_runs', 0)} execucions "
                          f"({after.get('records_with_item_id', 0)} amb item_id)")
                body = log.read_text(encoding="utf-8")
                uneven = body.count("PUNT DE PARTIDA DIFERENT")
                stuck = body.count("la persistència encara escrivia")
                if uneven or stuck:
                    print(f"    ⚠ {uneven} execucions amb un punt de partida diferent"
                          + (f" · {stuck} amb la persistència penjada" if stuck else "")
                          + " — aquests números no es poden comparar")
                res = read_result(body)
                all_checks[(name, scen)] = res["checks"]
                failed = {k: v for k, v in res["checks"].items() if v[0]}
                rows.append({"setting": name, "scenario": scen,
                             **{k: v for k, v in knobs.items()},
                             "uneven_starts": uneven,
                             "persistence_stuck": stuck,
                             "items_before": before.get("items", -1),
                             "items_after": after.get("items", -1),
                             "records": after.get("records", 0),
                             "records_with_item_id": after.get("records_with_item_id", 0),
                             "guards_total": res["guards"],
                             "ungraded_runs": res["ungraded"],
                             "guards_per_run": round(res["guards"] / max(1, args.repeat), 1),
                             "checks": len(res["checks"]),
                             "checks_failing": len(failed),
                             "worst": max((f"{v[0]}/{v[1]} {k}" for k, v in failed.items()),
                                          default="")})
                print(f"    guard {res['guards']}× · {len(failed)} de {len(res['checks'])} "
                      f"comprovacions fallen alguna vegada")
    finally:
        # Leave nothing running: the instance carries the last setting's
        # sampling in its environment and would go on serving it.
        sh([str(REPO / "scripts" / "flowed-web.sh"), "--stop", "--port", str(args.port)],
           out_root / "99-stop.log", timeout=120)
        print("\nl'app de proves aturada")

    if rows:
        cols = sorted({k for r in rows for k in r})
        head = ["setting", "scenario", "guards_per_run", "guards_total", "ungraded_runs",
                "checks_failing", "checks", "uneven_starts", "persistence_stuck",
                "items_before", "items_after",
                "records", "records_with_item_id", "worst"]
        cols = head + [c for c in cols if c not in head]
        with open(out_root / "summary.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"\n=== resum ===")
        w = max(12, max(len(r["setting"]) for r in rows) + 2)
        print(f"  {'setting':<{w}}{'escenari':<11}{'guard/exec':>11}{'falles':>8}"
              f"{'cua':>12}{'regs':>7}{'item_id':>9}{'sense nota':>12}{'desigual':>10}")
        for r in rows:
            cua = f"{r['items_before']}→{r['items_after']}"
            flag = " ⚠" if r["items_after"] < r["items_before"] else ""
            odd = r.get("uneven_starts", 0) + r.get("persistence_stuck", 0)
            print(f"  {r['setting']:<{w}}{r['scenario']:<11}{r['guards_per_run']:>11}"
                  f"{r['checks_failing']:>8}{cua + flag:>12}{r['records']:>7}"
                  f"{r['records_with_item_id']:>9}"
                  f"{(str(r['ungraded_runs']) + '/' + str(args.repeat)) if r['ungraded_runs'] else '·':>12}"
                  f"{(str(odd) + ' ⚠' if odd else '·'):>10}")

        # Side by side, one row per check: the only view that says whether a
        # setting made things better or merely different. A column of numbers
        # per setting, and the checks that never fail anywhere are dropped —
        # they are not what the decision turns on.
        settings_seen = [n for n, _ in dict.fromkeys(all_checks)]
        if settings_seen:
            labels = list(dict.fromkeys(l for c in all_checks.values() for l in c))
            interesting = [l for l in labels
                           if any(all_checks[k].get(l, (0, 0))[0] for k in all_checks)]
            if interesting:
                title = ("què canvia, comprovació per comprovació" if len(settings_seen) > 1
                         else "taxa de fallada per comprovació (falles/execucions)")
                print(f"\n=== {title} ===")
                head = "".join(f"{n[:11]:>13}" for n in settings_seen)
                print(f"  {'':<46}{head}")
                for l in interesting:
                    cells = ""
                    for n in settings_seen:
                        k = next((k for k in all_checks if k[0] == n), None)
                        f_, t_ = all_checks[k].get(l, (0, 0)) if k else (0, 0)
                        cells += f"{(f'{f_}/{t_}' if f_ else '·'):>13}"
                    print(f"  {l[:44]:<46}{cells}")
                print("\n  · = no falla mai en aquella configuració")
        print(f"\n  summary.csv a {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
