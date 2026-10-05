# Banc de models — com avaluar un model per a Fluent

*2026-09-23 · Estat: **construït (rols alumne i tutor)**; el rol corrector queda
per més endavant.*

## Per a què serveix

Per decidir amb números si un altre model fa millor la feina que Fluent li
demana. **No mesura la qualitat general del model**, només els tipus
d'exercici de l'app, i no substitueix el banc de l'app (`flowed-bench.sh`): el
modelbench serveix per **triar** el model, l'e2e per **confirmar** que funciona
dins l'app.

## La peça central: l'alumne simulat

`bench/learner-a1.md` és una skill que fa respondre un model **com una alumna
d'A1 que ha estudiat el currículum**: rep la llista de lliçons d'A1, la lliçó en
què és ara i la targeta tal com la veu a la pantalla, i respon només el que va
al buit.

Serveix per a dues coses:

| Rol | Què fa el model sota prova | Qui jutja | Puntuació |
|---|---|---|---|
| **alumne** (`learner`) | respon els `Check:` del currículum fent d'alumna | la resposta esperada del currículum | % d'encerts |
| **tutor** (`generate`) | escriu N exercicis per competència, en JSON `{sentence, answer}` | 1) regles fixes, 2) l'alumne simulat al model **de referència** | % d'exercicis justos |

**Un exercici és just** si una alumna que ha estudiat la lliçó arriba a la
resposta que el tutor esperava. «The car is ___» no ho és: l'alumna posarà un
color, però no necessàriament el del tutor.

Regles fixes, abans del jutge: exactament un buit; la resposta no surt a la
frase; a vocabulari, la resposta és de la llista i el buit porta la paraula en
català entre parèntesis (la mateixa regla que `vocabBlankGuard` a l'app).

**El jutge és fix.** Per defecte, el model de producció (`--judge-url`,
port 12322). Si canvia el jutge, els números d'abans no es poden comparar amb
els d'ara: el jutge queda escrit a cada resultat.

## Com es llança

Un model candidat s'aixeca **en un altre port**; el de producció (12322) fa de
jutge i no es toca. Amb una sola GPU, cal que els dos hi càpiguen o fer servir
el jutge en una altra màquina (`--judge-url`).

```bash
# 0. la línia base: el model actual (per defecte fa servir el port 12322)
python3 scripts/flowed-modelbench.py --name qwen3-14b-q4 learner
python3 scripts/flowed-modelbench.py --name qwen3-14b-q4 generate

# 1. aixecar un candidat (qualsevol GGUF) en un port de proves
scripts/models/llama-deep.sh --model ~/aidev/models/<candidat>.gguf --port 12330

# 2. passar-li el banc
python3 scripts/flowed-modelbench.py --url http://127.0.0.1:12330/v1/chat/completions --name <candidat> learner
python3 scripts/flowed-modelbench.py --url http://127.0.0.1:12330/v1/chat/completions --name <candidat> generate

# 3. la taula
python3 scripts/flowed-modelbench.py compare
```

Opcions: `--curriculum curriculum/en-A2.md` (un altre nivell), `generate --per 3`
(més exercicis per competència), `--temperature`, i `--api-key` per a una API
remota compatible amb OpenAI.

Resultats a `results/modelbench/<nom>/<data>/`: `learner.json` /
`generate.json` (la fitxa) i `*.jsonl` (cada exercici, amb el que va dir el
jutge i, si es va rebutjar, per què).

## La taula

```
model                    alumne  tutor just  varietat   JSON  mediana   tok/s
qwen3-14b-q4                …%         …%        …%     …%      …s       …
<candidat>                  …%         …%        …%     …%      …s       …
```

- **alumne**: entén els exercicis del currículum.
- **tutor just**: escriu exercicis que una alumna pot resoldre. És la xifra
  que més pesa per triar el model del tutor.
- **varietat**: frases diferents entre les justes.
- **JSON**: respecta el format.
- **mediana / tok/s**: velocitat.

Amb el currículum A1 i `--per 2` són unes 36 generacions i 44 respostes: prou
per veure diferències grans, no per a diferències de 2–3 punts.

## Més endavant

- **Rol corrector**: exercici + resposta de l'alumna → nota i correcció,
  contra un conjunt etiquetat a mà. És el que falta per avaluar el model del
  tutor sencer.
- Mesurar la VRAM automàticament.

## Decisió

Un candidat només passa a l'e2e de l'app (`flowed-bench.sh --repeat 6`) si
iguala o supera la línia base en **tutor just** sense perdre velocitat de manera
que es noti a classe. L'e2e té l'última paraula.

## Tutor bench (2026-09-27): les pràctiques obertes, amb el servidor real

Des del banc (2026-09-24) el model només fa Speaking, Writing i Reading.
`scripts/flowed-tutorbench.py` les recorre pel servidor real (HTTP, com el
navegador) amb un alumne fix — les mateixes respostes per a tots els models.

**Suficiència** (taxa; veredicte = ≥ 90 % a cada una): `ok` (sense error
LLM/HTTP) · `saved` (la resposta arriba a `.records`, per l'eina o derivada pel
servidor) · `graded` (hi ha puntuació, al text o a l'eina) · `shown` (la
puntuació surt a pantalla) · `continues` (pregunta/tasca següent, reintent
explícit o «ready») · `clean` (sense `{❌}`, menú, salutació ni escriptura no
llatina).

**Qualitat:** `catches` (l'error plantat apareix corregit) · `consistent`
(puntuació de l'eina = la que veu l'alumne) · segons per torn (només
comparable a la mateixa màquina). `rescore` torna a jutjar una execució des del
seu `.md`.

**v1 → v2 (2026-09-27).** La primera versió comptava com a «no puntuat» tot el
que no passava per l'eina (el 14B puntua al text i el servidor deriva el
registre), exigia ≥ 7 a respostes bones que no responien la pregunta (el tutor
feia bé de baixar-les) i no acceptava un reintent com a continuació. Tots dos
models sortien «no suficients» per culpa del test.

### Primer resultat (2026-09-27, 3 passades, perfil nou `e2e-bench`)

| | 14B Q4 (railab 12322) | 27B (llvm 12321, TabbyAPI) |
|---|---|---|
| ok · graded | 39/39 · 30/30 | 39/39 · 30/30 |
| saved (`.records`, comprovat a mà) | 30/30 (quasi tot derivat) | 30/30 (quasi tot per l'eina) |
| shown | 30/30 | **26/30** («Waiting for your answer!» sense correcció) |
| continues | 36/39 («Try the next one!» sense la pregunta) | 36/39 |
| clean | **32/39** — Reading: `{❌}` i caràcters xinesos (滑梯) dins del text | 39/39 |
| catches · consistent | 9/9 · 4/4 | 8/9 · 11/12 (eina 9, pantalla 7) |
| s/torn (mediana) | 3.8 | **53.4** |

Cap dels dos arriba al 90 % a totes les portes, per motius diferents: el 14B
embruta Reading; el 27B a vegades amaga la correcció. **El temps no compara
models aquí:** el 14B corria a la 4090 (railab) i el 27B a la 4060 Ti (llvm).
Per comparar-lo, tots dos a la mateixa GPU (previst: 27B i 14B a la 4060 Ti).

### Temps de resposta (`timing`, 2026-09-27)

Cada execució guarda, per botó / resposta / pràctica: mediana, p90 i màxim dels
segons que espera l'alumne, i — de `<perfil>/.metrics/turns.jsonl` — tokens de
prompt i tok/s de generació. `--host` etiqueta la màquina (per defecte el
hostname); `compare` en fa una segona taula.

| | host | botó med | resposta med | resposta p90 | màx | tok/s |
|---|---|---|---|---|---|---|
| 14B | railab-4090 | 6.4 | 2.0 | 6.5 | 12.3 | 44 |
| 27B | llvm-4060ti | 65.1 | 51.5 | 116.8 | 156.4 | — (TabbyAPI no torna `usage`) |

Prompt mediana ~17k tokens (14B); amb el 27B a la 4060 Ti, el prompt pesa molt
en el temps.

```bash
# servidor de prova, en un perfil test*/demo*/e2e* (hi escriu respostes)
scripts/flowed-web.sh --app --port 4199 test-en
python3 scripts/flowed-tutorbench.py run --port 4199 --name qwen3-27b test-en --repeat 3
python3 scripts/flowed-tutorbench.py compare
```

Resultats a `results/tutorbench/<nom>-<hora>.json` + `.md` (transcripció per
llegir-la). `--only speaking` per provar-ne una.

### 2026-09-28, 4060 Ti: execució invàlida (perfil sense configurar)

`e2e-bench2` es va crear amb `new-user.sh` però no es va omplir amb
`flowed-profile.py`: tots els camps eren plantilla (`{YOUR_NAME}`,
`{LANGUAGE_YOU_WANT_TO_LEARN}`). El 27B va dedicar torns a demanar-los; el 14B
es va inventar que l'alumne aprenia neerlandès. Cap de les dues mesura el tutor.
Des d'ara el bench es nega a començar si el perfil té camps buits o de plantilla.

Només el temps és orientatiu (mateixa GPU, però torns diferents): resposta
mediana 14B 16.7 s / 27B 43.0 s; botó 16.6 s / 115.2 s; p90 resposta 30.9 / 119.3 s.

### 2026-09-29, tots dos a la 4060 Ti (llvm), perfil configurat

Perfil `e2e-bench4` (Test, català → anglès, A1). Atenció: el 27B hi va córrer
després del 14B (mateix perfil), així que partia amb l'historial del 14B.

| | 14B Q4 (llama.cpp) | 27B EXL3 3bpw (TabbyAPI) |
|---|---|---|
| veredicte (≥ 90 %) | **suficient** | no |
| ok · saved · graded · shown | 39 · 30 · 30 · 30 | 39 · 29 · 29 · 29 |
| continues | 39/39 | **31/39** — «Take your time — I'm ready when you are!» sense pregunta; 2 respostes tallades a mitja frase |
| clean | 38/39 (`{"Question 1…" — in English}`, ja arreglat) | 39/39 |
| catches | 7/9 | 9/9 |
| consistent (eina = pantalla) | 9/9 | **12/17** |
| crida l'eina de registre | 9/30 (la resta, derivat) | 17/30 |
| roundtrips (mediana) | 1 | 2 |
| resposta: mediana / p90 | 10.3 / 26.6 s | 61.6 / 115.7 s |
| botó: mediana | 16.2 s | 67.4 s |
| intervencions del servidor (guards) | 18 | 19 |

**Per què el 27B és lent** (curl directe, 2026-09-29): amb un prompt curt respon
en 2.1 s, i pensa poc (`reasoning_content` d'unes 60 paraules). El temps és el
prompt de ~17k tokens a cada crida, multiplicat per les crides: la de l'eina
(`fluent_record_answer`) en fa una segona, i cada reescriptura d'un guard una
altra. `chat_template_kwargs.enable_thinking=false` NO serveix amb aquest
TabbyAPI: posa tota la resposta a `reasoning_content` i `content` queda buit
(el servidor mostraria una resposta en blanc).

**Què pot fer l'app** (serveix per als dos models): menys crides per torn (eina
de registre fora de les pràctiques obertes; el servidor ja deriva el registre
del text), menys reescriptures (guards amb falsos positius) i un prompt més
petit a Speaking/Writing/Reading.
