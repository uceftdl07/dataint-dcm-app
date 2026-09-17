# Impact Backend & Frontend — migration collecteur → system tables

> Anticipation des modifications applicatives induites par la bascule du domaine `workflow`
> sur `system.lakeflow.*`. **Principe** : le contrat GOLD (`gold_dbx_workflow_*`, 8 tables) est
> conservé → **aucune route ne disparaît, aucun schéma de réponse n'est cassé**. L'impact se
> limite aux **colonnes devenues `NULL`** (champs perdus, cf. [migration_steps.md](migration_steps.md) §A)
> et à la **fraîcheur**.

---

## 1. Backend (`packages/dcm-backend`)

### 1.1 Services / routes concernés

| Fichier | Rôle | Impact |
|---|---|---|
| `app/api/services/lakeflow_jobs.py` | N1/N2/N3 page Jobs (runs, tasks, matrice, task health) | Colonnes NULL dans les SELECT (voir §1.2) — **aucune modif de requête obligatoire** |
| `app/api/services/lakeflow_overview.py` | Overview Databricks (success rate, percentiles, drift, concurrency, failures) | Fraîcheur dégradée ; concurrency moins « live » |
| `app/api/routes/databricks.py` → `/workspaces` | Résolution nom de workspace | Sources 1 & 2 (`workspace_name` gold/curated) deviennent NULL → **repli sur tags compute / id** |

### 1.2 Colonnes SELECT qui remontent `NULL`

Les requêtes de `lakeflow_jobs.py` sélectionnent explicitement (elles restent valides, colonnes
présentes au schéma gold, valeurs NULL) :

- `queued_duration_seconds` → **NULL**
- `execution_duration_seconds` → **NULL**
- `schedule_lag_seconds` → **NULL**
- `workspace_name` → **NULL** (sauf résolution optionnelle)
- `creator_user_name` → **id numérique** (dégradé)
- `run_page_url` → reconstruit (OK)
- `error_message` → `termination_code` + message court (dégradé)

Agrégats gold (`gold_dbx_workflow_duration_percentiles`) : `avg_queued_duration_seconds`,
`avg_schedule_lag_seconds`, `max_schedule_lag_seconds` → **NULL**.

### 1.3 Modifications backend recommandées

- [ ] **`/workspaces`** : documenter/ajuster l'ordre de résolution — sources 1 (`gold_dbx_workflow_runs.workspace_name`)
      et 2 (`curated_dbx_workflow_runs.workspace_name`) ne renvoient plus rien ; le repli sur les
      **tags compute** (`dcm_workspace_name`/`Project`, `dbw-%`) puis l'`workspace_id` devient la voie
      principale. Vérifier que ce repli couvre tous les workspaces (sinon prévoir une dimension DCM).
- [ ] **Résolution `creator_user_name`** (optionnel) : si le nom lisible est requis, ajouter un lookup
      identité (join SCIM / `system.access`) dans la vue-pont ; sinon exposer `creator_id` tel quel et
      l'afficher comme identifiant.
- [ ] **Contrat de réponse** : garder les champs dans les modèles Pydantic mais tolérer `None`
      (types `... | None`) — vérifier qu'ils le sont déjà. Aucun champ retiré → pas de rupture front.
- [ ] **Tests** : `test_lakeflow_overview.py`, tests jobs, `test_databricks_workspaces.py`
      (ce dernier teste justement la priorité gold > curated > tags — adapter les fixtures pour le cas
      `workspace_name = NULL` en gold/curated).
- [ ] **Freshness / SLA** : si un endpoint annonce une fraîcheur, refléter la latence system tables
      (quelques heures) dans la doc API / le champ `as_of`.

> Rien à supprimer côté backend : les 8 tables gold et les routes restent. C'est un travail de
> **tolérance au NULL** et d'ajustement de la résolution de nom de workspace.

---

## 2. Frontend (`packages/dcm-frontend`)

Page cible : **`/Lakeflow/Jobs`** (story [T004](../../../specs/011-dbx-workflow-job-metrics/stories/T004-lakeflow-jobs.md)),
3 niveaux N1 (liste workflows) / N2 (détail workflow + runs) / N3 (détail run + tasks).

### 2.1 Colonnes / éléments UI impactés

| Élément UI (T004) | Champ gold | Après migration | Action front |
|---|---|---|---|
| Colonne **« Attente »** (barre empilée queue \| lag) | `avg_queued_duration_seconds`, `avg_schedule_lag_seconds` | **NULL** | Masquer la colonne, ou afficher « n/d » — **ne pas** afficher 0 (fausse info) |
| **Trigger** — cron affiché en survol | (cron) | indisponible (`jobs` sans cron) | Retirer le tooltip cron ; garder `trigger_type` |
| Colonne **Workspace** | `workspace_name` | NULL sauf repli tags | Fallback affichage `workspace_id` si nom absent |
| Colonne **Propriétaire** | `creator_user_name` | `creator_id` (id) | Afficher l'id, ou masquer si non résolu |
| Drill N3 — **ventilation durée** (queue/exec) | `queued_/execution_duration_seconds` | NULL | Afficher uniquement `duration_seconds` total ; retirer la ventilation |
| Drill N3 — **message d'erreur** | `error_message` | `termination_code` + court | Afficher le code + message court ; libellé « code de terminaison » |
| Lien **run_page_url** | reconstruit | OK | inchangé (vérifier l'URL workspace) |
| Colonne **Historique** (10 barres), **Succès**, **Durée moy/p95**, **Tâches KO**, **Retries** | status, duration, tasks, retry | **OK** | inchangé |

### 2.2 Modifications frontend recommandées

- [ ] **Rendre les colonnes NULL-safe** : composants d'affichage durée/attente doivent gérer
      `null` → « n/d » / tiret, jamais `0`.
- [ ] **Colonne « Attente »** : par défaut masquée (déjà `visible ⬜` possible) ou retirée du sélecteur
      tant que la donnée n'existe pas — décision PO.
- [ ] **Tooltip cron du Trigger** : supprimer (donnée absente).
- [ ] **Bandeau fraîcheur** : ajouter un indicateur « données à ~X h » sur la page (latence system tables),
      surtout pour les runs `running`.
- [ ] **Tests Vitest** : mettre à jour les fixtures mockées (champs NULL), vérifier le rendu « n/d ».
- [ ] Aucune route front à retirer ; `app-routes.ts` inchangé.

---

## 3. Récap décisions à trancher (PO / archi)

| Sujet | Option par défaut (recommandée) | Alternative |
|---|---|---|
| `workspace_name` | NULL + repli tags/id | Résoudre via dimension workspaces DCM |
| `creator_user_name` | Exposer `creator_id` (id) | Lookup identité (join SCIM) |
| Colonne « Attente » (queue \| lag) | Masquer (donnée perdue) | Garder vide « n/d » |
| Fraîcheur | Bandeau « ~X h de latence » | Endpoint `as_of` explicite |
| Champs durée détaillée (drill N3) | Retirer ventilation | Garder placeholders « n/d » |

> Toutes ces décisions respectent la règle DCM : **un champ non disponible reste vide/`NULL`,
> jamais rempli d'une valeur inventée**.

---

## 4. Ce qui NE change pas

- Les 8 tables gold `gold_dbx_workflow_*` (schéma + noms).
- Les routes backend Lakeflow (Jobs N1/N2/N3, Overview).
- La navigation front `/Lakeflow/Jobs` et sa hiérarchie 3 niveaux.
- Les métriques cœur : taux de succès, durées/p95/drift, taux d'échec de tâches, historique 10 runs,
  santé par tâche — toutes dérivables des system tables.
