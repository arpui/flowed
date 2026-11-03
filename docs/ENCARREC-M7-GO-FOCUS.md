# Encàrrec G-M7 — Go de m7: competències actives i adormides, i quatre blocs nous

Branca: `flash-vocab`. Decisions tancades (Albert, 2026-11-03).

## 1. Què es vol

Al **Go de m7** han de sortir **només** les competències que l'Albert activa. La resta queden **adormides**: no surten al Go, però no s'esborren ni perden el progrés, i es poden despertar més endavant canviant una sola línia.

Ara mateix les actives són quatre blocs, i de cadascun cal que hi hagi **exercicis de debò** al banc:

1. **Operacions combinades llargues** (parèntesis, jerarquia, distributiva, associativa).
2. **Potències** (totes les propietats).
3. **Divisibilitat** (divisors, múltiples, criteris, primers).
4. **Descomposició factorial, MCD i mcm** (amb problemes de rajoles).

## 2. Mecanisme: `go_active`

- Al front matter del fitxer de nivell (`curriculum/math-m7.md`), una clau nova opcional:
  `go_active: m7.props_grouping, m7.props_distributive, m7.integers, m7.powers_roots, m7.powers_base, m7.divisors_multiples, m7.divisibility_rules, m7.primes, m7.prime_factorization, m7.factor_gcd_lcm`
- **Sense la clau, tot com ara** (tots els altres nivells i domini language no canvien).
- Amb la clau, a `hooks/curriculum.py`:
  - `active_competences` (les noves d'avui) i `review_pool` (les de repàs) només donen competències de `go_active`. Respecta `Requires:` com ara, però un requisit adormit no bloqueja (compta com a fet).
  - Les adormides surten a la ruta / Stats amb l'estat "💤 adormida" (en gris), amb el seu progrés intacte.
  - El percentatge del nivell, el `ready_share` i el test de nivell **no canvien** de regla (les adormides continuen comptant): el nivell no es pot aprovar sense despertar-les. Això és volgut.
- Un id de `go_active` que no existeix al fitxer és un error de validació (test), no se salta en silenci.
- Documenta-ho en una línia a la capçalera de `math-m7.md` i a `docs/DISSENY-MATEMATIQUES.md` (secció del format).

## 3. Les competències (`curriculum/math-m7.md`)

Fes servir el format existent (`### id — Nom [core]`, `Can do`, `Depth`, `Weight`, `Requires`, `Forms`, `Tags`, `Signals`, `Bank`, `Check:`). **No canviïs cap id existent** (es perdria el progrés dels alumnes). Les noves van a la secció que toca.

### 3.1 Operacions combinades llargues — ja existeixen, s'activen i s'amplien
- `m7.props_grouping` (associativa i commutativa) i `m7.props_distributive` (distributiva), tal com són (bancs `steps`).
- `m7.integers`: amplia el generador `integers_combined` (`scripts/mathbank.py`) amb una variant **llarga**: 5–8 operacions, parèntesis niats (`[ ]` o parèntesis dins de parèntesis), potències i signes, p. ex. `18 - [3 · (4 - 7) + 2^3] : 5` → valor. Els ítems existents es mantenen. Afegeix-ne prou per tenir com a mínim 24 ítems vàlids en total, la meitat llargs.

### 3.2 Potències
- `m7.powers_roots` (es manté l'id; es reescriu el contingut): **mateixa base i exponents especials**
  - producte de la mateixa base (`2^3 · 2^4 = 2^7`), quocient de la mateixa base (`3^8 : 3^5 = 3^3`), potència d'una potència (`(5^2)^3 = 5^6`), exponent 1 i 0 (`7^1 = 7`, `9^0 = 1`, `a^5 : a^5 = a^0 = 1`);
  - exercicis "expressa com una sola potència" (resposta `2^7`) i, després, "calcula'n el valor" (resposta `128`). Pot ser un ítem `steps`: `2^3 · 2^4 : 2^2 → 2^5 ; 32`.
- `m7.powers_base` (nova): **producte, quocient i canvi de base**
  - potència d'un producte (`(2 · 5)^3 = 2^3 · 5^3`), d'un quocient o fracció (`(6 : 3)^2`, `(2/3)^3 = 8/27`);
  - **canviar la base** per poder ajuntar: `4^3 · 2^5 = 2^6 · 2^5 = 2^11`; `9^2 · 27 = 3^4 · 3^3 = 3^7`; `8^2 : 4^2 = 2^6 : 2^4 = 2^2`;
  - expressa com una sola potència i, al final, calcula el valor (mateix patró `steps`).
- Generadors nous o ampliats a `scripts/mathbank.py` (`powers_props` existeix); com a mínim 24 ítems per competència.

### 3.3 Divisibilitat (tres competències noves, secció "Nombres enters i divisibilitat")
- `m7.divisors_multiples` — **divisors i múltiples**
  - "Escriu tots els divisors de 46" → `1, 2, 23, 46` (notació `D(46) = {1, 2, 23, 46}` a l'explicació);
  - "Escriu els cinc primers múltiples de 7" → `7, 14, 21, 28, 35`;
  - problemes en lletres: "Quants múltiples de 9 hi ha entre 1 i 200?" → `22`; "Quin és el múltiple de 12 més proper a 100?"; "És 84 múltiple de 6? I divisor de 252?" (choose).
- `m7.divisibility_rules` — **criteris del 2 a l'11** (2, 3, 4, 5, 6, 8, 9, 10, 11)
  - "Per quins d'aquests nombres és divisible 660: 2, 3, 4, 5, 6, 8, 9, 10, 11?" → `2, 3, 4, 5, 6, 10, 11` (és la fila d'una taula; la taula interactiva vindrà en un encàrrec posterior, vegeu §6);
  - "Quina xifra pot anar a 4_2 perquè sigui divisible per 3?" (totes les solucions);
  - `why` amb el criteri aplicat (suma de xifres, dues últimes xifres, alternança per a l'11…).
- `m7.primes` — **primers i compostos, garbell d'Eratòstenes**
  - "Què és un nombre primer?" / "És 91 primer o compost?" (choose, amb el perquè: 91 = 7 · 13);
  - "Escriu els nombres primers entre 30 i 50" → `31, 37, 41, 43, 47` (el garbell, explicat al `why`);
  - problemes combinats: "Quin és el nombre de dues xifres més gran divisible per 2 i per 3?" → `96`; "El nombre més petit de tres xifres que és múltiple de 2, 3 i 5" → `120`.

### 3.4 Descomposició factorial, MCD i mcm
- `m7.prime_factorization` (nova) — **descompondre**
  - "Descompon 360 en factors primers" → `2^3 · 3^2 · 5` (accepta `2³·3²·5`, ordre lliure, `x` o `·`);
  - "la taula de descomposició": un ítem `steps` amb la columna de divisions `360 | 2 ; 180 | 2 ; 90 | 2 ; 45 | 3 ; 15 | 3 ; 5 | 5 ; 1` o, si el format `steps` no ho permet llegible, la seqüència de quocients `180 ; 90 ; 45 ; 15 ; 5 ; 1` i al final la potència;
  - "Quin nombre és `2^2 · 3 · 7`?" → `84` (construir el nombre a partir dels primers).
- `m7.factor_gcd_lcm` (es manté l'id; s'amplia): MCD i mcm per descomposició (comuns amb el menor exponent / tots amb el major) i **problemes de rajoles**: "Un terra fa 360 cm × 240 cm. Quina és la rajola quadrada més gran que el cobreix sense tallar-ne cap?" → `120` (cm), "I quantes en calen?" → `6`; i problemes de coincidir (mcm). Com a mínim 24 ítems.

## 4. Respostes en llista

Divisors, múltiples, primers i criteris tenen respostes amb **diversos nombres**. Comprova com les corregeix avui `hooks/mathgrade.py` (i el corrector del servidor del Go, `server/src/bank.ts`). Si no hi ha correcció de llistes:
- afegeix-la: **com a conjunt** (l'ordre no importa, ni els separadors `,` `;` espais, ni les claus `{ }`; un nombre repetit no compta dues vegades);
- feedback útil: quins en falten i quins sobren (p. ex. "et falta el 23"), i puntuació parcial proporcional si el format de feedback ho permet; si no, correcte només si el conjunt és igual.
- La factorització (`2^3 · 3^2 · 5`) es corregeix comparant els factors i exponents (ordre lliure); mira si ja existeix (Flash té el tipus `factorization`) i reaprofita-ho.

## 5. Abast

`curriculum/math-m7.md`, `hooks/curriculum.py`, `hooks/mathgrade.py` i `server/src/bank.ts` (només si cal per a llistes o factorització), `scripts/mathbank.py`, els bancs generats a `curriculum/bank/math-m7/` (amb el mateix procediment de generació i validació que els existents: `status: validated`, `source: mathbank · data · seed`), `docs/DISSENY-MATEMATIQUES.md` (una línia), i tests. **No toquis** `web/` ni els altres nivells.

## 6. Fora d'aquest encàrrec (següent)

La **taula interactiva** de criteris (files = nombres, columnes 2–11, marcar caselles) i el **garbell interactiu** (graella 1–100 on es marquen els primers) són tipus de Go nous amb interfície pròpia: un segon encàrrec quan aquest estigui fet. Aquí es fan amb respostes en llista.

## 7. Tests

- `go_active`: amb la clau, `active_competences` i `review_pool` només en donen d'actives; una adormida mai surt; sense la clau, res canvia (els tests existents en verd); id inexistent ⇒ error; un requisit adormit no bloqueja.
- Cada competència activa té ≥ 24 ítems vàlids al banc, i tots passen el validador (`validate_item`) i el corrector amb la seva pròpia resposta.
- Correcció de llistes i factoritzacions (ordre, separadors, falten/sobren).
- Una prova del Go real (servidor + perfil m7 temporal): 20 exercicis seguits del Go, tots de competències actives (mira el log o `/api/math/session-state`).
- Tots els tests (`bun test` i `bun x tsc --noEmit` a `server/`, `python3 -m unittest discover -s tests`) en verd.

## 8. Acceptació

- [ ] Al Go de m7 només surten les 10 competències de `go_active`; les altres, adormides i visibles com a tals.
- [ ] Exercicis de cada bloc (operacions llargues, potències, divisibilitat, factorització/MCD/mcm), amb la correcció i el perquè.
- [ ] Despertar una competència = afegir-la a `go_active`.
- [ ] Tests en verd.
