# Encàrrec E1 — Flash: tipus de resposta i generadors de m5

Branca: `flash-vocab`. Disseny: `docs/DISSENY-M5.md` §2.1 i §2.2 (llegir-lo). Parteix de Flash per a math (`docs/ENCARREC-FLASH-MATH.md`, commit `93f26c3`). Decisions tancades.

## 1. Abast

Fitxers: `server/src/flash.ts`, `web/flash.js`, `web/style.css` (secció Flash), `hooks/curriculum.py` (només `flash_lists`), `server/test/flash.test.ts`, `tests/test_flash_math.py`. **No** toquis `curriculum/math-m5.md`, `scripts/mathbank.py` ni `curriculum/bank/` (els fa un altre agent en paral·lel). **No** creïs contingut de m5 nou a `curriculum/flash/` més enllà del necessari per als tests (fes servir directoris temporals als tests).

## 2. Tipus de resposta

Cada paraula de math que envia el servidor porta, a més de `id`, `prompt`, `target`:

- `answer_kind`: `"number"` (per defecte) | `"fraction"` | `"unit"` | `"choice"`.
- `unit` (si `unit`): text curt, p. ex. `"m"`, `"cm²"`, `"min"`.
- `options` (si `choice`): llista de textos.
- `form` (si `fraction`): `"value"` (per defecte, accepta equivalents) | `"simplest"` (cal la irreductible).

Client (`FlashCore`, pur i testat):

- `number`: com ara (coma/punt, espais).
- `fraction`: parser racional propi (enters, `a/b`, mixtos `1 1/2`, decimals amb coma/punt). `value` ⇒ igualtat de valor; `simplest` ⇒ mateix valor **i** fracció irreductible (o enter si el valor és enter). Denominador 0 ⇒ resposta no vàlida (compta com a error).
- `unit`: l'alumne escriu només el número; la unitat es mostra **fora** de la caixa, a la dreta. Si escriu el número amb la unitat enganxada (`3500 m`), es treu la unitat i es compara el número.
- `choice`: en lloc de caixa de text, **botons** (un per opció) i tecles `1..n`. Error ⇒ el botó triat queda desactivat i marcat; es revela la resposta quan només en queda una d'activa o al 3r error. Mateix flux de punts/temps/progrés que la resta.
- La pista del 2n error només s'aplica a `number`/`unit` (primera xifra + guions); a `fraction` mostra el denominador (`?/8`); a `choice` no hi ha pista (ja hi ha l'opció desactivada).

## 3. Generadors nous

Format a la llista:

```json
{ "id": "math-m5.flash.arrodonir", "level": "m5",
  "title": { "ca": "Arrodonir", "es": "Redondear", "en": "Rounding" },
  "generate": { "kind": "round", "count": 12 } }
```

- `generate.kind` absent o `"op"` ⇒ el generador actual (`op`, `a`, `b`) **sense canvis** (ids i Python iguals que ara).
- Qualsevol altre `kind` ⇒ `count` ítems (per defecte 12, màx. 50), ids `g1…gN`, **deterministes**: PRNG amb llavor = hash estable de l'id de la llista (p. ex. mulberry32 sobre FNV-1a). Mateixa llista ⇒ mateixes targetes sempre. Evitar duplicats de `prompt` dins la llista (reintentar).
- `params` opcional per ajustar rangs; els valors per defecte han de ser adequats a m5.
- **Python** (`flash_lists`): per a aquests `kind`, les paraules són `g1…gN` segons `count` (no cal replicar la generació). Test: ids Python == ids servidor per a tots els fitxers.

Generadors (taula de `docs/DISSENY-M5.md` §2.2). Resultats calculats en aritmètica exacta (enters o racionals; res de coma flotant per comparar). Decimals es mostren amb coma.

| kind | Targeta | Resposta | Notes |
|---|---|---|---|
| `round` | "Arrodoneix 4.735.218 a la centena" | number | Desena / centena / unitat de miler; nombres fins a 7 xifres; separador de milers amb punt **només a la pantalla**, l'alumne escriu sense punts (accepta-ho també amb punts si el nombre té > 4 xifres: treu-los). |
| `digit_value` | "Quin valor té el 7 a 4.735.218?" | number | La xifra triada apareix una sola vegada al nombre. |
| `compare_numbers` | "1.204.500 ? 1.240.050" | choice `["<", ">", "="]` | ~10 % iguals. |
| `frac_of` | "3/4 de 120" | number | Quantitat múltiple del denominador. |
| `frac_equiv` | "2/3 = ?/12" | number | |
| `frac_same_den` | "3/8 + 2/8" o "7/9 − 4/9" | fraction (`value`) | Resultat ≥ 0. |
| `frac_dec` | "25/100 = ?" → 0,25 · "0,7 = ?/10" → 7 | number | Denominadors 10, 100, 1000. |
| `dec_times_int` | "2,35 × 4" | number | Fins a 3 decimals × 2..9. |
| `percent_of` | "25 % de 80" | number | 10 %, 25 %, 50 %, 75 %; resultat enter. |
| `divisible` | "És 135 divisible per 3?" | choice `["Sí", "No"]` | Divisors 2, 3, 5, 10; ~50 % de cada. |
| `combined` | "4 + 3 × 5", "(4 + 3) × 5", "20 − 12 : 4" | number | Resultat enter ≥ 0; divisions exactes. |
| `unit_convert` | "3,5 km = ? m" | unit (`m`) | Longitud km…mm, massa kg…mg, capacitat kl…ml; factors 10/100/1000. |
| `complex_to_simple` | "2 m 45 cm = ? cm" | unit | També "1 kg 250 g = ? g". |
| `time_convert` | "3 h 15 min = ? min" · "2 min 30 s = ? s" | unit | |
| `area_simple` | "Rectangle de 8 cm × 5 cm. Àrea?" · "Triangle: base 10 cm, altura 6 cm. Àrea?" | unit (`cm²`) | Triangle amb b·h parell. |
| `mean` | "Mitjana de 4, 8, 6, 2" | number | 4-6 valors, mitjana entera. |
| `probability` | "Dau de 6 cares: probabilitat de treure un nombre parell?" | fraction (`value`) | Daus, monedes, bosses de boles de colors. |
| `equation` | "3·x + 5 = 20. x = ?" | number | Formes `a·x + b = c`, `a·x − b = c`, `x + b = c`; solució entera positiva. |
| `sequence` | "3, 7, 11, 15, ?" | number | Aritmètiques (+/−) i alguna geomètrica (×2, ×3). |

Llistes `items` (explícites) també poden portar `answer_kind`, `unit`, `options`, `form` per ítem. La validació actual (recalcular operacions simples) es manté per a `number`; per a `choice` cal que `answer[0]` sigui una de les `options`.

## 4. Tests

- TS: cada generador (determinisme amb la mateixa llavor, `count`, sense prompts duplicats, resultat correcte en una mostra recalculada amb aritmètica independent), cada tipus de resposta (equivalents, `simplest`, mixtos, unitat enganxada, choice), ids `g1…gN`, validació de `choice`.
- Python: `flash_lists` amb `kind` ≠ `op` ⇒ `g1…gN`; ids iguals als del servidor (el test existent que crida node ja ho cobreix si l'estens).
- jsdom (scratchpad): choice amb botons i tecles, opció desactivada, revelació; unitat a la dreta; fracció equivalent acceptada.
- Tots els tests: `server/test/*.test.ts`, `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests`. L'única fallada esperada és la de les 4 llistes buides d'anglès (`en-A1/06,07,10,11`), que no s'han de tocar.

## 5. Acceptació

- [ ] Els 19 generadors funcionen i són deterministes.
- [ ] Fraccions equivalents acceptades; `simplest` exigeix irreductible.
- [ ] Choice amb botons, tecles i desactivació; unitat visible fora de la caixa.
- [ ] Les llistes `op` actuals (taules) no canvien d'ids ni de comportament; language no canvia.
- [ ] Tests en verd (llevat de l'esperada).
