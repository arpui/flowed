# WP1.1 — Notes per al coordinador (canvis ajornats + decisions)

Aquest fitxer recull el que el WP1.1 **no** ha pogut tocar directament (fitxers
congelats per l'agent de calibratge de prompts) i les decisions de disseny que
cal conèixer per rellegir el codi. Un cop l'agent de calibratge acabi, els
canvis pendent són de dues línies.

## Canvis pendent (fitxers congelats durant el WP1.1)

### 1. `server/src/tools.ts` — l'enum de nivells math ha d'acceptar `m7`

Línia 681:

```ts
const M_LEVELS = ["m1", "m2", "m3", "m4", "m5", "m6"];
```

→ afegir `"m7"` (i actualitzar el comentari de la 680: m1–m6 primària,
**m7 = 1r ESO** — extensió D3 del WP1.1; m8/m9 reservats per a 2n/3r ESO).
És l'única llista dura del servidor: `web/app.js` (M_ORDER),
`hooks/curriculum.py` (LEVELS) i `scripts/flowed-profile.py` (M_LEVELS) ja
inclouen m7. Sense aquest canvi, `fluent_set_profile` rebutja `target_level:
"m7"` i cap perfil nou d'1r ESO es pot crear des del xat.

### 2. `server/src/bank.ts` — la categoria d'error algebraic no arriba al feedback

Línea 267 (`mathFeedback`, ítems compute/compare):

```ts
const category = g.verdict === "near" ? "calculation" : String(g.item.error_class || "calculation");
```

→ preferir la categoria del **veredicte**, que per a ítems algebraics és la que
calcula `mathgrade.grade_algebraic` (sign / incomplete / procedure /
wrong_operation / calculation):

```ts
const category = g.verdict === "near" ? "calculation" : String(g.error_class || g.item.error_class || "calculation");
```

(És exactament el patró que la línia 227 ja fa servir per als ítems `steps`.)
Cal eixamplar també el comentari del camp `BankGrade.error_class` (línia ~68:
diu "steps items only"; ara els ítems algebraics també el porten). El costat
python ja ho emet: el veredicte `wrong` d'un ítem algebraic inclou **`category`
i `error_class`** amb el mateix valor.

## Decisions de disseny preses al WP1.1

### Escala D3 ampliada

- `m7` = **1r ESO** (competències A/B/C del draft `docs/competencies1eso.md`).
- `m8`/`m9` es deixen **reservats** per a 2n/3r ESO: hi ha lloc a les llistes
  però cap currículum ni banc encara.

### Notació algebraica acceptada per `mathgrade.parse_poly`

- Operadors: `+ - * · × ÷ /` (amb `/` només per constants: `6x ÷ 3` ✓, `x/y` ✗), parèntesis, potències `x^2`, `x²`, `x · x` (exp ≤ 6).
- Coeficients enters; juxtaposició `3x`, `4·x`, `3 x` ✓. **`x5` NO** (error de sintaxi, com a l'àlgebra real).
- Variables d'una lletra (`x y z a b …`); fraccions de coeficient només si són triviales (`6x ÷ 3` → `2x`).
- Forma canònica = diccionari expandida {monomi → coeficient}; dues expressions són equivalents **si i només si** les formes canòniques coincideixen.

### Mapa de categories (taxonomy de 12, `db_schema.ERROR_CATEGORIES`)

| Cas del veredicte | Categoria |
|---|---|
| un sol coeficient difereix i és un rellisc d'un dígit (`_near_slip`) | veredicte **near** (7/10), sense categoria |
| coeficients oposats (`-2x + 8` vs `-2x - 8`) | `sign` |
| falta un terme exactament (l'enunciat en tenia un de més) | `incomplete` |
| terme extra, o diverses diferències no explicables | `procedure` |
| l'aprenent ha tornat a escriure l'enunciat **literal** (`3(x+4)` com a resposta) | `procedure` (guard de còpia literal, comparat sense espais) |
| un sol coeficient difereix, no és signe ni near (`3(x+4)` → `3x + 4`) | `wrong_operation` |

**Limitació coneguda (documentada al docstring de mathgrade):** l'equivalència
accepta qualsevol escritura equivalent, fins i tot sense simplificar i
desordenada (`2x + 5 + 3x` passa contra `5x + 5`). Només la còpia literal de
l'enunciat és atrapada. Per al nivell m7 (no aïllem variables, transformació
d'expressions) això és acceptable; si es volgués obligar la forma factoritzada,
caldria un check de "forma esperada" a nivell d'ítem, no de normalitzador.

### Famílies del banc m7 (generador `scripts/mathbank.py`, seed 42)

Totes validades amb `mathgrade` (numèric **i** algebraic) i amb
autoverificació al generador (`parse_poly(problem) ≡ parse_poly(answer)`).

| Família | Tipus | Competència | Ítems |
|---|---|---|---|
| `props_grouping_numeric` | steps | m7.props_grouping | 12 (.001–.012) |
| `props_distributive_numeric` | steps | m7.props_distributive | 12 |
| `props_factor_numeric` | steps | m7.props_factor | 12 |
| `syntax_grouping_letters` | compute | m7.syntax_letters | 12 |
| `value_numeric` | compute | m7.value_numeric | 12 |
| `distributive_letters` | compute | m7.distributive_letters | 12 (inclou factor negatiu −2·(x+4) → −2x−8) |
| `factor_letters` | compute | m7.factor_letters | 12 (4 nivells: lletra, lletra+número, número ocult, x²) |

Els fitxers `steps/` viuen a `curriculum/bank/math-m7/steps/<cid>__steps.json`
i queden fora del glob `bank/*/*.json` de TheWholeBank (un sol nivell), com els
d'm4.

### Checkpoints amb `Compute:` / `Steps:` (`hooks/curriculum.py`)

- `CLOSED_TYPES` ara inclou `Compute` i `Steps`.
- `_grade_math_check`: alternatives separades per " / " (les fraccions com
  `5/6` no es trenquen); numèric via `grade_single`, algebraic via
  `grade_algebraic(..., problem=prompt)` — el guard de còpia literal també val
  als checkpoints.
- `_grade_steps_check`: la resposta esperada es parteix per " ; "; cada pas
  esperat s'ha de trobar en ordre entre les línies de l'aprenent
  (`bank._grade_step_line`).
- Els ítems de banc math (tenen `problem`, no `sentence`) ja són candidats al
  level test (`_bank_checkpoint_items`); el test end-to-end d'm4 puja 12/12 i
  certifica.

## Què queda per tancar la Fase 1

*(Tancat el 2026-10-06 per la fase WP1.1-live — vegeu `docs/DISSENY-MATEMATIQUES.md`, «Tancament de Fase 1».)*

1. Aplicar els dos canvis de dalt (tools.ts + bank.ts) — **fet** (`b88c3f2`).
2. **e2e en viu d'm7** — **fet**: perfil `test-m7:4201` + escenari `algebra` a `scripts/flowed-e2e.py` (RC=0; forma equivalent 10/10, categoria `sign` en viu, còpia literal `procedure`, steps v2 d'm7, prova de nivell Compute:/Steps: 12/12 «pass»). L'e2e va destapar un bug de producte (avís d'encallament de nota en torns servits només pel banc) — arreglat a `agent.ts` i fixat a `server/test/lesson-note.test.ts`.
3. Decidir si el draft `docs/AlgebraNumericaBasica.md` creua cap a més competències m7 (aritmètica bàsica amb suport del banc) — el pilot actual cobreix només els blocs A/B/C de `competencies1eso.md`. **OBERT — decisió de producte de l'Albert.**
4. Quan el pilot s'obri a alumnes de veritat: revisar els `why` dels ítems steps (són plantilles; el to podria calibrar-se amb l'agent de prompts). **OBERT — decisió de producte.**
