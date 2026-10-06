---
description: Canvia el perfil d'aprenent actiu (usuari/nivell) o mostra els perfils disponibles. Multi-usuari sense tornar a fer el setup.
agent: tutor
---
Perfils disponibles:
!`python3 scripts/list-profiles.py`

Perfil actiu ara mateix:
!`cat .flowed-active 2>/dev/null || echo "(cap — s'usa data/ del repo)"`

Ets el tutor de FlowMath. L'aprenent vol veure o canviar el perfil actiu (qui és i quines matemàtiques practica) sense tornar a fer el setup.

1. Mostra la llista de perfils i el perfil actiu (ja carregats a dalt). Pregunta només una cosa alhora.
2. Si l'aprenent tria un perfil que ja existeix a la llista, activa'l:
   - Perfil "data": si existeix `.flowed-active`, elimina'l (`rm -f .flowed-active`) — torna al directori per defecte del repo.
   - Qualsevol altre: amb l'eina write, escriu el CAMÍ ABSOLUT del seu directori de dades (p. ex. `/home/<usuari>/.flowmath/naia-math`) com a contingut ÚNIC del fitxer `.flowed-active` a la arrel del projecte.
3. Confirma en una línia: "Perfil actiu: <nom> (matemàtiques, nivell X). Ara /math-learn, /math-review, /math-vocab... apuntaran a aquest perfil."
4. Si el perfil demanat NO existeix a la llista: explica que cal crear-lo primer (l'administrador, amb `scripts/new-user.sh`). No creïs tu el directori: escriu només el camí absolut d'un perfil JA existent a `.flowed-active`, i segueix el flux de /math-setup (carrega la skill `math-setup`) per omplir les 6 BDs si el perfil encara no està configurat.
5. Recorda: el canvi és persistent (s'aplica a les sessions futures) fins que es canviï de nou. L'env-var FLOWED_DATA_DIR, si n'hi ha una, té prioritat sobre el marcador.
6. No iniciis cap sessió de pràctica des d'aquesta comanda.
