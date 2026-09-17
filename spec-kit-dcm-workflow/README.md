# Spec Kit — DCM Team Workflow Extension

Framework spec-driven DCM : **intake de scope**, **un sub-spec par story**, commandes speckit
natives, Jira + branches filles. Extension **2.9.2**.

**IDEs supportés : Claude Code et GitHub Copilot (VS Code) uniquement** — pas Cursor.
Voir [COMMANDS.md](./COMMANDS.md) (English) et [GETTING-STARTED.md](./GETTING-STARTED.md).

Cette page est un index. Tout le reste est dans **une** doc par sujet — si une information est
ici *et* ailleurs, c'est l'autre qui fait foi.

| Doc | Contenu |
|-----|---------|
| **[GETTING-STARTED.md](./GETTING-STARTED.md)** | **commencer ici** : installer la CLI spec-kit, `specify init`, l'extension, MCP, puis lancer sa première commande — pas à pas pour **Claude Code et GitHub Copilot** |
| **[GUIDE.md](./GUIDE.md)** | flow, install, commandes, branches, hooks, gates, multi-Epics, dépannage |
| **[COMMANDS.md](./COMMANDS.md)** | **English** — Claude Code & Copilot command reference (not Cursor), flags, hooks, workflow order |
| [CONTRACTS.md](./CONTRACTS.md) | schémas des JSON échangés entre commandes, writers/readers, et les divergences réellement constatées sur disque |
| [USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md) | `usage-log.jsonl`, collecte des tokens, préférences de modèle par step |
| `commands/*.md` | le corps de chaque commande — la source de vérité de son comportement (Claude Code + Copilot) |
| [commands/README.md](./commands/README.md) | **English** — index des 9 commandes, où elles sont générées par hôte |
| `dcm-config.template.yml` | tous les réglages, commentés |

## Flow

```
/speckit.dcm.specify "..." → intake (type, domaines, tickets) puis spec.md
/{speckit}clarify           → recommandé, pas imposé
/{speckit}plan              → hook before_plan = gate Prerequisites
/{speckit}tasks             → tasks.md + stories/ depuis la spec, sans questions
/speckit.dcm.dispatch      → 1 Epic + N Stories Jira + branches depuis develop à jour
/{speckit}implement T001    → une task, un checkpoint
/speckit.dcm.review --commit → obligatoire avant chaque git commit
/speckit.dcm.sync-status   → tasks [x] → Jira Done
```

`{speckit}` = `speckit-` sur Claude Code, `speckit.` sur Copilot — les commandes de base sont
installées en skills sur Claude Code et un nom de skill ne peut pas contenir de point. Les
commandes DCM, générées comme fichiers, gardent le `.` sur les deux hôtes.
Détail : [GUIDE.md § Notation `{speckit}`](./GUIDE.md).

## Installation

```bash
./spec-kit-dcm-workflow/scripts/install.sh        # tout-en-un, idempotent
./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh   # regénère les artefacts seuls
./spec-kit-dcm-workflow/scripts/dcm-selftest.sh   # les gates se comportent-ils comme documenté ?
```

Ces deux scripts supposent la CLI `specify` installée **et** `specify init` déjà passé sur le
dépôt **pour votre hôte** — `--integration claude` **ou** `--integration copilot`, un dépôt
n'en porte qu'une — sinon il manque les commandes de base. `install.sh` génère les deux couches,
Claude Code *et* Copilot, quel que soit l'hôte que vous utilisez. Parcours complet depuis zéro :
[GETTING-STARTED.md](./GETTING-STARTED.md). Rien de tout cela n'arrive avec un `git pull` :
`.specify/`, `.claude/`, `CLAUDE.md`, `.github/agents/`, `.github/prompts/`, `.agents/skills/` et
`.vscode/` sont gitignorés, donc **chaque** arrivant installe sur sa machine.

## Ce qui bloque réellement

Les hooks spec-kit sont **indicatifs** — le CLI ne les exécute pas lui-même. Ce qui arrête
vraiment, ce sont des scripts à code de sortie : `dcm-precheck.sh --gate`,
`dcm-branch-sync-check.sh`, `dcm-conflict-check.sh`, et le gate `git commit`
(`.git/hooks/pre-commit` + hook Claude Code). Toute règle non contournable va là.
Voir [GUIDE.md](./GUIDE.md) § 11.
