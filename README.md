# 🌍 Fluent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Un tutor d'idiomes personal que corre a casa teva, sobre un LLM local.**

Un servidor propi i una web per alumne. Cada alumne entra amb un enllaç i una
contrasenya, practica, i el sistema recorda: què li costa, què ja domina, i què
toca repassar avui. Sense núvol, sense API de pagament i sense que les dades de
ningú surtin de la màquina.

---

## Què fa

- **Repetició espaiada (SM-2)** — cada paraula i cada patró tornen just abans
  d'oblidar-se.
- **Aprèn dels errors** — el que falles s'arxiva amb la seva categoria i torna
  com a exercici fins que el domines.
- **La lliçó del dia** — un nucli que té final (repàs vençut + drills dels
  punts febles), i després joc lliure amb el que vulguis.
- **Veu** — sentir la frase ben pronunciada, amb TTS local.
- **Multi-alumne** — un perfil i un port per persona, cada un amb les seves
  dades i la seva contrasenya.

## Com és per dins

```
web/          interfície de l'alumne (HTML/CSS/JS, sense framework)
server/       servidor propi en TypeScript sobre Bun: HTTP, SSE, bucle
              d'eines contra un llama.cpp compatible amb OpenAI
prompts/      el que fa de tutor: agents, comandes, regles dures
skills/       una carpeta per tipus de pràctica (vocabulari, escriptura…)
hooks/        la capa de dades en Python: SM-2, patrons d'error, persistència
scripts/      arrencada, configuració, diagnòstic, migracions
docs/         arquitectura, manual, pla de proves, migració
```

El contracte entre el servidor i la capa de dades és una **BD SQLite de
sessions** i **sis fitxers JSON** per alumne, tots inspeccionables amb un editor
de text.

## Requisits

- **[Bun](https://bun.sh)** per al servidor
- **Python 3.9+** (només biblioteca estàndard)
- Un **llama.cpp** servint un model compatible amb l'API d'OpenAI
  (provat amb Qwen3-14B-Q4_K_M)
- Una GPU amb ~14 GB lliures per a aquest model

## Posar-lo en marxa

```bash
git clone https://github.com/arpui/fluent_dev.git
cd fluent_dev/server && bun install && cd ..

cp .env.railab .env          # o .env.rapve — plantilla per màquina
scripts/new-user.sh alex-en  # crea el perfil
python3 scripts/fluent-profile.py alex-en \
  --name Alex --native Catalan --target English --level A2 --goal B1

scripts/fluent-start.sh      # puja el model i una web per alumne
```

`docs/MANUAL.md` té el detall, i `docs/ARQUITECTURA.md` explica per què cada
cosa és on és.

## Comprovar què està passant

```bash
python3 scripts/fluent-check.py all alex-en       # perfil, SM-2, patrons, sessions
python3 scripts/fluent-check.py sortida alex-en   # els últims missatges del tutor
python3 scripts/fluent-check.py metrics alex-en   # temps i tokens per torn
python3 -m unittest discover -s tests -q          # la suite
```

## D'on ve

Fluent va començar com un plugin de Claude Code: un conjunt de *skills* i
*hooks* que convertien l'assistent en un tutor d'idiomes. Aquesta versió n'és
la continuació per un altre camí — servidor propi, model local, i una interfície
pensada per a una nena de vuit anys, no per a algú amb un terminal obert.

L'estructura ho recorda: els *skills* segueixen sent carpetes amb un `SKILL.md`,
i els *hooks* segueixen sent scripts de Python que parlen per JSON. El que ha
canviat és qui els crida.

El README original d'aquella etapa és a
[`docs/README-original-plugin.md`](docs/README-original-plugin.md), i el camí
per opencode, que també es va explorar, és a `obsolet/`.

## Llicència

MIT — vegeu [LICENSE](LICENSE).
