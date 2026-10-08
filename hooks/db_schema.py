"""
Fluent DB schema versioning — shared helpers for hooks and scripts.

Every learning database carries an optional top-level ``_schema_version``
integer. Documents without the field are treated as version 1 (the baseline
schema that predates versioning), so existing installs keep working untouched.

``MIGRATIONS`` maps a source version to a function that upgrades the whole set
of databases (a dict of filename -> document) from that version to
``source + 1``, in place. Register one entry per version bump; the migration
tool applies them sequentially until ``CURRENT_SCHEMA_VERSION`` is reached.
"""
from __future__ import annotations

from typing import Callable, Optional

CURRENT_SCHEMA_VERSION = 1

# --- Error categories (SINGLE SOURCE OF TRUTH) -------------------------------
# Every correction the tutor writes is tagged with one of these. The same list
# must appear in three places; tests/test_error_categories.py enforces it:
#   1. here (used by persist-session.parse_error_patterns to build pattern ids)
#   2. server/src/tools.ts  -> DEEP_RUBRIC (what the deep evaluator may emit)
#   3. skills/math-feedback-formatter/SKILL.md and
#      references/feedback-template.md (what the tutor is told to use)
# Anything unrecognized silently became the default category, which is how
# mistakes-db used to collapse into a single category.
#
# Math taxonomy (docs/DISSENY-MATEMATIQUES.md §4.4), replacing the 15 language
# categories of the FlowEd original — those now live in LEGACY_ERROR_CATEGORIES.
ERROR_CATEGORIES = (
    "calculation",          # lliscada de càlcul: mètode bé, número malament
    "sign",                 # signe +/− (o >/<) canviat o perdut
    "place_value",          # valor posicional: unitats / desenes / centenes
    "carrying",             # transport / arrestament oblidat o mal fet
    "order_of_operations",  # passos fets en un ordre de precedència erroni
    "wrong_operation",      # tria l'operació equivocada amb els números bons
    "procedure",            # seqüència de passos incorrecta per a la tasca
    "facts",                # fet bàsic no recordat: taules, dobles, meitats
    "simplification",       # fracció no simplificada / forma final incorrecta
    "unit",                 # unitat absent o errònia
    "misread",              # llegeix malament l'enunciat
    "incomplete",           # deixa la feina a mitges
)

# Surface terms a tutor or learner would actually write — Catalan, Spanish and
# English — -> canonical id. Normalization lowercases and turns hyphens and
# spaces into underscores but KEEPS accents, so accented spellings are listed
# exactly as written. (Same pattern as the old grammar aliases: the tutor names
# the slip in everyday words, "(transport — …)", and every unmapped label used
# to collapse into one category.)
ERROR_CATEGORY_ALIASES = {
    # calculation
    "calculo": "calculation",
    "cálculo": "calculation",
    "càlcul": "calculation",
    "compta": "calculation",
    "comptar": "calculation",
    "calcular": "calculation",
    "arithmetic": "calculation",
    "aritmética": "calculation",
    "aritmètica": "calculation",
    # sign
    "signe": "sign",
    "signo": "sign",
    "minus": "sign",
    "plus": "sign",
    "negatiu": "sign",
    "positiu": "sign",
    # place_value
    "valor_posicional": "place_value",
    "posicio": "place_value",
    "posició": "place_value",
    "posicion": "place_value",
    "unitats_desenes_centenes": "place_value",
    "ones_tens_hundreds": "place_value",
    # carrying
    "carry": "carrying",
    "carries": "carrying",
    "carried": "carrying",
    "carry_over": "carrying",
    "transport": "carrying",
    "transportar": "carrying",
    "arrestando": "carrying",
    "arrestament": "carrying",
    "llevadas": "carrying",
    # order_of_operations
    "ordre": "order_of_operations",
    "orden": "order_of_operations",
    "ordre_d'operacions": "order_of_operations",
    "orden_de_operaciones": "order_of_operations",
    "orden_operaciones": "order_of_operations",
    "operation_order": "order_of_operations",
    "operator_precedence": "order_of_operations",
    "precedence": "order_of_operations",
    "bodmas": "order_of_operations",
    "pemdas": "order_of_operations",
    # wrong_operation
    "operacio_equivocada": "wrong_operation",
    "operació_equivocada": "wrong_operation",
    "operacion_equivocada": "wrong_operation",
    "operación_equivocada": "wrong_operation",
    "wrong_op": "wrong_operation",
    "operation_choice": "wrong_operation",
    # procedure
    "procediment": "procedure",
    "procedimiento": "procedure",
    "sequencia": "procedure",
    "seqüència": "procedure",
    "method": "procedure",
    "mètode": "procedure",
    # facts
    "fet_basic": "facts",
    "fet_bàsic": "facts",
    "basic_fact": "facts",
    "hecho_basico": "facts",
    "hecho_básico": "facts",
    "taula": "facts",
    "taules": "facts",
    "tabla": "facts",
    "tablas": "facts",
    "times_table": "facts",
    "times_tables": "facts",
    "multiplicar": "facts",
    "memorization": "facts",
    # simplification
    "simplificacio": "simplification",
    "simplificació": "simplification",
    "simplificación": "simplification",
    "simplify": "simplification",
    "simplified": "simplification",
    "unsimplified": "simplification",
    "not_simplified": "simplification",
    "lowest_terms": "simplification",
    # unit
    "unitat": "unit",
    "units": "unit",
    "unidad": "unit",
    "unidades": "unit",
    "measurement": "unit",
    # misread
    "lectura": "misread",
    "enunciat": "misread",
    "enunciado": "misread",
    "reading": "misread",
    "misreading": "misread",
    "comprehension": "misread",
    "problem_statement": "misread",
    # incomplete
    "incomplet": "incomplete",
    "incompleto": "incomplete",
    "partial": "incomplete",
    "unfinished": "incomplete",
    "half_done": "incomplete",
}

# Accepted but deprecated: the 15 language categories of the FlowEd original.
# The fork has no migrated language mistakes-db data, but the language
# curriculum files it still ships (curriculum/en-A1.md, en-A2.md — replaced by
# the math curriculum in WP1.1) use these names as `#tags`, and curriculum.py
# validates tags against ERROR_CATEGORIES ∪ this tuple. Keeping them here (not
# in ERROR_CATEGORIES) means: stored language-era ids keep their shape instead
# of collapsing into the default, while the tutor-facing surfaces (tools.ts,
# skills, feedback template) only ever offer the 12 math classes. The five
# even-older FlowEd ids ("writing", "pronunciation", "reflexive", "subject",
# "gerund") are dropped outright — nothing in the fork references them.
# Drop this tuple together with the language content (C10).
LEGACY_ERROR_CATEGORIES = (
    "grammar", "word_order", "tenses", "agreement", "articles",
    "prepositions", "pronouns", "vocabulary", "spelling", "punctuation",
    "capitalization", "formal_informal", "register", "missing", "comprehension",
)

# Fallback for unrecognized labels. "calculation" because a one-off arithmetic
# slip is by far the most common unknown in math practice; "procedure" (the
# other plausible fallback) over-claims a structural weakness when most
# unknowns are single slips, and would pollute the error profile.
DEFAULT_ERROR_CATEGORY = "calculation"

# --- Taxonomy per domain (WP6, 2026-10-08) -------------------------------------
# Skills, error categories and their fallbacks belong to the DOMAIN of the
# profile, not to the core: a language learner's grammar slip must never land
# on "calculation", nor her vocabulary on the math skill "facts". The math
# lists above are the math domain's; these are the language domain's, restored
# from the language product (FlowEd 0.5) where they were never mixed. The TS
# mirror is server/src/taxonomy.ts (tests/test_taxonomy.py keeps both, and the
# manifest, in sync). `domain` is the manifest name (hooks/domain.py); anything
# that is not "language" is math, which is also what every old call site meant.
LANGUAGE_ERROR_CATEGORIES = LEGACY_ERROR_CATEGORIES  # the 15 (see above)
# Ids of the oldest FlowEd; 0.5 still accepted them verbatim (stored data).
LANGUAGE_OLD_CATEGORIES = ("writing", "pronunciation", "reflexive", "subject", "gerund")
LANGUAGE_ERROR_CATEGORY_ALIASES = {
    "wordorder": "word_order",
    "preposition": "prepositions",
    "pronoun": "pronouns",
    "tense": "tenses",
    "informal_formal": "formal_informal",
    "reading": "comprehension",
    "inference": "comprehension",
    "detail": "comprehension",
    "past": "tenses",
    "present": "tenses",
    "future": "tenses",
    "past_tense": "tenses",
    "present_tense": "tenses",
    "verb_tense": "tenses",
    "verb": "tenses",
    "conjugation": "tenses",
    "article": "articles",
    "capitalisation": "capitalization",
    "caps": "capitalization",
    "word_choice": "vocabulary",
    "wording": "vocabulary",
    "plural": "agreement",
    "singular": "agreement",
    "number": "agreement",
    "subject_verb": "agreement",
    "formality": "formal_informal",
    "typo": "spelling",
}
DEFAULT_LANGUAGE_ERROR_CATEGORY = "grammar"


def is_language(domain) -> bool:
    return str(domain or "").strip().lower() == "language"


def error_categories(domain="math") -> tuple:
    """The error categories the tutor may emit in this domain."""
    return LANGUAGE_ERROR_CATEGORIES if is_language(domain) else ERROR_CATEGORIES


def default_error_category(domain="math") -> str:
    return DEFAULT_LANGUAGE_ERROR_CATEGORY if is_language(domain) else DEFAULT_ERROR_CATEGORY


def normalize_error_category(raw, domain="math") -> str:
    """Map a category label written by the tutor to a canonical one.

    Accepts hyphens and spaces ("word-order", "word order") and known aliases.
    Unknown labels fall back to the DOMAIN's default (math: "calculation";
    language: "grammar"). `domain` defaults to math, as every call site did
    before the taxonomy became per-domain.
    """
    cat = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if is_language(domain):
        cat = LANGUAGE_ERROR_CATEGORY_ALIASES.get(cat, cat)
        if cat in LANGUAGE_ERROR_CATEGORIES or cat in LANGUAGE_OLD_CATEGORIES:
            return cat
        return DEFAULT_LANGUAGE_ERROR_CATEGORY
    cat = ERROR_CATEGORY_ALIASES.get(cat, cat)
    if cat in ERROR_CATEGORIES or cat in LEGACY_ERROR_CATEGORIES:
        return cat
    return DEFAULT_ERROR_CATEGORY


# --- Skill keys (C7) ---------------------------------------------------------
# The five math practices. The record's `skill` field (math_record_answer, the
# server's derived and bank records) is persisted into .records/ and read back
# by persist-session/accumulate-session, and it keys skill_scores /
# skills_practiced downstream — so it must carry math keys. The TS mirror is
# SKILL_KEYS in server/src/tools.ts (tests/test_deep_rubric.py keeps them in
# sync).
SKILL_KEYS = ("computation", "steps", "problems", "reasoning", "facts")

# Read-old/write-new (WP3.1, same pattern as FLUENT_*→FLOWED_* in
# scripts/lib-paths.sh): records written before the math fork carry the
# language-era skill names, and update-db re-applies old records on every
# persistence (restore T0, re-apply). Mapping them here means a stored
# "writing" record lands on "reasoning" instead of inventing a phantom skill
# in progress-db and mastery-db.
LEGACY_SKILL_KEYS = {
    "writing": "reasoning",
    "speaking": "reasoning",
    "listening": "facts",
    "reading": "problems",
    "vocabulary": "facts",
    "grammar": "computation",
}

# Surface names for the math practices, in the languages a Catalan classroom
# mixes — a feedback heading ("## Repte de Raonament") or a chatty model's
# skill argument. Accents are kept by the normalization, so they are listed as
# written.
SKILL_SURFACE_ALIASES = {
    "raonament": "reasoning",
    "razonamiento": "reasoning",
    "reasoning": "reasoning",
    "problema": "problems",
    "problemes": "problems",
    "problemas": "problems",
    "problem": "problems",
    "passos": "steps",
    "pasos": "steps",
    "step": "steps",
    "fet": "facts",
    "fets": "facts",
    "hecho": "facts",
    "hechos": "facts",
    "calcul": "computation",
    "càlcul": "computation",
    "calculo": "computation",
    "cálculo": "computation",
}

DEFAULT_SKILL_KEY = "computation"

# The language domain's skills (FlowEd 0.5: writing | speaking | vocabulary |
# reading | grammar, plus listening for the panel). Surface names in the
# languages a Catalan classroom mixes, like the math ones above.
LANGUAGE_SKILL_KEYS = ("writing", "speaking", "vocabulary", "reading", "grammar", "listening")
LANGUAGE_SKILL_ALIASES = {
    "vocab": "vocabulary", "vocabulari": "vocabulary", "vocabulario": "vocabulary",
    "words": "vocabulary", "flashcards": "vocabulary", "facts": "vocabulary",
    "gramatica": "grammar", "gramàtica": "grammar", "gramática": "grammar",
    "escriptura": "writing", "escritura": "writing", "redaccio": "writing",
    "redacció": "writing", "spelling": "writing", "ortografia": "writing",
    "lectura": "reading", "comprehension": "reading",
    "parla": "speaking", "oral": "speaking", "conversa": "speaking",
    "conversation": "speaking", "pronunciation": "speaking",
    "escolta": "listening", "comprensio_oral": "listening",
    "comprensió_oral": "listening",
}
# A math key arriving in a language profile (a misrouted turn, old pollution):
# land it on the nearest language skill instead of inventing a math skill there.
MATH_TO_LANGUAGE_SKILL = {
    "computation": "grammar", "steps": "grammar", "problems": "reading",
    "reasoning": "writing", "facts": "vocabulary",
}
DEFAULT_LANGUAGE_SKILL_KEY = "writing"


def skill_keys(domain="math") -> tuple:
    """The skills a practice can be filed under in this domain."""
    return LANGUAGE_SKILL_KEYS if is_language(domain) else SKILL_KEYS


def default_skill_key(domain="math") -> str:
    return DEFAULT_LANGUAGE_SKILL_KEY if is_language(domain) else DEFAULT_SKILL_KEY


def normalize_skill_key(raw, domain="math") -> str:
    """Map a skill label to one of this domain's skill keys.

    Math: canonical names pass through; language-era names (LEGACY_SKILL_KEYS)
    and surface spellings (SKILL_SURFACE_ALIASES) are mapped; anything else
    falls back to DEFAULT_SKILL_KEY — mirrors normalizeSkillKey in tools.ts.
    Language: its own keys pass through, never onto the math ones.
    """
    s = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if is_language(domain):
        if s in LANGUAGE_SKILL_KEYS:
            return s
        if s in LANGUAGE_SKILL_ALIASES:
            return LANGUAGE_SKILL_ALIASES[s]
        return MATH_TO_LANGUAGE_SKILL.get(s, DEFAULT_LANGUAGE_SKILL_KEY)
    if s in SKILL_KEYS:
        return s
    if s in LEGACY_SKILL_KEYS:
        return LEGACY_SKILL_KEYS[s]
    return SKILL_SURFACE_ALIASES.get(s, DEFAULT_SKILL_KEY)


# --- Mastery decay ----------------------------------------------------------
# Skill mastery only ever went up: a learner who had not written a line in two
# months was still "4 stars at writing", and the tutor planned accordingly.
#
# It does NOT apply to spaced-repetition items: those already carry time in
# their due_date / interval, and decaying them too would count the same thing
# twice. It applies to mastery-db skills, which move only with practice.
#
# Shape: nothing for `grace_days`, then one level per `step_days` idle, never
# below `floor`. With the defaults: a level-5 skill is still 5 after a month,
# 4 at 35 days, 3 at 56, 2 at 77, 1 at 98 — slow enough that a holiday does not
# erase a year, fast enough that "mastered" means something.
MASTERY_DECAY = {
    "grace_days": 14,
    "step_days": 21,
    "floor": 1,
}


def decay_config(preferences=None) -> dict:
    """Per-learner override: preferences.mastery_decay in learner-profile.json.

    `{"step_days": 0}` switches decay off for that learner.
    """
    cfg = dict(MASTERY_DECAY)
    override = (preferences or {}).get("mastery_decay")
    if isinstance(override, dict):
        for key in cfg:
            value = override.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                cfg[key] = int(value)
    return cfg


def decayed_mastery(earned_level, days_idle, cfg=None) -> int:
    """The level an untouched skill is worth today.

    Pure and absolute — computed from the EARNED level and the idle days, never
    from the previous decayed value. That is what makes it safe to re-apply:
    update-db.py restores the pre-session state and replays the payload, so a
    decay that subtracted from itself would compound on every run.
    """
    cfg = cfg or MASTERY_DECAY
    try:
        level = int(earned_level)
    except (TypeError, ValueError):
        return 0
    step_days = int(cfg.get("step_days", 0) or 0)
    if step_days <= 0 or level <= 0:
        return max(0, level)
    idle = max(0, int(days_idle) - int(cfg.get("grace_days", 0)))
    steps = idle // step_days
    floor = int(cfg.get("floor", 0))
    return max(min(floor, level), level - steps)


DB_FILENAMES = [
    "learner-profile.json",
    "spaced-repetition.json",
    "mistakes-db.json",
    "progress-db.json",
    "mastery-db.json",
    "session-log.json",
]


def get_schema_version(doc: dict) -> int:
    """Return the document's schema version; missing/invalid means baseline 1."""
    v = doc.get("_schema_version", 1)
    return v if isinstance(v, int) and not isinstance(v, bool) else 1


def is_current(doc: dict) -> bool:
    return get_schema_version(doc) == CURRENT_SCHEMA_VERSION


def is_future(doc: dict) -> bool:
    return get_schema_version(doc) > CURRENT_SCHEMA_VERSION


MIGRATIONS: dict[int, Callable[[dict], None]] = {}


def min_version(docs: dict) -> Optional[int]:
    """Lowest schema version across the given documents, or None if empty."""
    if not docs:
        return None
    return min(get_schema_version(doc) for doc in docs.values())


def max_version(docs: dict) -> Optional[int]:
    """Highest schema version across the given documents, or None if empty."""
    if not docs:
        return None
    return max(get_schema_version(doc) for doc in docs.values())


def migrate_docs(docs: dict) -> tuple[int, int]:
    """Apply registered migrations in place until CURRENT_SCHEMA_VERSION.

    ``docs`` maps filename -> document. Raises LookupError if a migration step
    is missing for an intermediate version, ValueError if any document is from
    a future schema version. Returns the (from, to) version span applied.
    """
    start = min_version(docs)
    if start is None:
        return (CURRENT_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION)
    if max_version(docs) > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"database schema version {max_version(docs)} is newer than "
            f"supported {CURRENT_SCHEMA_VERSION}; upgrade Fluent first"
        )
    version = start
    while version < CURRENT_SCHEMA_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise LookupError(
                f"no migration registered for schema version {version} "
                f"(target {CURRENT_SCHEMA_VERSION})"
            )
        step(docs)
        version += 1
        for doc in docs.values():
            doc["_schema_version"] = version
    return (start, CURRENT_SCHEMA_VERSION)


def stamp_docs(docs: dict) -> None:
    """Set ``_schema_version`` to CURRENT_SCHEMA_VERSION on every document."""
    for doc in docs.values():
        doc["_schema_version"] = CURRENT_SCHEMA_VERSION
