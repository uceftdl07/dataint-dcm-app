# Usage / tokens / modèles — DCM Workflow

Comment les tokens sont **enregistrés**, **agrégés** et **restitués** par l'extension DCM
(extension **2.9.0**). Ce document décrit uniquement ce que les scripts font réellement.

---

## 1. Chaîne de fichiers

| Fichier | Écrit par | Rôle |
|---------|-----------|------|
| `specs/NNN-slug/.dcm-step-start.json` | `scripts/dcm-step-start.sh` | Marqueur de début d'étape (`started_at`, `step`, `task`, `actor`, `branch`) |
| `specs/NNN-slug/usage-log.jsonl` | `scripts/dcm-track-session.sh` ou `scripts/dcm-append-usage.sh` | **Log brut** — 1 ligne JSON = 1 passage |
| `specs/NNN-slug/usage-report.md` | `scripts/dcm-render-usage-report.sh` | Rapport Markdown généré depuis le log |

Le log est **append-only** : aucun script ne réécrit ni ne dédoublonne les lignes existantes.

---

## 2. Format `usage-log.jsonl`

Un objet JSON par ligne. Champs réellement écrits :

| Champ | Type | Contenu |
|-------|------|---------|
| `ts` | string ISO UTC | Horodatage d'écriture de la ligne |
| `started_at` / `ended_at` | string ISO UTC | Début / fin du passage |
| `duration_s` | int / null | Durée calculée (`ended_at - started_at`) — **`dcm-append-usage.sh` uniquement** |
| `step` | string | `scope`, `specify`, `plan`, `tasks`, `dispatch`, `implement`, `review`, `publish-pr`, `sync-status`, `amend`, `other`… |
| `task` | string / null | Ex. `T001` |
| `work_mode` | string | `speckit` \| `direct` \| `manual` \| `ai` |
| `outcome` | string / null | `ok` \| `fail` \| `partial` \| `skipped` |
| `provider` | string | `claude` \| `copilot` \| `estimate` |
| `model` | string / null | Nom du modèle tel que lu dans la source |
| `model_recommended` | string / null | Préférence `model_preferences` pour ce step — **append uniquement** |
| `model_match` | bool / null | `model` cohérent avec `model_recommended` — **append uniquement** |
| `tokens_input` / `tokens_output` | int / null | Tokens in / out |
| `tokens_cache_read` / `tokens_cache_write` | int / null | Cache Anthropic (`cache_read_input_tokens`, `cache_creation_input_tokens`) |
| `tokens_total` | int / null | `input + output` |
| `cost_usd` | float / null | Coût **indicatif** (voir §6) |
| `source` | string | `claude` \| `copilot-chat-log` \| `manual` \| `estimate` |
| `source_path` / `readable` | string / bool | Fichier source lu — **`dcm-track-session.sh` uniquement** |
| `estimated` | bool | `false` = tokens réels, `true` = estimation |
| `jira_keys` | array / null | Ex. `["DCINT-201"]` — **append uniquement** |
| `pr_url` / `branch` | string / null | PR et branche fille |
| `actor` / `git_author` | string / null | Attribution (auto depuis `git config`) |
| `notes` | string / null | Trace libre (`claude-jsonl:<fichier>`, `ccreq:<id> dur=…ms ctx=…`) |
| `skills_used` | array / null | Skills loggés via `--skills` — **append uniquement** |

Les deux producteurs n'écrivent donc **pas exactement le même jeu de champs** : un lecteur du log
doit traiter tout champ absent comme `null`.

---

## 3. Ajouter une entrée manuellement

`scripts/dcm-append-usage.sh` — écrit **une** ligne. Obligatoires : `--feature-dir` et `--step`.

```bash
spec-kit-dcm-workflow/scripts/dcm-append-usage.sh \
  --feature-dir specs/011-carousel-scoring \
  --step implement --task T002 \
  --provider copilot --model gpt-5 \
  --work-mode direct --outcome ok \
  --input 3000 --output 900 \
  --source manual --estimated true \
  --notes "RBAC fait à la main"
```

Options : `--task`, `--provider`, `--model`, `--model-recommended`, `--input`, `--output`,
`--cache-read`, `--cache-write`, `--source`, `--estimated`, `--started`, `--ended`, `--notes`,
`--work-mode`, `--outcome`, `--jira-keys`, `--pr-url`, `--branch`, `--actor`, `--git-author`,
`--skills`.

Comportements automatiques :

| Cas | Effet |
|-----|-------|
| `--work-mode` absent | `speckit` pour les steps du workflow, sinon `direct` |
| `--work-mode` / `--outcome` hors valeurs autorisées | **exit 2** (validation stricte) |
| `--provider` absent | déduit de `source` + `model` (`claude`, `copilot`, sinon `estimate`) |
| `--model-recommended` absent | rempli via `dcm-model-pref.sh --step <step>` |
| `--actor` / `--git-author` / `--branch` absents | déduits de `git log` / `git config` / `git rev-parse` |
| `--task` présent et `dispatch-manifest.json` existe | `jira_keys`, `branch`, `pr_url` enrichis depuis le manifest (à défaut : clé de l'Epic) |

---

## 4. Collecte depuis les logs des agents

`scripts/dcm-track-session.sh --feature-dir specs/NNN-slug --step <step> [--task T00X] [--dry-run]`
lit les logs locaux des agents et **append** les lignes trouvées dans la fenêtre de temps.

| Source | Lecture | Qualité |
|--------|---------|---------|
| `~/.claude/projects/**/*.jsonl` (+ `~/.config/claude`) | lignes `type=assistant` → `message.usage` (`input_tokens`, `output_tokens`, `cache_*`) | **réel** (`estimated: false`) |
| `GitHub Copilot Chat.log` (logs VS Code) | lignes `ccreq:` en `success` → durée ms × tok/s + profil de contexte | **estimé** (`estimated: true`) |
| Tout autre agent | pas de log lisible → saisie via `dcm-append-usage.sh` | manuel |

Fenêtre de temps : depuis `started_at` de `.dcm-step-start.json`, sinon **90 dernières minutes**.

Variables d'environnement de surcharge : `DCM_CLAUDE_ROOT`, `DCM_COPILOT_LOG_ROOT`.

Le script affiche les sources lues **et** les sources ignorées avec leur raison (`dir not found`,
`no activity in window`, `unreadable: …`), puis un résumé `in/out/cost/estimées`. `--dry-run`
n'écrit rien.

> `dcm-step-start.sh` et `dcm-track-session.sh` encadrent une étape workflow
> (marqueur au début, collecte à la fin). Les commandes `specify` et `implement` les
> invoque explicitement. Fallback manuel : `dcm-append-usage.sh`.

---

## 5. Générer le rapport

```bash
spec-kit-dcm-workflow/scripts/dcm-render-usage-report.sh --feature-dir specs/011-carousel-scoring
```

- Lit **uniquement** `usage-log.jsonl` (aucune collecte, aucun appel réseau).
- Écrit `specs/011-carousel-scoring/usage-report.md` depuis `templates/usage-report.template.md`.
- Si le log est vide ou absent : message explicatif en français (ancien epic sans tracking) et
  sortie **0**, sans créer de rapport.

Sections du rapport et sources des chiffres :

| Section du template | Marqueur | Agrégation |
|---------------------|----------|------------|
| En-tête | `{EPIC}`, `{STORIES}`, `{PERIOD_START/END}`, `{TOTAL_*}`, `{ACCURACY_LABEL}` | totaux du log + `jira-mapping.json` / `dispatch-manifest.json` |
| 2. Totaux par step | `BY_STEP` | runs, tokens, % du total, modèles, coût — trié par tokens |
| 3. Jira | `JIRA_TABLE` | Epic + Stories du mapping/manifest, complétés par les `jira_keys` du log |
| 4. Synthèse | `{PROVIDERS}`, `{MODELS}`, `{WORK_MODES}`, `{AC_COVERAGE}`, `{PREF_MATCH}`, `BY_PROVIDER`, `BY_MODEL` | dimensions distinctes du log ; `AC_COVERAGE` = cases `- [ ]` / `- [x]` sous la section *Acceptance Criteria* de `spec.md` |
| 5. Skills | `SKILLS_USED`, `{EPIC_SKILLS}` | `skills_used` par step — `explicite` si loggé, sinon `non loggé` |

Garde-fou : si un placeholder `{MAJUSCULES}` ou un marqueur `<!-- … -->` reste non résolu, le
script **n'écrit pas** le rapport, liste les placeholders manquants sur stderr et sort en **1**.

Via la commande : `/speckit.dcm.usage-report --spec 011-carousel-scoring` — c'est le seul nom,
les alias `tokens` / `speckit.dcm.*` ont été supprimés en 2.8.0.

---

## 6. Réel vs estimé, et coûts

| `source` | `estimated` | Origine du chiffre |
|----------|-------------|--------------------|
| `claude` | `false` | `message.usage` d'Anthropic — **réel** |
| `copilot-chat-log` | `true` | durée `ccreq` × tokens/s + profil de contexte — **estimation** |
| `manual` / `estimate` | selon `--estimated` | saisi à la main |

`cost_usd` est **toujours indicatif** : les deux scripts embarquent leur propre table de tarifs
(USD / 1M tokens, taux publics approximatifs) et retombent sur `3.00 / 15.00` pour un modèle
inconnu. Les tables ne sont pas identiques (ex. `claude-haiku` : `0.80 / 4.00` dans
`dcm-append-usage.sh`, `0.25 / 1.25` dans `dcm-track-session.sh`). Ce n'est pas une facture.

Le rapport compte séparément les lignes sans aucun token (`{UNKNOWN_COUNT}`).

---

## 7. Préférences de modèle par step (soft)

Bloc `model_preferences` de `dcm-config.yml` (défauts du template) :

| Step | Modèle préféré |
|------|----------------|
| `default` | `claude-sonnet` |
| `scope` | `claude-sonnet` |
| `specify` | `claude-opus-4.8` |
| `clarify` | `gpt-5.5` |
| `plan` | `claude-opus-4.8` |
| `tasks` | `claude-sonnet-5` |
| `analyze` | `gpt-5.4` |
| `dispatch` | `claude-haiku` |
| `implement` | `claude-sonnet-5` |
| `review` | `claude-sonnet-5` |
| `amend` | `claude-sonnet-5` |
| `publish-pr` | `claude-haiku-4.5` |
| `sync-status` | `claude-haiku-4.5` |
| `usage-report` | `claude-haiku-4.5` |

Deux réglages accompagnent le bloc : `enforce_banner: true` (l'agent affiche la préférence) et
`ask_if_mismatch: true`. **Aucun verrouillage** : c'est toi qui changes le picker de modèle.

```bash
spec-kit-dcm-workflow/scripts/dcm-model-pref.sh --step implement
# → claude-sonnet-5
```

Le helper accepte le nom court comme le nom complet (`specify`, `speckit.dcm.specify`, `tasks`…), lit
`.specify/extensions/dcm/dcm-config.yml` puis, à défaut,
`spec-kit-dcm-workflow/dcm-config.template.yml`, et retombe sur `default` puis `claude-sonnet`.
La préférence retenue est stockée dans `model_recommended` / `model_match` du log.
