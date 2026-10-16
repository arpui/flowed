# Encàrrec E8 — Go: currículum m6 i banc

Disseny: `docs/DISSENY-M7-M6.md` §2 (llegir-lo). Mateix enfocament que E2 i E6 (`docs/ENCARREC-M5-E2-BANC.md`, `docs/ENCARREC-M7-E6-BANC.md`). Decisions tancades.

## 1. Abast

Fitxers: `curriculum/math-m6.md` (nou), `scripts/mathbank.py`, `curriculum/bank/math-m6/` (nou), tests de `tests/` del banc/currículum de math. **No** toquis `server/`, `web/`, `hooks/curriculum.py`, `curriculum/flash/`.

## 2. `curriculum/math-m6.md`

Mateix format que `math-m5.md`. Capçalera: `language: math`, `level: m6`, `status: esborrany`, `pass_mark: 80`, `carry_mark: 65`, `checkpoint_items: 12`, `ready_share: 50`. **Sense `flash_share`** (ho fa E9). Les 17 competències de la taula §2 del disseny, en 5 seccions (Sentit numèric i càlcul, Proporcionalitat i àlgebra, Mesura, Geometria, Estadística i probabilitat). `[core]` segons el disseny; la resta `[extra]`. `m6.coordinates` sense `Bank:`. Ha de validar.

Les competències que reutilitzen famílies de m5/m7 (`equations_simple`, `mean_mode_range`, `probability_simple`, `sexagesimal_ops`, `stats_tables`, `gcd_lcm_problems`) fan servir la mateixa família; si cal un nivell més fàcil per a m6, afegeix un paràmetre o una família germana (`sexagesimal_ops_easy`) **sense canviar** els ítems ja generats.

## 3. Famílies noves

`powers_value` (potències i arrels exactes), `integers_context` (temperatures, ascensors, deutes; sumes i restes), `frac_ops4` (+ − × : amb denominadors diferents; `also_accept` simplificada), `dec_division` (decimal entre enter i entre decimal, resultat exacte), `percent_change` (augments i descomptes, regla de tres directa), `scales` (mapa ↔ realitat, unitats), `area_units` (km²…mm², ha/a/ca), `volume_units` (m³, dm³, cm³, l, ml), `areas_polygons` (regular amb apotema, rombe, trapezi; unitat), `circle_measures` (longitud i àrea, π = 3,14; unitat), `volumes_solids` (prisma, cilindre amb π = 3,14; unitat). Banc generat, ~12 per competència.

## 4. Tests i acceptació

- Tests de les famílies noves; `math-m6.md` vàlid; cada `Bank:` existeix; ítems de m4/m5/m7 **idèntics**.
- `python3 -m unittest discover -s tests` sencer (única fallada esperada: harness de `flash.test.ts` per les 4 llistes buides d'anglès).
- [ ] `math-m6.md` amb 17 competències. [ ] Famílies + banc generat i validat. [ ] Res existent canviat.
