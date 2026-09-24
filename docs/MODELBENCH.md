# Banc de models — com avaluar un model per a Fluent

*2026-09-23 · Estat: **construït (rols alumne i tutor)**; el rol corrector queda
per més endavant.*

## Per a què serveix

Per decidir amb números si un altre model fa millor la feina que Fluent li
demana. **No mesura la qualitat general del model**, només els tipus
d'exercici de l'app, i no substitueix el banc de l'app (`fluent-bench.sh`): el
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
python3 scripts/fluent-modelbench.py --name qwen3-14b-q4 learner
python3 scripts/fluent-modelbench.py --name qwen3-14b-q4 generate

# 1. aixecar un candidat (qualsevol GGUF) en un port de proves
scripts/models/llama-deep.sh --model ~/aidev/models/<candidat>.gguf --port 12330

# 2. passar-li el banc
python3 scripts/fluent-modelbench.py --url http://127.0.0.1:12330/v1/chat/completions --name <candidat> learner
python3 scripts/fluent-modelbench.py --url http://127.0.0.1:12330/v1/chat/completions --name <candidat> generate

# 3. la taula
python3 scripts/fluent-modelbench.py compare
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

Un candidat només passa a l'e2e de l'app (`fluent-bench.sh --repeat 6`) si
iguala o supera la línia base en **tutor just** sense perdre velocitat de manera
que es noti a classe. L'e2e té l'última paraula.
