# Currículum d'Àlgebra Operativa per a 1r d'ESO: De l'Aritmètica a l'Àlgebra

Aquest document recull l'enfocament competencial per a la introducció a l'àlgebra a 1r d'ESO. El focus es posa en l'**operativa, la sintaxi i l'agilitat algorísmica**, diferenciant-ho temporalment de la modelització matemàtica abstracta de sistemes reals, que requereix una maduresa cognitiva posterior.

---

## 1. Marc Competencial i Sabers Associats

Aquesta fase introductòria s'avalua a través de la següent competència i saber fonamental:

### Competència 4: Representació, Comunicació i Sintaxi
Codificar i descodificar el llenguatge algebraic de manera purament mecànica i operativa.
*   **Objectiu:** Comprendre la sintaxi formal de la matemàtica. L'alumne ha d'entendre que les lletres operen sota les mateixes regles i propietats que els nombres, aprenent a respectar la prioritat de les operacions i l'agrupació de termes similars.

### Saber Bàsic: Sentit Algebraic (Destreses i algorismes)
*   **Objectiu:** Reconeixement de patrons estructurals elementals i aplicació fluida d'algorismes de resolució. Es tracta de construir la "caixa d'eines" mecànica necessària (propietat distributiva, factor comú) perquè l'operativa no suposi un fre quan s'arribi a la resolució completa d'equacions en cursos superiors.

---

## 2. Desplegament Operatiu: Les subcompetències en acció

A continuació es detalla com es materialitza aquesta competència en exercicis pràctics progressius, que actuen com un joc de manipulació (dels nombres a les lletres) sense necessitat d'arribar a aïllar completament variables.

### A. Sintaxi i Agrupació (Iniciació a la Representació)
L'alumne consolida l'estructura identificant que només es poden agrupar elements de la mateixa naturalesa.

*   **Commutativa i Associativa amb lletres:** 
    Les lletres iguals es poden sumar entre elles; els nombres sols van per la seva banda.
    *   *Exemple directe:* 3x + 5 + 2x  -->  (3x + 2x) + 5 = 5x + 5
    *   *Exemple mixt:* 4y + 7z + 2y + z  -->  (4y + 2y) + (7z + z) = 6y + 8z

*   **El Valor Numèric (Mecànica de substitució):** 
    Tractar la lletra com una casella on s'insereix un valor, forçant a aplicar correctament la jerarquia d'operacions.
    *   *Exemple:* Donada l'expressió 2a - 3b, calcula'n el resultat si a = 5 i b = 2.

### B. Aplicació de Propietats Algebraiques (La Distributiva)
Mecanitzar la propietat distributiva com una regla de transformació d'estructures, partint de l'aritmètica cap a l'àlgebra.

*   **Operativa numèrica (desplegar per simplificar):**
    *   *Exemple:* 5 · (10 + 3)  -->  5 · 10 + 5 · 3 = 50 + 15 = 65
*   **Operativa literal (desplegant paquets):** El nombre de fora multiplica absolutament tot el que hi ha dins.
    *   *Exemple:* 3 · (x + 4)  -->  3 · x + 3 · 4 = 3x + 12
    *   *Gestió del signe:* -2 · (x + 4)  -->  -2x - 8

### C. Reconeixement de Patrons: El Factor Comú
Aquest és el pas algorísmic estrella: identificar què es repeteix a tots els termes (el pas invers a la distributiva) per modificar l'estructura de l'expressió sense resoldre-la.

*   **Nivell 1 (Factor comú numèric ocult):** Buscar la taula de multiplicar compartida.
    *   *Referència prèvia:* 7 · 8 + 7 · 2  -->  7 · (8 + 2) = 70
    *   *Aplicació algebraica:* 8x + 12  -->  (taula del 4)  -->  4 · 2x + 4 · 3  -->  4(2x + 3)

*   **Nivell 2 (Factor comú literal):** Extracció de lletres que es repeteixen a tot arreu.
    *   *Exemple bàsic:* ax + bx  -->  x(a + b)
    *   *Combinat (número i lletra):* 4x + xy  -->  x(4 + y)

*   **Nivell 3 (Potències com a paquet repetit):** 
    Introducció al fet que x^2 és operativament x · x.
    *   *Exemple:* x^2 + 5x  -->  x · x + 5 · x  -->  x(x + 5)