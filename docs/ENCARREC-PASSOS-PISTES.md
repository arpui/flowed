# Encàrrec E10 — Exercicis de passos: pistes quan hi ha un error

Branca: `flash-vocab`. Decisions tancades (Albert, 2026-10-17).

## 1. Problema

Als exercicis de passos (Go, `type: "steps"`), un nen no sap **què** ha d'escriure en cada pas, i quan s'equivoca el missatge només diu "❌ Aquesta línia no és el pas 1 de 3". Exemple: `2 × 20 × 5`, pas 1 "agrupa els dos nombres que fan un resultat rodó (escriu-ho amb parèntesis)"; s'esperava `(2 × 5) × 20` i el nen va escriure `2x20`.

## 2. Què es fa

**No** es mostra res de nou abans del primer intent (l'enunciat del pas queda com ara). L'ajuda arriba **davant l'error**:

| Intent fallat | Resposta |
|---|---|
| 1r | **Diagnòstic** (§3) + **motlle** del pas: `Escriu-ho així: ( ▢ × ▢ ) × ▢` |
| 2n | **Motlle amb un nombre posat**: `( 2 × ▢ ) × ▢` (el primer nombre de l'esperat) i el diagnòstic nou si n'hi ha |
| 3r | Es revela el pas (com ara: `❌ El pas 1 de 3 és: …`) i se segueix |

Per tant, `STEPS_V2_MAX_ATTEMPTS` passa de 2 a **3**. Revisa la política de puntuació del comentari de capçalera de `server/src/steps.ts` i mantén-la coherent (encert al 1r intent, amb pista, revelat).

## 3. Diagnòstic (comparar la línia amb el pas esperat)

Funció pura nova (p. ex. `diagnoseStepLine(step, line, item)` a `server/src/steps.ts`) que retorna **una** frase en català, la primera que s'apliqui, o res:

1. **Ha escrit només un nombre** i el pas esperat és una operació: "Aquí no cal el resultat: escriu l'**operació** del pas."
2. **El nombre és el resultat final** de l'exercici i el pas no és l'últim: "Has saltat passos: primer escriu …" (amb la meta del pas, `goal`, abreujada).
3. **La línia coincideix amb el pas següent** (`expect` o `accept` del pas k+1, comparant sense espais i amb `x`/`*`/`·` = `×`): "Això és el pas següent. Primer: …" (meta del pas actual).
4. **Falten els parèntesis**: l'esperat en té i la línia no, i els nombres són els mateixos: "Hi falten els **parèntesis**: marca quins nombres van junts."
5. **Mateixos nombres però agrupats diferent** (els de dins del parèntesi no coincideixen): "Has agrupat el 2 i el 20. Busca els dos nombres que junts fan un resultat **rodó** (10, 100…)." Adapta el final segons el `method` de l'ítem quan n'hi hagi (`grouping`: resultat rodó; `distributive`: "multiplica el de fora per **cada** nombre del parèntesi"; `common_factor`: "treu fora el nombre que es repeteix"; `long_division`, `partial_products`, `partial_sums`, `common_denominator`: frase curta a partir de la `goal`).
6. **Hi falta o hi sobra algun nombre**: "Fes servir els nombres del problema: 2, 20 i 5."
7. **Cap regla**: "Mira el motlle i omple'l amb els nombres del problema."

Normalitza abans de comparar: espais, `x`/`X`/`*`/`·` → `×`, `:`/`/` → `÷` quan l'esperat en té, `−` → `-`.

## 4. Motlle

Funció pura `stepShape(expect, reveal = 0)`: substitueix cada nombre de `expect` per `▢`, mantenint operadors i parèntesis; amb `reveal = 1` deixa visible el primer nombre. Si `expect` és un nombre sol (pas final), el motlle és l'operació del pas anterior: "Calcula: 10 × 20 = ▢".

## 5. On es mostra

`stepsV2Note` per a `move.kind === "retry"`: el missatge actual es substitueix per:

```
❌ {diagnòstic}

**Problema:** 2 × 20 × 5
**Pas 1 de 3** — {goal}.

Escriu-ho així: `( ▢ × ▢ ) × ▢`

Torna-ho a provar.
```

Al 2n error, igual però amb el motlle d'un nombre visible i el text "Et poso el primer nombre:". El cas `near` (🟡 a un dígit) es manté, però afegeix-hi el motlle.

## 6. Tests

- `server/test/steps-v2.test.ts`: cada regla del diagnòstic amb un exemple real del banc (agrupació, distributiva, divisió llarga), el motlle (normal, amb un nombre, pas final), el flux de 3 intents (diagnòstic+motlle → motlle amb nombre → revelat) i que un encert al 1r intent no mostra res de nou.
- Comprova amb tots els ítems `steps` del banc (m4, m5, m7) que `stepShape` i `diagnoseStepLine` no peten i que el motlle té tants `▢` com nombres té `expect`.
- Tots: `server/test/*.test.ts` (`node --experimental-strip-types`), `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests`. Única fallada esperada: la de les 4 llistes buides d'anglès del Flash.

## 7. Acceptació

- [ ] 1r error: diagnòstic + motlle. 2n: motlle amb un nombre. 3r: revelat.
- [ ] Res nou abans del primer intent.
- [ ] Funciona per a tots els mètodes de passos del banc.
- [ ] Tests en verd (llevat de l'esperada).
