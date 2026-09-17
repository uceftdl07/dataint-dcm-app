## Workflow DCM (spec-kit) — extension `dcm` v{DCM_VERSION}

Workflow spec-driven : toute feature passe par `specs/{NNN}-{slug}/`.
Doc unique : [GUIDE.md](spec-kit-dcm-workflow/GUIDE.md) · schémas JSON : [CONTRACTS.md](spec-kit-dcm-workflow/CONTRACTS.md) · tokens : [USAGE-AND-TOKENS.md](spec-kit-dcm-workflow/USAGE-AND-TOKENS.md)

```
/speckit.dcm.specify "..."   → intake de scope, puis spec.md
/{speckit}plan                → plan.md (prérequis validés par plan-guide)
/{speckit}tasks               → tasks.md + stories/
/speckit.dcm.dispatch        → Epic + Stories Jira + branches filles
/{speckit}implement T001      → une task, un checkpoint
/speckit.dcm.sync-status     → tasks [x] → Jira Done
```

Deux conventions de nommage cohabitent, et ce n'est pas un défaut d'installation :

- Les **commandes DCM** (`speckit.dcm.*`) sont générées comme fichiers → toujours en `.`.
- Les **commandes spec-kit de base** sont installées en skills sur Claude Code
  (`.claude/skills/speckit-plan/`) → en `-`. spec-kit ≥ 0.11 ne permet pas de choisir :
  `ClaudeIntegration` est une `SkillsIntegration` et `--no-skills` est refusé. Les noms
  ci-dessus sont déjà rendus pour cet hôte.

Chaque workflow a **un seul nom par hôte**, celui affiché ici — pas d'alias. Si un nom ne
résout pas, relancer `./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh`.

Un hook annoncé `/speckit-dcm-…` désigne la commande `/speckit.dcm.…` : les skills de base
convertissent les points en tirets pour construire le slash, mais seule la forme pointée
existe. Invoquer la forme pointée — il n'existe pas de variante en tirets.

### Ce qui bloque réellement

Les hooks de `extension.yml` sont **indicatifs** : spec-kit ne les exécute pas. Seuls ces
scripts ont un pouvoir d'arrêt, par leur code de sortie :

| Gate | Effet |
|------|-------|
| `scripts/dcm-precheck.sh --gate specify\|plan\|tasks\|implement` | exit 2 = ne pas continuer |
| `scripts/dcm-branch-sync-check.sh` | **lecture seule** — exit 2 = `BEHIND` ou `SYNC FAILED`. Ne rebase que si on l'appelle avec `--sync` |
| `scripts/dcm-conflict-check.sh` | non-zéro = chevauchement avec un autre Epic actif |
| `.claude/hooks/dcm-before-commit-review.sh` + `.git/hooks/pre-commit` | `git commit` refusé sans stamp de review |

**Avant tout `git commit`** : `/speckit.dcm.review --commit`, qui produit le stamp
`.specify/pre-commit-review-stamp.json` lié au hash du diff *staged* — restager l'invalide.
Ne jamais le contourner avec `--no-verify`, ne jamais l'écrire à la main.

### Conventions

- Branches filles `{domain}/{spec_num}-{slug}` depuis `origin/develop` à jour → PR vers
  `develop`, **petites** (moins de fichiers changés, revue plus simple).
- Lire `tasks.md` **uniquement** via `scripts/dcm-parse-tasks.sh --spec <folder> [--json]` :
  exit 2 = le fichier existe mais aucune ligne n'est conforme, ce qui n'est pas « rien à faire ».
- Domaine `dataeng` → subagent `dp-data-databricks-engineer` (délégation bloquante). Il vient
  du plugin APM `…/dp-ai-tools/plugins/data-integration`, à installer par hôte (`--target`).
- Revue d'agent sur une PR → `develop` : **convention d'équipe**, aucun workflow ne se
  déclenche sur `pull_request`.
- Beaucoup de clés de `dcm-config.yml` sont **descriptives** — vérifier qu'un script la lit
  avant de promettre qu'un réglage a un effet.
- Tokens : encadrer une étape avec `dcm-step-start.sh` puis `dcm-track-session.sh`, sinon
  `/speckit.dcm.usage-report` rend un rapport vide.
