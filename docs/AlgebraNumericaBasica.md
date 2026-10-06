# Document de Treball: El Joc de les Propietats (Dels Nombres a les Lletres)

Aquest document entrena l'agilitat operativa. L'objectiu no és "trobar quant val la lletra", sinó aprendre a manipular les expressions per fer-les més curtes o més fàcils de calcular. 

## BLOC 1: El Joc dels Nombres (Càlcul Intel·ligent)
*Objectiu: Arribar a un resultat numèric final modificant l'estructura de l'operació per fer-la més fàcil.*

**1. Propietats Commutativa i Associativa (Moure i Agrupar)**
En lloc d'operar d'esquerra a dreta, busca les parelles que sumin 10 o multipliquin nombres rodons.
* **Exemple Suma:** $13 + 25 + 7 \rightarrow (13 + 7) + 25 = 20 + 25 = 45$
* **Exemple Multiplicació:** $4 \cdot 17 \cdot 25 \rightarrow (4 \cdot 25) \cdot 17 = 100 \cdot 17 = 1700$
* **El teu torn:**
  * $2 + 48 + 18 =$
  * $5 \cdot 33 \cdot 2 =$

**2. Propietats Distributiva (Desplegar per simplificar)**
Multiplicar per un nombre gran és difícil. Trenca'l en dos de més fàcils.
* **Exemple:** $5 \cdot (10 + 3) \rightarrow 5 \cdot 10 + 5 \cdot 3 = 50 + 15 = 65$
* **El teu torn:** 
  * $4 \cdot (20 + 5) =$
  * $6 \cdot (10 - 2) =$

**3. Factor Comú Numèric (Agrupar per calcular ràpid)**
Si multipliques dues coses pel mateix nombre i després les sumes, pots treure aquest "factor comú" a fora per estalviar-te passos.
* **Exemple:** $7 \cdot 8 + 7 \cdot 2 \rightarrow 7 \cdot (8 + 2) = 7 \cdot 10 = 70$
* **El teu torn:**
  * $8 \cdot 6 + 8 \cdot 4 =$
  * $3 \cdot 15 - 3 \cdot 5 =$

---

## BLOC 2: L'entrada de les Lletres (Mateixes Regles)
*Objectiu: Operar combinant nombres i lletres ($x, y, z$). Com que no sabem el valor de la lletra, el resultat final serà una expressió simplificada (una barreja de números i lletres), no un nombre sol.*

**4. Commutativa i Associativa amb lletres (Agrupar "coses" iguals)**
Les lletres iguals es poden sumar entre elles; els nombres sols van per la seva banda.
* **Exemple:** $3x + 5 + 2x \rightarrow (3x + 2x) + 5 = 5x + 5$
* **Exemple mixt:** $4y + 7z + 2y + z \rightarrow (4y + 2y) + (7z + z) = 6y + 8z$
* **El teu torn:**
  * $4x + 10 + 3x =$
  * $5x + 2y - x + 4y =$

**5. Distributiva amb lletres (Desplegant els paquets)**
El nombre de fora multiplica absolutament tot el que hi ha dins del parèntesi.
* **Exemple:** $3 \cdot (x + 4) \rightarrow 3 \cdot x + 3 \cdot 4 = 3x + 12$
* **Exemple negatiu:** $2 \cdot (3y - 5) \rightarrow 2 \cdot 3y - 2 \cdot 5 = 6y - 10$
* **El teu torn:**
  * $5 \cdot (x + 2) =$
  * $4 \cdot (2z - 3) =$

**6. Factor Comú amb lletres (El pas estrella)**
Busca què es repeteix a tots els termes. Ara no només pot ser un número amagat (una taula de multiplicar), sinó que també pot ser que **una lletra es repeteixi** a tot arreu.

* **Nivell 1 (Només lletra):** $ax + bx \rightarrow$ (la $x$ es repeteix) $\rightarrow x(a + b)$
* **Nivell 2 (Lletra i número combinat):** $4x + xy \rightarrow$ (la $x$ es repeteix) $\rightarrow x \cdot 4 + x \cdot y \rightarrow x(4 + y)$
* **Nivell 3 (Només número amagat):** $8x + 12 \rightarrow$ (taula del 4) $\rightarrow 4 \cdot 2x + 4 \cdot 3 \rightarrow 4(2x + 3)$
* **Nivell 4 (Potències):** Recorda que $x^2$ vol dir $x \cdot x$. 
  $x^2 + 5x \rightarrow x \cdot x + 5 \cdot x \rightarrow x(x + 5)$
  
* **El teu torn:**
  * $7x + 7y =$
  * $10x + 15 =$ 
  * $3x + xz =$
  * $x^2 + 9x =$