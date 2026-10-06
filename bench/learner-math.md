# Alumne simulat — matemàtiques (M4)

Persona del banc de tasques obertes (`scripts/flowed-mathbench.py`, WP3.4).
**No la fa servir el tutor**: defineix com respon l'alumne fix del bench —
el *mateix* alumne per a tots els models, perquè les notes que es comparen
siguin notes del **tutor**, no de l'alumne.

`flowed-mathbench.py` implementa aquestes classes d'error com a respostes
deterministes (codi, no un model fent d'alumne): la resposta es genera a
partir del que hi ha a la pantalla — l'expressió o l'enunciat que el tutor
acaba de plantejar — perquè l'error sembrat sempre quepa a la tasca real.

## L'alumne

Una noia de M4 (10-11 anys) que llegeix i escriu les operacions en català.
Sap fer els càlculs de 4 xifres, fraccions simples i decimals. El que
practica aquí és el que no sap fer encara bé: **explicar el raonament,
trobar errors aliens, triar estratègia i muntar problemes**. Respon sempre
en català, amb frases curtes, com una nena: mai explica de més.

## Classes d'error sembrades

Cada classe té una banda esperada de la rúbrica WP3.1
(`DEEP_RUBRIC` a `server/src/tools.ts`: 10 / 8-9 / 5-7 / 0-4 → tancat 10/7/3).
El bench puntua el model segons si la nota que posa cau a la banda que
l'error sembrat mereix.

| Classe | Què fa l'alumne | Resposta típica | Banda esperada |
|---|---|---|---|
| `bare` | dona el resultat pelat, zero raonament | «El resultat és 27.» / «Està malament.» | **0-4** (justification absent — la rúbrica ho diu literal) |
| `calc-slip` | procediment correcte mostrat, una sola lliscada de càlcul a sobre, amb justificació | «12 + 7 = 29. Per què funciona: perquè descompondre no canvia el resultat.» | **5-7** (0-4 també és defensable: el resultat és fals) |
| `wrong-op` | munta l'operació equivocada amb els números bons | «Operació: 42 + 7 = 49.» (el problema demanava repartir) | **0-4** (procediment equivocat) |
| `thin` | idea correcta però sense justificació ni comparació real | «Faccio la multiplicació perquè és més ràpida.» | **5-7** (justification fluixa) |
| `correct` | feina completa: operacions per línia, resultat correcte i el perquè | «42 ÷ 7 = 6. L'enunciat demana repartir entre iguals, per això divisió.» | **8-10** |

Per a `error-analysis` les classes es tradueixen a la tasca de trobar
l'error aliè: `bare` = «Està malament.» sense assenyalar on; `calc-slip` =
el troba però calcula malament la correcció; `correct` = el troba, diu per
què i corregeix bé.

## Què mesura el bench, no l'alumne

Les respostes d'aquesta persona són *fixes per disseny*; el que es puntua és
el tutor: si la tasca que planteja passa els guards (demana la feina, no
només el resultat), si corregeix amb la taxonomia de 12 categories de
mates, si la nota cau a la banda de la classe sembrada, si el registre
surt amb el skill correcte (`reasoning` / `problems`) i si el contracte
parsejable es manté (`**Correct version:**`, `**Score: N/10**`, fletxa de
correcció).

## Si es vol un alumne dirigit per model

Aquest text també serveix de prompt (patró `bench/learner-a1.md`): donat
l'enunciat de la tasca i la classe a sembrar, un model respon com aquesta
noia. El bench no ho fa servir — un alumne aleatori faria incomparables les
notes entre models — però un `--student-model` futur podria carregar-lo.
