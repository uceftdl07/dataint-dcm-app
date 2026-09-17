# technique : Remplacer `dim_landing_zone` par une vue union

**Feature Branch**: `021-dim-landing-zone-view` — branches filles `{domain}/021-dim-landing-zone-view`
**Work Type**: technique
**Priority**: P2
**Created**: 2026-09-02

**Input**: Je veux remplacer la table `dim_landing_zone` par une vue qui union l'ancienne table `dim_landing_zone` (à renommer en `dim_landing_zone_collector`) avec `dim_dbx_workspace`, jointe au référentiel `dim_reference_landing_zone_business_application`, dédupliquée par `subscription_or_account_id` en privilégiant les lignes ayant un `lz_name`.

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 1 |
|---|---|
| Mode | single_domain |
| Domaines avec ticket | dataeng |

## Clarifications

### Session 2026-09-02

- Q: Le join au référentiel BA doit-il être INNER (SQL fourni) ou LEFT pour ne pas perdre les LZ AWS ? → A: **INNER JOIN** — la dimension est volontairement restreinte aux LZ ayant une Business Application connue. Conséquence assumée : **toute LZ sans BA dans le référentiel disparaît de `dim_landing_zone`**. Le référentiel BA est **multi-cloud** (AWS + Azure) — validé live : vue déployée = aws=143 / azure=65.
- Q: La vue se limite-t-elle aux 6 colonnes du SQL fourni ou préserve-t-elle les colonnes lues par le backend ? → A: **Étendre la vue** avec les colonnes héritées `environment`, `region`, `owner_team`, `onboarded_at` (portées par le collector ; `NULL` côté `dim_dbx_workspace`) pour ne pas casser le backend.
- Q: Le `lz_id` recalculé (`CONCAT('lz-', cloud_provider, '-', subscription_or_account_id)`) est-il accepté comme clé canonique même s'il diffère des `source_lz_id` historiques ? → A: **Oui**, `lz_id` recalculé devient la clé canonique, alignement avec `source_lz_id` des tables gold assumé.
- Q: La déduplication par `subscription_or_account_id` seul est-elle correcte (1 subscription = 1 LZ) ? → A: **Oui**, une subscription/account = une LZ ; dédup par `subscription_or_account_id` seul.

## Contexte

Aujourd'hui `dim_landing_zone` est une **streaming table gold SCD Type 1** alimentée par `apply_changes` depuis `raw_metrics` (clé `lz_id`, séquence `_ingested_at`), définie dans [pipelines/dlt_03_gold_layer.py](../../packages/dcm-databricks-pipeline/pipelines/dlt_03_gold_layer.py#L135). Son `lz_id` sert de PK et est référencé en FK par 8 tables gold (`gold_pipeline_summary`, `gold_compute_utilization`, `gold_cost_summary`, `gold_db_capacity`, `gold_standard_check`, `gold_security`, `gold_activity`…).

Cette dimension ne couvre que les LZ vues par les collecteurs DCM (source `raw_metrics`). Elle ignore les workspaces Databricks connus via le référentiel (`dim_dbx_workspace`) qui n'émettent pas encore de métriques collectées, et n'est pas enrichie par le référentiel Business Application.

**Objectif** : exposer `dim_landing_zone` comme une **vue** qui unifie deux sources — les LZ collectées (l'actuelle table, renommée) et les workspaces référentiels `dim_dbx_workspace` — enrichie par `dim_reference_landing_zone_business_application`, avec une clé `lz_id` recalculée et une déduplication par `subscription_or_account_id`.

**Approche retenue** :

1. **Renommer** la streaming table gold `dim_landing_zone` → `dim_landing_zone_collector` en conservant son alimentation SCD1 / `apply_changes` inchangée.
2. **Créer** un objet Unity Catalog `VIEW` nommé `dim_landing_zone` (nom historique conservé → substitution transparente pour les consommateurs qui lisent la dimension).
3. **Supprimer** les contraintes FK `... REFERENCES … dim_landing_zone (lz_id)` des 8 tables gold : une vue ne peut pas être la cible d'une FK Databricks.

SQL cible de la vue (étendu avec les colonnes héritées suite aux clarifications) :

```sql
CREATE OR REPLACE VIEW {catalog}.{schema}.dim_landing_zone AS
SELECT
    CONCAT('lz-', a.cloud_provider, '-', a.subscription_or_account_id) AS lz_id,
    a.cloud_provider,
    a.subscription_or_account_id,
    a.lz_name,
    a.environment,
    a.region,
    a.owner_team,
    a.onboarded_at,
    b.business_application_id,
    b.business_application_name
FROM (
    SELECT
        cloud                       AS cloud_provider,
        subscription_or_account_id,
        CAST(NULL AS STRING)        AS lz_name,
        CAST(NULL AS STRING)        AS environment,
        CAST(NULL AS STRING)        AS region,
        CAST(NULL AS STRING)        AS owner_team,
        CAST(NULL AS DATE)          AS onboarded_at
    FROM {catalog}.{schema}.dim_dbx_workspace
    UNION ALL
    SELECT
        cloud_provider,
        subscription_or_account_id,
        lz_name,
        environment,
        region,
        owner_team,
        onboarded_at
    FROM {catalog}.{schema}.dim_landing_zone_collector
    WHERE subscription_or_account_id IS NOT NULL
) a
INNER JOIN {catalog}.{schema}.dim_reference_landing_zone_business_application b
    ON a.subscription_or_account_id = b.subscription_or_account_id
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY a.subscription_or_account_id
    ORDER BY CASE WHEN a.lz_name IS NOT NULL THEN 0 ELSE 1 END
) = 1;
```

> `INNER JOIN` volontaire (clarif C1) : `dim_reference_landing_zone_business_application` est **multi-cloud** (AWS + Azure) → la vue contient **les LZ AWS et Azure référencées BA**. Seules les LZ sans BA dans le référentiel sortent de la dimension. Validé live (dev) : aws=143 / azure=65.

## Dependency Analysis

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| Vue `dim_dbx_workspace` (source de l'union) | dataeng | Confirmé existant par le demandeur ; contrat en [specs/020-dbx-workspace-dim/data-model.md](../020-dbx-workspace-dim/data-model.md) | Prérequis satisfait — la vue existe, aucune Story supplémentaire |
| Référentiel `dim_reference_landing_zone_business_application` avec `business_application_id` / `business_application_name` + `subscription_or_account_id` | dataeng | [pipelines/reference_lz/ingest.py#L145](../../packages/dcm-databricks-pipeline/pipelines/reference_lz/ingest.py#L145) | ✅ Vérifié — `lz_id` source renommé en `subscription_or_account_id` (clé de merge), `name`→`business_application_name`, `ba_id`→`business_application_id`. **Multi-cloud (AWS+Azure)** → INNER JOIN restreint la dimension aux LZ ayant une BA (clarif C1) |
| FK gold → `dim_landing_zone` incompatibles avec une vue | dataeng | 8 `CONSTRAINT fk_gold_*_lz` dans [dlt_03_gold_layer.py](../../packages/dcm-databricks-pipeline/pipelines/dlt_03_gold_layer.py) | Supprimer les FK (choix intake) |

## Prerequisites

- **Small branches / small PRs** : une seule branche fille `dataeng/021-dim-landing-zone-view`, périmètre limité au package `packages/dcm-databricks-pipeline` (module gold + tests).
- Intake + domain scope confirmés ([intake.json](intake.json) / [domain-scope.json](domain-scope.json)).
- Dépendance `dim_dbx_workspace` : confirmée présente par le demandeur → non bloquante.
- Colonnes exactes des sources (`dim_dbx_workspace.cloud`, `dim_reference_landing_zone_business_application.subscription_or_account_id / business_application_id / business_application_name`) vérifiées avant écriture du SQL final.
- `[NEEDS CLARIFICATION]` levés avant l'étape `plan`.

## Impact

- **Réduction du périmètre de la dimension (clarif C1)** : `INNER JOIN` sur le référentiel BA (multi-cloud AWS+Azure) → `dim_landing_zone` **perd les LZ (AWS ou Azure) sans Business Application référencée**. Impact direct sur le backend (sélecteurs de LZ, `lz_scope`) et sur les jointures `source_lz_id → lz_id` des 8 tables gold pour ces LZ. Comportement voulu — validé live (dev) : 208 LZ (aws=143 / azure=65).
- **Schéma dimension (clarif C2)** : `dim_landing_zone` passe de table SCD1 à `VIEW` exposant `lz_id`, `cloud_provider`, `subscription_or_account_id`, `lz_name`, `environment`, `region`, `owner_team`, `onboarded_at`, `business_application_id`, `business_application_name`. Les colonnes `environment`/`region`/`owner_team`/`onboarded_at` sont conservées (côté collector ; `NULL` pour les lignes issues de `dim_dbx_workspace`). Les colonnes `is_active` et `_ingested_at` ne sont plus exposées — le backend les lit en `.get()` → dégradation en `NULL` acceptée.
- **Perte des FK** : les 8 tables gold n'ont plus de contrainte FK déclarative vers la dimension. La cohérence `source_lz_id → lz_id` n'est plus garantie par le moteur (les FK Databricks sont `NOT ENFORCED`, donc impact réel limité à la documentation / lignée).
- **Grain / clé (clarif C3/C4)** : `lz_id` recalculé (`CONCAT('lz-', cloud_provider, '-', subscription_or_account_id)`) devient la clé canonique, alignement avec `source_lz_id` assumé. Dédup par `subscription_or_account_id` seul (1 subscription = 1 LZ).
- **Performance** : la vue est recalculée à chaque lecture (union + join + window `QUALIFY`). Acceptable pour une dimension de faible cardinalité ; sinon envisager une matérialisation (hors périmètre de cet Epic).

## Acceptance Criteria

1. **Given** le pipeline gold déployé, **When** on décrit `dim_landing_zone_collector`, **Then** c'est l'ancienne streaming table SCD1, alimentée à l'identique, avec les mêmes données qu'avant le rename.
2. **Given** la vue `dim_landing_zone` créée, **When** on la lit, **Then** elle expose exactement `lz_id, cloud_provider, subscription_or_account_id, lz_name, environment, region, owner_team, onboarded_at, business_application_id, business_application_name` et une seule ligne par `subscription_or_account_id`.
3. **Given** un `subscription_or_account_id` présent dans les deux sources, **When** la vue déduplique, **Then** la ligne conservée est celle ayant un `lz_name` non nul.
4. **Given** un `subscription_or_account_id` absent du référentiel BA (AWS ou Azure), **When** on lit la vue, **Then** cette LZ **n'apparaît pas** (INNER JOIN assumé, clarif C1). Le référentiel étant multi-cloud, les LZ AWS **avec** BA restent présentes.
5. **Given** les 8 tables gold, **When** le pipeline se déploie, **Then** aucune ne déclare de FK vers `dim_landing_zone` et le déploiement réussit.
6. **Given** le package, **When** on lance les gates, **Then** lint → types → tests (builder SQL pur unit-testé) sont verts.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Rename `dim_landing_zone` → `dim_landing_zone_collector`, créer la vue union `dim_landing_zone`, supprimer les FK gold, tests du builder SQL | ✅ |

## Rollback

- Rétablir la définition `dlt.create_streaming_table(name="dim_landing_zone", …)` + `apply_changes` d'origine (annuler le rename), supprimer la vue, restaurer les `CONSTRAINT fk_gold_*_lz`.
- Le rename étant un changement de code du pipeline (pas une migration de données destructive), le rollback est un revert du commit + redéploiement du bundle. Aucune donnée collectée n'est perdue : la table renommée conserve son contenu.

## Assumptions

- `dim_dbx_workspace` existe et expose au moins `cloud` (aliasé `cloud_provider`) et `subscription_or_account_id`.
- `dim_reference_landing_zone_business_application` expose `subscription_or_account_id`, `business_application_id`, `business_application_name` (colonnes issues du renommage `name`→`business_application_name`, `ba_id`→`business_application_id`, `lz_id`→`subscription_or_account_id`). **Vérifié**.
- La restriction du périmètre aux LZ (AWS ou Azure) référencées BA est un comportement **voulu** (clarif C1), pas une régression à corriger. Le référentiel BA est multi-cloud (validé live : aws=143 / azure=65).
- Les colonnes héritées (`environment`, `region`, `owner_team`, `onboarded_at`) restent alimentées côté collector ; `is_active` / `_ingested_at` non exposées sont tolérées en aval (backend en `.get()`).
- Les FK gold étant `NOT ENFORCED`, leur suppression n'a pas d'effet fonctionnel sur l'intégrité des données au runtime.
