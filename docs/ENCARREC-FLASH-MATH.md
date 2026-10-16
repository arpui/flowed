# Encàrrec — Flash per a math (taules i càlcul ràpid)

Branca: `flash-vocab`. Parteix de Flash v1 (`docs/ENCARREC-FLASH-v1.md`). El motor, el progrés (`flash-db.json`), les rondes, el temps per paraula, el tancament de llistes, l'avís diari i el requisit de nivell (`flash_share`) **es reutilitzen tal qual**. Aquí només s'hi afegeix el que math necessita.

## 1. Decisions preses (no reobrir)

| # | Decisió |
|---|---|
| 1 | Flash s'activa per a math al manifest. Primer contingut: nivell **m5** (taules de multiplicar i multiplicació de 2 xifres × 1 xifra). |
| 2 | Albert hi anirà afegint contingut ⇒ el format ha de ser fàcil d'escriure a mà. |
| 3 | Dos tipus de llista: **generada** (el servidor calcula les operacions i els resultats; cap resultat escrit a mà) i **explícita** (ítems escrits a mà). |
| 4 | Math no té direcció: sempre operació → resultat. |
| 5 | No hi ha `curriculum/math-m5.md` ⇒ per a m5 no hi ha requisit de nivell (`flash_progress` ja dona `met` sense fitxer de nivell / sense `flash_share`). No en creïs cap. |

## 2. Format de llistes de math

Carpeta: `curriculum/flash/math-m5/`. Mateixa idea que `en-A1`: un fitxer per llista, ordenats pel nom.

### 2.1 Llista generada

```json
{
  "id": "math-m5.flash.taula-7",
  "level": "m5",
  "title": { "ca": "Taula del 7", "es": "Tabla del 7", "en": "7 times table" },
  "generate": { "op": "×", "a": [7], "b": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] }
}
```

- `op`: `"+"`, `"−"`, `"×"`, `":"` (divisió exacta; descartar parells no exactes). Acceptar també `"x"`, `"*"`, `"-"`, `"/"` com a sinònims a l'entrada del fitxer; a la pantalla es mostra sempre `×`, `−`, `:`.
- `a`, `b`: llistes d'enters, o `{"from": 1, "to": 10}`. Es generen tots els parells `a × b` (producte cartesià), en ordre.
- Cada ítem generat: `id` = `"<a><opcurt><b>"` (p. ex. `"7x3"`, opcurt: `p`, `m`, `x`, `d`), `prompt` = `"7 × 3"`, `target` = `["21"]`.
- Resta: descartar resultats negatius.

### 2.2 Llista explícita

```json
{
  "id": "math-m5.flash.2x1-xifres",
  "level": "m5",
  "title": { "ca": "2 xifres × 1 xifra", "es": "2 cifras × 1 cifra", "en": "2-digit × 1-digit" },
  "items": [
    { "id": "23x4", "prompt": "23 × 4", "answer": ["92"] }
  ]
}
```

- Una llista té **o** `generate` **o** `items`, no tots dos (si en té tots dos o cap ⇒ es descarta, i el test de llistes ho detecta).
- **Validació de les explícites:** si el `prompt` és una operació simple `n op m` reconeixible, el carregador recalcula el resultat i, si no coincideix amb `answer[0]`, **descarta l'ítem** i el test ho marca (amb el fitxer i l'id). Així un error de tecleig no s'ensenya mai.

### 2.3 Contingut inicial (crear-lo)

- `01-taula-2.json` … `08-taula-9.json`: generades, `a = [n]`, `b = 1..10`.
- `09-2x1-xifres.json`: explícita, 12 ítems (2 xifres × 1 xifra, resultats ≤ 999, variats: amb i sense portar-ne).

## 3. Feina

### 3.1 Manifest

`config/domain.json`, domini `math`: `"flash": { "enabled": true, "dir": "curriculum/flash/math-*" }`. (Actualitzar `server/test/domain-shell.test.ts` si alguna comprovació suposava que math no té Flash.)

### 3.2 Servidor (`server/src/flash.ts`)

- `loadFlashLists`: entendre `generate` i `items` (§2), i retornar-los amb **la mateixa forma** que ara (`{id, level, title, words:[{id, target, native}]}`), més un camp `kind: "math"` a la llista i `prompt` a cada paraula. Per a math, `native` = `[prompt]` (així el client existent no peta) però el client de math farà servir `prompt`.
- Funcions pures exportades i testades: expansió de `generate`, càlcul i validació d'una operació simple.
- `curriculum.py` `flash_lists()` ha de comptar **les mateixes paraules** que el servidor (ids generats inclosos). Implementa l'expansió de `generate` també a Python (mateixes regles, mateixos ids) i un test que compari ids Python vs TS per a tots els fitxers de `curriculum/flash/math-*`.

### 3.3 Client (`web/flash.js`)

Quan la llista és `kind: "math"`:

- Sense selector de direcció al menú (amagat); la targeta mostra `prompt` i espera el resultat. Etiqueta sobre la targeta: "Calcula".
- Input amb `inputmode="numeric"` (teclat numèric al mòbil) i `aria-label="Resultat"`.
- Correcció numèrica: treure espais, acceptar coma o punt decimal, comparar com a número (`72`, `72,0` i `72.0` són iguals). Res d'articles ni accents.
- Pista (2n error): la mateixa idea (primera xifra + guions per a la resta).
- La traça al xat i el resum diuen "operacions" en lloc de "paraules" quan la llista és de math.

### 3.4 Tests

- TS (`server/test/flash.test.ts`): expansió de `generate` (taula del 7 → 10 ítems, ids i resultats), divisió no exacta descartada, resta negativa descartada, ítem explícit amb resultat erroni descartat i reportat, totes les llistes de `curriculum/flash/math-*` vàlides; correcció numèrica (coma/punt, espais); el test de llistes existent ha de cobrir també `math-*`.
- Python: `flash_lists` de math-m5 dona els mateixos ids que el servidor; `flash_progress` sense fitxer de nivell ⇒ `met`.
- Passar **tots** els tests: `server/test/*.test.ts` (amb `node --experimental-strip-types` o `bun`), `cd server && bun x tsc --noEmit`, `python3 -m unittest discover -s tests`.

## 4. Criteris d'acceptació

- [ ] Un perfil de math veu ⚡ Flash amb les 9 llistes de m5; un de language continua veient només les seves.
- [ ] La taula del 7 mostra `7 × 3` i accepta `21`; teclat numèric; sense selector de direcció.
- [ ] Afegir un fitxer generat nou a `curriculum/flash/math-m5/` apareix sense tocar codi.
- [ ] Un ítem explícit amb un resultat erroni no surt mai i el test el marca.
- [ ] Res de `data/`, de les 6 BD ni del Facts/Go de math tocat. Tests en verd.
