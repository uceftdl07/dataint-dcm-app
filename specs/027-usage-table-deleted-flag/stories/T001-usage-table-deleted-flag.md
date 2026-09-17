# T001 — DataEng : marquage des tables supprimées (`is_deleted`) en gold usage

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: `dataeng/027-usage-table-deleted-flag` — cut depuis `origin/develop` à jour
**Jira**: pending (1 seule Story pour cette feature)
**Depends on**: features 019 (tables gold usage) et 020 (purge des curated full-load) — toutes deux sur `develop`
**Work type**: feature

## Description

Les tables Unity Catalog supprimées continuent de peupler la couche gold usage : elles apparaissent dans les registres, alimentent des prévisions et déclenchent des recommandations qui ne mènent nulle part. Cette task ajoute l'état de cycle de vie à la source (`gold_dbx_usage_table_catalog`) et l'applique aux deux consommateurs internes du pipeline (forecast, recommandations).

Couvre les user stories **US1** (signal), **US3** (forecast) et **US4** (gouvernance/recommandations) de [spec.md](../spec.md). **US2** (filtre API + toggle UI) est hors de cette task : le code concerné vit sur la branche `dataeng/024-usage-tracking-governance` (cf. [api-include-deleted.md](../contracts/api-include-deleted.md)).

Portée bornée : 3 colonnes sur 2 tables snapshot. **Aucune table gold créée**, aucun grain ni clé de merge modifié, **aucune colonne ajoutée aux 4 tables de fait quotidiennes**.

## Files to create/modify

- UPDATE `pipelines/gold_dbx_usage/sql_helpers.py` — constantes `LIFECYCLE_STATE_*` (modèle `FRESHNESS_BASIS_*`)
- UPDATE `pipelines/gold_dbx_usage/specs.py` — commentaires de colonnes sur `TABLE_CATALOG_COLUMN_COMMENTS` et `TABLE_GOVERNANCE_COLUMN_COMMENTS`
- UPDATE `pipelines/gold_dbx_usage/table_catalog.py` — socle `base ∪ deleted_only` + dérivation de l'état
- UPDATE `pipelines/gold_dbx_usage/table_governance.py` — propagation + neutralisation `recommended_action`/`severity`
- UPDATE `pipelines/gold_dbx_usage/forecast_daily.py` — exclusion en entrée + fenêtre de purge d'horizon
- UPDATE `pipelines/gold_dbx_usage/recommendations.py` — `AND NOT is_deleted` sur les règles `DATA_PRODUCT`
- UPDATE `pipelines/gold_dbx_usage/entrypoint.py` — passage de `table_catalog_table` au forecast + log du compte `DELETED`
- UPDATE `tests/gold_dbx_usage/` — `test_sql_helpers.py`, `test_table_catalog.py`, `test_table_governance.py`, `test_forecast_daily.py`, `test_recommendations.py`, `test_specs.py`, `test_entrypoint.py`

> **Pas de mise à jour de `docs/02-data-model/data-models.md`** : ce document ne référence aucune table `gold_dbx_*` (0 occurrence — il décrit la couche `MetricPayload`/`curated_*` antérieure), et aucune des 8 tables gold usage de la feature 019 n'y figure. La documentation de cette couche passe par les `column_comments` / `table_comment` des specs gold, attachés à Unity Catalog par `merge_into_table` — c'est le mécanisme retenu par la feature 019, et il est couvert ici.

## Conception

Détail complet : [data-model.md](../data-model.md) · décisions et alternatives : [research.md](../research.md) · contrat : [gold-lifecycle-contract.md](../contracts/gold-lifecycle-contract.md).

### Règle de détection (par corroboration)

| Présente dans `curated_dbx_uc_tables` | Dernière opération d'audit | `lifecycle_state` | `is_deleted` | `deleted_at` |
|---|---|---|---|---|
| oui | quelconque | `ACTIVE` | `false` | `NULL` |
| non | `deleteTable` | `DELETED` | `true` | `last_operation_at` |
| non | autre / aucune | `UNKNOWN` | `false` | `NULL` |

L'absence du référentiel **ne suffit pas** : c'est majoritairement un défaut de GRANT sur le principal d'ingestion. La présence au référentiel **prime** sur tout événement passé, ce qui traite la recréation sans code dédié.

### Deux pièges structurels

1. **Une table supprimée n'a aucune ligne source** — elle a disparu de `curated_dbx_uc_tables`, et `merge_into_table` ne supprime jamais de ligne cible. Sans union d'un squelette `deleted_only`, une table déjà connue garderait `is_deleted = false` pour toujours. Corollaire favorable : un état `DELETED` écrit survit à la sortie de l'événement d'audit de sa rétention.
2. **Ne pas dénormaliser sur les tables de fait** — leur MERGE est incrémental sur 3 jours glissants (`INCREMENTAL_LOOKBACK_DAYS`) : le drapeau resterait figé à `false` sur tout l'historique antérieur. Les consommateurs filtrent par jointure sur `table_catalog`.

### Étapes d'exécution

Ordre contraint : **A bloque B et C** ; B et C sont indépendantes entre elles.

#### A. Socle + signal (US1)

1. Tests des constantes `LIFECYCLE_STATE_ACTIVE/DELETED/UNKNOWN` → `test_sql_helpers.py`
2. Constantes + export `__all__` → `sql_helpers.py`
3. Tests des 5 cas de détection (ACTIVE · DELETED · UNKNOWN · recréation · ligne `deleted_only` à colonnes de registre NULL) → `test_table_catalog.py`
4. Test de présence des commentaires des 3 colonnes → `test_specs.py`
5. Test du log structuré comptant les `DELETED` par `cloud_provider` (FR-018) → `test_entrypoint.py`
6. Commentaires de colonnes + complément de `TABLE_CATALOG_TABLE_COMMENT` → `specs.py`
7. Socle `base ∪ deleted_only` → `table_catalog.py`
8. Dérivation `lifecycle_state` / `is_deleted` / `deleted_at` dans le SELECT final → `table_catalog.py`
9. Log structuré du compte `DELETED` → `entrypoint.py`

#### B. Exclusion du forecast (US3)

10. Test : le SQL rendu exclut les clés `is_deleted` dans les 3 sous-requêtes observées (`eligible`, `calendar`, `daily`) → `test_forecast_daily.py`
11. Test : la fenêtre de suppression des lignes d'horizon porte sur l'horizon **entier**, pas sur les seules clés recalculées → `test_forecast_daily.py`
12. Paramètre `table_catalog_table` + anti-jointure dans `_dense_observed_sql`, `render_forecast_query` restant **pure** → `forecast_daily.py`
13. Correction de la fenêtre de purge d'horizon si nécessaire, garde-fou « zéro ligne calculée ⇒ aucune suppression » conservé → `forecast_daily.py`
14. Propagation du paramètre + test → `entrypoint.py`, `test_entrypoint.py`

#### C. Exclusion gouvernance et recommandations (US4)

15. Tests propagation + `recommended_action`/`severity` à NULL + non-régression sur table active → `test_table_governance.py`
16. Tests : aucune ligne `OPEN` sur table supprimée, et transition `OPEN → RESOLVED` d'une recommandation préexistante (FR-014) → `test_recommendations.py`
17. Test de présence des commentaires sur `TABLE_GOVERNANCE_COLUMN_COMMENTS` → `test_specs.py`
18. Commentaires de colonnes → `specs.py`
19. Propagation + neutralisation `recommended_action`/`severity` → `table_governance.py`
20. `AND NOT is_deleted` sur les règles `DATA_PRODUCT` (LIFECYCLE, FRESHNESS, GOVERNANCE, RELIABILITY), règle FINOPS `CONSUMER` inchangée → `recommendations.py`

La transition `OPEN → RESOLVED` ne demande **aucun code** : le moteur résout déjà toute clé métier qui cesse d'être détectée.

## Acceptance Criteria

- [x] **Trois états** : `lifecycle_state` ne prend que `ACTIVE`, `DELETED`, `UNKNOWN`
- [x] **Jamais NULL** : `is_deleted` est non-NULL sur 100 % des lignes ; `UNKNOWN` vaut `false`
- [x] **Cohérence** : `is_deleted = true ⟺ deleted_at IS NOT NULL` (quickstart §2.3 ⇒ `0`)
- [x] **Zéro faux positif** : aucune table présente dans `curated_dbx_uc_tables` n'est marquée supprimée (quickstart §2.2 ⇒ `0`, SC-002)
- [x] **Ligne pour les supprimées** : une table absente du référentiel avec un `deleteTable` produit bien une ligne, colonnes de registre NULL
- [x] **Rémanence** : un état `DELETED` écrit n'est pas perdu au run suivant, même sans nouvel événement d'audit
- [x] **Réversibilité** : une table recréée repasse `ACTIVE` / `false` / `NULL` (FR-016)
- [x] **Forecast** : aucune ligne d'horizon futur pour une table supprimée (quickstart §2.4 ⇒ `0`, SC-004)
- [x] **Recommandations** : aucune ligne `OPEN` `DATA_PRODUCT` sur table supprimée (quickstart §2.5 ⇒ `0`, SC-005) ; les lignes `CONSUMER` restent inchangées
- [x] **Historique préservé** : `gold_dbx_usage_table_daily` conserve les lignes des tables supprimées (quickstart §2.6 ⇒ `> 0`, FR-004)
- [x] **Idempotence (P6)** : deux runs consécutifs sans changement au catalogue ⇒ répartition des états strictement identique (quickstart §2.7)
- [x] **Aucune dénormalisation** : `git diff` ne touche aucune des 4 tables de fait quotidiennes
- [x] **Aucun littéral** : les états s'écrivent via les constantes `LIFECYCLE_STATE_*`, jamais en dur dans le SQL
- [x] **Pureté conservée** : `render_forecast_query` n'effectue toujours aucun accès réseau/compute
- [x] **Performance** : durée du job `dcm_gold_dbx_usage` non dégradée de plus de 10 % (SC-007)
- [x] `git diff --stat` ne touche que `pipelines/gold_dbx_usage/` et `tests/gold_dbx_usage/`

## Validation dev — 2026-09-16

Déploiement `databricks bundle deploy -t dev_local`, puis job `dcm_gold_dbx_usage` (7 tâches, SUCCESS en 5 min) et `dcm_gold_forecast --only gold_usage_forecast_daily` (SUCCESS).

| Contrôle | Attendu | Obtenu |
|---|---|---|
| §2.1 Répartition | 3 états max | `ACTIVE` aws 72 322 / azure 17 806 · `DELETED` aws 1 349 035 / azure 1 761 |
| §2.2 Faux positifs | 0 | **0** |
| §2.3 Invariant `is_deleted`/`deleted_at` | 0 | **0** |
| §2.4 Prévisions sur table supprimée | 0 | **0** (témoin : 1 682 723 lignes produites sur 87 301 objets) |
| §2.5 Recos `OPEN` sur table supprimée | 0 | **0** (témoin : 35 265 `DATA_PRODUCT` passées `RESOLVED`) |
| §2.6 Historique d'usage préservé | > 0 | **1 395 864** |
| §2.7 Idempotence | comptes identiques | **4/4 identiques** entre deux runs |
| Gouvernance neutralisée si supprimée | 0 | **0** |

**Le volume AWS est réel, pas un faux positif.** Les 1,35 M de tables `DELETED` sont des objets éphémères : `curated_dbx_*__stg_<id>` (staging du MERGE de DCM lui-même), `temp_op_curated_sapfi_*`, `_discovered_types_*`. La source confirme : 1 366 036 tables distinctes portent un événement `deleteTable` côté AWS.

**Performance** : le job usage a tourné en 5 min. Le job forecast a pris 74 min, mais un run **antérieur à 027** avait pris 76,3 min (09-14) — variance propre à ce job, aucune régression imputable à l'anti-jointure.

**Volumétrie** : les tables `DELETED` vivent dans les deux snapshots au grain table, `gold_dbx_usage_table_catalog` et `gold_dbx_usage_table_governance` — 1 440 924 lignes chacune, dont 1 350 796 supprimées (93,7 %). À relativiser : `gold_dbx_usage_table_daily` en compte 11 073 765, soit 7,7× plus. Ces snapshots ne sont pas le poids dominant du domaine.

**Pas de filtre des tables éphémères, décision assumée.** Elles sont toutes `is_deleted = true`, donc déjà masquées par le défaut `include_deleted=false` du contrat API : les écrans de la 024 ne les verront pas. Un filtre par motif de nom (`__stg_`, `temp_`, `_discovered_types_`) a été écarté — il encoderait les conventions de trois équipes distinctes dans notre pipeline, produirait des faux négatifs silencieux à chaque nouvelle LZ et des faux positifs destructeurs (`temperature_readings` matche `temp`). Si le besoin se confirme, la bonne réponse est un critère **mesuré** (durée de vie courte + jamais lue, dérivable de `created_at`/`deleted_at`/`last_read_at`) exposé en colonne, jamais un `DELETE` de lignes gold.

> Les 6 cases restées ouvertes ne sont **pas** des oublis : elles portent sur le comportement de la donnée, que la session Spark factice des tests unitaires ne peut pas prouver. Elles se cochent après la validation dev (`quickstart.md` §2), bloquante avant la PR.

## Tests

```bash
cd packages/dcm-databricks-pipeline
uv run ruff check . && uv run ruff format --check .
uv run mypy .
uv run pytest tests/ -q
```

⚠️ Les tests unitaires de ce package s'appuient sur une session Spark **factice** (cf. `tests/conftest.py`) : ils valident le **texte SQL généré**, pas le comportement sur la donnée. Une suite verte ne prouve donc ni la justesse de la détection, ni l'idempotence, ni l'absence de faux positifs.

Les invariants de données se valident sur l'environnement dev via les requêtes §2.1 à §2.7 de [quickstart.md](../quickstart.md), après exécution des tâches gold dans l'ordre :

```
table_daily → table_popularity_daily → table_catalog → table_governance
                                    → recommendations
                                    → forecast_daily
```

Cette validation dev est **bloquante avant la PR**, pas optionnelle.
