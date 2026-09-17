# Contrats des artefacts JSON — DCM Workflow

Référence **autoritaire** des fichiers JSON que le workflow se passe d'une étape à l'autre.

Jusqu'ici ces formats n'existaient qu'en prose, dupliquée dans plusieurs `commands/*.md`, et
les descriptions **ne concordaient pas** entre le producteur et les consommateurs. Ce document
a été écrit en **lisant les fichiers réels** du repo, pas les prompts. Quand les fichiers sur
disque se contredisent, c'est écrit noir sur blanc dans une section
**⚠️ Divergences constatées** — l'information est utile, on ne l'écrase pas avec une vérité
inventée.

Conventions :

- **requis** = un consommateur plante ou perd de l'information si le champ manque.
- **optionnel** = absent dans au moins un fichier réel du repo, et personne ne casse.
- `null` autorisé signifie que la clé existe mais peut valoir `null` (≠ clé absente).
- `ISO8601` = `2026-08-17T13:53:30Z` (UTC, secondes, suffixe `Z`).

Table des matières :

| Artefact | Écrit par | Lu par |
|----------|-----------|--------|
| [`.specify/pending-intake.json`](#1-specifypending-intakejson) | agent `/speckit.dcm.specify --intake-only` | `dcm-precheck.sh --gate specify`, agent specify |
| [`specs/<spec>/intake.json`](#2-specsspecintakejson) | agent specify (copie du pending) | `dcm-precheck.sh --gate tasks`, `dcm-conflict-check.sh`, tasks/plan/dispatch |
| [`specs/<spec>/domain-scope.json`](#3-specsspecdomain-scopejson) | agent specify | `dcm-conflict-check.sh` |
| [`specs/<spec>/jira-mapping.json`](#4-specsspecjira-mappingjson) | `/speckit.dcm.dispatch` (moitié Jira) | dispatch (resume), sync-status, amend, publish-pr, `dcm-render-usage-report.sh` |
| [`specs/<spec>/branches-created.json`](#5-specsspecbranches-createdjson) | `/speckit.dcm.dispatch` (moitié branches) | dispatch (resume) |
| [`specs/<spec>/dispatch-manifest.json`](#6-specsspecdispatch-manifestjson) | `/speckit.dcm.dispatch` | implement, sync-status, publish-pr, review, `dcm-append-usage.sh`, `dcm-render-usage-report.sh` |
| [`specs/active-epics.json`](#7-specsactive-epicsjson) | `dcm-active-epics-update.sh` | `dcm-conflict-check.sh` |
| [`dcm-parse-tasks.sh --json`](#8-sortie-de-dcm-parse-taskssh---json) | `scripts/dcm-parse-tasks.sh` | dispatch, sync-status, tasks (génération, `--consolidate`, `--add`), implement |

Règle générale de tous les writers : **merge, jamais overwrite**. Une clé déjà remplie
(`epic.key`, une entrée `dispatch[]`, une branche) n'est jamais supprimée par une nouvelle
exécution — c'est ce qui rend le dispatch idempotent (« resume »).

---

## 1. `.specify/pending-intake.json`

Intake transient, **racine du repo**, avant que le dossier `specs/NNN-*/` n'existe.

- **Écrit par** : l'agent `/speckit.dcm.specify` (Q1–Q7, phase 1). Il n'y a plus de writer
  en script : `dcm-scope-intake.sh` était un fallback terminal « si AskQuestion est
  indisponible » qu'aucun des deux hosts n'emprunte, et il a été supprimé.
- **Lu par** : `scripts/dcm-precheck.sh --gate specify` — exit 2 si le fichier est absent,
  s'il n'a pas de `work_type`, ou s'il est *byte-identique* à un `specs/*/intake.json` déjà
  persisté (auquel cas c'est le résidu d'un specify qui a sauté sa suppression, pas un
  intake ; il tenait le gate ouvert pour toutes les features suivantes). Aussi lu par
  l'agent `/{speckit}specify` (`{speckit}` = `speckit-` sur Claude Code, `speckit.` sur
  Copilot — voir [GUIDE.md](./GUIDE.md)).
- **Supprimé par** : l'agent specify, après copie en `specs/<spec>/intake.json`
  (`commands/specify.md`, phase 2).

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `work_type` | string | requis | `feature` \| `technique` \| `dette` \| `hotfix` \| `fixture` |
| `domains` | string[] | requis | domaines *en lecture* (⊇ `ticket_plan.ticket_domains`) |
| `ticket_plan.mode` | string | requis | `single_domain` \| `one_per_domain` \| `custom` |
| `ticket_plan.ticket_domains` | string[] | requis | domaines qui reçoivent réellement une Story |
| `ticket_plan.expected_story_count` | int | requis | `len(ticket_domains)` côté script |
| `dependency_gaps` | array | requis | `[]` par défaut ; rempli par l'analyse de dépendances |
| `packages` | string[] | requis | chemins des packages en scope |
| `priority` | string | requis | `P0` \| `P1` \| `P2` \| `P3` |
| `selection_mode` | string | requis | `preset` \| `manual` |
| `summary` | string | requis | résumé une phrase |
| `created_at` | string | requis | ISO8601 (le script écrit avec secondes + `Z`) |
| `preset` | string \| null | optionnel | ajouté seulement si un preset a été choisi ; `null` possible |
| `spike_reference` | string | optionnel | ajouté à la main (vu dans le pending actuel) |
| `architecture_decisions` | object | optionnel | ajouté à la main, clés libres |

## 2. `specs/<spec>/intake.json`

Copie persistée du pending, dans le dossier de la spec.

- **Écrit par** : l'agent `/{speckit}specify` (copie de `.specify/pending-intake.json`).
- **Lu par** : `dcm-precheck.sh --gate tasks` (existence → exit 2), `dcm-conflict-check.sh`
  (`ticket_plan.ticket_domains`, `domains`, `packages`), `commands/tasks.md`,
  `plan-guide.md`, `dispatch.md`, `implement.md`.

Même schéma que `pending-intake.json`. Champs supplémentaires observés :

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `feature_summary` | string | optionnel | variante de `summary` (009) |
| `task_dispatch_mode` | string | optionnel | `one_per_domain` \| `granular` (009) |
| `spec_number` | string | optionnel | `"009"` (009) |
| `spec_directory` | string | optionnel | `specs/009-widget-inactive-cluster` (009) |
| `dependency_analysis` | object | optionnel | `{gaps_found: bool, notes: string}` (009) |
| `notes` | string | optionnel | commentaire libre de re-intake (014) |

### ⚠️ Divergences constatées

1. **`summary` vs `feature_summary`** : le contrat ci-dessus impose `summary`. Or
   `specs/009-widget-inactive-cluster/intake.json` n'a **que** `feature_summary` (pas de
   `summary`), et `specs/013-*` / `specs/014-*` n'ont **que** `summary`. Un lecteur doit
   accepter les deux : `summary or feature_summary`.
2. **`ticket_plan`** : la clé de comptage n'est pas stable. `expected_story_count` dans
   013/014 et dans le pending, mais `stories_count` dans 009. 009 ajoute aussi
   `non_ticket_domains` (absent ailleurs).
3. **`dependency_gaps` (liste) vs `dependency_analysis` (objet)** : 009 utilise le second,
   les autres le premier. Ils portent la même intention.
4. **`created_at`** : ISO8601 complet partout, sauf 009 qui écrit `"2026-07-01"` (date
   seule). Un `datetime.fromisoformat()` strict sur secondes échouerait.

## 3. `specs/<spec>/domain-scope.json`

Périmètre lecture/écriture par domaine, dérivé de l'intake.

- **Écrit par** : l'agent `/{speckit}specify` (`commands/specify.md`, phase 2).
- **Lu par** : `dcm-conflict-check.sh` (fonction `load_domains_packages`), `tasks.md`,
  `commands/plan-guide.md`, `commands/dispatch.md`, `commands/tasks.md` (`--add`).

**Il n'existe aucun schéma unique sur disque : trois formes cohabitent.** Aucun script n'écrit
ce fichier — il est produit par un LLM, ce qui explique la dérive. Le seul consommateur
mécanique (`dcm-conflict-check.sh`) est écrit pour tolérer les trois.

**Forme A — booléens par domaine** (`specs/014-reference-lz-tables`) :

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `work_type` | string | requis | dupliqué depuis l'intake |
| `domains` | object\<string, bool> | requis | `{"frontend": false, "dataeng": true, ...}` |
| `packages` | string[] | requis | à plat, pas par domaine |
| `priority` | string | requis | |

**Forme B — listes `*_in_scope`** (`specs/009-widget-inactive-cluster`) :
`domains_in_scope: string[]`, `ticket_domains: string[]`, `non_ticket_domains: string[]`,
`packages_in_scope: object<domain, string[]>`, `read_scope: string[]`, `write_scope: string[]`.

**Forme C — `in_scope_domains` + `packages_by_domain`** (`specs/013-workflow-sys-tables-migration`) :
`in_scope_domains: string[]`, `ticket_domains: string[]`, `out_of_ticket_domains: string[]`,
`packages_by_domain: object<domain, string[]>`.

### ⚠️ Divergences constatées

- Le nom de la liste des domaines change trois fois : `domains` (objet booléen),
  `domains_in_scope`, `in_scope_domains`. `dcm-conflict-check.sh` teste explicitement
  `domains` → `active_domains` → `in_scope_domains` → `ticket_domains` (dans cet ordre) et
  accepte objet **ou** liste. `domains_in_scope` (forme B, 009) **n'est pas dans cette
  liste** : pour 009 le conflict-check ne récupère les domaines que via `ticket_domains`.
- Le nom du mapping packages change aussi : `packages` (plat), `packages_in_scope`,
  `packages_by_domain`. Seul `packages_by_domain` est lu par `dcm-conflict-check.sh` ;
  `packages_in_scope` (009) est **ignoré** et les packages proviennent alors de `intake.json`.
- La forme A liste 5 ou 6 domaines selon le fichier (`misc` présent dans 001, absent dans 014).
- **Recommandation** : pour tout nouveau fichier, écrire la forme C (`in_scope_domains` +
  `packages_by_domain` + `ticket_domains`) — c'est la seule intégralement lue par le
  conflict-check.

## 4. `specs/<spec>/jira-mapping.json`

Table de correspondance `task_id` → issue Jira.

- **Écrit par** : `/speckit.dcm.dispatch` (§6, merge en mode resume ; `--jira-only` pour la
  moitié Jira seule), enrichi par `/speckit.dcm.sync-status`.
- **Lu par** : `commands/dispatch.md` (audit resume : `epic.key`, `stories[].key`),
  `commands/sync-status.md`, `commands/tasks.md` (`--add`), `commands/publish-pr.md`,
  `scripts/dcm-render-usage-report.sh` (`epic.key/url`, `stories[].task_id/key/branch/url`).

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `spec` | string | requis | nom du dossier spec (absent dans `demo-usage-tokens`) |
| `updated_at` | string | requis | ISO8601 (absent dans `demo-usage-tokens`) |
| `epic.key` | string | requis | `DCINT-236` ; `"pending_mcp"` = pas encore créé (`dispatch.md` §6a) |
| `epic.url` | string | requis | URL `browse/` |
| `epic.summary` | string | optionnel | préfixée `[NNN]` si `multi_epic.epic_title_prefix` |
| `epic.status` | string | optionnel | statut Jira brut (`Draft`) |
| `stories[]` | array | requis | 1 entrée par task |
| `stories[].task_id` | string | requis | `T001` — clé de jointure |
| `stories[].key` | string | requis | `DCINT-238` |
| `stories[].url` | string | requis | URL `browse/` |
| `stories[].domain` | string | optionnel | absent dans 011-dbx et demo |
| `stories[].branch` | string | optionnel | **nom** de branche, jamais un SHA |
| `stories[].summary` | string | optionnel | résumé Jira (format instable, voir plus bas) |
| `stories[].sub_spec_path` | string | optionnel | `stories/T001-x.md` |
| `stories[].status` | string | optionnel | statut Jira cible (`To Do`, `Done`) |
| `stories[].issuetype` | string | optionnel | `Sub-task` dans 011-dbx |
| `project` | string | optionnel | `DCINT` (010, 012 seulement) |
| `last_run_at` | string | optionnel | 011-nav-v2 seulement |
| `jira_model` | string | optionnel | `subtasks_under_existing` (011-dbx) |
| `parent.{key,url,summary,issuetype}` | object | optionnel | 011-dbx : Story parente hors modèle DCM |
| `hotfix_park` | string | optionnel | 011-dbx : branche de parking |
| `cancelled[]` | array | optionnel | 011-dbx : `{task_id, key, reason, status, pr, pr_state}` |

### ⚠️ Divergences constatées

1. **`specs/011-dbx-workflow-job-metrics` casse le modèle DCM** : Sub-tasks sous une Story
   existante (`jira_model: subtasks_under_existing`, bloc `parent`) au lieu de Stories sous
   Epic. Tout code qui suppose « `epic` + `stories[]` = Epic + Stories » lit ici un Epic qui
   n'est pas le parent réel des issues.
2. **Format de `stories[].summary` : 4 variantes**, aucune parsable de façon stable —
   `"T001 [Frontend] Add ..."` (009), `"T001: Frontend — Main nav ..."` (011-nav-v2),
   `"T001: Curated system tables ..."` (012), `"T001 — Usage Databricks ..."` (010).
   Ne jamais re-dériver le domaine depuis `summary` : utiliser `stories[].domain`, ou
   `dcm-parse-tasks.sh`.
3. `stories[].status` est présent dans 009/011 et absent dans 010/012/013 — un
   sync-status doit traiter l'absence comme « statut inconnu », pas comme `To Do`.
4. `spec` et `updated_at` manquent dans `spec-kit-dcm-workflow/specs/demo-usage-tokens`
   (fixture de démo), donc un lecteur ne peut pas les considérer garantis.

## 5. `specs/<spec>/branches-created.json`

Journal des branches filles créées.

- **Écrit par** : `/speckit.dcm.dispatch` (§6c, ou `--branches-only`) — merge : jamais de
  suppression d'entrée.
- **Lu par** : `commands/dispatch.md` (audit resume `branches_done` + idempotence).
- **Un seul exemplaire réel dans le repo** : `specs/013-workflow-sys-tables-migration`.

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `spec` | string | requis | nom du dossier spec |
| `updated_at` | string | requis | ISO8601 |
| `base` | string | requis | ref de départ réelle — `origin/develop` |
| `base_sha` | string | requis | SHA du tip de base au moment de la création (traçabilité) |
| `branches[]` | array | requis | 1 entrée par branche |
| `branches[].task_id` | string | requis | `T001` |
| `branches[].name` | string | requis | nom de branche |
| `branches[].pushed` | bool | requis | reflète `push_to_origin` / `--no-push` |
| `branches[].status` | string | optionnel | `created` \| `skipped_exists` \| `pushed` \| `push_failed` — **jamais écrit dans le fichier réel** |

### ⚠️ Divergences constatées

1. L'ancien `commands/dispatch-branches.md` (supprimé en 2.8.0, fusionné dans `dispatch.md`)
   documentait un fichier au format `{branch_strategy, child_branch_base, pr_target, spec}` —
   **sans le tableau `branches[]`**, c'est-à-dire sans l'information utile. Le fichier réel a
   `branches[]` mais **pas** les trois clés de stratégie (elles vivent dans
   `dispatch-manifest.json`).
2. Le champ `status` par branche n'existe pas sur disque ; on trouve à sa
   place le booléen `pushed`. Un consommateur doit accepter les deux et ne pas déduire
   `push_failed` d'un `pushed: false` (qui veut aussi dire `--no-push`).
3. `base`/`base_sha` sont sur disque mais ne sont documentés **nulle part** dans les prompts.

## 6. `specs/<spec>/dispatch-manifest.json`

Cross-référence `task_id` ↔ Jira ↔ branche. C'est le fichier le plus lu du workflow… et le
plus divergent.

- **Écrit par** : `/speckit.dcm.dispatch` §8 (merge par `task_id`), mis à jour par
  `/speckit.dcm.sync-status` §5 (champ `status`).
- **Lu par** : `commands/implement.md` (checkout de la branche d'une task),
  `commands/sync-status.md`, `commands/publish-pr.md`, `commands/review.md`,
  `commands/tasks.md` (`--add`),
  `scripts/dcm-append-usage.sh` (`dispatch[].task_id`, `dispatch[].jira_key`,
  `dispatch[].branch`, `dispatch[].pr_url`, `epic.key`),
  `scripts/dcm-render-usage-report.sh` (fallback si pas de `jira-mapping.json`).

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `spec` | string | requis | nom du dossier spec |
| `updated_at` | string | requis | ISO8601 (absent dans `demo-usage-tokens`) |
| `branch_strategy` | string | requis | `direct_to_base` \| `integration_branch` \| `consolidated` (010) |
| `child_branch_base` | string | requis | `develop` |
| `pr_target` | string | requis | `develop` |
| `integration_branch` | string \| null | requis | `null` en `direct_to_base` |
| `epic.key` / `epic.url` | string | requis | `epic.status` optionnel (011-nav-v2) |
| `dispatch[]` | array | requis | 1 entrée par task |
| `dispatch[].task_id` | string | requis | **seule clé présente dans 100 % des fichiers** |
| `dispatch[].branch` | string | requis | nom de branche |
| `dispatch[].domain` | string | optionnel | absent dans 010, 011-dbx, demo |
| `dispatch[].jira_key` | string | optionnel | ⚠️ voir divergence 1 |
| `dispatch[].jira` | string | optionnel | ⚠️ même sémantique que `jira_key` (010, 013) |
| `dispatch[].jira_story_key` | string | optionnel | ⚠️ même sémantique (011-nav-v2) |
| `dispatch[].jira_url` | string | optionnel | 009 seulement |
| `dispatch[].branch_created` | bool | optionnel | 009, 010 |
| `dispatch[].branch_pushed` | bool | optionnel | 011-nav-v2 |
| `dispatch[].jira_created` | bool | optionnel | 009 |
| `dispatch[].jira_status` | string | optionnel | 011-nav-v2 (`created`) |
| `dispatch[].title` | string | optionnel | 011-nav-v2 |
| `dispatch[].sub_spec` | string | optionnel | 011-dbx |
| `dispatch[].pr_url` | string | optionnel | lu par `dcm-append-usage.sh`, **jamais écrit** |
| `dispatch[].status` | string | optionnel | `sync-status.md` §5 dit l'écrire ; absent partout |
| `summary` | object | requis | voir divergence 3 |
| `parent.{key,url}` | object | optionnel | 011-dbx (Sub-tasks) |
| `hotfix_park` | string | optionnel | 011-dbx |

### ⚠️ Divergences constatées

1. **La clé Jira porte trois noms différents selon la spec** :
   `jira_key` (009, 011-dbx, demo), `jira` (010, 013), `jira_story_key` (011-nav-v2).
   **Conséquence réelle et mesurable** : `scripts/dcm-append-usage.sh` ne lit que
   `row.get("jira_key")`, donc l'enrichissement automatique de la clé Jira dans le log
   d'usage **est silencieusement vide** pour 010, 013 et 011-nav-v2. Un lecteur robuste doit
   faire `jira_key or jira or jira_story_key`.
2. **`dcm-render-usage-report.sh` lit `d.get("url")`** dans les lignes `dispatch[]` en
   fallback. Aucun fichier réel n'a `url` à ce niveau : 009 écrit `jira_url`. La colonne
   arrive donc vide.
3. **`summary` n'a pas de schéma stable** :
   - modèle nominal (009, 010, 011-nav-v2, 013) : `jira_stories_done`, `jira_stories_total`,
     `branches_done`, `branches_total`, `status` (`complete` \| autre) ;
   - 010 ajoute `mode` (`"jira-only (consolidated branch)"`) ;
   - 011-dbx remplace **tout** par `jira_subtasks_active`, `jira_subtasks_cancelled[]`,
     `branches_active`, `prs_active[]` (numéros de PR), `no_demo_data`, `no_lakeflow_overview`.
   Un contrôle « dispatch complet ? » ne peut donc pas se fier à `summary` seul : recompter
   depuis `dispatch[]` et `dcm-parse-tasks.sh`.
4. **Le lien Epic ↔ tasks n'est pas homogène** : 011-dbx a un `parent` **et** un `epic`, et
   les branches n'y suivent pas `child_branch_pattern` (`feature/DCINT-211-databricks-hub`).
   010 met la **même** branche `feature/010_metrics_system` sur les deux tasks
   (`branch_strategy: consolidated`, valeur absente de la config comme des prompts).
5. `spec-kit-dcm-workflow/specs/demo-usage-tokens/dispatch-manifest.json` n'a que
   `spec`, `epic`, `dispatch[]` : ni `updated_at`, ni stratégie, ni `summary`. Tous les
   champs « requis » ci-dessus doivent donc être lus défensivement.

## 7. `specs/active-epics.json`

Registre **d'équipe** des epics en cours (état partagé, à committer).

- **Écrit par** : `scripts/dcm-active-epics-update.sh` (lecture-modification-écriture sous
  `flock`, remplacement atomique). Appelé par `dispatch.md` §7 et `sync-status.md` §6
  (`--complete`).
- **Lu par** : `scripts/dcm-conflict-check.sh` (strict : JSON invalide → exit 4, jamais un
  « pas de conflit »).
- **Chemin** : `multi_epic.registry_path` de `dcm-config.yml`, résolu par
  `scripts/lib-dcm-registry.sh` (défaut `specs/active-epics.json`). L'ancien emplacement
  `.specify/active-epics.json` est **migré par copie** au premier usage.
- **Modèle de référence** : `templates/active-epics.template.json`.

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `epics[]` | array | requis | `dcm-conflict-check.sh` exige un objet avec une liste `epics` |
| `epics[].spec` | string | requis | clé d'identité du merge |
| `epics[].spec_num` | string | requis | 3 chiffres, `"000"` si le dossier n'en a pas |
| `epics[].title` | string | requis | défaut = `spec` si `--title` absent |
| `epics[].domains` | string[] | requis | source du calcul de recouvrement |
| `epics[].packages` | string[] | requis | source du calcul de recouvrement |
| `epics[].branches` | string[] | requis | `[]` autorisé (015 : Epic créé, pas de branche) |
| `epics[].status` | string | requis | `in_progress` \| `completed` ; `dcm-conflict-check.sh` compte comme actif `in_progress`, `dispatched`, `active` (défaut si absent : `in_progress`) |
| `epics[].updated_at` | string | requis | ISO8601, réécrit à chaque update |
| `epics[].epic_key` | string | optionnel | écrit seulement si `--epic-key` fourni ; préservé au merge |
| `epics[].dispatched_at` | string | optionnel | écrit en même temps que `epic_key` |
| `updated_at` | string | requis | horodatage racine (`null` dans le template) |

### ⚠️ Divergences constatées

1. **Deux copies du registre coexistent aujourd'hui** : `specs/active-epics.json` et
   `.specify/active-epics.json`, actuellement **identiques** au caractère près. La seconde
   est le legacy : elle est ignorée par git, donc invisible pour l'équipe. Le code de
   migration de `lib-dcm-registry.sh` ne copie que si la cible est absente — il ne
   supprime jamais la source, d'où la coexistence. Seule `specs/active-epics.json` fait foi.
2. `templates/active-epics.template.json` met `updated_at` en **première** clé, le script
   l'écrit en **dernière**, et `status`/`dispatched_at` sont dans un ordre différent. C'est
   cosmétique (JSON), mais le template ne peut pas servir de test d'égalité littérale.
3. Le champ `status` du template ne documente pas les valeurs `dispatched` / `active` que
   `dcm-conflict-check.sh` accepte pourtant comme « actif ».

## 8. Sortie de `dcm-parse-tasks.sh --json`

Contrat de sortie du parseur unique de `tasks.md`
(`scripts/dcm-parse-tasks.sh`, voir son en-tête pour l'algorithme exact du slug).

- **Écrit par** : `scripts/dcm-parse-tasks.sh --spec <nom> --json` (stdout, jamais de fichier).
- **Lu par** : `dispatch.md` (§3, obligatoire), `sync-status.md` (§2), `implement.md` (§2),
  `tasks.md` (étape 5 validation, `--consolidate` §1, `--add` §1 et §3) —
  au lieu de re-dériver domaine, slug et branche à la main.
- **stdout est le seul canal de données** ; le résumé et les `WARN:` vont sur stderr.
- Sortie par défaut (sans `--json`) : lignes **TAB-séparées**, sans en-tête, dans l'ordre
  `task_id`, `status`, `domain`, `slug`, `branch`, `sub_spec` (`-` si absent), `title`.

| Champ | Type | Req. | Note |
|-------|------|:----:|------|
| `spec` | string | requis | nom du dossier spec |
| `spec_num` | string | requis | 3 chiffres du dossier, `"000"` + warning sinon |
| `spec_dir` | string | requis | chemin relatif à la racine du repo |
| `tasks_file` | string | requis | chemin relatif du `tasks.md` analysé |
| `config_file` | string | requis | config effectivement lue (installée ou template) |
| `branch_pattern` | string | requis | `git.child_branch_pattern` **lu dans la config** |
| `domains` | string[] | requis | `git.domains` de la config (liste de validation) |
| `slug_max_len` | int | requis | `40` |
| `counts.total` | int | requis | ≥ 1 (0 est impossible : voir codes de sortie) |
| `counts.pending` / `.in_progress` / `.completed` | int | requis | |
| `warnings` | string[] | requis | mêmes messages que les `WARN:` de stderr ; `[]` possible |
| `tasks[]` | array | requis | ordre = ordre d'apparition dans `tasks.md` |
| `tasks[].task_id` | string | requis | `T001` ; unique (le premier gagne) |
| `tasks[].title` | string | requis | titre nettoyé (peut être vide si la ligne n'a qu'un domaine) |
| `tasks[].status` | string | requis | `pending` \| `in_progress` \| `completed` |
| `tasks[].domain` | string | requis | ∈ `domains` ; `misc` en repli (toujours avec un warning) |
| `tasks[].domain_source` | string | requis | `tag` \| `first_word` \| `fallback_misc` |
| `tasks[].slug` | string | requis | non vide ; `t00n` en repli |
| `tasks[].branch` | string | requis | `branch_pattern` avec `{domain}` `{spec_num}` `{slug}` |
| `tasks[].sub_spec` | string \| null | requis | `stories/T001-x.md` ou `null` |
| `tasks[].sub_spec_exists` | bool | requis | le fichier est réellement sur disque |
| `tasks[].jira_key` | string \| null | requis | seulement `<project.key>-nnn` (jamais `FR-011`) |
| `tasks[].tags` | string[] | requis | tags de tête bruts (`["P", "US1"]`) ; `[]` possible |
| `tasks[].line` | int | requis | numéro de ligne dans `tasks.md` |

**Objet d'erreur** (`--json` + code ≠ 0) — forme alignée sur `dcm-conflict-check.sh` :
`{spec, tasks_file, error, details[], exit_code, tasks: []}` avec `tasks` **toujours vide**.

Codes de sortie : `0` ok · `1` erreur d'usage · `2` aucune ligne conforme dans `tasks.md`
(divergence de format — jamais « 0 task ») · `3` config inutilisable.

### ⚠️ Divergences arbitrées par le parseur

Les prompts qui parsaient `tasks.md` à la main ne décrivaient pas le même parseur. Ce qui a
été tranché avant de les faire tous passer par le script :

1. **`specs/010-databricks-usage-finops-curated/tasks.md` n'a pas de cases à cocher** : c'est
   un tableau Markdown avec un statut en glyphe (`☐ To Do`). Le parseur sort en **2** avec un
   message nommant le fichier et le format attendu, plutôt que de renvoyer zéro task — un
   appelant lirait « rien à dispatcher ».
2. **Longueur du slug** : seul l'ancien `dispatch-branches.md` la mentionnait
   (« max 40 chars ») ; `dispatch.md` et le mode `--consolidate` étaient muets. Retenu :
   **40**, avec coupe sur frontière de mot.
3. **Préfixe `spec_num`** : le mode `--consolidate` annonçait `frontend/{slug}` (sans numéro),
   la config annonce `{domain}/{spec_num}-{slug}`. Retenu : le pattern **de la config**,
   jamais de valeur en dur.
4. **Domaine** : le mode `--consolidate` décrit `- [ ] T00X {Domain} ...` (1er mot),
   l'ancien `dispatch-branches.md` disait « first word if in domains list, else misc », et
   `specs/009-databricks-workflows-observability` écrit en fait le domaine dans un tag
   (`` **T001** `[DataEng]` ``). Retenu : tag connu d'abord, puis 1er mot, puis `misc`
   **avec warning sur stderr**.
5. **Premier mot non reconnu** : il est **conservé** dans le slug (sinon
   « T001 Vérifier que… » perdrait « Vérifier »). Les prompts ne tranchaient pas.
6. **`task_id` dupliqué** : `specs/011-nav-v2-cleanup` répète `T003` sur trois lignes
   « sub-task ». Retenu : la **première** occurrence gagne, les suivantes sont ignorées avec
   un warning.
7. **Le slug ne reproduit pas les branches historiques** : la task réelle de 009 est
   « Frontend inactive cluster widget on Dashboard », donc slug
   `inactive-cluster-widget-on-dashboard`, alors que la branche réellement créée est
   `frontend/009-inactive-cluster-widget` (titre raccourci à la main). Le parseur est
   déterministe, pas rétro-compatible : pour les specs déjà dispatchées, la branche
   autoritaire reste celle de `branches-created.json` / `dispatch-manifest.json`.

---

## Hors périmètre de ce document

Fichiers présents sous `specs/*/` mais sans schéma défini nulle part (à ce jour aucun
consommateur mécanique) : `jira-sync-log.json` (`sync-status.md` §7),
`jira-create-log.json` (`dispatch.md` §3), `tasks-consolidated-log.json`
(`tasks.md --consolidate`), `pr-links.json` (009, 012), `.spec-context.json`
(010, 012, 013), `usage-log.jsonl` (voir `USAGE-AND-TOKENS.md`).
