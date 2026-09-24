---
language: English
level: A2
version: 2
status: esborrany
pass_mark: 80
carry_mark: 65
checkpoint_items: 24
ready_share: 50
---

# English A2 — currículum

> **Esborrany v2, pendent de revisió docent** contra el MCER i l'English Grammar / Vocabulary Profile. Serveix per fixar el marc; el contingut es pot canviar (vegeu «Ids i versions»).

## Com es llegeix aquest fitxer

- Una competència = un títol `###`. Format: `### id — Nom [core]` o `[extra]`.
  `core` = imprescindible per donar el nivell per assolit. `extra` = útil, no bloqueja ni compta al checkpoint.
- Front matter: `pass_mark` / `carry_mark` = % per pujar / per pujar amb reforç; `checkpoint_items` = exercicis de la prova; **`ready_share`** = % de les competències `core` que han d'estar **consolidades** perquè s'obri la prova de nivell (0 = n'hi ha prou amb «en pràctica»; recomanat 50).
- Línies `Clau: valor` sota el títol:
  - `Can do:` què sap fer l'alumne (en anglès, independent de l'idioma natiu).
  - `Requires:` ids que han d'anar abans (opcional, **tou**: avisa, no bloqueja).
  - `Forms:` estructures a dominar. Es donen les formes (+), (-), (?) perquè el model generi varietat.
  - `Words:` només als conjunts de vocabulari, separades per comes.
  - `Replaces:` id antic que aquesta competència substitueix (opcional).
  - `Depth:` quanta evidència cal per donar la competència per consolidada: `light` (8 respostes, ≥ 3 dies), `normal` (12, ≥ 5 dies; per defecte), `deep` (20, ≥ 7 dies); sempre ≥ 80 % de les últimes 8 / 10 / 12. També decideix quants exercicis al dia rep mentre s'aprèn (3 / 3 / 4 de nova, 2 / 2 / 3 de repàs). Un temps verbal que costa setmanes és `deep`; cinc paraules de menjar són `light`.
  - `Weight:` importància, 1 a 3 (1 per defecte): pesa a la barra del nivell.
  - `Signals:` (gramàtica i funcions) paraules o expressions que és normal trobar en un **exercici** d'aquesta competència (l'enunciat, el context i la frase amb el buit; no la resposta, que el buit amaga). Serveixen perquè el servidor comprovi que el tutor ha fet un exercici d'aquesta competència i no d'una altra: n'hi ha prou que en surti una. Més generoses que `Tags`, que assignen respostes ja fetes. Si falta, es fa servir el que `Tags` té sense `#`.
  - `Tags:` (gramàtica i funcions) com s'assignen a aquesta competència les respostes registrades. `#categoria` = tipus d'error o d'ítem (`#agreement`, `#tenses`, `#prepositions`…; llista a `hooks/db_schema.py`); la resta, paraules o expressions que hi surten (`yesterday`, `going to`). Regla: es miren les competències que tenen la `#categoria` de la resposta i guanya la que té més paraules; si cap paraula surt, només s'assigna quan hi ha una sola candidata. Vocabulari no en porta: s'assigna per `Words`.
- `Check:` 3 exercicis per competència, un per línia: `- Tipus: enunciat → resposta`.
  - **Tot en anglès.** Cap check depèn de l'idioma natiu de l'alumne.
  - Tipus tancats (`Complete`, `Correct`, `Meaning`): la resposta es compara amb l'esperada.
  - Tipus oberts (`Ask`, `Say`): la resposta és un exemple; la valora el model.
  - Lectura: el **tipus** és el text abans del primer `:`; la **resposta** és el text després de l'última `→`.
  - `/` separa respostes alternatives vàlides. `, ` separa les respostes de buits successius (`on, at` = primer buit `on`, segon `at`).
  - `Meaning: <definició> → <paraula>` és la prova de vocabulari (sense traducció).
- Els `Check` són **exemples**, no el banc complet: el model n'ha de generar de nous a partir de `Forms`, `Words` i `Can do`, i no repetir els ja fets.

## Ordre

- **L'ordre del fitxer és l'ordre d'ensenyament** dins de cada secció (Gramàtica, Funcions, Vocabulari).
- El servidor hi porta com a màxim **3 competències actives**, una per secció: així cada dia hi ha estructura, ús i paraules, i no deu setmanes de gramàtica seguides.
- `Requires` avisa si no es compleix (l'alumne o el docent poden saltar).

## Promoció de nivell

- **Quan es pot fer el checkpoint:** quan totes les competències `core` són com a mínim `practicing`, o quan el docent el llança.
- **Mecànica:** `checkpoint_items` exercicis de les `core`, **almenys 1 per competència**; la resta es reparteix entre les menys consolidades. Sense repetir els vists els últims 7 dies. Es compta com a correcte una nota ≥ 8.
- **≥ `pass_mark` %:** puja de nivell.
- **entre `carry_mark` % i `pass_mark` %:** puja, però les competències que ha fallat queden **obertes** al nivell nou, amb prioritat de repàs.
- **< `carry_mark` %:** es queda; reforç de les competències fluixes i repetició del checkpoint (màxim 2 vegades); després decideix el docent.
- **Promoció manual:** el docent pot fer pujar un alumne en qualsevol moment; queda registrada com a «promoció manual» i les competències fluixes queden obertes igualment.

## Ids i versions

- Un id (`a2.nom`) no es canvia: el progrés dels alumnes hi va lligat.
- Si una competència es fusiona o es divideix, la nova porta `Replaces: <id antic>` i el servidor hi migra el progrés.
- Si se'n retira una sense substitut, es llista a «Retirades».
- Cada canvi de contingut puja `version`.

---

## Gramàtica

### a2.present_simple_vs_continuous — Present simple vs present continuous [core]
Can do: Say what I do every day and what I am doing now.
Depth: deep
Weight: 3
Forms: (+) I work / I am working; (-) She doesn't work / She isn't working; (?) Do you work? / Are you working?
Tags: #agreement, #tenses, #grammar, now, at the moment, every day, usually, always, goes, works, doesn't, isn't, raining
Signals: now, right now, at the moment, currently, these days, today, every day, every morning, every, usually, always, often, sometimes, never, look, listen, on mondays
Check:
- Complete: Look! It ___ (rain). → is raining
- Complete: She ___ (work) in a bank every day. → works
- Correct: I am go to school every day. → I go to school every day.

### a2.pronouns_possessives — Object pronouns and possessives [core]
Can do: Say who things belong to and who receives an action, without repeating names.
Depth: normal
Weight: 2
Forms: me, you, him, her, it, us, them; mine, yours, his, hers, ours, theirs
Tags: #pronouns, me, him, her, us, them, mine, yours, hers, ours, theirs
Signals: me, him, her, us, them, it, my, your, his, our, their, its, mine, yours, hers, ours, theirs, whose, belongs, borrow, give, tell, show
Check:
- Complete: That is not your bag. It is my bag. It is ___. → mine
- Complete: I can't find my keys. Have you seen ___? → them
- Correct: Give it to she. → Give it to her.

### a2.prepositions_time_place — Prepositions of time and place [core]
Can do: Say exactly when and where things happen.
Depth: deep
Weight: 2
Forms: time: at (hours, night), on (days, dates), in (months, years, seasons); place: in, on, at, under, next to
Tags: #prepositions, at, on, in, under, next to
Signals: at, on, in, under, next to, between, behind, opposite, in front of, above, across, near, from, before, after, during, until, by, preposition, prepositions, when, where, time, place, monday, tuesday, wednesday, thursday, friday, saturday, sunday, january, february, march, april, may, june, july, august, september, october, december, november, morning, afternoon, evening, night, weekend, o'clock, table, box, room, park, street, city, school, home
Check:
- Complete: The meeting is ___ Monday ___ 9 o'clock. → on, at
- Complete: I was born ___ 1998. → in
- Complete: She lives ___ a small flat ___ the city centre. → in, in

### a2.infinitive_gerund — Verb + infinitive / -ing [core]
Can do: Say what I want, need, like and decide, using two verbs together.
Depth: deep
Weight: 1
Forms: want / need / decide + to + verb; like / enjoy / love / hate + -ing
Tags: #grammar, want to, need to, decide, decided, enjoy, enjoys, like, love, hate
Signals: want, wants, need, needs, decide, decided, enjoy, enjoys, like, likes, love, loves, hate, hates, start, stop, finish, hope, plan, prefer
Check:
- Complete: I want ___ (learn) English. → to learn
- Complete: She enjoys ___ (swim) in the sea. → swimming
- Correct: He decided going home early. → He decided to go home early.

### a2.countable_uncountable — Countable and uncountable nouns [core]
Can do: Ask about quantities and describe amounts that are not exact.
Depth: normal
Weight: 2
Forms: How much / How many; some / any; a lot of; a few (countable) / a little (uncountable)
Tags: #grammar, much, many, some, any, a lot of, a few, a little
Signals: much, many, some, any, a lot of, lots of, a few, a little, how much, how many, there is, there are, how, water, sugar, milk, rice, bread, money, time, food, information, people, apples, bottles, chairs
Check:
- Complete: How ___ water do you drink a day? → much
- Complete: How ___ apples do we need? → many
- Complete: There isn't ___ milk in the fridge. → any

### a2.past_simple — Past simple: regular and common irregular verbs [core]
Can do: Say what happened yesterday or in the past.
Depth: deep
Weight: 3
Forms: (+) worked, went, saw, bought; (-) didn't work, didn't go; (?) Did you work? Did you see...?
Tags: #tenses, #grammar, yesterday, ago, last week, last year, last night, did, didn't, went, saw, bought, woke, visited
Signals: yesterday, ago, last week, last year, last night, last month, last weekend, when i was, did, didn't, went, saw, bought, woke, visited, then
Check:
- Complete: Yesterday we ___ (go) to the cinema. → went
- Complete: She didn't ___ (buy) the tickets. → buy
- Correct: Did you saw the match? → Did you see the match?

### a2.past_continuous — Past continuous [core]
Can do: Describe a scene in the past and an action interrupted by another event.
Depth: normal
Weight: 1
Requires: a2.past_simple
Forms: (+) was / were + -ing; (-) wasn't / weren't + -ing; (?) Were you + -ing?; linkers: when, while
Tags: #tenses, #grammar, was, were, wasn't, weren't, while, when
Signals: was, were, wasn't, weren't, while, when, at that moment, at 8, all evening
Check:
- Complete: I ___ (read) a book when the phone rang. → was reading
- Complete: They ___ (not/sleep) at 10 PM. → weren't sleeping / were not sleeping
- Correct: She was walk in the park. → She was walking in the park.

### a2.comparatives_superlatives — Comparatives and superlatives [core]
Can do: Compare people, places and things, and say which is the most or the least.
Depth: normal
Weight: 2
Forms: -er than; more ___ than; the -est; the most ___; as ... as; good – better – best; bad – worse – worst
Tags: #grammar, taller, better, worse, more, most, than, best, worst
Signals: than, taller, better, worse, more, most, best, worst, older, bigger, cheaper, biggest, the oldest, as
Check:
- Complete: My brother is ___ (tall) than me. → taller
- Complete: This is the ___ (interesting) book in the shop. → most interesting
- Correct: She is more taller than her sister. → She is taller than her sister.

### a2.modals_ability_obligation — can, must, have to, should [core]
Can do: Say what I can do, what I must do, what is forbidden, and give advice.
Depth: normal
Weight: 2
Forms: can / can't / could; must / mustn't; have to / don't have to; should / shouldn't
Tags: #grammar, can, can't, could, must, mustn't, have to, don't have to, should, shouldn't
Signals: can, can't, could, must, mustn't, have to, has to, don't have to, should, shouldn't, may, allowed, wear, law, rule, rules, forbidden, advice, obligation, ability, permission, not sure, maybe, perhaps, might, need to, seatbelt, helmet
Check:
- Complete: You ___ wear a seatbelt in the car. It's the law. → must / have to
- Complete: You ___ pay to enter the museum. It's free today. → don't have to
- Complete: You have a fever. You ___ see a doctor. → should

### a2.future_going_to_will — Future: going to and will [core]
Can do: Talk about plans (going to) and about quick decisions or predictions (will).
Depth: normal
Weight: 2
Forms: (+) I'm going to visit, I'll help; (-) I'm not going to, I won't; (?) Are you going to ...? Will you ...?
Tags: #tenses, #grammar, going to, will, won't, tomorrow, next week
Signals: going to, will, won't, tomorrow, next week, next year, next month, tonight, soon, this weekend, plan, plans, this evening, this afternoon, this week, later, weekend, next, maybe, perhaps, think, in the future
Check:
- Complete: I've bought the ticket. I ___ (visit) my grandma this weekend. → am going to visit / 'm going to visit
- Complete: "There's no milk." "Don't worry, I ___ (get) some." → will get / 'll get
- Correct: I am going help you with your homework. → I am going to help you with your homework.

### a2.present_perfect_experience — Present perfect: life experiences [extra]
Can do: Talk about experiences without saying when they happened.
Depth: normal
Weight: 1
Requires: a2.past_simple
Forms: (+) have / has + participle; (-) haven't / hasn't + participle; (?) Have you ever ...?; ever, never, already, yet
Tags: #tenses, #grammar, have, has, ever, never, already, yet, been, lived
Signals: have, has, ever, never, already, yet, just, been, lived, since, for
Check:
- Complete: I ___ (never/be) to Japan. → have never been / 've never been
- Correct: Have you ever eat sushi? → Have you ever eaten sushi?
- Complete: She hasn't finished her homework ___. (yet/already) → yet

## Funcions

### a2.directions — Asking for and giving directions [core]
Can do: Move around a city by asking for and understanding directions.
Depth: normal
Weight: 2
Requires: a2.prepositions_time_place
Forms: How do I get to ...? Go straight on. Turn left / right. It's between ... / opposite ... / next to ...
Tags: #prepositions, #grammar, turn, straight, left, right, between, opposite, how do i get
Signals: turn, straight, left, right, between, opposite, how do i get, how can i get, next to, behind, corner, cross, street, road, bridge, station, where is, way to
Check:
- Ask: Ask politely how to get to the station. → Excuse me, how do I get to the station? / Could you tell me the way to the station?
- Complete: Go straight on and ___ left at the bank. → turn
- Complete: The pharmacy is ___ the bank and the post office. → between

### a2.suggestions — Making and answering suggestions [core]
Can do: Suggest plans and react naturally to other people's suggestions.
Depth: light
Weight: 1
Requires: a2.infinitive_gerund
Forms: Let's ...; Why don't we ...? Shall we ...? How about + -ing? Answers: That's a good idea. / Sorry, I can't.
Tags: #grammar, let's, why don't, shall we, how about
Signals: let's, lets, why don't, shall we, how about, what about, we could, sounds good, good idea, would you like
Check:
- Complete: Let's ___ (go) to the cinema. → go
- Complete: Why don't we ___ (eat) out tonight? → eat
- Complete: How about ___ (visit) the museum? → visiting

### a2.shopping_restaurant — Shops and restaurants [core]
Can do: Order food, ask prices and do simple shopping.
Depth: normal
Weight: 2
Requires: a2.countable_uncountable
Replaces: a2.restaurant
Forms: I'd like ...; Could I have ...? How much is this? Can I try it on? Could we have the bill, please?
Tags: #grammar, i'd like, could i have, how much, bill, menu, try it on
Signals: i'd like, i would like, could i have, can i have, how much, bill, menu, try it on, buy, price, excuse me, size, pay, order, waiter, cost, cheap, shop, restaurant, table
Check:
- Ask: Ask for the menu in a restaurant. → Could I have the menu, please? / Can I see the menu, please?
- Ask: Ask the price of a t-shirt in a shop. → How much is this t-shirt? / How much does this t-shirt cost?
- Complete: I'd like ___ orange juice, please. → an

## Vocabulari

### a2.vocab_food_and_drink — Food and drink [core]
Can do: Recognise and use everyday food words and meals.
Depth: light
Weight: 1
Words: bread, cheese, butter, rice, chicken, fish, meat, egg, vegetables, fruit, apple, banana, sugar, salt, pepper, coffee, tea, juice, water, milk, breakfast, lunch, dinner, hungry, thirsty
Check:
- Meaning: the first meal of the day → breakfast
- Meaning: a white drink that comes from cows → milk
- Meaning: a yellow fruit that monkeys like → banana

### a2.vocab_house_and_furniture — House and furniture [core]
Can do: Describe where I live and the things in my home.
Depth: light
Weight: 1
Words: kitchen, bedroom, bathroom, living room, garden, garage, door, window, floor, stairs, wall, table, chair, sofa, bed, shelf, lamp, cupboard, fridge, mirror, carpet
Check:
- Meaning: the steps that take you to the floor above → stairs
- Meaning: a cold box in the kitchen where you keep food → fridge
- Complete: I sleep in the ___. → bedroom

### a2.vocab_health_and_body — Health and the body [core]
Can do: Tell a doctor what hurts and name parts of the body.
Depth: light
Weight: 1
Words: head, arm, leg, back, stomach, throat, tooth, eye, ear, hand, foot, feet, cold, fever, cough, headache, stomachache, pain, doctor, medicine, hurt, ill
Check:
- Meaning: a pain in your head → headache
- Meaning: the part of your body inside your neck; it hurts when you have a cold → throat
- Complete: I have a ___ and I can't stop coughing. → cold

### a2.vocab_travel_transport — Travel and transport [extra]
Can do: Buy tickets and understand basic travel information.
Depth: light
Weight: 1
Words: ticket, luggage, bag, suitcase, train, bus, plane, airport, station, platform, map, hotel, holiday, tour, passenger, flight, delay, arrive, leave, catch
Check:
- Meaning: a big bag you take on holiday → suitcase
- Meaning: the place at a station where you wait for the train → platform
- Complete: We must be at the ___ two hours before the flight. → airport

### a2.vocab_clothes — Clothes and accessories [extra]
Can do: Say what someone is wearing or what I want to buy.
Depth: light
Weight: 1
Words: shirt, t-shirt, trousers, jeans, dress, skirt, jacket, coat, shoes, boots, trainers, socks, hat, glasses, wear, try on, size, large, medium, small
Check:
- Meaning: long clothes for your legs, not shorts → trousers
- Meaning: you wear them on your feet inside your shoes → socks
- Complete: It's cold outside, put on your ___. → coat / jacket

---

## Retirades

- `a2.restaurant` → substituïda per `a2.shopping_restaurant`.
- `a2.describing_people`, `a2.first_conditional`, `a2.adverbs_frequency_time`: eren a l'esborrany inicial i es van retirar abans que cap alumne les usés; els ids es poden reutilitzar.
