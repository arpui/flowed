# `prompts/` — el comportament del tutor

Tot el que decideix **com ensenya** Fluent viu aquí, en Markdown. El servidor
(`server/src/agent.ts` i `server/src/commands.ts`) ho llegeix directament a cada
torn: canviar el comportament no requereix tocar codi ni reiniciar res.

| Fitxer | Rol |
|---|---|
| `agents/learner.md` | L'agent de la web: permisos tancats, to i límits per a l'alumne final |
| `agents/tutor.md` | L'agent complet (model deep) per a les comandes llargues |
| `agents/tutor-fast.md` | El mateix en mode ràpid (model face, amb *fallback* al deep) |
| `agents/rules.md` | **Font única** de les regles dures — identitat de llengua, no repetir, alternança, prompts no circulars. El servidor la concatena a TOTS els agents, cada torn |
| `commands/fluent-*.md` | Les 10 comandes. *Frontmatter* `agent:` (qui la respon) i directives `` !`…` `` que precarreguen l'estat de l'alumne |

El *system prompt* d'un torn és: `AGENTS.md` + `LEARNING_SYSTEM.md` +
`agents/<agent>.md` + `agents/rules.md`. Els skills (`skills/`) no hi
són: el model els carrega sota demanda amb l'eina `skill`.

## Història del nom

Fins al 2026-09-13 això era `.opencode/`, perquè el projecte s'executava sobre
opencode i aquell era el camí que ell descobria. Amb el servidor propi ja no
calia, i el nom enganyava. El que era específic d'opencode (el seu plugin,
`opencode.json` i el llançador de models gratuïts) és a
`obsolet/opencode-runtime/`; per tornar-hi caldria desfer el renombrat.

`.claude/` es manté com està perquè allà el nom **sí** que és funcional: és el
que Claude Code descobreix per instal·lar Fluent com a plugin.
