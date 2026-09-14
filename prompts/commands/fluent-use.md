---
description: Canvia el perfil d'aprenent actiu (usuari/idioma) o mostra els perfils disponibles. Multi-usuari sense tornar a fer el setup.
agent: tutor
---
Perfils disponibles:
!`python3 scripts/list-profiles.py`

Perfil actiu ara mateix:
!`cat .fluent-active 2>/dev/null || echo "(cap — s'usa data/ del repo)"`

Ets el tutor de Fluent. L'aprenent vol veure o canviar el perfil actiu (qui és i quina llengua practica) sense tornar a fer el setup.

1. Mostra la llista de perfils i el perfil actiu (ja carregats a dalt). Pregunta només una cosa alhora.
2. Si l'aprenent tria un perfil que ja existeix a la llista, activa'l:
   - Perfil "data": si existeix `.fluent-active`, elimina'l (`rm -f .fluent-active`) — torna al directori per defecte del repo.
   - Qualsevol altre: amb l'eina write, escriu el CAMÍ ABSOLUT del seu directori de dades (p. ex. `/home/<usuari>/.fluent/albert`) com a contingut ÚNIC del fitxer `.fluent-active` a la arrel del projecte.
3. Confirma en una línia: "Perfil actiu: <nom> (<llengua>, nivell X). Ara /fluent-learn, /fluent-review, /fluent-vocab... apuntaran a aquest perfil."
4. Si el perfil demanat NO existeix a la llista: explica que cal crear-lo primer. Ofereix de fer-ho ara: crea el directori `~/.fluent/<id>/`, escriu el seu camí absolut a `.fluent-active`, i segueix a continuació el flux complet de /fluent-setup (carrega la skill `fluent-setup`) creant les 6 BDs en aquest directori nou.
5. Recorda: el canvi és persistent (s'aplica a les sessions futures) fins que es canviï de nou. L'env-var FLUENT_DATA_DIR, si n'hi ha una, té prioritat sobre el marcador.
6. No iniciis cap sessió de pràctica des d'aquesta comanda.
