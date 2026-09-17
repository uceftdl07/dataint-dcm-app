
# Implementation Plan: Migration Lakebase → Databricks SQL Warehouse

**Branch**: `001-migration-lakebase-to-warehouse` | **Date**: 2026-05-19 | **Spec**: specs/001-migration-lakebase-to-warehouse/spec.md

**Input**: Feature specification from `/specs/001-migration-lakebase-to-warehouse/spec.md`

**Note**: Ce plan est généré selon le prompt speckit.plan.prompt.md et la spec validée.

## Summary

Supprimer la couche Lakebase PostgreSQL et faire lire le backend FastAPI directement dans Unity Catalog via Databricks SQL Warehouse, sans changer la surface API pour le frontend. Auth SPN OAuth2, secrets externalisés, databricks-sql-connector (sync) + asyncio.to_thread, migration sans downtime frontend.


## Technical Context

- **Language/Version**: Python 3.12
- **Primary Dependencies**: FastAPI, databricks-sql-connector, structlog, pytest
- **Storage**: Databricks SQL Warehouse (Unity Catalog, Delta tables)
- **Testing**: pytest, pytest-asyncio, CI/CD GitHub Actions
- **Target Platform**: AWS ECS Fargate, Databricks Cloud
- **Project Type**: web-service (API backend)
- **Performance Goals**: Latence < 500ms p95 sur endpoints principaux
- **Constraints**: Auth SPN OAuth2, secrets externalisés, pas de pool global, pas de breaking change API
- **Scale/Scope**: 10 tables, 14 routes API, 1 backend, 1 frontend


## Constitution Check

*GATE: Le script our_catalogs_spn.py doit fonctionner sur l’environnement cible (ppd/prd) avec le SPN cible, et tous les tests backend doivent passer sur Databricks. Zéro secret en dur, zéro warning CI. Documentation et rollback validés.*

ios/ or android/

## Project Structure

### Documentation (this feature)

```
specs/001-migration-lakebase-to-warehouse/
├── plan.md              # Ce plan
├── research.md          # Analyse technique et risques
├── data-model.md        # Modèle de données cible
├── quickstart.md        # Guide de migration rapide
├── contracts/           # Contrats d’interface API
└── tasks.md             # Tâches détaillées (phase suivante)
```

### Source Code (repository root)

- packages/dcm-backend/app/db/connection.py   # Refactoring Databricks
- packages/dcm-backend/app/config.py          # Secrets & settings
- packages/dcm-backend/tests/                 # Tests migration
- docs/MIGRATION-LAKEBASE-TO-WAREHOUSE.md     # Documentation

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
