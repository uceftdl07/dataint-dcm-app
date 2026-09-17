# T004 — Rollup efficacité au grain stable `job_id` / `dlt_pipeline_id`

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: `dataeng/024-rollup-efficacite-grain-stable-job`
**Jira**: à créer (`/speckit.dcm.dispatch`) — Epic [DCINT-325](https://tdf.atlassian.net/browse/DCINT-325)
**Depends on**: T001 (socle gold livré) ; interne : T004a → T004b (R7 tranchée le 2026-09-09)
**Work type**: feature

## Description

Amendement du 2026-09-09. T001–T003 ont livré le **coût** aux grains stables `job_id` et
`dlt_pipeline_id`, mais pas l'**efficacité** : les pages Jobs et Pipelines DLT n'ont donc que
2 sous-onglets et des lignes inertes. Cette task produit le socle manquant.

La matière première **existe déjà** : `gold_dbx_compute_cluster_efficiency_daily` conserve les
clusters `JOB` et `PIPELINE` (le filtre `ALL_PURPOSE` de T001a ne borne que le `_rolling`).
Il ne manque que l'agrégation au grain stable.

Quatre tables neuves, en **2 PR** :

1. **T004a** — `gold_dbx_compute_job_efficiency_daily` + `_rolling` (grain `job_id`).
2. **T004b** — `gold_dbx_compute_pipeline_efficiency_daily` + `_rolling` (grain
   `dlt_pipeline_id`), mapping billing-direct tranché par R7.

## R7 — mapping DLT tranché (mesuré en dev le 2026-09-09)

Le rollup **coût** DLT est *billing-direct* (R2, option A) : aucune résolution
`cluster_id → dlt_pipeline_id` n'avait été écrite. Or l'efficacité vient de `node_timeline`,
au grain `cluster_id`. Mesuré sur le warehouse `DCM-metrics`, fenêtre 30 j :

| Mesure | Résultat |
|---|---|
| Unicité — `cluster_id` portant plusieurs `dlt_pipeline_id` | **0** violation |
| Clusters `PIPELINE` présents dans `cluster_efficiency_daily` (aws / azure) | 5037 / 4 |
| Résolus par la facturation (`usage_metadata.cluster_id`) | 5029 / 4 → **99,84 % / 100 %** |
| Accord avec `system.lakeflow.pipeline_update_timeline` (source documentée) | **61 826 / 61 826**, 0 désaccord |

**Mapping retenu : billing-direct**, couples distincts `(cluster_id, dlt_pipeline_id)` depuis
`curated_dbx_billing_usage`. Trois raisons : validé sans divergence par la source documentée ;
couvre **les deux clouds** sans ingestion nouvelle (`system.lakeflow` n'est lisible que côté
AWS, l'option C perdrait l'efficacité DLT Azure) ; et c'est **la même source que le coût**,
donc coût et efficacité ne peuvent pas désigner deux pipelines différents pour un cluster.

**Résidu** : 8 clusters AWS sur 5037 sans ligne de facturation portant un `cluster_id` →
**exclus** (`INNER JOIN`), jamais rattachés par défaut. À documenter en SC-005.

Le parsing du nom `dlt-execution-<id>` reste **rejeté** malgré 0 désaccord mesuré : contrat non
documenté. Repli en cas de régression amont : ingérer `pipeline_update_timeline` (2 clouds).

⚠️ **Piège de dénominateur** : mesurée sur *tous* les pipelines facturés, la couverture semble
tomber à 6 %. C'est un artefact — les pipelines manquants sont **serverless**, sans cluster,
donc hors de portée de toute option. Le dénominateur qui décide est l'ensemble des clusters
`PIPELINE` présents dans `cluster_efficiency_daily`.

Le mapping job, lui, ne demandait aucune mesure : la CTE `job_clusters` de
`job_cluster_cost_daily.py` le résout déjà.

## Files to create/modify

### T004a — efficacité job
- UPDATE `pipelines/gold_dbx_compute/job_cluster_cost_daily.py` — extraire la CTE
  `job_clusters` en helper réutilisable (comportement inchangé, SQL identique)
- CREATE `pipelines/gold_dbx_compute/grain_resolution.py` — helpers de résolution
  `cluster_id → job_id` / `→ dlt_pipeline_id`. **Écart assumé** avec la rédaction initiale, qui
  visait `sql_helpers.py` : ces helpers portent une connaissance de *lignée* (quelle table
  curated, quel résultat de mesure R7, pourquoi un `INNER JOIN`), alors que `sql_helpers` ne
  contient que des primitives SQL génériques. Les mélanger aurait fait de `sql_helpers` une
  dépendance du modèle de données
- CREATE `pipelines/gold_dbx_compute/job_efficiency_daily.py` —
  `build_job_efficiency_daily(...)`, grain `(cloud_provider, workspace_id, job_id, period_start)`
- CREATE `pipelines/gold_dbx_compute/job_efficiency_rolling.py` —
  `build_job_efficiency_rolling(...)`, `+ window_days`, miroir de `cluster_efficiency_rolling.py`
- UPDATE `pipelines/gold_dbx_compute/specs.py` — `GOLD_JOB_EFFICIENCY_DAILY`/`_ROLLING`,
  merge keys, specs + `column_comments`, entrées `GOLD_SPECS`, `__all__`
- UPDATE `pipelines/gold_dbx_compute/entrypoint.py` — câbler les 2 builders **après**
  `cluster_efficiency_daily` (dépendance directe)
- UPDATE `resources/job_dcm_gold_dbx_compute.yml` — **2 tâches** `python_wheel_task` neuves
  (`gold_job_efficiency_daily` → `depends_on: gold_cluster_efficiency_daily`, puis
  `gold_job_efficiency_rolling` → `depends_on: gold_job_efficiency_daily`). Omis de la première
  rédaction de cette story : sans ces tâches, les tables sont enregistrées mais **jamais
  calculées** en dev
- CREATE `tests/gold_dbx_compute/test_job_efficiency.py`
- UPDATE `tests/gold_dbx_compute/test_entrypoint.py`, `test_job_cluster_cost_daily.py`,
  `test_pipeline_cost.py`, `test_specs.py` (helpers extraits — non-régression SQL)

### T004b — efficacité pipeline
- CREATE `pipelines/gold_dbx_compute/pipeline_efficiency_daily.py` — grain
  `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)`, mapping issu de R7
- CREATE `pipelines/gold_dbx_compute/pipeline_efficiency_rolling.py` — `+ window_days`
- UPDATE `pipelines/gold_dbx_compute/specs.py` — `GOLD_PIPELINE_EFFICIENCY_DAILY`/`_ROLLING`
  (+ merge keys, specs, `GOLD_SPECS`)
- UPDATE `pipelines/gold_dbx_compute/entrypoint.py` — câblage
- UPDATE `resources/job_dcm_gold_dbx_compute.yml` — 2 tâches symétriques
  (`gold_pipeline_efficiency_daily` / `_rolling`)
- CREATE `tests/gold_dbx_compute/test_pipeline_efficiency.py`
- UPDATE `tests/gold_dbx_compute/test_entrypoint.py`

## Sub-tasks

### T004a — efficacité job
- [x] **Tests d'abord** (`FakeSpark`, SQL généré) : source filtrée `cluster_type = 'JOB'` ;
      grain `(cloud_provider, workspace_id, job_id, period_start)` ; moyennes et `idle_pct`
      **pondérées par `uptime_hours`** ; p95 issus de `percentile_from_histogram_sql` sur des
      histogrammes **sommés** (jamais `AVG(cpu_util_p95_pct)`) ; `uptime_hours` sommé ;
      `cluster_count = COUNT(DISTINCT cluster_id)` ; **aucune** colonne `is_zombie` ;
      `LEFT JOIN prev_agg` portant `window_days` dans sa condition ;
      `WHERE uptime_hours > 0` en sortie du `_rolling` ; fenêtre précédente `NULL` (jamais `0`).
- [x] Extraire le helper de résolution `cluster_id → job_id` (SQL identique — un test de
      non-régression sur `job_cluster_cost_daily` le prouve).
- [x] `job_efficiency_daily.py` : `INNER JOIN` délibéré sur le mapping ; une ligne dont le
      `job_id` n'est pas résolvable est **exclue** (clé de merge jamais NULL).
- [x] `job_efficiency_rolling.py` : CTE `daily`/`anchor`/`windows`/`latest_attrs`/`agg`/
      `prev_agg`/`with_metrics`, seuils de `utilization_status` / `rightsizing_reco`
      **identiques** à ceux du grain cluster.
- [x] `specs.py` + `entrypoint.py` : registre + câblage (ne jamais modifier une entrée existante).
- [x] Gates : `pytest` (715 tests du package), `ruff check` (15 fichiers touchés, propre),
      `mypy` (0 erreur sur les 9 fichiers touchés), `bundle validate --strict`.
- [x] Déploiement dev + **SC-004** / **SC-005** — résultats en « Vérification dev » ci-dessous.

### T004b — efficacité pipeline
- [x] **R7 mesurée en dev** (2026-09-09) — résultats et décision consignés ci-dessus :
      mapping billing-direct, 0 violation d'unicité, 99,84 % de couverture, validé sans
      divergence contre `system.lakeflow.pipeline_update_timeline`.
- [x] **Tests d'abord** : mêmes assertions que T004a au grain `dlt_pipeline_id`, plus
      l'exclusion documentée du **DLT serverless** (aucune ligne `node_timeline` → aucune ligne
      d'efficacité, sans perte de la ligne de coût).
- [x] `pipeline_efficiency_daily.py` + `_rolling.py`.
- [x] `specs.py` + `entrypoint.py`.
- [x] Gates + déploiement dev : **SC-004** et **SC-005** au grain pipeline.

## Vérification dev (2026-09-09)

Déployé sur `dev_local` (`--profile dcm-dev`, OAuth) puis run `639064433481168` limité aux
4 tâches neuves via `run_now` + `only` — la source `cluster_efficiency_daily` étant déjà
peuplée, relancer les 22 tâches n'aurait rien apporté. Les 4 : **SUCCESS**.

| Table | lignes | grains | période |
|---|---|---|---|
| `job_efficiency_daily` | 71 954 | 6 580 jobs | 2026-07-07 → 09-09 |
| `job_efficiency_rolling` | 14 937 | 6 580 jobs | as_of 2026-09-09 |
| `pipeline_efficiency_daily` | 7 716 | 202 pipelines | 2026-07-06 → 09-09 |
| `pipeline_efficiency_rolling` | 624 | 202 pipelines | as_of 2026-09-09 |

### SC-004 — toutes les assertions à 0

Unicité `grain × window_days` (rolling) et `grain × period_start` (daily) : **0** doublon sur les
4 tables. `cpu/mem_util_p95_pct` hors `[0,100]` ou `uptime_hours <= 0` : **0**. Clé de merge
`NULL` : **0** (l'`INNER JOIN` fait son travail). `uptime_hours_prev_window = 0` : **0** — la
fenêtre précédente est bien `NULL` et jamais `0`. Fenêtre 90 j : `prev_window` `NULL` partout,
attendu tant que l'historique fait 65 jours.

`DESCRIBE` des 4 tables : **aucune** colonne `is_zombie`, `cluster_name`, `cluster_type`,
`dbr_version`, owner ni oversizing.

### Contrôle d'arithmétique (au-delà de SC-004)

Sur le job le plus agrégé d'une journée (**739 clusters**, 73,65 h allumées), recalcul complet
depuis `cluster_efficiency_daily` : `cluster_count`, `uptime_hours`, `active_hours`,
`worker_count_max`, `estimated_savings_usd` et les 4 moyennes pondérées (`cpu`, `mem`, `idle`,
`worker_count_avg`) **égaux à 10⁻⁹ près**. La pondération par `uptime_hours` est donc exacte sur
données réelles, pas seulement sur `FakeSpark`.

Anti-double-comptage du mapping R7 : Σ `uptime_hours` de `pipeline_efficiency_daily` = 3538,7833
= Σ recalculée sur les clusters `PIPELINE` résolus, **à l'identique**. **0** cluster rattaché à
plusieurs pipelines. Écart avec le total des clusters `PIPELINE` (3541,9333) = **3,15 h, soit
0,089 %** — exactement les 8 clusters du résidu R7.

### SC-005 — couverture mesurée

Le dénominateur naïf (tout `*_cost_rolling`) **ment** : les rollups de coût émettent une ligne
par grain de tout l'historique × chaque fenêtre, à `cost_usd = 0` hors activité (comportement
pré-existant, identique sur `cluster_`/`job_cluster_`/`pipeline_cost_rolling`), alors que les
rollups d'efficacité portent `WHERE uptime_hours > 0`. Il faut donc filtrer `cost_usd > 0`.

| Famille | dénominateur naïf | dénominateur réel (`cost_usd > 0`) | mesurés | couverture |
|---|---|---|---|---|
| job | 6 759 → 71,7 % | **4 896** | 4 846 | **99,0 %** |
| pipeline | 6 062 → 2,9 % | **2 965** | 174 | **5,9 %** |

**Résidu job (70 grains)** : les 70 sont résolvables par le mapping — ce n'est donc *pas* une
lacune de résolution. 69 n'ont aucune ligne dans `cluster_efficiency_daily` (lacune
`node_timeline` **amont**) ; le 70ᵉ tourne sur un cluster **`ALL_PURPOSE`**, donc exclu à juste
titre par `WHERE cluster_type = 'JOB'` : son efficacité appartient à la page All-purpose.

**Résidu pipeline** : les 5,9 % sont le même piège de dénominateur que R7. Décomposé :
**181** pipelines facturés tournent sur un cluster classique → **174 mesurés = 96,1 %** ; les
**2 784** autres sont **serverless**, sans `node_timeline`, hors de portée de *toute* option de
mapping. Le chiffre à publier est 96,1 % sur le périmètre atteignable, avec le serverless
déclaré non mesurable — pas 5,9 % présenté comme un échec.

### Deux artefacts constatés, non corrigés (délibérément)

1. `idle_pct` = `100.00000000000001` sur 1 ligne (ε = 1,4·10⁻¹⁴) : arrondi double précision de
   la moyenne pondérée. **Déjà présent** dans `cluster_efficiency_rolling` livré en T001
   (91 lignes). Clamper à `LEAST(…, 100)` ici seulement créerait une divergence avec la table
   existante pour un écart invisible à l'affichage.
2. `cpu_util_p95_pct` < `cpu_util_avg_pct` sur 2,50 % des lignes job : granularité des buckets
   d'histogramme, pas une erreur de calcul. Taux comparable à l'existant
   (`cluster_efficiency_rolling` : 1,50 %) ; légèrement plus haut car le grain job somme
   jusqu'à 739 histogrammes au lieu d'un seul.

## Notes

- **`cluster_efficiency_daily` ne doit pas être filtrée** `ALL_PURPOSE` : c'est la source de
  cette task. À écrire dans le docstring des 4 builders neufs — un futur filtre « pour
  l'uniformité » supprimerait silencieusement l'efficacité job/pipeline.
- **Percentiles jamais moyennés** : un p95 de p95 quotidiens n'a pas de sens. Réutiliser
  `sum_histograms_sql` + `percentile_from_histogram_sql`, exactement comme
  `cluster_efficiency_rolling`.
- **Pas de `is_zombie`** (R8) : à ce grain la colonne serait `false` partout et se lirait comme
  un contrôle qui passe. Ne pas la produire vaut mieux que la produire vide.
- **Pas de gouvernance** (C2 inchangé) : aucun `dbr_version`, owner tag ni oversizing.
- **Anti-double-comptage** : `job_efficiency_*` et `pipeline_efficiency_*` sont des rollups de
  sous-ensembles **disjoints** de `cluster_efficiency_daily` — leurs `uptime_hours` ne se
  somment ni entre eux ni avec le grain cluster.
- L'écart de population entre `*_cost_*` et `*_efficiency_*` est **attendu** (couverture
  `node_timeline`) : le mesurer et l'écrire (SC-005), jamais le combler par une valeur par
  défaut (P9).
