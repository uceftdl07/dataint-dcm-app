# REFAC-2026-04-30-datamodel-backend.md

## Refactoring Datamodel DCM — Sprint 7/8

### Objectif
Aligner l’ensemble du code (backend, frontend, collecteurs, tests) sur le nouveau schéma Lakebase (Sprint 7/8) et supprimer tous les anciens noms hérités (ClusterMetric, ComplianceMetric, etc.).

---

## 1. Backend & dcm-commons
- Migration complète vers les nouveaux noms :
  - `compute_metrics` (ex-`cluster_metrics`)
  - `standard_checks` (ex-`compliance_metrics`)
  - Champs : `check_id`, `check_name`, `check_state`, `CheckEffect`, etc.
- Suppression de tous les alias legacy dans `dcm_commons/models/enums.py` (Sprint 8)
- Refactoring des modèles Pydantic, routes FastAPI, accès DB, et tests backend
- Documentation et schéma SQL mis à jour

## 2. Frontend (dcm-frontend)
- Legacy détecté :
  - Types `ClusterMetric`, `ClusterState` dans `src/pages/Clusters.tsx`
- Actions :
  - Refactorer pour utiliser `ComputeMetric`, `ComputeState`, nouveaux champs et endpoints `/compute` uniquement

## 3. Collecteurs AWS/Azure
- Legacy détecté :
  - dcm-aws-collector : `ClusterState`, `compliance_state`, `effect` dans `tests/test_emr_collector.py`, `config_compliance.py`
  - dcm-azure-collector : `complianceState`, `effect`, `policy_id`, `policy_name` dans `collectors/compliance.py`
- Actions :
  - Refactorer tous les collecteurs et tests pour utiliser les nouveaux noms (`ComputeState`, `StandardCheckState`, `CheckEffect`, etc.)
  - Mettre à jour les fixtures et mappings

## 4. Tests & Fixtures
- Backend : 100% refactorisé, legacy supprimé
- Collecteurs : legacy encore présent dans certains tests/fixtures, à corriger

## 5. Documentation & Schéma
- `data-models.md` à jour
- Ce fichier trace toutes les étapes de refacto cross-repo

---

## Points de vigilance
- **Aucun alias legacy ne doit subsister** (voir conventions Sprint 7)
- **Tests obligatoires** pour chaque refactoring
- **Vérifier les fixtures JSON**
- **Alignement complet frontend/backend/collecteurs**

---

## Historique
- 2026-04-29 : Backend, dcm-commons, doc, schéma refactorisés
- 2026-04-30 : Audit cross-repo, plan d’action frontend/collecteurs rédigé
- 2026-05-27 : Suppression du chemin backend Lakebase/PostgreSQL. Le backend lit Unity Catalog via Databricks SQL Warehouse (`DatabricksWarehousePool`) et les requêtes sont alignées sur Databricks SQL (`?`, tables qualifiées, `curated_*`/`gold_*`).

---

## Suivi
- [x] Frontend refacto terminé
- [x] Collecteurs refacto terminés
- [x] Tests/fixtures alignés
- [x] CI/CD validée

---

> Ce fichier doit être mis à jour à chaque refactoring majeur du datamodel.
