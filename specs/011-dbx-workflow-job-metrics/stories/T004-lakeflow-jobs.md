# T004 — Lakeflow Jobs (`/Lakeflow/Jobs`) — liste, runs et tasks

**Domain**: Fullstack  
**Packages**: `packages/dcm-frontend`, `packages/dcm-backend`  
**Branch**: `feature/DCINT-213-lakeflow-jobs`  
**Jira**: [DCINT-213](https://tdf.atlassian.net/browse/DCINT-213)  
**Parent**: [DCINT-173](https://tdf.atlassian.net/browse/DCINT-173)  
**Depends on**: T001, T002  
**Work type**: feature  
**Source PO**: Spec fonctionnelle 2/2 — Page `/Lakeflow/Jobs`

| | |
|---|---|
| **Maquette Jobs** | `maquette/Screen Recording 2026-07-02 at 14.29.37.html` (réf. `maquette_jobs.html`) |
| **Maquette Overview** | `maquette/maquette_overview.html` (contexte parent / drill Overview → Jobs) |

---

## 1. Vocabulaire — à figer

Chez Databricks, **un « Workflow » *est* un « Job »**. Il n'existe pas de `workflow_id` distinct d'un `job_id` : le schéma de system tables `lakeflow` s'appelait d'ailleurs `workflow` auparavant, et Databricks précise que le contenu des deux est identique. Le modèle gold DCM utilise `workflow_id` — c'est le même objet.

La hiérarchie réelle est à **3 niveaux** :

```
Workflow (= Job)           workflow_id         gold_dbx_workflow_*
└── Run                    run_id               gold_dbx_workflow_runs
     └── Task Run          task_id + task_key   gold_dbx_workflow_tasks
```

**Décision retenue :** les **Tasks n'apparaissent jamais comme onglet de premier niveau**. Elles ne sont accessibles qu'en drill-down à l'intérieur d'un run.

**DEMO interdit.** Soft-fail. Contexte nav : enfant de **Lakeflow**.

---

## 2. Arborescence

```
/Lakeflow
├── /Overview                                     → spec 1/2 (hors T004 — Databricks Overview T002)
└── /Jobs                              N1  Liste des workflows, une ligne par workflow
    └── /Jobs/{workflow_id}           N2 Détail workflow : matrice + liste de ses runs
         └── .../runs/{run_id}        N3 Détail run : timeline + liste de ses tasks
```

Le contexte de la barre haute (Landing Zone, workspaces, fenêtre) est **conservé** à chaque niveau, et le fil d'Ariane permet de remonter sans le perdre.

> En nav DCM actuelle : pas de page `/Lakeflow/Overview` dédiée — Overview = **Databricks Overview** (T002). Jobs reste sous Lakeflow.

---

## 3. Tables gold consommées

| Niveau | Table gold | Grain / PK |
|---|---|---|
| N1 — agrégats | `gold_dbx_workflow_success_rate` | jour × workflow |
| N1 — agrégats | `gold_dbx_workflow_duration_percentiles` | jour × workflow |
| N1 — agrégats | `gold_dbx_workflow_duration_drift` | jour × workflow |
| N1 — agrégats | `gold_dbx_workflow_task_failure_rate` | jour × workflow |
| N1 (colonne Historique) + N2 | `gold_dbx_workflow_runs` | `(source_lz_id, workspace_id, workflow_id, run_id)` |
| N2 (matrice) + N3 | `gold_dbx_workflow_tasks` | `(source_lz_id, workspace_id, workflow_id, run_id, task_id)` |
| N2 (santé par tâche) | `gold_dbx_workflow_task_health` | jour × workflow × `task_key` |

**Champs exposés par les deux tables de drill-down** (source : `Azure-Collector-End2End-Lineage.md` §6) :

- `gold_dbx_workflow_runs` — `run_id`, `execution_date`, `status`, `trigger_type`, `run_type`, `start_time`, `end_time`, `duration_seconds`, `queued_duration_seconds`, `execution_duration_seconds`, `schedule_lag_seconds`, `retry_count`, `tasks_total`, `tasks_failed`, `task_failure_rate`, `creator_user_name`, `cluster_instance_id`, `run_page_url`, `error_message`
- `gold_dbx_workflow_tasks` — `run_id` (parent), `task_id`, `task_key`, `execution_date`, `status`, `start_time`, `end_time`, `duration_seconds`, `attempt_number`, `cluster_instance_id`, `error_message`

---

## 4. Niveau 1 — `/Lakeflow/Jobs`

### 4.1 Intention

**Une ligne = un workflow**, agrégé sur la fenêtre. C'est la page de travail quotidienne : on y arrive soit directement, soit par clic depuis une carte de l'Overview.

### 4.2 Colonnes

| Colonne | Contenu | Table gold | Champ | Tri | Visible par défaut |
|---|---|---|---|---|---|
| **Statut** | Pastille du dernier run terminé | `gold_dbx_workflow_runs` | `status` du `MAX(start_time)` | ✅ | ✅ |
| **Workflow** | `workflow_name`, avec `workflow_id` en libellé secondaire | `..._success_rate` | `workflow_name`, `workflow_id` | ✅ | ✅ |
| **Workspace** | `workspace_name` | `gold_dbx_workflow_runs` | `workspace_name` | ✅ | ⬜ |
| **Historique** | **10 dernières exécutions** en barres verticales : couleur = statut, hauteur = durée relative | `gold_dbx_workflow_runs` | `status`, `duration_seconds` | ❌ | ✅ |
| **Runs** | Nb de runs terminaux sur la fenêtre | `..._success_rate` | `SUM(terminal_runs)` | ✅ | ✅ |
| **Succès** | % + mini-barre | `..._success_rate` | `SUM(succeeded_runs)/SUM(terminal_runs)` | ✅ | ✅ |
| **Durée moy.** | Durée formatée + `duration_drift_pct` avec flèche | `..._duration_percentiles` + `..._duration_drift` | `avg_duration_seconds`, `duration_drift_pct` | ✅ | ✅ |
| **p95** | Durée formatée | `..._duration_percentiles` | `p95` | ✅ | ⬜ |
| **Attente** | Moyenne, barre empilée queue \| lag | `..._duration_percentiles` | `avg_queued_duration_seconds`, `avg_schedule_lag_seconds` | ✅ | ✅ |
| **Retries** | Moyenne de tentatives | `..._duration_percentiles` | `avg_retry_count` | ✅ | ✅ |
| **Tâches KO** | % de tâches en échec | `..._task_failure_rate` | `SUM(tasks_failed)/SUM(tasks_total)` | ✅ | ⬜ |
| **Trigger** | Icône + libellé, cron en survol | `gold_dbx_workflow_runs` | `trigger_type` du dernier run | ✅ | ✅ |
| **Dernier run** | Temps relatif (« il y a 2 h ») | `gold_dbx_workflow_runs` | `MAX(start_time)` | ✅ | ✅ |
| **Propriétaire** | `creator_user_name` | `gold_dbx_workflow_runs` | `creator_user_name` | ✅ | ⬜ |

Sélecteur de colonnes masquables, préférences persistées par utilisateur.

### 4.3 La colonne « Historique » est la plus importante de la page

C'est la reprise de la *matrix view* de l'UI Databricks : une série de 10 barres verticales, couleur = statut, hauteur = durée relative au sein de la série.

Elle rend visible en un coup d'œil ce qu'**aucun agrégat ne montre** :

- un workflow qui alterne succès et échec (instabilité) plutôt qu'un échec isolé ;
- une durée qui dérive progressivement, run après run ;
- un workflow qui a récemment recommencé à tourner après une interruption.

Interactions : survol → tooltip (date, statut, durée, `retry_count`). Clic → détail du run (N3).

> **Implémentation — piège de performance.** Cette colonne exige les 10 derniers runs de **chaque** workflow listé. En requêtes séparées, c'est un N+1 catastrophique à 200 workflows.
> ```sql
> SELECT * FROM (
>   SELECT workflow_id, run_id, status, duration_seconds, start_time,
>         ROW_NUMBER() OVER (PARTITION BY workflow_id ORDER BY start_time DESC) rn
>   FROM gold_dbx_workflow_runs
>   WHERE workspace_id IN (:workspaces) AND workflow_id IN (:page_ids)
> ) WHERE rn <= 10
> ```
> Une seule requête, restreinte aux `workflow_id` de la page courante.

### 4.4 Tri par défaut

**Surtout pas l'ordre alphabétique.** Ordre de priorité :

1. Workflows ayant au moins un run `failed` ou `timed_out` sur la fenêtre, triés par nb d'échecs desc
2. Workflows en dérive (`duration_drift_pct > 20`), triés par drift desc
3. Le reste, par `MAX(start_time)` desc

Bascule « Ordre alphabétique » disponible. **La page s'ouvre sur ce qui pose problème** — c'est ce qui la rend consultable quotidiennement plutôt qu'une fois par mois.

### 4.5 Filtres

| Filtre | Champ gold | Type |
|---|---|---|
| Recherche | `workflow_name`, `workflow_id` | Texte libre |
| Landing Zone | `source_lz_id` | Multi-select |
| Workspace | `workspace_id` | Multi-select |
| Statut du dernier run | `gold_dbx_workflow_runs.status` | Multi-select : succeeded / failed / timed_out / cancelled / running |
| Trigger | `trigger_type` | Multi-select |
| Propriétaire | `creator_user_name` | Multi-select |
| **En dérive** | `duration_drift_pct > 20` | Toggle |
| **Sans exécution** | Aucun run sur la fenêtre | Toggle |
| **Avec retries** | `avg_retry_count > 0` | Toggle |

Les trois toggles en gras n'existent pas dans l'UI Databricks native. Ils répondent à des questions que les équipes se posent réellement — c'est une part concrète de la valeur ajoutée de DCM par rapport à l'outil natif.

> ⚠️ **Filtre par tag absent.** `tags` est marqué « non utilisé » en gold (§8.2 du doc de lineage). Sans lui, impossible de filtrer par domaine métier — on ne peut parler que `workflow_id` / `workflow_name`. C'est l'écart le plus pénalisant pour l'adoption par des utilisateurs non-data-engineers. **Correctif demandé : propager `tags` typé `MAP<STRING,STRING>` jusqu'à `gold_dbx_workflow_runs`.**

### 4.6 Requête d'assemblage N1

Les quatre tables d'agrégat partagent le même grain `(execution_date, workflow_id, workspace_id, source_lz_id)` : la jointure est directe.

```sql
WITH win AS (SELECT :date_from AS d0, :date_to AS d1),
sr AS (
 SELECT source_lz_id, workspace_id, workflow_id, ANY_VALUE(workflow_name) AS workflow_name,
       SUM(terminal_runs)  AS terminal_runs,
       SUM(succeeded_runs) AS succeeded_runs,
       SUM(failed_runs)    AS failed_runs,
       SUM(timed_out_runs) AS timed_out_runs,
       SUM(cancelled_runs) AS cancelled_runs
 FROM gold_dbx_workflow_success_rate, win
 WHERE execution_date BETWEEN d0 AND d1 AND workspace_id IN (:workspaces)
 GROUP BY ALL
),
dp AS (
 SELECT source_lz_id, workspace_id, workflow_id,
       SUM(avg_duration_seconds * total_runs) / NULLIF(SUM(total_runs),0) AS avg_duration_seconds,
        MAX(p95) AS p95, MAX(p99) AS p99,
       SUM(avg_queued_duration_seconds * total_runs) / NULLIF(SUM(total_runs),0) AS avg_queued_s,
       SUM(avg_schedule_lag_seconds  * total_runs) / NULLIF(SUM(total_runs),0) AS avg_lag_s,
       SUM(avg_retry_count           * total_runs) / NULLIF(SUM(total_runs),0) AS avg_retry_count
 FROM gold_dbx_workflow_duration_percentiles, win
 WHERE execution_date BETWEEN d0 AND d1 GROUP BY ALL
),
dd AS (   -- dernière valeur de drift disponible sur la fenêtre
 SELECT source_lz_id, workspace_id, workflow_id, duration_drift_pct, baseline_avg_14d
 FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY source_lz_id, workspace_id, workflow_id
                                    ORDER BY execution_date DESC) rn
       FROM gold_dbx_workflow_duration_drift, win
       WHERE execution_date BETWEEN d0 AND d1) WHERE rn = 1
),
tf AS (
 SELECT source_lz_id, workspace_id, workflow_id,
       SUM(tasks_failed) AS tasks_failed, SUM(tasks_total) AS tasks_total
 FROM gold_dbx_workflow_task_failure_rate, win
 WHERE execution_date BETWEEN d0 AND d1 GROUP BY ALL
)
SELECT sr.*,
     sr.succeeded_runs / NULLIF(sr.terminal_runs,0) * 100 AS success_rate_pct,
      dp.*, dd.duration_drift_pct,
      tf.tasks_failed / NULLIF(tf.tasks_total,0) * 100     AS task_failure_rate_pct
FROM sr
LEFT JOIN dp USING (source_lz_id, workspace_id, workflow_id)
LEFT JOIN dd USING (source_lz_id, workspace_id, workflow_id)
LEFT JOIN tf USING (source_lz_id, workspace_id, workflow_id)
```

**Deux règles à ne pas rater dans cette requête :**

1. Les moyennes sont **pondérées par `total_runs`**. Une moyenne simple de moyennes journalières donnerait le même poids à un jour de 2 runs et à un jour de 300.
2. `MAX(p95)` est une **approximation assumée** : un percentile ne s'agrège pas. Pour une valeur exacte sur des fenêtres multi-jours, recalculer depuis `gold_dbx_workflow_runs`. Acceptable en V1 sur la fenêtre « jour courant », où il n'y a qu'une ligne par workflow — donc exact.

---

## 5. Niveau 2 — `/Lakeflow/Jobs/{workflow_id}`

### 5.1 En-tête

`workflow_name` · `workflow_id` · `workspace_name` · `creator_user_name` · `trigger_type` · Landing Zone  
Bouton **« Ouvrir dans Databricks »** → `run_page_url` du dernier run. *(Petit détail, gros effet sur l'adoption : sans ce lien, l'utilisateur qui veut agir doit rechercher le job à la main dans Databricks.)*

### 5.2 Bandeau KPI du workflow

Cinq cartes compactes, mêmes sources qu'en N1 mais filtrées sur un seul `workflow_id` :

| Carte | Table | Champ |
|---|---|---|
| Taux de succès | `..._success_rate` | `success_rate_7d_pct` — **ici la colonne est directement utilisable**, le grain est le workflow |
| Durée moyenne + drift | `..._duration_percentiles` + `..._duration_drift` | `avg_duration_seconds`, `duration_drift_pct`, `baseline_avg_14d` |
| p50 / p95 / p99 | `..._duration_percentiles` | `p50`, `p95`, `p99` |
| Attente moyenne | `..._duration_percentiles` | `avg_queued_duration_seconds`, `avg_schedule_lag_seconds` |
| Tâches en échec | `..._task_failure_rate` | `task_failure_rate_pct` |

### 5.3 Matrice runs × tasks

Reprise du modèle Databricks. Axe X = les N derniers runs (ordre chronologique), axe Y = les `task_key` du workflow. Chaque cellule est colorée par `gold_dbx_workflow_tasks.status`.

Une ligne supplémentaire en haut, **« Run total »**, porte le statut et la durée du run entier (`gold_dbx_workflow_runs`).

**C'est la vue la plus efficace du module.** Elle répond à une question qu'aucun agrégat ne traite : *quelle tâche casse systématiquement dans un workflow qui, globalement, « passe » ?* Une ligne rouge horizontale saute aux yeux là où le taux de succès du run affiche 100 %.

Colonne latérale optionnelle depuis `gold_dbx_workflow_task_health` : `task_failure_rate_pct` et `p95_task_duration_seconds` par `task_key`, pour classer les tâches par fragilité.

### 5.4 Table des runs

| Colonne | Champ (`gold_dbx_workflow_runs`) |
|---|---|
| Début | `start_time` |
| Run | `run_id` |
| Déclencheur | `trigger_type`, `run_type` |
| Durée | Barre empilée `queued_duration_seconds` \| `execution_duration_seconds` \| reste de `duration_seconds` |
| Retard planif. | `schedule_lag_seconds` |
| Statut | `status` |
| Tâches | `tasks_failed` / `tasks_total` |
| Retries | `retry_count` |
| Cluster | `cluster_instance_id` |
| Erreur | `error_message` tronqué, dépliable |
| ↗ | `run_page_url` |

Tri par défaut : `start_time` desc. Filtres : statut, plage de dates, `trigger_type`.

> **La barre empilée de durée est le principal apport par rapport à l'UI Databricks.** Elle permet de répondre instantanément à « pourquoi ce run a-t-il pris 40 minutes ? » : attente de provisionnement (`queued`), retard d'orchestration (`schedule_lag`), ou exécution réelle (`execution`). C'est exactement la lecture demandée dans l'énoncé de l'épic.

---

## 6. Niveau 3 — `/Lakeflow/Jobs/{workflow_id}/runs/{run_id}`

Panneau latéral ou page dédiée. **Jamais un onglet de premier niveau.**

### 6.1 En-tête du run

`run_id` · `status` · `start_time` → `end_time` · `duration_seconds` · `trigger_type` · `retry_count` · `cluster_instance_id` · lien `run_page_url`.

Bandeau de décomposition de la durée : `schedule_lag` → `queued` → `execution` → reste, en barre horizontale segmentée avec les valeurs en clair.

### 6.2 Timeline des tasks (Gantt)

Une barre par `task_id`, positionnée sur l'axe temps entre `start_time` et `end_time`, colorée par `status`. Source : `gold_dbx_workflow_tasks`.

Ce que la vue rend immédiatement lisible :

- le **chemin critique** — la tâche qui détermine la durée totale ;
- le **parallélisme réel** vs celui attendu ;
- les **trous** entre tâches (attente de ressources entre deux étapes) ;
- les tâches relancées, via `attempt_number > 0`.

### 6.3 Table des tasks

| Colonne | Champ (`gold_dbx_workflow_tasks`) |
|---|---|
| Tâche | `task_key` |
| Statut | `status` |
| Début / Fin | `start_time`, `end_time` |
| Durée | `duration_seconds` |
| Tentative | `attempt_number` |
| Cluster | `cluster_instance_id` |
| Erreur | `error_message` — dépliable en intégralité |

Filtre rapide **« Tâches en échec uniquement »**.

> ⚠️ **`depends_on_keys` n'est pas exposé** dans `curated_dbx_workflow_task_runs`. Conséquences : impossible de reconstruire le DAG du workflow, et impossible d'identifier les *leaf tasks* — donc impossible de distinguer un run « Succeeded with failures » (tâches intermédiaires en échec, leaf tasks OK) d'un run pleinement réussi. **Le graphe de dépendances est hors périmètre V1** ; à demander au collecteur pour la V1.1.

---

## 7. Contrat d'API

| Endpoint | Retour | Cache |
|---|---|---|
| `GET /api/v1/lakeflow/jobs` | Liste paginée, tri et filtres **serveur**. Inclut les 10 derniers runs par workflow (colonne Historique) | 30 s |
| `GET /api/v1/lakeflow/jobs/{workflow_id}` | En-tête + bandeau KPI | 30 s |
| `GET /api/v1/lakeflow/jobs/{workflow_id}/runs` | Runs paginés + matrice runs × tasks | 30 s |
| `GET /api/v1/lakeflow/jobs/{workflow_id}/runs/{run_id}/tasks` | Task runs du run | 30 s |

Paramètres communs : `lz[]`, `workspaces[]`, `window`, `page`, `page_size`, `sort`, `order`, plus les filtres du §4.5.

**Deux points de performance :**

1. Tri et pagination **côté serveur** obligatoirement. Un parc de plusieurs centaines de workflows rend le tri client inutilisable.
2. Les percentiles et le drift sont coûteux à recalculer à la volée sur une fenêtre longue. Les tables gold étant déjà pré-agrégées au jour, la lecture est directe — **ne pas retomber sur `curated_*` depuis l'API**.

---

## 8. Écarts entre le besoin UI et le modèle gold actuel

| # | Manque | Impact | Correctif | Priorité |
|---|---|---|---|---|
| 1 | `tags` non propagé en gold | Aucun filtre par domaine métier ; on ne parle que `workflow_id` | Propager `tags` typé `MAP` jusqu'à `gold_dbx_workflow_runs` | **Haute** |
| 2 | `termination_code` absent | Pas de filtre ni de regroupement par cause d'échec — seulement du texte libre | Ajouter au collecteur → curated → gold | **Haute** |
| 3 | `depends_on_keys` absent | Pas de DAG, pas de notion de *leaf task*, pas de distinction « Succeeded with failures » | Exposer dans `_map_tasks` | Moyenne |
| 4 | `setup_duration_seconds` / `cleanup_duration_seconds` non exposés en gold | Décomposition de durée incomplète en N2/N3 | Ajouter à `gold_dbx_workflow_runs` | Moyenne |
| 5 | Pas de `task_type` | Impossible de distinguer notebook / dbt / SQL / `run_job` dans la table des tasks | Ajouter dans `_map_tasks` | Basse |
| 6 | `workspace_name` absent de `gold_dbx_workflow_tasks` | Jointure supplémentaire pour l'affichage | Propager | Basse |

---

## 9. États non nominaux

| Situation | Comportement |
|---|---|
| Aucun workflow sur la fenêtre | État vide explicite + suggestion d'élargir à 7 j |
| Workflow sans run sur la fenêtre | Ligne affichée en grisé, colonnes agrégées à `—`, badge « Aucune exécution » |
| `duration_drift_pct` null (baseline < 5 runs ou < 30 s) | `n/a` en gris, durée moyenne toujours affichée |
| Run en cours (`end_time` null) | Statut « running », durée = temps écoulé, barre animée |
| `error_message` très long | Tronqué à 120 caractères, dépliable, bouton copier |
| Task sans `end_time` | Barre Gantt ouverte vers la droite avec hachures |

---

## 10. Acceptance Criteria

- [ ] Vocabulaire Workflow=Job ; tasks pas en 1er niveau
- [ ] N1 : colonnes + Historique 10 runs (1 requête page) ; tri défaut « problèmes d’abord »
- [ ] Filtres + toggles dérive / sans exécution / retries
- [ ] N2 : KPI + matrice + table runs + lien Databricks
- [ ] N3 : Gantt + table tasks
- [ ] APIs paginées serveur ; soft-fail ; **pas DEMO** / pas prefetch id maquette
- [ ] Contexte nav Lakeflow + barre haute conservée
- [ ] UI alignée sur la maquette (§12) — menu vertical DCM existant uniquement
- [ ] PR → develop (ce sub-spec + spec parent)

---

## 11. Points à valider avec Adrien (Techlead)

1. **`tags` et `termination_code`** — inclus dans la V1 ? Ce sont les deux écarts qui pèsent le plus sur l'utilisabilité (§8, n° 1 et 2).
2. **Volumétrie** — combien de workflows et de runs par jour ? Détermine la pagination et l'intérêt d'un index sur `gold_dbx_workflow_runs(workflow_id, start_time)`.
3. **Profondeur de la colonne Historique** — 10 runs retenus ; est-ce le bon compromis lisibilité / charge ?
4. **`run_page_url`** — accessible à tous les utilisateurs DCM, ou faut-il masquer le lien selon les droits Databricks de chacun ?
5. **Rétention gold** — l'API Jobs Databricks ne conserve l'historique que **60 jours**. Le drift 14 j est donc sûr, mais toute vue au-delà de 60 jours suppose une historisation propre côté DCM. Quelle rétention cible sur `gold_dbx_workflow_runs` ?
6. **Runs sans workflow parent** (`run_type = SUBMIT_RUN`, typiquement lancés par Airflow ou ADF) — les affiche-t-on ? Ils n'ont pas de `workflow_id` stable et n'apparaîtront donc pas dans la liste N1.

---

## 12. Maquettes — obligation agent

**L’agent d’implémentation DOIT respecter la maquette Jobs** et l’adapter au design system DCM existant.

| Fichier | Rôle |
|---|---|
| `maquette/Screen Recording 2026-07-02 at 14.29.37.html` | Maquette de référence Jobs (alias PO : `maquette_jobs.html`) |
| `maquette/maquette_overview.html` | Maquette Overview (drill / cohérence visuelle avec Jobs) |

**Remarque UX (bloquante) :**

- **Pas besoin de prendre le menu horizontal** de la maquette.
- **On reste sur le menu vertical déjà existant** (sidebar DCM / groupes Lakeflow–Compute).
- Adapter layout, tableaux, Historique (barres), KPIs, matrices et drill-downs N1→N2→N3 au look & feel DCM — pas de navigation top-bar alternative.
