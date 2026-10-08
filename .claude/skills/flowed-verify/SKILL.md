---
name: flowed-verify
description: Verifica una versió del core FlowEd (0.6+: dominis language i math) abans de producció — llança scripts/flowed-verify.sh, analitza l'informe i dona un veredicte a results/verify-<data>/ANALISI.md.
---

# Verificar una versió de FlowEd

Objectiu: decidir, amb proves, si una versió del core (aquest repo) pot anar a
producció i si `flowed-language` ja es pot retirar. Executa i informa; no
corregeix codi ni fa commit sense que l'Albert ho demani.

## Regles que no es negocien

- Tot viu a `~/.flowed` (`~/.flowmath` ja no existeix; `~/.fluent` és llegat: no tocar-lo). Dins `~/.flowed` només es toquen perfils de prova (`test*`, `demo*`, `e2e*`); mai `naia-en`, `iona-en` ni `nes-en` (només es llegeix per fer la còpia `test-nes`).
- Mai els perfils `naia-en` ni `iona-en`. Només perfils de prova: `test*`, `demo*`, `e2e*`.
- No pujar cap model local: el model és el remot `http://192.168.31.102:12321/v1` (`FLOWED_DEEP_MANAGED=0`).
- `flowed-language` només es retira amb el veredicte «llest» i la confirmació de l'Albert.
- No fer commit, push ni esborrar res.

## 1. Executar (a railab)

```bash
scripts/flowed-verify.sh                 # suites + e2e language + algebra
TUTORBENCH=1 scripts/flowed-verify.sh    # + tutor bench de les pràctiques obertes (lent)
```

Abans, comprova que el model respon (`curl -s -m5 http://192.168.31.102:12321/health`).
Si no hi ha `bun` o no hi arriba, no ho intentis d'una altra manera: digues-ho.

Què fa el script (per repetir un pas a mà):
1. `model-health`: `/health` del model remot.
2. `unittest`: `python3 -m unittest discover -s tests` (referència 2026-10-08: 767 OK).
3. `ts-harnesses`: cada `server/test/*.test.ts` amb bun (referència: 17 OK).
4. `tsc`: `bun x tsc --noEmit` a `server/` (referència: 0 errors).
5. En directe, per domini: arrenca la web de prova, passa `scripts/flowed-e2e.py`
   (`--scenario language` a `test-lang`:4205, `--scenario algebra` a `test-m7`:4201)
   i l'atura. Desa la transcripció `e2e-<escenari>.md`.
6. Opcional (`TUTORBENCH=1`): `scripts/flowed-tutorbench.py` sobre el perfil de llengua.

## 2. Analitzar

Llegeix `results/verify-<data>/summary.md` i, per cada pas que falla, el seu
`.log`; per als e2e, també la transcripció. Classifica cada fallada:

- **codi**: regressió (traça, assert, comanda que no carrega, registre que no arriba a `.records`).
- **model**: el servidor fa la feina però el model no compleix (no puntua, no continua,
  text brut). Contrasta amb `docs/MODELBENCH.md` abans de culpar el codi.
- **entorn**: model caigut, port ocupat per una altra web (401), perfil sense
  configurar (camps `{…}` de plantilla), bun absent.

Abans de donar una fallada per real, cita'n l'evidència (línia del log o fragment de
la transcripció). Un detector també es pot equivocar: si la transcripció mostra que el
tutor ho va fer bé, digues-ho i proposa arreglar el test o el detector del servidor.

Mira també si un pas ha passat sense provar res (p. ex. un e2e que acaba en 1 s no ha
parlat amb el model): digues-ho com a reserva.

Compara amb la verificació anterior (`results/verify-*` més recent) si n'hi ha.

## 3. Informe — `results/verify-<data>/ANALISI.md`, en català, breu

1. **Veredicte** en una línia: «llest per producció», «llest amb reserves (…)» o «no llest (…)».
2. **Taula** de passos: resultat, temps, i per als e2e les comprovacions que passen.
3. **Fallades**: una per línia, amb tipus (codi/model/entorn), evidència i correcció proposada.
4. **Retirar flowed-language**: sí/no i per què (cal l'e2e de language i el tutor bench
   al nivell del 14B de `docs/MODELBENCH.md`).
5. **Pas següent**: una sola acció concreta.
