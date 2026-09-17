# Tasks — 016 Registration par projet + refonte des rôles à 3 niveaux

**Feature**: 016-project-registration-roles | **Work type**: feature | **Mode**: one_per_domain
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

> **Exécution single-branch (override)** : les deux tasks sont réalisées sur la branche courante `frontend/015-project-access-governance` (pas de branches filles `{domain}/016-{slug}`), PR unique → `develop`. Garder des commits focalisés par préoccupation.

## Tasks

- [x] T001 Frontend Page login « Join or Register a project » + suppression « My Landing Zones » + UI 3 rôles → [stories/T001-frontend-project-registration-login.md](stories/T001-frontend-project-registration-login.md)
- [x] T002 Backend Endpoints register/join projet + modèle d'autorisation réduit à 3 rôles → [stories/T002-backend-project-register-join-roles.md](stories/T002-backend-project-register-join-roles.md)

## Out of scope (cet Epic)

- DataEng — tables projet + `platform_role` + migration : livrés par 015 T001 (prérequis figé), aucun ticket ici.
