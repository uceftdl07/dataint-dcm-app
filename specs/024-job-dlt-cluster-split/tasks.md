# Tasks: Séparation compute Job cluster / DLT vs All-purpose

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Work type**: feature · **Priority**: P2
**Mode**: `one_per_domain` — 6 stories de domaine (2 par domaine : lot initial + amendement),
plus T007 et T008 (amendements non dispatchés), 8 tasks.

Chaque task est un index : le détail vit dans son sub-spec `stories/`.

- [ ] T001 [DataEng] Purge liste `ALL_PURPOSE` + rollup DLT `pipeline_cost_daily`/`_rolling` + ingest `system.lakeflow.pipelines` + forecast/reco `PIPELINE` → [stories/T001-purge-cluster-liste-et-rollup-dlt.md](stories/T001-purge-cluster-liste-et-rollup-dlt.md) · [DCINT-326](https://tdf.atlassian.net/browse/DCINT-326)
- [ ] T002 [Backend] Filtre dur `ALL_PURPOSE` + endpoints/schemas compute **job** & **pipeline** + forecast `object_type=PIPELINE` → [stories/T002-filtre-all-purpose-et-endpoints-job-pipeline.md](stories/T002-filtre-all-purpose-et-endpoints-job-pipeline.md) · [DCINT-328](https://tdf.atlassian.net/browse/DCINT-328)
- [ ] T003 [Frontend] Nav Compute 3 onglets (All-purpose / Jobs / Pipelines DLT) + forecast/reco par famille → [stories/T003-nav-compute-3-onglets.md](stories/T003-nav-compute-3-onglets.md) · [DCINT-327](https://tdf.atlassian.net/browse/DCINT-327)
- [x] T004 [DataEng] Rollup **efficacité** grain stable : `job_efficiency_daily`/`_rolling` + `pipeline_efficiency_daily`/`_rolling` → [stories/T004-efficacite-grain-job-et-pipeline.md](stories/T004-efficacite-grain-job-et-pipeline.md)
- [x] T005 [Backend] Endpoints `efficiency` + détail + tendances coût/uptime pour job & pipeline → [stories/T005-endpoints-efficiency-et-detail-job-pipeline.md](stories/T005-endpoints-efficiency-et-detail-job-pipeline.md)
- [ ] T006 [Frontend] Sous-onglet **Efficiency** + lignes cliquables → tiroirs job & pipeline → [stories/T006-onglet-efficiency-et-tiroirs-job-pipeline.md](stories/T006-onglet-efficiency-et-tiroirs-job-pipeline.md)
- [ ] T007 [Frontend] All-purpose clusters + Lifetime/Utilization sur Jobs & Pipelines → [stories/T007-all-purpose-rename-et-lecture-lifetime.md](stories/T007-all-purpose-rename-et-lecture-lifetime.md)
- [ ] T008 [DataEng] Colonne `compute_kind` en gold DLT + page bornée au DLT classique → [stories/T008-compute-kind-dlt-classique.md](stories/T008-compute-kind-dlt-classique.md)

Les clés Jira de T004–T008 sont **absentes volontairement** : `/speckit.dcm.dispatch` les
ajoute en fin de ligne au format `· [DCINT-nnn](url)`. Ne pas y écrire de texte libre — le
parseur le prendrait pour du titre et le dispatch en ferait un résumé de Story.

T007 n'est **pas** dispatchée (consigne utilisateur : tasks enchaînées sur la branche
`frontend/024-nav-compute-3-onglets-all-purpose-jobs`). Elle touche 2 domaines — frontend, plus
les 2 routes overview du backend — là où le reste de la spec est en `one_per_domain` : ce qui
est demandé est **une lecture d'IHM**, et la jointure backend n'existe que pour la servir.

T008 non dispatchée non plus, même branche. Elle est marquée `[DataEng]` parce que c'est le
gold qui porte la décision (colonne `compute_kind`) et que ce domaine impose la délégation à
`dp-data-databricks-engineer` ; la partie backend (filtre `CLASSIC`) est un corollaire de
quelques lignes, écrit dans la même task.

## Ordre imposé

```
T001 (gold : purge + rollup DLT + ingest pipelines + forecast) ──► déploiement dev + vérification
   └──► T002 (backend : filtre dur + endpoints job/pipeline) ──► T003 (frontend : 3 onglets)
        └──► T004 (gold : efficacité job puis pipeline) ──► déploiement dev + vérification
             └──► T005 (backend : efficiency + détail + tendances) ──► T006 (frontend : onglet + tiroirs)
```

Le fil n'est **pas** parallélisable : T002 lit les tables gold que T001 produit (rollup DLT)
et purge (liste `ALL_PURPOSE`), T003 consomme les endpoints que T002 expose. Le critère de
sortie de T001 et T002 est « déployée **et vérifiée** en dev », pas « implémentée » — les
contrôles d'acceptation SC-001/002/003 se jouent sur données réelles AWS + Azure.

Le second lot (T004→T006, amendement) suit la **même règle** : T005 lit les 4 tables gold de
T004, T006 consomme les 6 routes de T005, et le critère de sortie de T004/T005 est
« vérifiée en dev » (SC-004 / SC-005).

## Séquencement interne T001 (DataEng) — petits PR

La branche DataEng est séquencée en **4 PR** pour rester en petits diffs (Prerequisites de la
spec). Détail et fichiers dans la story. Ordre imposé par les dépendances de données :

```
T001a purge liste (ALL_PURPOSE)  ──►  T001b ingest system.lakeflow.pipelines
   └──►  T001c rollup DLT pipeline_cost_daily/_rolling  ──►  T001d forecast/reco PIPELINE
```

- **T001a** ne dépend de rien : filtre `ALL_PURPOSE` sur `cluster_cost_rolling` /
  `cluster_efficiency_rolling` / `cluster_governance`, généralisation forecast grain CLUSTER
  `cluster_type != 'JOB'` → `NOT IN ('JOB','PIPELINE')`. Débloque immédiatement la purge visuelle.
- **T001b** (ingest `pipelines`) est prérequis du **nom lisible** consommé par T001c/T002.
- **T001c** crée le rollup DLT ; **R2 à mesurer en dev avant écriture** (source du rollup —
  voir [research.md](./research.md) R2 et [quickstart.md](./quickstart.md) §0).
- **T001d** projette `object_type='PIPELINE'` dans le forecast (coût + DBU seulement, C4).

## Séquencement interne T004 (DataEng) — petits PR

```
T004a efficacité job (mapping cluster_id → job_id DÉJÀ disponible)
   └──►  T004b efficacité pipeline (mapping tranché par R7 → billing-direct)
```

- **T004a** ne dépend d'aucune mesure : la CTE `job_clusters` de `job_cluster_cost_daily`
  résout déjà `cluster_id → job_id`. À **factoriser** en helper partagé, pas à recopier.
- **T004b** n'est **plus bloquée** : R7 a été mesurée le 2026-09-09 → mapping billing-direct
  depuis `curated_dbx_billing_usage`.

## Point ouvert bloquant T001c — R2 (TRANCHÉ)

Mesuré le 2026-09-09 : **toutes** les lignes `PIPELINE_MAINTENANCE` de `billing_usage` portent
`usage_metadata.dlt_pipeline_id` → agrégation **billing directe** (option A, FR-002). Aucune
résolution `cluster_id → dlt_pipeline_id` n'a donc été écrite — c'est ce qui a rendu **R7**
nécessaire pour T004b.

## Point tranché pour T004b — R7 (mesuré le 2026-09-09)

`gold_dbx_compute_pipeline_efficiency_daily` a besoin d'un mapping
`cluster_id → dlt_pipeline_id`, l'efficacité venant de `node_timeline` (grain `cluster_id`).
Mesuré en dev sur le warehouse `DCM-metrics`, fenêtre 30 j — détail chiffré en
[research.md](./research.md) R7 :

| Mesure | Résultat |
|---|---|
| Unicité (`cluster_id` multi-pipeline) | **0** violation |
| Clusters `PIPELINE` dans `cluster_efficiency_daily` (aws / azure) | 5037 / 4 |
| Résolus par la facturation | 5029 / 4 → **99,84 % / 100 %** |
| Accord facturation vs `system.lakeflow.pipeline_update_timeline` | **61 826 / 61 826**, 0 désaccord |

**Décision : mapping billing-direct** (couples distincts `(cluster_id, dlt_pipeline_id)` depuis
`curated_dbx_billing_usage`) — validé par la source documentée, couvre les deux clouds sans
ingestion nouvelle, et **même source que le coût**, donc pas de contradiction possible dans
l'IHM. Résidu assumé : 8 clusters AWS sur 5037, **exclus** par `INNER JOIN`, jamais rattachés
par défaut (à documenter en SC-005).

Le parsing du nom `dlt-execution-<id>` reste **rejeté** bien qu'exact aujourd'hui (0 désaccord
mesuré) : c'est un contrat non documenté. Si la facturation cessait de projeter `cluster_id`,
le correctif est d'ingérer `system.lakeflow.pipeline_update_timeline` **pour les deux clouds**.

## Dépendances externes

| Ce dont T001 dépend | État |
|---|---|
| `cluster_type_case_expr` (classification JOB/ALL_PURPOSE/PIPELINE/OTHER) | ✅ présent (`sql_helpers.py`), réutilisé |
| `billing_usage.usage_metadata.dlt_pipeline_id` fiable AWS + Azure | ⚠️ **à mesurer** (R2) avant T001c |
| `system.lakeflow.pipelines` lisible | à ingérer (T001b) |

| Ce dont T002 dépend | État |
|---|---|
| Tables gold liste purgées `ALL_PURPOSE` | produit par T001a |
| `gold_dbx_compute_pipeline_cost_rolling` | produit par T001c |
| `gold_dbx_compute_job_cluster_cost_rolling` | ✅ déjà présent (jamais exposé) |

| Ce dont T003 dépend | État |
|---|---|
| Endpoints compute job & pipeline | produit par T002 |

| Ce dont T004 dépend | État |
|---|---|
| `gold_dbx_compute_cluster_efficiency_daily` porte encore JOB et PIPELINE | ✅ vérifié (le filtre `ALL_PURPOSE` de T001a ne borne que le `_rolling`) |
| Résolution `cluster_id → job_id` | ✅ présente (`job_cluster_cost_daily.py`, CTE `job_clusters`) — à factoriser |
| Résolution `cluster_id → dlt_pipeline_id` | ✅ **tranchée** (R7, 2026-09-09) : billing-direct depuis `curated_dbx_billing_usage`, 99,84 % de couverture |
| Helpers histogrammes / fenêtres | ✅ présents (`sql_helpers.py`) |

| Ce dont T005 dépend | État |
|---|---|
| `gold_dbx_compute_job_efficiency_rolling` / `pipeline_efficiency_rolling` | produit par T004 |
| `*_cost_daily` / `*_efficiency_daily` (tendances) | coût ✅ présent ; efficacité produite par T004 |
| Services `compute_metrics_jobs` / `_pipelines` | ✅ présents (T002), à étendre |

| Ce dont T006 dépend | État |
|---|---|
| 6 routes efficiency / détail / tendances | produit par T005 |
| Patron de tiroir (`compute-cluster-drawer`) | ✅ présent, à décliner sans gouvernance |

| Ce dont T007 dépend | État |
|---|---|
| `*_efficiency_rolling` job & pipeline (uptime + `utilization_status`) | produit par T004 |
| Pages Jobs / Pipelines à 3 sous-onglets | produit par T006 |
| Page clusters déjà bornée à `ALL_PURPOSE` | produit par T001a — c'est ce qui rend la colonne `Cluster type` redondante |

## Success Criteria (rappel spec)

- **SC-001** : 0 ligne `cluster_type` ≠ `ALL_PURPOSE` renvoyée par l'endpoint liste clusters.
- **SC-002** : chaque `dlt_pipeline_id` facturé apparaît exactement une fois par fenêtre.
- **SC-003** : Σ `cost_usd` `pipeline_cost_daily` = Σ `cost_usd` `cluster_cost_daily` restreint `PIPELINE`.
- **SC-004** : une ligne par grain × `window_days` dans les `*_efficiency_rolling`, p95 dans `[0,100]`, `uptime_hours > 0`.
- **SC-005** : taux de couverture efficacité **mesuré et documenté** par famille (résidu attendu, pas un échec).
- **SC-006** : 3 sous-onglets présents et clic → tiroir renseigné sur chaque page (test + navigateur).

## Invariant anti-double-comptage

`pipeline_cost_daily` et `job_cluster_cost_daily` sont des **rollups des mêmes lignes** de
facturation que `cluster_cost_daily`. Ne **jamais** les sommer ensemble — chacun agrège son
sous-ensemble disjoint par `cluster_type`.

Le même invariant vaut pour l'efficacité : `job_efficiency_*` et `pipeline_efficiency_*` sont
des rollups des mêmes lignes de `cluster_efficiency_daily` (sous-ensembles disjoints par
`cluster_type`). Leurs `uptime_hours` ne se somment pas avec ceux du grain cluster.

## Invariant « pas de faux signal »

Une métrique qui n'a pas de sens à un grain n'est **pas produite vide** : `is_zombie` est
absente des tables d'efficacité job/pipeline (elle serait `false` partout et se lirait comme
un contrôle qui passe), et le bloc `governance` est absent des payloads de détail (clé
absente, pas `null`). Un grain sans efficacité mesurable n'a pas de ligne, et l'UI affiche
« — » — jamais `0`.
