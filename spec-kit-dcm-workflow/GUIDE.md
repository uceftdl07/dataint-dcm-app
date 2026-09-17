# Guide DCM Workflow — de A à Z

Doc de référence de l'extension : flow, install, branches, commandes, gates. Les schémas des
JSON échangés sont dans [CONTRACTS.md](./CONTRACTS.md), les tokens dans
[USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md), et le comportement exact de chaque commande dans
son propre `commands/*.md`.

### Notation `{speckit}` — le nom des commandes de base dépend de l'hôte

| | Commandes DCM | Commandes spec-kit de base |
|---|---|---|
| **Claude Code** | `/speckit.dcm.tasks` | `/speckit-tasks` |
| **Copilot** | `/speckit.dcm.tasks` | `/speckit.tasks` |

Les commandes DCM sont générées comme **fichiers** (`.claude/commands/speckit.dcm.tasks.md`,
`.github/prompts/speckit.dcm.tasks.prompt.md`) : un nom de fichier accepte les points, donc
elles gardent le `.` partout. Les commandes de base, elles, sont installées en **skills** sur
Claude Code (`.claude/skills/speckit-tasks/`) et un nom de répertoire de skill ne peut pas
contenir de point. Le séparateur suit donc le *mode d'installation*, pas l'hôte :
`_invocation_style.py` de spec-kit place `claude` **et** `copilot` dans
`CONDITIONAL_SLASH_AGENTS`, mais `ClaudeIntegration` est une `SkillsIntegration` sans opt-out
(`--no-skills` est refusé) alors que `CopilotIntegration` reste en mode fichiers par défaut.

**Dans cette doc et dans toutes les sources partagées, `{speckit}` note ce préfixe variable** :
`speckit-` sur Claude Code, `speckit.` sur Copilot. `sync-dcm-extension.sh` le résout par hôte
au moment de générer les artefacts, donc ce que tu lis dans `.claude/` ou `.github/` est déjà
le bon nom. Pour aligner les deux hôtes sur `-`, installer Copilot en mode skills :
`specify init --here --integration copilot --integration-options="--skills"`.

---

## 1. Flow — une commande par étape

| Étape | Commande | Ce qui se passe |
|-------|----------|-----------------|
| 1 | `/speckit.dcm.specify "..."` (ou `/{speckit}specify` natif) | Questions type / domaines / packages / tickets **avant** `spec.md`, puis la spec — dont la section **Prerequisites** |
| 2 | `/{speckit}clarify` puis `/{speckit}plan` | Hook `before_plan` = gate Prerequisites (bloque si la section est absente ou vide) |
| 3 | `/{speckit}tasks` | `tasks.md` + un `stories/T00X.md` par task, depuis la spec, sans questions |
| 4 | `/speckit.dcm.dispatch` | Jira (description Markdown, champ **Git branch** = nom de branche, jamais un SHA) + branches depuis `develop` à jour |
| 5 | `/{speckit}implement T001` | Sync obligatoire avant de coder, une task, un checkpoint après chaque |
| 5b | `/speckit.dcm.review --commit` puis `git commit` | **Bloquant** — un seul stamp partagé (§ 11) |
| 6 | `/speckit.dcm.review` puis `/speckit.dcm.publish-pr` | Revue pre-PR, puis PR vers `develop` |
| 7 | `/speckit.dcm.sync-status` | Après merge de la PR : tasks `[x]` → Jira Done |
| 8 | `/speckit.dcm.usage-report` | Tokens et modèles par step |

**Pas sûr du scope ?** `/speckit.dcm.specify --intake-only` rejoue l'intake seul, à tout moment.

### Fichiers d'une feature

```
specs/001-feature/
├── intake.json / domain-scope.json   ← scope persisté (contrats § 1–3)
├── spec.md                           ← depuis templates/spec.md
├── plan.md                           ← si le work type le demande
├── tasks.md                          ← index des tasks, lu par un seul parseur
├── stories/T001-frontend-x.md        ← sub-spec par task : c'est là que vit le détail
├── merge-strategy.md                 ← si multi-dev
├── dispatch-manifest.json / jira-mapping.json / branches-created.json
└── usage-log.jsonl
```

### Lecture de `tasks.md` — un seul parseur

`scripts/dcm-parse-tasks.sh` (`--json` ou TSV) est le **seul** lecteur : dispatch,
sync-status, implement et `tasks` l'appellent, y compris pour valider le fichier qu'ils
viennent d'écrire. Il lit `git.domains` et `git.child_branch_pattern` dans la config au lieu
de les coder en dur, et sort **exit 2** si `tasks.md` existe sans aucune ligne conforme —
plutôt que « 0 task », qu'un appelant lirait comme « rien à dispatcher ».

Format attendu : `- [ ] T001 Frontend <titre> → [stories/T001-….md](stories/T001-….md)`
(`[~]` = en cours, `[x]` = fait).

### Work types

`feature` (capacité métier) · `technique` (refacto / infra) · `dette` · `hotfix` (prod urgent,
max 3 tasks) · `fixture` (tests, mocks, JSON). Choisi à l'intake ; un seul
`templates/spec.md` couvre les cinq, l'agent y supprime les blocs `[work_type: …]` des autres.

### Checkpoint d'implement

Après chaque task `[x]` : **Question** | **Continue** | **Stop** | **Review**. L'agent ne
démarre pas la task suivante sans un « Continue ».

---

## 2. Le modèle en une image

```
develop                       ← branche d'intégration (cible des PR)
 │
 ├── frontend/011-carousel-ui      ← branche fille (cut depuis develop à jour)
 ├── backend/011-scoring-endpoint  ← branche fille
 └── dataeng/011-feature-pipeline  ← branche fille
      │
      │  PRs directes → develop
      ▼
 develop → main               ← release (hors scope spec-kit)
```

**Règle d'or** : `1 spec = 1 Epic Jira = 1 dossier specs/NNN-*`. Chaque task = 1 Story Jira
+ 1 branche fille. **Pas de branche mère git** : le dossier `specs/NNN-*/` la remplace, ce qui
évite le double merge (fille → mère → develop) et les conflits en cascade.

Conflits git, au quotidien :

- **Avant de coder** (implement Step 4.5, bloquant) : `dcm-branch-sync-check.sh` — **lecture
  seule**, il dit si tu es en retard sur `origin/develop` sans rien réécrire. Si `BEHIND`,
  l'agent te demande, puis lance `--sync --strategy rebase` (ou `merge`). Aucun script DCM ne
  rebase ta branche sans que tu l'aies choisi.
- **Avant chaque PR** : `git fetch && git merge origin/develop` (merge, pas rebase, une fois la
  branche pushée et donc partagée).
- Multi-dev sur des fichiers communs : voir `merge-strategy.md` de la spec.
- Legacy : `branch_strategy: integration_branch` dans la config = ancien modèle mère + filles.

---

## 3. Installation (une fois par machine)

Pas-à-pas complet — CLI, `specify init` selon l'hôte, MCP, vérifications, pièges :
**[GETTING-STARTED.md](./GETTING-STARTED.md)**, qui fait foi sur le bootstrap. Résumé :

```bash
specify --version                                               # CLI spec-kit >= 0.8.0
specify init --here --integration claude --ignore-agent-tools   # OU --integration copilot
./spec-kit-dcm-workflow/scripts/install.sh                      # tout-en-un, idempotent
cat .specify/extensions/dcm/dcm-config.yml                      # GÉNÉRÉ — vérifier project.key
```

Rien de tout ceci n'arrive avec un `git pull` : `.specify`, `.claude/`, `CLAUDE.md`,
`.github/agents/`, `.github/prompts/`, `.agents/skills/` et `.vscode/` sont gitignorés.
**Chaque** arrivant installe sur sa machine — sinon il n'a ni les commandes, ni le gate de commit.

`.mcp.json` n'est **pas** généré automatiquement : l'écrire approuverait des endpoints distants
pour quiconque ouvre le dépôt. Sans MCP, `/speckit.dcm.dispatch` s'arrête avec
`epic.key: "pending_mcp"` plutôt que d'inventer une clé Jira.

Le gate de commit est posé par l'install. Optionnel, pour avoir **aussi** black/ruff/commitizen :

```bash
pipx install pre-commit && pre-commit install && ./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh
```

Deux scripts à connaître ensuite :

```bash
./spec-kit-dcm-workflow/scripts/sync-dcm-extension.sh   # regénère les artefacts générés seuls
./spec-kit-dcm-workflow/scripts/dcm-selftest.sh         # lecture seule, hors réseau
./spec-kit-dcm-workflow/scripts/dcm-selftest.sh --with-network --with-sync
```

`dcm-selftest.sh` vérifie que chaque gate **sort toujours le code documenté** (l'extension n'a
pas de suite de tests, et le contrat d'un gate *est* son code de sortie), plus la cohérence
déclarations ↔ disque : commandes déclarées et présentes, hooks qui nomment une commande
existante, template de spec qui passe le gate plan. `--with-sync` écrit — il regénère `.claude/`,
`.github/` et le paquet installé, puis vérifie l'idempotence.

---

## 4. Nomenclature des branches

| Élément | Format | Exemple |
|---------|--------|---------|
| Dossier spec | `specs/{num}-{short-name}/` | `specs/001-carousel-scoring/` — 3 chiffres, 2–4 mots kebab-case |
| Jira | 1 **Epic** par spec | `DCINT-200` |
| Branche fille | `{domain}/{spec_num}-{slug}` | `frontend/011-carousel-ui` |
| Domaine | premier mot de la task (ou tag `[DataEng]`) | `frontend`, `backend`, `dataeng` |
| Slug | reste du titre en kebab-case, 40 car. max | `carousel-ui` |
| Créée depuis | **`develop` à jour** | `git fetch && git checkout develop && git pull` |
| Cible de PR | **`develop`** | jamais une branche mère |
| Jira | 1 **Story** par task | liée à l'Epic |

Domaines reconnus (`git.domains`) : `frontend`, `backend`, `dataeng`, `devops`, `qa`. Un
premier mot non reconnu retombe sur `misc` **avec un warning** — la branche serait alors
`misc/…`, ce qui veut dire que le titre de la task doit être corrigé, pas que le repli est
acceptable.

### Subagents imposés à l'implement

Certains domaines délèguent obligatoirement l'implémentation (config
`implement.domain_subagents`, `domain_subagents_required: true`) : l'agent principal **ne code
pas** ces tasks.

| Domaine | Subagent | Claude Code | Copilot (VS Code) |
|---------|----------|-------------|-------------------|
| `dataeng` | dp-data-databricks-engineer | `Agent(subagent_type: "dp-data-databricks-engineer")` | `runSubagent(agentName: "dp-data-databricks-engineer")` |

L'agent ne vient **pas** de ce dépôt : il est fourni par le plugin APM
`TotalEnergiesCode/dp-ai-tools/plugins/data-integration`, que `install.sh` pose pour Copilot.

```bash
apm install TotalEnergiesCode/dp-ai-tools/plugins/data-integration --target copilot --only apm
apm install TotalEnergiesCode/dp-ai-tools/plugins/data-integration --target claude  --only apm
```

`--target` décide **où** le fichier d'agent atterrit, et seul cet hôte résout le subagent :
Copilot lit `.github/agents/`, Claude Code `.claude/agents/`. N'installer qu'un seul target laisse
donc l'autre hôte incapable de tenir la règle bloquante. `--only apm` évite la résolution des
dépendances MCP du plugin, qui échoue sur un nom de serveur non qualifié déclaré en amont.

L'agent route vers les skills Databricks officielles, que le plugin ne redistribue pas —
sans elles il tourne en mode dégradé (règles cyber, pas de syntaxe Databricks) :
`databricks aitools install --path .agents/skills` (Copilot) ou `--path .claude/skills`
(Claude Code). Vérification : skill `dp-data-databricks-setup`.

Si l'identifiant ne résout pas, c'est l'install qui manque — pas une raison de coder la task
soi-même. Détail : `commands/implement.md` Step 5.7.

---

## 5. Multi-Epics en parallèle

| Mécanisme | Rôle |
|-----------|------|
| Branches préfixées | `frontend/009-*` vs `frontend/010-*` — pas de collision de nom |
| `specs/active-epics.json` | Registre d'équipe (**versionné**) : domaines, packages, branches, statut |
| `dcm-conflict-check.sh` | Avant dispatch — détecte un recouvrement domaine/package, **échoue fermé** |
| `merge-strategy.md` | Section Cross-Epic Shared Files + ordre de merge |

```bash
./spec-kit-dcm-workflow/scripts/dcm-conflict-check.sh --spec 009-widget-inactive-cluster

./spec-kit-dcm-workflow/scripts/dcm-active-epics-update.sh \
  --spec 009-widget-inactive-cluster --title "..." --domains frontend \
  --packages packages/dcm-frontend --branches frontend/009-inactive-cluster-widget \
  --epic-key DCINT-200 --status in_progress

./spec-kit-dcm-workflow/scripts/dcm-active-epics-update.sh --spec 009-… --complete
```

**Règle d'équipe** : max 1 Epic owner par fichier partagé · merge `develop` quotidien sur les
branches filles · `--spec` obligatoire dès que 2 specs sont actives.

---

## 6. Exemple — feature « Carousel scoring »

Une feature, 3 devs (frontend, backend, dataeng), le lead lance la spec.

```bash
git checkout develop && git pull      # les branches filles seront cut d'ici
```

```
/speckit.dcm.specify Carousel scoring for DCM dashboard
/{speckit}plan
/{speckit}tasks
/speckit.dcm.dispatch
```

| # | Commande | Résultat |
|---|----------|----------|
| 1 | `/speckit.dcm.specify` | `specs/001-carousel-scoring/` : `spec.md` + `intake.json` (pas de branche git) |
| 2 | `/{speckit}plan` | `plan.md` — le hook valide **Prerequisites** |
| 3 | `/{speckit}tasks` | `tasks.md` + un `stories/T00X.md` par task |
| 4 | `/speckit.dcm.dispatch` | Epic `DCINT-200`, Stories `DCINT-201/202/203`, 3 branches filles poussées, `dispatch-manifest.json` |

`tasks.md` généré, au format que le parseur attend :

```markdown
- [ ] T001 Frontend carousel UI component → [stories/T001-carousel-ui.md](stories/T001-carousel-ui.md)
- [ ] T002 Backend scoring endpoint GET /api/v1/scores → [stories/T002-scoring-endpoint.md](…)
- [ ] T003 DataEng feature store pipeline → [stories/T003-feature-pipeline.md](…)
```

Le contenu de `dispatch-manifest.json`, `jira-mapping.json` et `branches-created.json` est
décrit champ par champ dans [CONTRACTS.md](./CONTRACTS.md) § 4–6.

Trois variantes du dispatch, une seule commande :

| Commande | Quand |
|----------|-------|
| `/speckit.dcm.dispatch` | Jira + branches |
| `--jira-only` | Epic + Stories seulement |
| `--branches-only` | branches git seulement |

---

## 7. Travail d'un dev sur sa branche fille

Identique pour les trois domaines — seuls la branche, le package et le ticket changent.

```bash
git fetch origin
git checkout frontend/011-carousel-ui      # voir dispatch-manifest.json

# Sync AVANT de coder (implement Step 4.5) — branche pas encore pushée → rebase
git rebase origin/develop

cd packages/dcm-frontend
# ... code ...

/speckit.dcm.review --commit               # obligatoire : produit le stamp
git commit -m "feat(frontend): carousel UI component with score badges"
git push -u origin frontend/carousel-ui
```

PR : `base: develop`, `compare: frontend/011-carousel-ui` — ou `/speckit.dcm.publish-pr`.
Après merge, cocher la task dans `tasks.md` puis `/speckit.dcm.sync-status` (la Story passe à
Done).

| ✅ Faire | ❌ Ne pas faire |
|----------|----------------|
| Travailler sur **ta** branche fille | Commiter direct sur `develop` |
| PR vers **`develop`** | PR vers une branche mère intermédiaire |
| `rebase origin/develop` **avant** de coder | Démarrer sur une branche en retard |
| `merge origin/develop` avant la PR | Laisser la branche diverger |
| Cocher la task + sync Jira après merge | Oublier le ticket |
| Petites PR | Une grosse PR multi-domaines |

---

## 8. Fin de feature et sync Jira

Marqueurs de `tasks.md` → statut Jira :

| Syntaxe | Local | Jira |
|---------|-------|------|
| `- [ ] T001 …` | pending | To Do |
| `- [~] T001 …` | in progress | In Progress |
| `- [x] T001 …` | completed | Done |

```
/speckit.dcm.sync-status                       # ou --spec 001-carousel-scoring
```

Lit `dispatch-manifest.json` + `tasks.md`, met à jour les Stories, journalise dans
`jira-sync-log.json`. Quand toutes les Stories sont Done, l'Epic passe à Done. Les branches
filles mergées peuvent être supprimées (`git push origin --delete <branche>`).

---

## 9. Récap des commandes

9 commandes, **un seul nom chacune**. Pas d'alias, pas de jumeau en skill : le CLI `specify`
enregistre une skill par nom *et* par alias, ce qui coûtait ~35 entrées de contexte par session
pour zéro portée supplémentaire.

| Commande | Qui | Quand, et flags utiles |
|----------|-----|------------------------|
| `/speckit.dcm.specify` | Lead | Intake puis `spec.md`. `--intake-only` = intake seul, `--reuse-intake` = garder le précédent |
| `/speckit.dcm.plan-guide` | — | Le gate `--gate plan` seul (hook `before_plan`) |
| `/speckit.dcm.tasks` | Lead | `tasks.md` + `stories/`. `--consolidate` (1 task/domaine), `--add` (task tardive, après dispatch), `--append` |
| `/speckit.dcm.implement` | Dev | Une task, une branche, un checkpoint |
| `/speckit.dcm.dispatch` | Lead | conflict-check + Jira + branches, en resume. `--jira-only`, `--branches-only`, `--dry-run`, `--force` |
| `/speckit.dcm.review` | Dev | Qualité. **`--commit` obligatoire avant chaque `git commit`** ; sans flag = pre-PR |
| `/speckit.dcm.publish-pr` | Dev | PR branche fille → `develop` |
| `/speckit.dcm.sync-status` | Tout dev | Après merge de la PR |
| `/speckit.dcm.usage-report` | Lead | Tokens + modèles par step |

Les commandes natives `/{speckit}specify`, `/{speckit}plan`, `/{speckit}tasks` et
`/{speckit}implement` restent le point d'entrée habituel : leurs hooks appellent la commande DCM
correspondante (§ 10).

---

## 10. Hooks (`.specify/extensions.yml`)

**Fichier généré — ne pas éditer.** `sync-dcm-extension.sh` le réécrit depuis le bloc `hooks:`
de `extension.yml`, donc les noms de commandes ne peuvent plus diverger de `provides.commands`.
C'était le seul artefact resté manuel, et il avait dérivé : après le renommage de la 2.8.0 il
pointait encore vers les anciens noms, qui ne résolvaient plus, alors que
`auto_execute_hooks: true` déclenchait quand même chaque hook. Si une autre extension
déclare des hooks dans ce fichier, le script **refuse** de le réécrire et affiche les noms à
recopier.

```yaml
hooks:
  before_specify:  { command: speckit.dcm.specify --intake-only, optional: false }
  before_plan:     { command: speckit.dcm.plan-guide,            optional: false }
  before_tasks:    { command: speckit.dcm.tasks,                 optional: false }
  before_implement:{ command: speckit.dcm.implement,             optional: false }
  after_tasks:     { command: speckit.dcm.dispatch,              optional: true  }
```

Un hook ne peut nommer qu'une commande **enregistrée** ; le reste de la chaîne est passé tel
quel, d'où le `--intake-only` : sans lui, le hook `before_specify` écrirait `spec.md` juste
avant que le `/{speckit}specify` natif ne l'écrive à son tour, et créerait un second dossier
`specs/NNN-*`.

---

## 11. Ce qui bloque réellement

Les hooks spec-kit sont **indicatifs** : `execute_hook()` renvoie la commande à lancer et
délègue à l'agent, donc `optional: false` est une consigne forte, pas une contrainte. Ce qui
arrête vraiment, ce sont des scripts à code de sortie — et toute règle qui ne doit pas être
contournable va là, pas dans les hooks :

| Gate | Effet |
|------|-------|
| `dcm-precheck.sh --gate specify\|plan\|tasks\|implement` | exit 2 = ne pas continuer |
| `dcm-branch-sync-check.sh` | exit 2 = `BEHIND` ou `SYNC FAILED` |
| `dcm-conflict-check.sh` | non-zéro = recouvrement avec un Epic actif ; échoue fermé |
| `dcm-parse-tasks.sh` | exit 2 = `tasks.md` au mauvais format ; 3 = config illisible |
| `.git/hooks/pre-commit` + hook Claude Code | `git commit` refusé sans stamp de review |

Ces gates sont **en lecture seule** : `dcm-branch-sync-check.sh` fetch et rapporte, il ne
rebase que si on l'appelle explicitement avec `--sync`. Un script dont le nom promet une
vérification ne réécrit pas l'historique de l'utilisateur de sa propre initiative.

### Le gate `git commit`

Squad mixte — Claude Code, Copilot, terminal — **même stamp**, mêmes règles.

```bash
/speckit.dcm.review --commit    # findings + stamp PASS, quel que soit l'agent
git commit …                    # refusé s'il n'y a pas de stamp PASS sur ce diff staged
```

| Couche | Mécanisme | Bloquant ? |
|--------|-----------|------------|
| `/speckit.dcm.review --commit` | produit le stamp | non — c'est elle qui débloque |
| `git commit`, y compris hors agent | `.git/hooks/pre-commit` → `dcm-pre-commit-review-stamp.sh check` | **oui**, exit 1 |
| Claude Code, `git commit` via Bash | `.claude/hooks/` `PreToolUse` → `permissionDecision: deny` | **oui**, avant même le hook git |
| PR → `develop` | revue humaine + `@claude` en commentaire | **non** — convention d'équipe |

Le stamp est `.specify/pre-commit-review-stamp.json` (gitignoré), lié au hash du diff
**staged** : restager du code l'invalide. `sync-dcm-extension.sh` installe le gate git ; si le
framework `pre-commit` est présent il l'utilise, sinon il pose `.git/hooks/pre-commit` en
standalone et **prévient sur stderr** que `black` / `ruff` / `commitizen` ne tournent pas.

⚠️ Aucune revue d'agent n'est déclenchée par l'ouverture d'une PR : le workflow
`cicd-template-workflow-review-claude.yml` se déclenche sur `issue_comment`, pas sur
`pull_request`, et n'est pas un check requis. `review.copilot_auto_review_required` dans la
config est donc une **convention**, pas un gate. Bypass d'urgence, à annoncer :
`DCM_SKIP_PRE_COMMIT_REVIEW=1 git commit …` — `--no-verify` saute **tous** les hooks, donc
personne n'a relu le diff.

---

## 12. Couche Claude Code

Claude Code ne lit **aucun** des artefacts générés pour Copilot (`.github/agents/`,
`.github/prompts/`, `.agents/skills/`) : il lit `.claude/` et `CLAUDE.md`.
`sync-dcm-extension.sh` génère donc une couche dédiée depuis `claude-code/` (sortie
per-machine, ces chemins étant gitignorés) :

| Généré | Rôle |
|--------|------|
| `.claude/commands/speckit.dcm.*.md` | les 9 commandes en slash commands, `allowed-tools` traduit depuis le frontmatter |
| `.claude/hooks/dcm-before-commit-review.sh` | gate `git commit` — hook `PreToolUse` sur `Bash` |
| `.claude/settings.json` | enregistre le hook + pré-autorise les helpers en lecture seule (**fusion**, jamais écrasement) |
| `CLAUDE.md` | bloc `<!-- BEGIN dcm-workflow -->` : flow, gates réels, conventions. Le reste du fichier est préservé |
| `.claude/skills/dcm-{python,react,verify,testing}/SKILL.md` | skills d'équipe, là où Claude Code les cherche |
| `.claude/agents/dp-data-databricks-engineer.agent.md` | subagent `dataeng` — **pas** généré par `sync-dcm-extension.sh` : posé par `apm install …/data-integration --target claude` (§ 4) |

Les skills `speckit-dcm-*` que le CLI `specify` enregistre sont **supprimées** au passage :
même corps de texte que la slash command, compté deux fois en contexte. La suppression n'a lieu
qu'après génération des commandes, donc un workflow ne peut pas devenir injoignable.

Différences à connaître :

- **Vocabulaire d'outils.** Le frontmatter des commandes est en vocabulaire Copilot
  (`read_file`, `execute`, `create_file`) ; la génération le traduit (`Read`, `Bash`, `Write`…)
  et n'ajoute les MCP qu'au niveau serveur (`mcp__atlassian`), pas outil par outil : un nom
  d'outil MCP erroné **refuserait** l'outil au lieu de le manquer.
- **Le hook ne dit jamais « allow ».** En Claude Code un `allow` court-circuite les règles de
  permission de l'utilisateur : le hook reste silencieux quand le stamp est bon, et ne répond
  `deny` que pour bloquer. Un stamp valide n'auto-approuve pas le commit.
- **Ce qui est pré-autorisé l'est au plus juste.** Les helpers en lecture seule le sont avec
  `:*` (tous leurs arguments) ; `dcm-selftest.sh` l'est **sans** `:*`, parce que son
  `--with-sync` régénère `.claude/`, `.github/` et le paquet installé — un run par défaut est
  inoffensif, celui-là passe par une demande. `dcm-pre-commit-review-stamp.sh` n'est pas
  pré-autorisé du tout : l'agent ne doit pas pouvoir se tamponner lui-même sans que tu le
  voies. `settings.json` étant du JSON, ces raisons ne peuvent vivre qu'ici.

---

## 13. Re-lancer un dispatch (idempotent)

Les commandes **reprennent** où elles se sont arrêtées ; pas de doublon par défaut.

```
/speckit.dcm.dispatch --spec 010-header-workspace-filter
```

L'agent affiche d'abord un Resume Report (`ALREADY DONE (will skip)` / `REMAINING (will
create)`), puis ne crée que le reste. `--dry-run` s'arrête au rapport ; `--force` recrée tout,
donc des doublons. Suivi : `jira-mapping.json`, `branches-created.json`,
`dispatch-manifest.json`, `jira-create-log.json`.

---

## 14. Dépannage

| Problème | Solution |
|----------|----------|
| MCP Jira non trouvé | Le serveur doit s'appeler exactement `atlassian` — les noms d'outils en dérivent ([GETTING-STARTED § 3](./GETTING-STARTED.md)) |
| Extension pas visible | `./spec-kit-dcm-workflow/scripts/install.sh` (un `extension add` seul échoue si l'ancien id `dcm-workflow` est encore enregistré) |
| Branche fille déjà existante | `git branch -d <branche>` puis re-dispatch |
| Task sans domaine (`misc/…`) | Préfixer le titre : `Frontend …`, `Backend …`, `DataEng …` |
| Parseur exit 2 | `tasks.md` au mauvais format — voir § 1 |
| Sync Jira échoue | Vérifier `status_mapping` dans `dcm-config.yml` |
| Conflit au rebase (Step 4.5) | `git status` → résoudre → `git add . && git rebase --continue` (ou `--abort`) |
| `git commit` refusé après une revue | Le diff staged a changé depuis le stamp — relancer `/speckit.dcm.review --commit` |
| Un gate se comporte autrement que documenté | `./spec-kit-dcm-workflow/scripts/dcm-selftest.sh` |

---

## 15. Version

**2.9.2 — le subagent `dataeng` vient d'un plugin APM, plus du dépôt.** `plugins/databricks-data-engineer/`
(agent vendored + son `scripts/install.sh`) est supprimé : l'agent est maintenant
`dp-data-databricks-engineer`, fourni par `TotalEnergiesCode/dp-ai-tools/plugins/data-integration`.
`install.sh` appelle `apm install … --target copilot --only apm` au lieu du script du plugin, et
`implement.domain_subagents.dataeng` vaut `dp-data-databricks-engineer` — **un seul** identifiant
pour les deux hôtes, là où l'ancien agent était enregistré sous deux noms. Conséquence à connaître :
`--target` décide de l'hôte servi, donc une machine sous Claude Code doit relancer la commande avec
`--target claude`, sinon la seule règle bloquante du workflow désigne un agent absent. `--only apm`
n'est pas un raccourci : un install complet résout aussi les dépendances MCP du plugin et échoue sur
un nom de serveur non qualifié déclaré en amont.

**2.9.2 — les commandes spec-kit de base sont rendues par hôte (`{speckit}`).** Depuis
spec-kit 0.11, `ClaudeIntegration` est une `SkillsIntegration` sans opt-out : les commandes de
base sont installées en skills et s'appellent `/speckit-plan`, pas `/speckit.plan`. Toute la
doc et tous les corps de commande annonçaient encore la forme pointée — y compris les messages
d'erreur de `dcm-precheck.sh` et `dcm-parse-tasks.sh`, qui bloquaient en donnant une commande
injouable. Les sources partagées écrivent désormais `{speckit}plan` et
`sync-dcm-extension.sh` (`speckit_prefix()` + `render_tpl()`) résout le préfixe par hôte.
Trois gardes dans le selftest : aucune forme pointée codée en dur dans `commands/`, `skills/`
ou `claude-code/` ; aucun `{speckit}` non résolu dans les artefacts générés ; et aucun script
qui *imprime* un nom de commande de base — `scripts/` est copié verbatim, jamais rendu, donc il
ne peut pas utiliser `{speckit}`. Cette troisième garde a immédiatement trouvé un cas manqué
(`dcm-precheck.sh`, gate `plan`, qui renvoyait vers `/speckit.plan`). Les messages des scripts
partagés nomment maintenant la commande **DCM** correspondante (`/speckit.dcm.tasks`),
identique sur les deux hôtes, ou restent neutres (« before the plan step »). Les
`specs/NNN-*/` existants gardent leurs références pointées : ce sont des archives, pas des
instructions.

**2.9.2 — le tool de délégation s'appelle `Agent`, plus `Task`.** La table des hôtes de
`commands/implement.md` et le `allowed-tools` généré nommaient `Task`, qui n'existe plus dans
Claude Code (il ne reste que `TaskOutput` / `TaskStop`). La seule règle marquée bloquante du
workflow — `dataeng` → le subagent Databricks (à l'époque `databricks-data-engineer`, aujourd'hui
`dp-data-databricks-engineer`), `domain_subagents_required: true`, sans
fallback sur l'agent principal — désignait donc un tool absent, et `allowed-tools` n'autorisait
pas celui qui existe. `claude_allowed_tools()` émet maintenant `Agent, Task` : une entrée
d'allowlist qui ne correspond à aucun tool est inerte, alors qu'une entrée manquante refuse la
délégation en silence. Deux assertions du selftest verrouillent les deux moitiés du correctif
séparément — le `allowed-tools` *généré* accorde `Agent`, et `commands/implement.md` nomme bien
`Agent(…)` — parce qu'un retour à `Task` seul laissait passer toute la suite en silence : le
corps de la commande reste lisible, seul le tool layer refuse.

**2.9.2 — id de l'extension `dcm-workflow` → `dcm`.** spec-kit valide à l'installation que
le namespace des commandes est exactement l'id (`speckit.{id}.{commande}`) : depuis que 2.8.0 a
raccourci les noms en `speckit.dcm.*` sans toucher l'id, `specify extension add` refusait
l'extension entière (« must use extension namespace 'dcm-workflow' »). Les noms de commandes ne
changent pas ; le répertoire d'installation devient `.specify/extensions/dcm/`. La migration est
faite par `install.sh` (désenregistrement de `dcm-workflow`, `--keep-config`) puis
`sync-dcm-extension.sh` (report du `dcm-config.yml` local, purge de l'ancien répertoire) — donc
un seul `./spec-kit-dcm-workflow/scripts/install.sh` suffit après le pull.

**2.9.0 — allègement.** 13 commandes → **9** (`scope` fusionné dans `specify --intake-only`,
`consolidate-tasks` et `amend` dans `tasks --consolidate` / `--add`, `review-before-commit` dans
`review --commit` ; `tasks-guide` et `implement-guide` renommés). 5 templates de spec → **un**
`templates/spec.md` avec des blocs `[work_type: …]`. Docs : README réduit à un index, ce guide
devient la doc de référence. Nouveau `scripts/dcm-selftest.sh` — il asserte le code de sortie de
chaque gate et la cohérence déclarations ↔ disque — c'est ainsi qu'un alias
`/speckit.dcm.pr` supprimé en 2.8.0 a été trouvé encore annoncé en tête de
`commands/publish-pr.md`. Clé `spec_template` supprimée de la config : descriptive,
aucun lecteur.

**2.8.0.** Un seul nom par commande (plus d'alias ni de famille `speckit.dcm.*`, skills
jumelles désenregistrées). `jira-create` + `dispatch-branches` → `dispatch`
(`--jira-only` / `--branches-only`) ; `discover-fields` supprimée.
`dcm-parse-tasks.sh` devient le lecteur unique de `tasks.md`, à la place de six parseurs en
prose divergents. Couche Cursor supprimée. Skills d'équipe déployées dans `.claude/skills/`.
Lectures `yq` mortes remplacées par `grep` dans `git-hooks/pre-commit` (`yq` n'est pas installé
sur les machines de l'équipe, donc `before_commit_require_pass` n'était jamais honoré).

**2.7.0.** Compatibilité Claude Code (slash commands, gate `git commit` en hook `PreToolUse`,
`CLAUDE.md` à bloc géré, subagent `dataeng`), gates en prose → `dcm-precheck.sh --gate`,
registre multi-Epics dans `specs/active-epics.json`.

---

## 16. Liens

- Extension source : `spec-kit-dcm-workflow/` · config générée :
  `.specify/extensions/dcm/dcm-config.yml` · source de la config :
  `dcm-config.template.yml`
- [README.md](./README.md) (index) · [CONTRACTS.md](./CONTRACTS.md) (schémas JSON) ·
  [USAGE-AND-TOKENS.md](./USAGE-AND-TOKENS.md) (tokens, modèles)
- Spec Kit : [github/spec-kit](https://github.com/github/spec-kit)
