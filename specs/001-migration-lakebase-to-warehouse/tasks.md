# Task List — Migration Lakebase → Databricks SQL Warehouse

**Source**: plan.md
**Date**: 2026-05-19

---

## Phase 1: Setup & Pré-validation
- [ ] T001 Vérifier que le script our_catalogs_spn.py fonctionne sur l’environnement cible (ppd/prd)
- [ ] T002 Vérifier que le SPN a les permissions USE CATALOG, USE SCHEMA, SELECT sur toutes les tables
- [ ] T003 S’assurer que tous les secrets sont externalisés (Key Vault/Secrets Manager)

## Phase 2: Refactoring & Migration
- [ ] T004 Adapter packages/dcm-backend/app/db/connection.py pour Databricks SQL Warehouse (connexion, placeholders, gestion context manager)
- [ ] T005 Adapter packages/dcm-backend/app/config.py pour la nouvelle gestion des secrets et settings
- [ ] T006 Refactorer toutes les requêtes SQL pour utiliser les noms fully qualified et la syntaxe Databricks
- [ ] T007 Mettre à jour la configuration d’environnement (env vars, settings)
- [ ] T008 Supprimer toute dépendance à Lakebase PostgreSQL dans le backend

## Phase 3: Tests & Validation
- [ ] T009 Écrire/adapter les tests pytest pour valider la migration sur Databricks
- [ ] T010 Ajouter des tests d’intégration sur les endpoints critiques
- [ ] T011 Vérifier la compatibilité API (pas de breaking change pour le frontend)
- [ ] T012 Valider la CI/CD (zéro warning ruff/mypy, tous les tests passent)

## Phase 4: Déploiement & Rollback
- [ ] T013 Déployer en environnement de test, puis ppd/prd
- [ ] T014 Valider la migration avec le PO et la QA
- [ ] T015 Documenter et tester le plan de rollback (remise en place Lakebase si blocage)

## Phase 5: Documentation & Handover
- [ ] T016 Mettre à jour docs/MIGRATION-LAKEBASE-TO-WAREHOUSE.md
- [ ] T017 Mettre à jour le README backend et la doc technique
- [ ] T018 Handover à l’équipe de support/ops

---

Chaque tâche doit être cochée et validée avant passage à la phase suivante. Les tests et la documentation sont obligatoires pour la complétion de la migration.
