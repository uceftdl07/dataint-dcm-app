# Implementation Plan: Purge générique des tables curated full-load

**Branch**: `020-curated-full-load-purge` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-curated-full-load-purge/spec.md`

## Summary

Le socle d'ingestion `pipelines/system_tables` écrit exclusivement en upsert (`MERGE INTO ... WHEN MATCHED UPDATE / WHEN NOT MATCHED INSERT`, jamais de `DELETE`). Pour les 4 tables curated déclarées en full load (`watermark_column=None` : `curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`), une ligne disparue de la source (snapshot d'état courant) reste indéfiniment en curated. L'approche retenue : un registre opt-in (`purge_specs.py`, sous-ensemble de `specs.SPECS` restreint aux tables full-load) + un module générique (`pipelines/common/purge.py`) qui relit la source, calcule les lignes absentes par clé de merge et par cloud, applique un garde-fou volumétrique (seuil absolu ET pourcentage, le plus restrictif), écrit un résultat vérifiable dans une table d'audit Delta dédiée, et supprime via `MERGE INTO ... WHEN NOT MATCHED BY SOURCE AND t.cloud_provider = '<cloud>' THEN DELETE` — scellé dans un job Databricks Asset Bundle **séparé** (`job_dcm_curated_purge.yml`), cron hebdomadaire décalé après l'ingestion, sans aucune dépendance technique entre les deux jobs.

## Technical Context

**Language/Version**: Python 3.12 (`requires-python = ">=3.12,<3.13"`, pyproject.toml existant) ; pyenv local pinné `3.12.11` pour les commandes (cf. mémoire repo)

**Primary Dependencies**: PySpark >=3.5, delta-spark >=3.1 (MERGE / `WHEN NOT MATCHED BY SOURCE`), databricks-sql-connector 4.2.6 + azure-identity 1.20.0 (lecture cross-tenant Azure, réutilisés tels quels depuis `pipelines/common/readers.py` / `azure_auth.py`), databricks-sdk >=0.30 — aucune nouvelle dépendance externe

**Storage**: Databricks Unity Catalog / Delta Lake, catalog+schema qualifiés au runtime (vars bundle `catalog`/`schema`, jamais en dur) — 4 tables curated existantes (lecture + suppression conditionnelle) + 1 nouvelle table d'audit Delta (`curated_dbx_purge_audit_log`, créée par le même pattern idempotent que `writers.py::merge_into_table`, aucune DDL manuelle requise)

**Testing**: pytest + pytest-asyncio + chispa (assertions DataFrame Spark, déjà en dev-dependency) ; zéro warning ruff/mypy ; `PYENV_VERSION=3.12.11 uv run pytest -q` et `PYENV_VERSION=3.12.11 uv run mypy -p pipelines.<subpkg>` (cf. mémoire repo — mode package `-p`, jamais `uv run mypy path/`)

**Target Platform**: Databricks Jobs (compute serverless, Databricks Asset Bundle), même environnement `finops_env`-like que `job_dcm_system_tables.yml` — nouveau job dédié, pas une tâche ajoutée au job existant

**Project Type**: Single project — extension de `packages/dcm-databricks-pipeline` existant, aucun nouveau package

**Performance Goals**: Batch hebdomadaire, pas de contrainte de latence ; volumes bornés (les 4 tables full-load sont de petits référentiels : node types ~centaines de lignes, billing list prices ~milliers, uc_tables/uc_table_tags dépendent du nombre d'objets Unity Catalog mais restent des tables de catalogue, plusieurs ordres de grandeur sous les tables d'événements déjà ingérées)

**Constraints**:
- Jamais appliqué à une table incrémentale (`watermark_column is not None`) — garde-fou de code (assertion au chargement du registre), pas seulement documentaire
- Chemin d'exécution et job Databricks strictement séparés de l'ingestion (aucun appel direct, aucune tâche partagée)
- Suppression toujours précédée d'un comptage (garde-fou avant écriture, jamais un DELETE en aveugle) et toujours tracée en table d'audit, y compris en dry-run
- Séparation par `cloud_provider` : la suppression Azure ne doit jamais affecter les lignes AWS de la même table curated (et réciproquement)

**Scale/Scope**: 4 tables curated activées dès ce ticket, registre extensible (activer une 5ᵉ table full-load future = 1 ligne de config, pas de nouveau code)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principe | Statut | Justification |
|---|---|---|
| P1 — Test-First (NON-NEGOTIABLE) | PASS | Tests pytest/chispa prévus pour le calcul des lignes absentes, le garde-fou (seuils), le dry-run et la table d'audit, avant l'implémentation (TDD) |
| P2 — Simplicité / Explicite | PASS | Réutilise `specs.SPECS` existant (sous-ensemble filtré) plutôt qu'un nouveau modèle de données dupliqué ; pas de sur-ingénierie |
| P4 — Fail Fast, Fail Loud | PASS | Dépassement de seuil = arrêt explicite + trace en audit (pas de suppression silencieuse partielle) ; toute erreur de lecture source propage (pas de `except: pass`) |
| P5 — Architecture explicite | PASS | Module `pipelines/common/purge.py` généraliste, séparé du domaine `system_tables` ; job Databricks dédié, aucun appel cross-composant |
| P6 — Idempotency by Design | PASS | Ré-exécuter la purge sur un état déjà purgé est un no-op (`WHEN NOT MATCHED BY SOURCE` ne trouve plus rien à supprimer) ; l'audit log est un `INSERT` append-only par run (`collection_run_id` distinct par run, pas de ré-écriture) |
| P7/P8 — Secrets | PASS | Réutilise la config Azure existante (`AzureConnectionConfig`, secrets résolus via `dbutils.secrets`), aucun nouveau secret |
| P9 — No Fake Data | PASS | Aucune fixture/mock en chemin de production ; les tests utilisent des DataFrames Spark construits en mémoire (pytest), jamais importés hors tests |
| P10 — Observability | PASS | Log structuré (structlog/logging existant) + nouvelle table d'audit Delta dédiée (traçabilité renforcée, décidée en clarification) |
| P11 — Naming Conventions | PASS | `curated_dbx_purge_audit_log` respecte `{layer}_{dp_type}_{metric}` |
| P12 — Aggregations Gold only | PASS (avec note) | La table d'audit stocke des compteurs de run (lignes évaluées/supprimées) : ce sont des **métadonnées opérationnelles du job de purge lui-même** (bookkeeping d'exécution, comme un `collection_run_id`/statut de run), pas une métrique métier dérivée des données ingérées — hors du périmètre visé par P12 (agrégations métier sur données source). Aucune agrégation métier n'est ajoutée en curated |
| P13 — Immutable Raw | PASS | Aucune table Raw touchée ; les tables curated visées reçoivent des suppressions **explicitement demandées par ce mécanisme opt-in**, pas de mutation du Raw |

Aucune violation nécessitant Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/020-curated-full-load-purge/
├── plan.md              # Ce fichier
├── research.md          # Phase 0 — décisions techniques (MERGE delete, seuils, ordonnancement)
├── data-model.md        # Phase 1 — registre de purge, table d'audit
├── quickstart.md        # Phase 1 — validation dry-run / réel
├── contracts/
│   └── purge-registry.md  # Contrat interne : registre opt-in + CLI du job de purge
└── tasks.md              # Phase 2 (/speckit.dcm.tasks — pas généré par /speckit.plan)
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/
│   ├── common/
│   │   ├── models.py            # inchangé — IngestionSpec réutilisé tel quel (merge_keys, source_table, curated_table)
│   │   ├── writers.py           # + purge_rows_not_in_source() : MERGE ... WHEN NOT MATCHED BY SOURCE AND cloud_provider=... THEN DELETE
│   │   └── purge.py             # NOUVEAU — orchestration générique : lecture source, anti-join, garde-fou, dry-run, écriture audit
│   └── system_tables/
│       ├── specs.py             # inchangé
│       ├── purge_specs.py       # NOUVEAU — PURGE_ENABLED_KEYS (sous-ensemble de SPECS, watermark_column=None uniquement) + seuils par table
│       └── purge_entrypoint.py  # NOUVEAU — point d'entrée wheel task (named_parameters incl. dry_run), même pattern que entrypoint.py
├── resources/
│   └── job_dcm_curated_purge.yml  # NOUVEAU — job dédié, cron hebdomadaire décalé, for_each sur PURGE_ENABLED_KEYS
├── pyproject.toml               # + [project.scripts] dcm-curated-purge = "pipelines.system_tables.purge_entrypoint:run"
└── tests/
    ├── common/test_purge.py            # NOUVEAU
    ├── common/test_writers.py          # + cas purge_rows_not_in_source
    └── system_tables/test_purge_specs.py  # NOUVEAU — assertion garde-fou (registre ne peut pas contenir de table watermarkée)
```

**Structure Decision**: Extension du projet single existant `packages/dcm-databricks-pipeline` (pas de nouveau package). Le mécanisme de purge suit le même socle générique/plugin que `pipelines/system_tables` (registre déclaratif + entrypoint wheel task + module `pipelines/common` partagé), mais avec son **propre point d'entrée** (`dcm-curated-purge`) et son **propre fichier de ressources Bundle** (`job_dcm_curated_purge.yml`) pour garantir l'indépendance de chemin d'exécution exigée par le besoin — jamais une tâche du job `dcm_system_tables` existant.

## Complexity Tracking

> Aucune entrée — Constitution Check ne révèle aucune violation à justifier.
