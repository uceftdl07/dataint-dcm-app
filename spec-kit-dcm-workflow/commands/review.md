---
description: "Quality review — gates + skills; --commit writes the mandatory pre-commit stamp"
tools:
  - bash
  - read
  - read_file
  - list_dir
  - execute
  - create_file
  - edit
---

# DCM Review — qualité avant commit et avant PR

Deux modes, même moteur (`dcm-review.sh` + revue de skills) :

| Mode | Quand | Sortie |
|------|-------|--------|
| *(défaut)* | avant PR branche fille → `develop`, ou au checkpoint Review d'implement | rapport + verdict |
| `--commit` | **obligatoire avant chaque `git commit`** | rapport + verdict + **stamp** qui débloque le commit |

```bash
spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step review   # préférence, pas un lock
```

## User Input

$ARGUMENTS

| Flag | Effet |
|------|-------|
| `--commit` | mode pre-commit : revue du diff **staged**, puis écriture du stamp |
| `--task T001` | charge le sub-spec + le package de la task |
| `--spec <feature-dir>` · `--package <dir>` | contexte explicite |
| `--duplication` · `--sonar` | jscpd / sonar-scanner si disponibles (mode défaut) |
| `--allow-warn` | stamp `WARN` — seulement si `review.before_commit_require_pass: false` |
| `--skip-gates` | revue de skills seule (déconseillé) |
| `--dry-run` | affiche les findings, n'écrit pas de stamp |

## Étape 1 — Contexte

```bash
git rev-parse --abbrev-ref HEAD
git status --short
git diff --cached --stat --name-only        # mode --commit
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks
```

Lire si présents : `FEATURE_DIR/dispatch-manifest.json` (branche ↔ `task_id`),
`intake.json` (packages par domaine), `stories/T00X-*.md` (critères d'acceptation).
Mapper la branche courante sur sa task (`frontend/011-workspace-name-display` → T001).

En `--commit` avec rien de staged : reviewer `git diff` + les untracked du package, ou
demander de `git add` d'abord.

Package : depuis le domaine de la task, ou `--package`. `frontend` →
`packages/dcm-frontend`, `backend` → `packages/dcm-backend`, `dataeng` → la section
`## Files` du sub-spec.

## Étape 2 — Gates automatisés

```bash
REPORT="specs/{feature}/review-report-{task_id}.md"

spec-kit-dcm-workflow/scripts/dcm-review.sh \
  --package {PACKAGE_DIR} \
  --base develop \
  --report "$REPORT" \
  ${COVERAGE_MIN:+--coverage-min $COVERAGE_MIN} ${DUPLICATION:+--duplication} ${SONAR:+--sonar}
```

**Retenir ce chemin** : c'est le fichier que l'étape 4 passera à `--report`, et le stamp est
refusé si le rapport n'existe pas ou si son verdict diffère de celui déclaré.

Gates lus depuis `dcm-config.yml` → `review.gates` : **lint** (eslint / ruff), **types**
(tsc / mypy, sur le module dérivé du `pyproject.toml` du package), **tests** (vitest /
pytest), **coverage** si `coverage_min`, **duplication** et **sonar** optionnels.
Verdict : **PASS** | **WARN** | **FAIL**.

Changements **extension / docs seuls** (`spec-kit-dcm-workflow/` uniquement) : sauter les
gates de package, faire la checklist ci-dessous — un PASS avec notes est légitime. Dans ce
cas, et avec `--skip-gates`, c'est à toi d'écrire le rapport ; il doit contenir une ligne
de verdict lisible par le gate :

```markdown
**Verdict**: **PASS**
```

## Étape 3 — Revue de skills (agent)

Charger les skills du domaine : frontend → `dcm-react`, backend / dataeng → `dcm-python`,
plus **`dcm-testing`** et **`dcm-verify`** dans tous les cas
(`.claude/skills/dcm-*/SKILL.md`, ou `.agents/skills/` sous Copilot).

```bash
git diff --cached                    # mode --commit
git diff origin/develop...HEAD -- {PACKAGE_DIR}     # mode défaut
```

Checklist :

1. Aucun secret, `.env` ou credential dans le diff.
2. Anti-patterns de la skill (handlers sync, imports relatifs, secrets…).
3. Chaque **critère d'acceptation** du sub-spec couvert par du code ou un test.
4. Fichiers modifiés ⊆ périmètre du package dans l'intake — pas de refacto hors sujet.
5. Tests présents pour tout changement de comportement (ou report explicite en note).
6. **Small PR** : le diff reste relisible — signaler un churn massif sans rapport.
7. Story Jira éventuelle : elle porte un **nom de branche**, pas un SHA de commit.

Findings, une ligne chacun :

```
packages/dcm-frontend/src/components/Header.tsx:42: 🟡 risk: affiche workspace_id au lieu de display_name — utiliser resolveWorkspaceDisplayLabel()
```

`🔴 blocker` · `🟡 risk` · `🟢 note`.

## Étape 4 — Verdict

| Situation | Verdict |
|-----------|---------|
| gates FAIL, ou au moins un 🔴 | **FAIL** |
| gates PASS, seulement 🟡 / 🟢 | **PASS** |
| gates WARN, aucun blocker | **WARN** |

Récap : branche, package, verdict, tableau des gates, nombre de findings par niveau,
chemin du rapport.

### Mode défaut — suite

```
○ OK        → /speckit.dcm.publish-pr --spec {feature} --task {task_id}
○ Fix       → je corrige puis re-review
○ Ignorer   → PR quand même (déconseillé, aux risques de l'utilisateur)
```

Sur **FAIL**, ne pas proposer la PR tant que les gates ne sont pas verts, sauf refus
explicite de l'utilisateur. La PR elle-même passe par `commands/publish-pr.md` (MCP
GitHub requis).

### Mode `--commit` — stamp

```bash
spec-kit-dcm-workflow/scripts/dcm-pre-commit-review-stamp.sh write \
  --verdict {PASS|WARN|FAIL} \
  --report "$REPORT" \
  --notes "résumé des findings"
```

`--report` est **obligatoire** et pointe sur le rapport de l'étape 2. Le script refuse
d'écrire (exit 2) si le fichier est absent, vide, sans ligne de verdict, ou si ce verdict
n'est pas celui passé à `--verdict` : le stamp atteste d'une revue, il ne la remplace pas.
Un `--verdict PASS` sur un rapport qui dit FAIL est rejeté.

Le stamp est `.specify/pre-commit-review-stamp.json` (gitignoré), lié au **hash du diff
staged** : restager du code l'invalide. Il enregistre aussi le chemin et le hash du
rapport. Ne jamais l'écrire ni l'éditer à la main.

Sur **FAIL** → demander la correction et **ne pas** dire à l'utilisateur qu'il peut
commiter. Sur **PASS** (ou **WARN** si la config l'autorise) → annoncer le verdict, les
findings, et que `git commit` est débloqué.

## Le gate `git commit`

Un seul stamp partagé, quel que soit l'agent qui a fait la revue :

| Couche | Mécanisme | Bloquant ? |
|--------|-----------|------------|
| cette commande | produit le stamp | non — c'est elle qui débloque |
| `git commit` (tous, y compris hors agent) | `.git/hooks/pre-commit` → `dcm-pre-commit-review-stamp.sh check` | **oui**, exit 1 |
| Claude Code, `git commit` via Bash | `.claude/hooks/` `PreToolUse` → `permissionDecision: deny` | **oui**, avant même le hook git |
| PR → `develop` | revue humaine + `@claude` en commentaire | **non** — convention d'équipe, aucun workflow ne se déclenche sur `pull_request` |

C'est donc ce gate local qui porte la charge, pas la CI. Installation par machine :
`./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh` (pose le hook Claude Code **et**
`.git/hooks/pre-commit` ; si le framework `pre-commit` est présent il est utilisé à la
place du standalone, ce qui fait tourner en plus `black` / `ruff` / `commitizen`).

Bypass réservé aux urgences, et à annoncer : `DCM_SKIP_PRE_COMMIT_REVIEW=1 git commit …`.
`git commit --no-verify` saute **tous** les hooks — donc personne n'a relu le diff.

Config (`dcm-config.yml` → `review`) : `enabled`, `before_commit`,
`before_commit_require_pass` (un stamp WARN ne suffit pas),
`copilot_auto_review_required` (convention PR, pas un gate).

## Troubleshooting

| Problème | Correction |
|----------|------------|
| Tests frontend rouges en local | `cd packages/dcm-frontend && npm test` |
| Aucun fichier modifié vs base | branche non pushée, ou mauvaise base d'intégration |
| `git commit` refusé après une revue | le diff staged a changé depuis le stamp — relancer `--commit` |
| Sonar SKIP | définir `SONAR_TOKEN`, ajouter `sonar-project.properties` |
| jscpd SKIP | `npm i -g jscpd`, ou ne pas passer `--duplication` |
