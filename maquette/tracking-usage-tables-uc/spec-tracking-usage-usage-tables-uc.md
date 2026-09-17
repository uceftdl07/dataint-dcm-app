# Spec — Usage des tables UC

> Statut : DRAFT — issu du spike challengé. Trois vues (Par table / Par consommateur / FinOps), précédées d'une section Vue d'ensemble (fusionnée depuis l'ancienne page Overview).
> Page accessible depuis le menu **Databricks** (plus de section "Tracking d'usage" séparée dans la sidebar). Module réduit à 2 pages : **Usage des tables UC** et **Gouvernance & Recommandations**.
> Persona cible : OWN, FIN, AN, DE, GOV.

## ⚠️ Vérification du périmètre réel (mapping feature 019)

Périmètre confronté au code livré dans `packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/` (registre `specs.py::GOLD_SPECS`) et aux jobs `resources/job_dcm_gold_dbx_usage.yml` / `resources/job_dcm_gold_forecast.yml`.

- **8 tables gold, pas 6** : `table_daily`, `table_popularity_daily`, `consumer_daily`, `table_query_performance_daily`, `table_catalog`, `table_governance`, `recommendations`, `forecast_daily`.
- **✅ `gold_dbx_usage_forecast_daily` est implémentée et déployée** (`forecast_daily.py`, tâche `gold_usage_forecast_daily` du job `dcm_gold_forecast`). Grain `(cloud_provider, object_type, object_id, metric_name, horizon_date)` ; `object_type` toujours `DATA_PRODUCT`, `object_id` = `table_full_name` ; colonnes `predicted_value`/`lower_bound`/`upper_bound`/`method` (toujours `ai_forecast`). Les 4 métriques projetées sont `request_count`, `distinct_consumers`, `estimated_cost_usd`, `data_read_bytes`.
- **⚠️ L'horizon réel est de 7 jours, pas 14** (`FORECAST_HORIZON_DAYS = 7` ; les 14 jours sont la fenêtre d'ENTRAÎNEMENT, `FORECAST_OBSERVED_LOOKBACK_DAYS = 14`). Tous les libellés "+14j" du mockup sont à corriger en "+7j" — sinon l'UI promet un horizon que la table ne contient pas.
- **⚠️ Pas de prévision pour une table sans activité récente** : la fenêtre d'entraînement borne aussi la population projetée — une table dont toutes les lignes de `table_popularity_daily` sont antérieures à `today - 14j` ne produit AUCUNE ligne de forecast. L'UI doit traiter l'absence de ligne comme "pas de projection", pas comme une projection à zéro.
- **⚠️ Aucune prévision de volume ÉCRIT** : `data_written_bytes` ne fait pas partie des 4 métriques projetées. Une carte de tendance "Volume écrit +7j" n'a pas de source ; seul l'historique observé est disponible.
- **✅ `gold_dbx_usage_recommendations` est implémentée et déployée** (`recommendations.py`, tâche `gold_usage_recommendations` du job `dcm_gold_dbx_usage`). Le bloc "Points d'attention" (FR0) a donc une source. Grain `(recommendation_id)` ; `object_type` ∈ {**`DATA_PRODUCT`**, `CONSUMER`} — **pas `TABLE`** ; `category` ∈ {`LIFECYCLE`, `FRESHNESS`, `GOVERNANCE`, `RELIABILITY`, `FINOPS`} ; `severity` ∈ {`HIGH`, `MEDIUM`, `LOW`} ; `status` ∈ {`OPEN`, `RESOLVED`} ; `mode` toujours `REACTIVE`.
- **✅ Confirmé (non un gap)** : le module ne nécessite pas de grain `workspace_id`. Le périmètre se pilote entièrement via période + catalogue/schéma/table(s), cohérent avec le grain réel des tables gold (`cloud_provider, catalog, schema, table_name, ...` — jamais `workspace_id`). Les filtres Workspace et LZ ajoutés dans une itération précédente du bandeau sont retirés du mockup — ils ne correspondaient à aucun besoin réel du module.
- **Périmètre des tables** : toutes les tables visibles dans Unity Catalog sont suivies, sans exception, y compris les tables techniques, curated, staging et internes DCM. Le champ `is_data_product` reste disponible comme attribut de segmentation future, mais ne filtre pas le périmètre courant.
- **✅ `data_written_bytes` / `rows_written` sont alimentés** dans `gold_dbx_usage_table_daily` : `query_history.written_bytes`/`written_rows` rattachés à la table CIBLE via le côté `target_*` du lineage, répartis à parts égales entre les cibles distinctes du statement. La carte "Volume écrit" de la Vue d'ensemble a donc une courbe réelle — pas d'état "En attente de données".
- **⚠️ `data_written_bytes` est `NULL`, jamais `0`, quand le volume n'est pas mesurable** (événement de lineage sans `statement_id`, cas des pipelines DLT). Un `SUM` traite ce NULL comme absent : ne pas afficher un total partiel comme un total complet, et ne jamais convertir NULL en 0 côté UI.
- **⚠️ Les lignes d'écriture portent `request_count = 0`** (la même requête est déjà comptée par la branche de lecture ; la renseigner deux fois doublerait le compte). Une table uniquement écrite apparaît donc avec 0 requête et un volume écrit non nul — comportement attendu, à ne pas lire comme une anomalie.
- **⚠️ `data_written_bytes` n'existe QUE dans `table_daily`** : ni `table_popularity_daily` ni `consumer_daily` ne l'agrègent. La carte "Volume écrit" doit lire `table_daily`, pas `table_popularity_daily` comme les autres KPI de volume.
- **Renommage de colonnes** : `cost_usd` → `estimated_cost_usd` partout ; le registre utilise `catalog`/`schema` (pas `table_catalog`/`table_schema`).
- **`distinct_data_products`** (consumer_daily) est un nom de colonne historique conservé dans le Gold ; son sens fonctionnel est "nombre de tables distinctes". L'UI et les specs fonctionnelles parlent uniquement de tables.
- **⚠️ `consumer_rank` n'est PAS partitionné par `cloud_provider`** : `RANK() OVER (PARTITION BY period_start ORDER BY SUM(estimated_cost_usd) DESC)` — un seul palmarès mélangeant aws et azure, contrairement à `popularity_rank` qui partitionne bien par `(cloud_provider, period_start)`. Deux classements de la même page ne suivent donc pas la même règle. La docstring de `consumer_daily.py` affirme l'inverse ("même partition que `popularity_rank`") : incohérence à remonter au data engineering, à trancher avant de brancher la vue Par consommateur.
- **`consumer_type` n'a pas de valeur `GENIE`**. Ce n'est pas une énumération fermée côté gold : hors branche audit, la valeur est le `entity_type` du lineage repris tel quel (`COALESCE(entity_type, 'UNKNOWN')`), donc `USER`, `SERVICE_PRINCIPAL`, `JOB`, `NOTEBOOK`, `PIPELINE`, `DASHBOARD_V3`, `UNKNOWN` selon ce que publie la source. Le traitement Genie (FR7) n'est donc pas qu'une décision PO en attente : c'est un développement non démarré côté data engineering (curated + gold).
- **Attribution de coût** : `cost_attribution_method` vaut `equal_parts_fallback` quand un coût a été calculé, et `NULL` quand aucun coût ne l'a été (la colonne décrit un calcul effectué, pas une intention). À afficher en tooltip/footnote partout où `estimated_cost_usd` apparaît, pour ne pas laisser croire à une attribution pondérée par volume réel.
- **⚠️ Le partage à parts égales inclut les vues** : une lecture via une vue `v` au-dessus de `t` produit une ligne sur `v` ET sur `t`, toutes deux facturées à parts égales. Le total par requête reste juste (redistribution, pas duplication), mais le coût d'une table n'est pas comparable à celui qu'elle aurait sans la vue. Idem pour `request_count` : ne pas sommer les lignes de plusieurs objets d'une même requête en espérant retrouver un nombre de requêtes.
- **⚠️ `costed_request_count` (table_daily) est le dénominateur qui dit si un coût est partiel** : `estimated_cost_usd` est une SOUS-ESTIMATION dès que `costed_request_count < request_count`, et `costed_request_count = 0` va de pair avec un coût NULL. Cette colonne n'existe pas dans `table_popularity_daily` : au grain table/jour, la complétude du coût n'est pas exposée.
- **⚠️ `cost_basis` (table_daily) additionne des grandeurs différentes** : `warehouse_prorata` (seul prorata fidèle), `serverless_job_prorata` et `cluster_prorata` (coût de TOUT le job/cluster attribué à ses seuls statements SQL), `mixed` (plusieurs seaux dans le même groupe). À exposer avec le coût, sinon deux lignes de coût non comparables se lisent comme comparables.
- **`catalog_resolution_status`** désambiguïse `unknown_data_product` : `RESOLVED`, `NOT_VISIBLE_TO_PIPELINE` (l'objet existe, le pipeline n'a pas le privilège de le voir), `NEVER_RESOLVED`. À utiliser pour tout badge "table inconnue" — `unknown_data_product` seul confond absence de data product et manque de GRANTS.

## User Scenarios

- En tant que propriétaire de tables, je veux voir en un coup d'œil l'état global de l'usage (lectures, coût, consommateurs) en arrivant sur la page, avant de creuser une vue de détail.
- En tant que propriétaire de tables, je veux voir qui lit une table précise (top consommateurs) pour évaluer l'impact d'une dépréciation.
- En tant que FinOps, je veux le classement des consommateurs par coût pour identifier les usages les plus chers et sensibiliser les équipes concernées.
- En tant que FinOps, je veux le coût par table avec sa projection à 7 jours, dans la même page que le reste de l'usage, pour ne pas naviguer entre plusieurs pages pour une analyse coût.
- En tant qu'analyste, je veux filtrer sur un sous-ensemble précis de tables (multi-sélection) pour ne voir que le périmètre qui me concerne, quelle que soit la vue active.

## Functional Requirements

- FR0 — La page s'ouvre sur une section **Vue d'ensemble** (fusionnée depuis l'ancienne page Overview) : 6 KPI agrégés, 4 cartes de tendance (3 prédictives + 1 "Volume écrit" observé), et un bloc "Points d'attention" (top 3 recommandations sévères, renvoyant vers Gouvernance & Recommandations). Cette section est au-dessus du switch de vues et n'est pas dans un onglet séparé. Les 3 tendances prédictives lisent `gold_dbx_usage_forecast_daily` (**horizon 7 jours**, pas 14) et le bloc Points d'attention `gold_dbx_usage_recommendations` (`status = 'OPEN'`, `severity = 'HIGH'`), les deux tables étant livrées. La carte "Volume écrit" est un historique OBSERVÉ (`table_daily.data_written_bytes`), pas une projection : `data_written_bytes` ne fait pas partie des métriques prévues par `forecast_daily`.
- FR1 — Trois vues accessibles par tabbar, sous la Vue d'ensemble : **Par table** (défaut), **Par consommateur**, **FinOps**. Le switch ne recharge pas les filtres communs.
- FR2 — Les filtres catalogue/schéma/table(s) sont **communs aux trois vues** : le filtre table restreint la vue "Par consommateur" aux consommateurs ayant lu au moins une des tables sélectionnées (intersection, pas égalité stricte) ; il restreint la vue FinOps aux tables sélectionnées directement.
- FR3 — Vue Par table : chaque ligne est dépliable (drill-down) pour afficher le **top 5 consommateurs** de cette table triés par coût. Chaque ligne affiche aussi la **fraîcheur** de la table, qui se lit sur `freshness_lag_hours` accompagné de `freshness_basis` — pas sur `last_write_at` seul, `NULL` dès qu'aucune écriture n'est prouvée (toutes les VIEW notamment).
- FR4 — Vue Par consommateur : classement complet trié par coût décroissant par défaut, les 5 premiers visuellement mis en avant (badge de rang).
- FR5 — Vue FinOps : KPI de coût agrégé, tableau de coût par table. La colonne prévisionnelle lit `forecast_daily` (`metric_name = 'estimated_cost_usd'`) et s'intitule **"Forecast +7j"** : l'horizon livré est de 7 jours. Une table sans activité sur les 14 derniers jours n'a aucune ligne de prévision — afficher un tiret, pas un zéro.
- FR6 — Recherche texte libre filtrant par nom (table ou consommateur selon la vue active ; sans effet sur la vue FinOps qui est déjà filtrée par le multi-select table).
- FR7 — ⛔ **BLOQUÉ (pas seulement une décision PO)** : le traitement des requêtes **Genie** nécessite un développement data engineering non démarré — `consumer_type` n'a aujourd'hui aucune valeur `GENIE` en gold, et la propagation de `query_source.genie_space_id` depuis `curated_dbx_query_history` n'est pas confirmée. Le filtre "GENIE" ajouté au mockup est prématuré tant que ce travail n'est pas engagé. Une fois fait, décision PO restante : `consumer_id` = `genie_space_id` ou identité utilisateur + tag.
- FR8 — Le drill-down "top 5 consommateurs par table" est plafonné à 5 (pas de pagination).
- FR9 — [NEEDS DECISION PO] Les filtres catalogue/schéma/table(s) doivent-ils être **persistés** en naviguant vers Gouvernance & Recommandations depuis le bloc "Points d'attention" ?

## Key Entities & Data Sources

### Vue d'ensemble (FR0 — fusionnée depuis Overview)

| Élément UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| KPI Tables suivies | `gold_dbx_usage_table_daily` | `table_full_name` (dérivé de `catalog.schema.table_name`) | `COUNT(DISTINCT table_full_name)` |
| KPI Requêtes + delta | `gold_dbx_usage_table_popularity_daily` | `request_count`, `request_count_prev_day` | `SUM(request_count)`, delta vs période précédente |
| KPI Consommateurs distincts | `gold_dbx_usage_table_daily` | `consumer_id` | `COUNT(DISTINCT consumer_id)` |
| KPI Coût attribué + delta | `gold_dbx_usage_table_popularity_daily` | `estimated_cost_usd` | `SUM(estimated_cost_usd)` sur période courante vs précédente |
| KPI Tables inutilisées | `gold_dbx_usage_table_governance` | `is_unused` | `COUNT(is_unused=true)` — snapshot d'état courant, insensible au filtre de période |
| KPI Taux d'échec d'accès | `gold_dbx_usage_table_query_performance_daily` | `failed_count`, `query_count` | `SUM(failed_count)/SUM(query_count)×100` |
| Tendance Lectures +7j | `gold_dbx_usage_forecast_daily` | `metric_name='request_count'`, `predicted_value`, `lower_bound`, `upper_bound`, `horizon_date` | `SUM(predicted_value)` par `horizon_date` sur les `object_id` du périmètre — bande de confiance à 95 % via `lower_bound`/`upper_bound` |
| Tendance Coût $ +7j | `gold_dbx_usage_forecast_daily` | `metric_name='estimated_cost_usd'`, idem | idem |
| Tendance Consommateurs distincts +7j | `gold_dbx_usage_forecast_daily` | `metric_name='distinct_consumers'`, idem | `SUM(predicted_value)` par `horizon_date` — ⚠️ somme de consommateurs distincts projetés par table, donc un MAJORANT (un même consommateur lisant 2 tables compte 2 fois), contrairement au KPI observé qui est un `COUNT(DISTINCT)` |
| Tendance Volume écrit (observé) | `gold_dbx_usage_table_daily` | `data_written_bytes` | `SUM` par `period_start` — historique observé, PAS une projection (`data_written_bytes` n'est pas dans `forecast_daily`). `NULL` = non mesurable (statement non joignable, pipelines DLT) : ne pas convertir en 0 |
| Points d'attention (top 3) | `gold_dbx_usage_recommendations` | `severity`, `status`, `title`, `category`, `object_type`, `object_id` | `WHERE status='OPEN'` trié par `severity` décroissant, `LIMIT 3` — ⚠️ `object_type` vaut `DATA_PRODUCT` ou `CONSUMER`, le lien de renvoi diffère selon le cas |

### Vue "Par table"

| Colonne UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| Nom table (+ type badge) | `gold_dbx_usage_table_catalog` | `table_full_name` (dérivé), `table_type` | direct |
| Lectures + delta | `gold_dbx_usage_table_popularity_daily` | `request_count`, `request_delta_pct` | `SUM` période, delta vs J-1/période préc. |
| Consommateurs (distincts) | `gold_dbx_usage_table_popularity_daily` | `distinct_consumers` | `SUM`/`COUNT DISTINCT` selon agrégation |
| Volume lu | `gold_dbx_usage_table_popularity_daily` | `data_read_bytes` | `SUM`, formaté en GB |
| Coût $ | `gold_dbx_usage_table_popularity_daily` | `estimated_cost_usd` | `SUM` — ⚠️ méthode d'attribution `equal_parts_fallback`, vues incluses dans le partage, à noter en tooltip. La complétude du coût (`costed_request_count`) n'est PAS exposée à ce grain |
| p95 latence | `gold_dbx_usage_table_query_performance_daily` | `latency_p95_ms` | `percentile_approx(total_duration_ms, 0.95)` par (table, jour). Sur une période multi-jours, aucun P95 exact n'est recalculable depuis le gold — les statements bruts ne vivent que dans `curated_dbx_query_history`. Repli à documenter dans l'UI, jamais une moyenne simple des P95 quotidiens |
| Taux d'échec accès | `gold_dbx_usage_table_query_performance_daily` | `failure_rate_pct` | `SUM(failed_count)/SUM(query_count)×100` recalculé sur la période, jamais un `AVG` des pourcentages quotidiens |
| Fraîcheur | `gold_dbx_usage_table_catalog` | `freshness_lag_hours`, `freshness_basis`, `last_write_at` | affiché en relatif ("il y a Xh/j") à partir de `freshness_lag_hours`. ⚠️ `freshness_basis` dit d'où vient la valeur : `lineage_write` (écriture prouvée) ou `table_altered` (repli sur `last_altered_at`, qui n'est PAS une preuve d'écriture — antérieur à une écriture attestée dans 44 % des cas). Un repli `table_altered` doit être signalé comme estimation. `last_write_at` seul est `NULL` sur toute VIEW et sur toute table sans écriture prouvée |

### Drill-down "Top consommateurs" (par table sélectionnée)

| Colonne UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| Rang | dérivé | — | `RANK() OVER (PARTITION BY table_full_name ORDER BY estimated_cost_usd DESC)` |
| Consommateur | `gold_dbx_usage_table_daily` | `consumer_name` | `WHERE table_full_name = :selected` |
| Type | `gold_dbx_usage_table_daily` | `consumer_type` | valeurs constatées : `USER`, `SERVICE_PRINCIPAL`, `JOB`, `NOTEBOOK`, `PIPELINE`, `DASHBOARD_V3`, `UNKNOWN` — **pas de `GENIE`**, cf. FR7. Vocabulaire NON fermé côté gold (reprise du `entity_type` du lineage) : l'UI doit tolérer une valeur inconnue plutôt que la masquer |
| Requêtes | `gold_dbx_usage_table_daily` | `request_count` | `SUM` |
| Coût $ | `gold_dbx_usage_table_daily` | `estimated_cost_usd` | `SUM`, `LIMIT 5` |
| Dernier accès | `gold_dbx_usage_table_daily` | `last_used_at` | `MAX` |

### Vue "Par consommateur"

| Colonne UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| Rang | `gold_dbx_usage_consumer_daily` | `consumer_rank` | `RANK() OVER (PARTITION BY period_start ORDER BY SUM(estimated_cost_usd) DESC)` — pas de `workspace_id` dans le grain, mais **pas de `cloud_provider` dans la partition non plus** : un seul palmarès aws+azure confondus, contrairement à `popularity_rank`. ⚠️ Rang du DERNIER JOUR, pas de la période : sur une période multi-jours, le classement doit être recalculé par l'API sur `SUM(estimated_cost_usd)`, pas lu dans cette colonne |
| Consommateur + type | `gold_dbx_usage_consumer_daily` | `consumer_name`, `consumer_type` | direct — mêmes valeurs que ci-dessus, pas de `GENIE` |
| Tables distinctes | `gold_dbx_usage_consumer_daily` | `distinct_data_products` | direct — nom de colonne historique côté Gold ; le libellé fonctionnel est "Tables distinctes". ⚠️ Compte JOURNALIER : sur une période, refaire `COUNT(DISTINCT table_full_name)` sur `table_daily`, jamais sommer cette colonne |
| Requêtes | `gold_dbx_usage_consumer_daily` | `request_count` | `SUM` |
| Volume lu | `gold_dbx_usage_consumer_daily` | `data_read_bytes` | `SUM`, formaté GB |
| Coût $ | `gold_dbx_usage_consumer_daily` | `estimated_cost_usd` | `SUM` |
| Filtre "type de consommateur" | `gold_dbx_usage_consumer_daily` | `consumer_type` | `SELECT DISTINCT` — retirer l'option `GENIE` du mockup tant que FR7 n'est pas livré. Alternative sans scan : `table_popularity_daily.consumers_by_type` (map `consumer_type` → nombre de consommateurs distincts) porte déjà la répartition au grain table/jour |

### Vue "FinOps"

| KPI / Colonne UI | Table gold source | Colonne(s) | Transformation |
|---|---|---|---|
| KPI Coût attribué (période) | `gold_dbx_usage_table_popularity_daily` | `estimated_cost_usd` | `SUM` |
| KPI Coût moyen / requête | dérivé | `estimated_cost_usd`, `request_count` | `SUM(estimated_cost_usd) / SUM(request_count)` — ⚠️ dénominateur trop large : `request_count` inclut les accès dont le coût n'a pas pu être calculé. Le dénominateur juste est `costed_request_count`, qui n'existe que dans `table_daily` ; sinon annoncer la valeur comme un minorant |
| KPI Top table coûteuse | `gold_dbx_usage_table_popularity_daily` | `estimated_cost_usd` | `SUM` par table sur la période, puis `MAX` de ce total (pas un `MAX` de valeurs journalières) |
| Tendance Coût $ +7j | `gold_dbx_usage_forecast_daily` | `metric_name='estimated_cost_usd'`, `predicted_value`, `lower_bound`, `upper_bound`, `horizon_date` | `SUM(predicted_value)` par `horizon_date` sur les `object_id` du périmètre |
| Tendance Volume lu +7j | `gold_dbx_usage_forecast_daily` | `metric_name='data_read_bytes'`, idem | idem |
| Tableau coût par table — Coût $ | `gold_dbx_usage_table_popularity_daily` | `estimated_cost_usd` | `SUM` |
| Tableau coût par table — Coût / requête | dérivé | `estimated_cost_usd`, `request_count` | `estimated_cost_usd / request_count` — même réserve de dénominateur que le KPI ci-dessus |
| Tableau coût par table — Volume lu | `gold_dbx_usage_table_popularity_daily` | `data_read_bytes` | `SUM` |
| Tableau coût par table — Forecast +7j | `gold_dbx_usage_forecast_daily` | `object_id` = `table_full_name`, `metric_name='estimated_cost_usd'`, `predicted_value` | `SUM(predicted_value)` sur les 7 `horizon_date`. Aucune ligne pour une table sans activité sur les 14 derniers jours → afficher un tiret, jamais 0 |

### Filtres communs

| Élément | Table gold source | Colonne(s) |
|---|---|---|
| Catalogue / Schéma | `gold_dbx_usage_table_catalog` | `catalog`, `schema` |
| Tables (multi-select) | `gold_dbx_usage_table_catalog` | `table_full_name` (dérivé de `catalog.schema.table_name`) |
| Application du filtre table à la vue consommateur | jointure `gold_dbx_usage_table_daily` (table lue) → `consumer_id` | intersection consommateur/tables sélectionnées |
| Application du filtre table à la vue FinOps | filtre direct | `WHERE table_full_name IN (:selected)` |

### Convention de période et d'agrégation

Le filtre global **Date de début / Date de fin** s'applique à toutes les vues de la page. Il filtre `period_start` sur les tables gold quotidiennes et doit être transmis au backend, pas appliqué uniquement côté frontend.

| Métrique | Agrégation sur la période |
|---|---|
| Requêtes, coûts, octets lus | `SUM` sur les jours de la période |
| Consommateurs distincts | `COUNT(DISTINCT consumer_id)` sur toute la période, pas somme des distincts quotidiens |
| Tables distinctes par consommateur | `COUNT(DISTINCT table_full_name)` sur toute la période |
| Taux d'échec | `SUM(failed_count) / SUM(query_count) * 100`, jamais moyenne simple des pourcentages quotidiens |
| Latence P95 | Non recalculable exactement depuis le gold (le quotidien est déjà un `percentile_approx`) : méthode de repli explicitement documentée, car moyenne de P95 quotidiens n'est pas un P95 de période |
| Volume écrit | `SUM(data_written_bytes)` sur `gold_dbx_usage_table_daily` uniquement — absent des tables d'agrégat. `NULL` = non mesurable, pas 0 |
| Delta | Comparaison avec une période précédente de même durée |
| Forecast | `SUM(predicted_value)` par `horizon_date`, horizon **7 jours** ; la projection ne doit pas être additionnée aux valeurs observées. `predicted_value` est borné à ≥ 0 (`global_floor` de `ai_forecast`) |
| Rangs (`popularity_rank`, `consumer_rank`) | Rangs du JOUR, pas de la période : sur une période multi-jours, recalculer le classement sur les totaux agrégés au lieu de lire ces colonnes |

La note d'information placée au-dessus des filtres doit expliquer ce comportement :

> Les métriques sont calculées sur la période sélectionnée. Les coûts, requêtes et volumes sont agrégés sur la période. Les P95, taux et pourcentages sont recalculés selon leur définition métier et ne sont pas additionnés entre les jours.

> **⛔ Filtres Workspace / LZ (bandeau)** : aucune des 8 tables gold ne porte `workspace_id` (il est lu dans les sources curated pour les jointures par `statement_id`, mais n'est jamais projeté en sortie). Ces filtres n'ont pas de source dans le périmètre feature 019 tel que livré — dépendent de `dim_dbx_workspace` (spec 020) **et** de la présence de `workspace_id` dans le grain des tables gold usage, non confirmée. À retirer du bandeau ou marquer "à venir" tant que non résolu.

## API Endpoints (proposition)

- `GET /api/usage/tables?catalog=&schema=&tables[]=&sort=popularity|cost|latency|failure_rate&period=` → vue Par table (FR1, FR2)
- `GET /api/usage/tables/{table_full_name}/top-consumers?limit=5` → drill-down (FR3, FR8)
- `GET /api/usage/consumers?catalog=&schema=&tables[]=&consumer_type=&sort=cost|requests|distinct_tables&period=` → vue Par consommateur (FR1, FR2, FR4)
- `GET /api/usage/finops/kpis?catalog=&schema=&tables[]=&period=` → KPI vue FinOps (FR5)
- `GET /api/usage/finops/trends?catalog=&schema=&tables[]=&metrics[]=` → tendances prévisionnelles depuis `forecast_daily` (`metrics[]` ⊂ {`request_count`, `distinct_consumers`, `estimated_cost_usd`, `data_read_bytes`}) ; pas de paramètre d'horizon, la table en contient 7 jours
- `GET /api/usage/finops/cost-by-table?catalog=&schema=&tables[]=&period=` → tableau coût par table, colonne forecast incluse (FR5)
- `GET /api/usage/attention?catalog=&schema=&tables[]=&limit=3` → bloc "Points d'attention" depuis `recommendations` (`status='OPEN'`, tri `severity`)

## Checklist

- [ ] Filtre table multi-select cohérent entre les trois vues (même référentiel, même state)
- [ ] Tous les libellés "+14j" du mockup corrigés en "+7j" (horizon réel de `forecast_daily`)
- [ ] Carte "Volume écrit" branchée sur `table_daily.data_written_bytes` (badge "En attente de données" retiré), sans conversion des `NULL` en 0
- [ ] Carte "Volume écrit" présentée comme observée, pas prévisionnelle (`data_written_bytes` absent de `forecast_daily`)
- [ ] Absence de ligne de forecast (table sans activité sur 14 jours) rendue par un tiret, jamais par 0
- [ ] ⛔ Filtres Workspace/LZ du bandeau retirés ou marqués "à venir" tant que `workspace_id` n'est pas confirmé dans le grain gold
- [ ] Toutes les occurrences `cost_usd` corrigées en `estimated_cost_usd` dans le frontend/API
- [ ] Décision Genie (FR7) requalifiée comme chantier data engineering, pas juste décision PO — retirer l'option `GENIE` du filtre tant que non livré
- [ ] Tooltip/footnote sur `estimated_cost_usd` mentionnant `cost_attribution_method = equal_parts_fallback`, le partage avec les vues, et `cost_basis` quand il vaut autre chose que `warehouse_prorata`
- [ ] Coût moyen / requête : dénominateur `costed_request_count` ou mention explicite "minorant"
- [ ] `object_type = DATA_PRODUCT` (pas `TABLE`) partout où le mockup lit `recommendations`
- [ ] Fraîcheur affichée depuis `freshness_lag_hours` + `freshness_basis`, avec mention "estimation" quand `freshness_basis = table_altered`
- [ ] Drill-down plafonné à 5, pas de fuite de volumétrie fine
- [ ] Vérifier que le périmètre inclut bien toutes les tables Unity Catalog, sans filtre `is_data_product` ; conserver `distinct_data_products` uniquement comme compatibilité technique du Gold.
- [ ] ⚠️ À remonter au data engineering : `consumer_rank` non partitionné par `cloud_provider` alors que sa docstring l'affirme (`consumer_daily.py`) — trancher avant de brancher la vue Par consommateur
