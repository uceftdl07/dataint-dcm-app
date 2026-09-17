# Feature Specification: Gouvernance des accès DCM — modèle « projet » + groupe Entra unique

**Feature Branch**: `015-project-access-governance`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-08-21

**Input**: Remplacer la stratégie d'access group et de rôles actuelle de DCM (rôle global plat + liste plate `dcm_user_lz_access`) par la stratégie décrite dans le spike `docs/spike/access-group-governance` (V2, validée Design Authority 2026-08-21) : autorisation multi-tenant scopée par **projet**, self-service d'enregistrement, Microsoft Entra ID réduit à un **groupe unique `DCM-Users`** servant de gate d'authentification.

## Clarifications

### Session 2026-08-21

- Q: Rôle du créateur d'un projet une fois celui-ci activé ? → A: Le créateur est automatiquement ajouté comme `admin` du projet à l'activation (garantit qu'un projet actif a toujours ≥1 admin).
- Q: Création d'un projet pour une Business Application ayant déjà un projet (contrainte 1:1) ? → A: Rejet **409** avec message clair invitant à demander l'adhésion au projet existant (flux join).
- Q: Comment les approbateurs (platform_admin / project admin) sont-ils notifiés des demandes en attente ? → A: **In-app uniquement** — liste des demandes en attente + badge pour l'approbateur concerné ; aucun email ni canal externe.
- Q: Un utilisateur/admin peut-il resoumettre une demande (adhésion ou extension de périmètre) après un rejet ? → A: **Oui, librement** — le rejet n'est pas définitif ; chaque resoumission crée une nouvelle ligne `pending` indépendante.
- Q: Comment un projet est-il archivé/désactivé et quel effet sur le périmètre + les membres ? → A: **Hors périmètre** de cette feature — aucun flux d'archivage/désactivation de projet n'est livré ici (à traiter dans une feature ultérieure).

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | ✅ | packages/dcm-frontend |
| Backend | ✅ | ✅ | packages/dcm-backend, packages/dcm-commons |
| DataEng | ✅ | ✅ | our_catalogs_spn.py, packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Champ | Valeur |
|-------|--------|
| Stories Jira | 3 |
| Mode | one_per_domain |
| Domaines avec ticket | dataeng, backend, frontend |

## Dependency Analysis

| Besoin | Domaine | Résolution |
|--------|---------|------------|
| Tables projet + colonne `platform_role` + migration | DataEng | Story T001 — prérequis des deux autres (schéma figé) |
| Référentiel Business Application (`lz_id → business_app_id`) | DataEng | Fourni par feature 014 (`dim_reference_landing_zone_business_application`) — déjà disponible |
| Couche d'autorisation `get_allowed_scope` + routes projet | Backend | Story T002 — dépend de T001 (schéma) ; contrat OpenAPI figé pour T003 |
| Écrans projet + matrice rôle | Frontend | Story T003 — dépend de T002 (contrat OpenAPI + `/auth/me` enrichi) |
| Groupe Entra `DCM-Users` | Hors code applicatif | Géré par la gouvernance IAM standard (provisioning amont) — aucun code à écrire (ADR-0001 §8) |

## Prerequisites

- **Small branches / small PRs**: une branche fille par domaine (`dataeng/015-…`, `backend/015-…`, `frontend/015-…`), chacune sur un package/concern focalisé pour faciliter la revue humaine.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- ADR-0001 (V2) acceptée et clarifications encodées (`research.md`, `data-model.md`) — aucun `[NEEDS CLARIFICATION]` résiduel.
- Feature 014 (référentiel `dim_reference_landing_zone_business_application`) déployée — prérequis de la migration.
- Ordre de merge imposé : DataEng → Backend → Frontend (contrats figés permettant le parallélisme).

## User Scenarios & Testing

### User Story 1 - DataEng : tables projet, colonne `platform_role` et migration des accès plats (Priority: P1)

Un ingénieur data crée les tables du modèle « projet » dans le schéma applicatif Delta, ajoute la colonne `platform_role` à `dcm_app_users`, puis exécute la migration qui regroupe les accès plats existants (`dcm_user_lz_access`) en projets par défaut (1 projet ↔ 1 Business Application).

**Why this priority**: Sans le schéma et la migration, ni le backend ni le frontend ne peuvent fonctionner. C'est le socle prérequis de toute la feature ; il doit préserver l'accès des utilisateurs existants.

**Independent Test**: Exécuter `our_catalogs_spn.py` puis `--migrate-projects --apply` sur un environnement dev ; vérifier la création des tables, le mapping des rôles, l'auto-promotion d'un `admin` par projet, et l'idempotence (re-run = 0 changement).

**Acceptance Scenarios**:

1. **Given** les tables projet absentes, **When** `our_catalogs_spn.py` s'exécute, **Then** les 5 tables projet (`dcm_projects`, `dcm_project_lz_scope`, `dcm_project_dbx_scope`, `dcm_project_members`, `dcm_project_join_request`) + la table `dcm_project_scope_requests` sont créées et `dcm_app_users` possède la colonne `platform_role`.
2. **Given** des lignes `dcm_user_lz_access` existantes, **When** la migration s'exécute avec `--apply`, **Then** chaque Business Application couverte donne un projet `active` (`id = business_app_id`), chaque utilisateur non-admin devient membre `viewer` de ses projets, et le membre le plus ancien de chaque projet est auto-promu `admin`.
3. **Given** un rôle global `super_admin` ou ancien `admin`, **When** la migration s'exécute, **Then** `platform_role = 'super_admin'` ; pour `data_architect`/`manager`/`viewer`, `platform_role = 'user'`.
4. **Given** une `lz_id` non résolvable vers une Business Application, **When** la migration s'exécute, **Then** elle est listée dans le rapport et loggée sans faire échouer la migration globale.
5. **Given** une migration déjà appliquée, **When** on la relance avec `--apply`, **Then** aucun doublon n'est créé (idempotence).

---

### User Story 2 - Backend : autorisation scopée projet, routes self-service et filtrage à deux dimensions (Priority: P1)

Le backend expose l'autorisation par projet : calcul du périmètre (union des LZ et workspaces DBX des projets actifs de l'utilisateur), routes de création/adhésion/extension de projet avec validation à deux étages (platform_admin / project admin), et bascule du filtrage des routes métriques vers les deux dimensions LZ + workspace Databricks.

**Why this priority**: Cœur fonctionnel de la nouvelle gouvernance ; il porte les règles de sécurité (isolation des project admins, garde dernier admin, gate d'authentification) et conditionne l'UI.

**Independent Test**: `uv run pytest tests/ -k "scope or project"` ; vérifier via headers dev qu'un membre ne voit que le périmètre de ses projets, qu'un utilisateur sans projet reçoit 200 + collection vide, et que les gardes admin renvoient 403/409 attendus.

**Acceptance Scenarios**:

1. **Given** un utilisateur membre actif de projets couvrant LZ_A et workspace_W, **When** il appelle une route métrique, **Then** il ne voit que les données de LZ_A et workspace_W (`WHERE :unrestricted OR source_lz_id IN (…) OR workspace_id IN (…)`).
2. **Given** un utilisateur sans aucun projet actif, **When** il appelle une route métrique, **Then** la réponse est **200 + collection vide** (pas 403).
3. **Given** un `platform_role = super_admin`, **When** il appelle une route métrique, **Then** le périmètre est `unrestricted` (toutes les LZ / workspaces).
4. **Given** un utilisateur authentifié via `DCM-Users`, **When** il crée un projet (BA existante, membres, LZ/DBX), **Then** le projet est `pending_validation` et une demande de validation est routée vers un platform_admin.
5. **Given** un projet `pending_validation`, **When** un platform_admin l'approuve, **Then** `status = active` et les membres sont créés.
6. **Given** un projet existant, **When** un utilisateur demande à le rejoindre, **Then** une `dcm_project_join_request` `pending` est créée et routée vers les admins du projet.
7. **Given** un admin de projet, **When** il demande une LZ/workspace supplémentaire, **Then** une `dcm_project_scope_requests` `pending` est créée et validée par un platform_admin avant application.
8. **Given** un projet `active` avec un seul `admin`, **When** on tente de retirer/rétrograder ce dernier admin, **Then** l'API renvoie **409** (sauf action d'un platform_admin).
9. **Given** un project admin, **When** il tente d'agir sur un autre projet, **Then** l'API renvoie **403**.
10. **Given** toute décision d'administration (validation, adhésion, extension, changement de rôle), **When** elle est prise, **Then** une ligne est écrite dans `dcm_audit_log`.

---

### User Story 3 - Frontend : écrans self-service projet et matrice de rôles à deux niveaux (Priority: P2)

L'utilisateur gère ses accès en autonomie via l'UI : créer un projet, rejoindre un projet existant, gérer les membres/rôles d'un projet qu'il administre, et demander une extension de périmètre. La matrice d'accès combine `platform_role` (plateforme) et rôle projet (`viewer`/`admin`).

**Why this priority**: Rend la gouvernance self-service utilisable ; dépend du contrat backend (T002) mais apporte la valeur visible pour l'utilisateur final.

**Independent Test**: `npm run test -- role-access projects` (réseau mocké) ; parcourir manuellement création/adhésion/gestion et l'état vide.

**Acceptance Scenarios**:

1. **Given** un compte `user` sans projet, **When** il ouvre DCM, **Then** il voit une application vide navigable l'invitant à créer ou rejoindre un projet.
2. **Given** l'écran de création, **When** l'utilisateur choisit une Business Application existante (pas de texte libre) + membres + LZ/DBX, **Then** le projet est soumis en `pending_validation`.
3. **Given** un admin de projet, **When** il ouvre la gestion du projet, **Then** il peut ajouter/retirer des membres, changer leurs rôles et demander une extension de périmètre — uniquement pour ce projet.
4. **Given** la tentative de retrait du dernier admin, **When** l'action est soumise, **Then** l'UI restitue l'erreur 409 de façon lisible.
5. **Given** la matrice de rôles, **When** l'UI décide de l'accès aux pages/actions, **Then** elle combine `platform_role` + rôle projet et affiche des libellés lisibles (noms, pas d'identifiants bruts).

## Out of scope (this Epic)

- **Provisioning Entra V1** (1 groupe par projet, privilège Graph `Group.Create`, job de réconciliation de drift) — explicitement rejeté par l'ADR-0001 ; `entra_group_id` reste nullable comme point d'extension futur.
- **Access reviews Entra / SCIM sortant / Conditional Access par projet** — gouvernance déportée dans DCM (`dcm_audit_log`, `platform_role`, `project_members`).
- **Retrait définitif de l'ancien `role` global** et de `get_allowed_lz_ids` (LZ seule) — conservés en lecture pour rollback, nettoyage prévu au sprint suivant.
- **Gestion IAM du groupe `DCM-Users`** (ajout/révocation de comptes) — hors code applicatif, gouvernance Entra standard.
- **Archivage / désactivation de projet** (soft-delete, révocation de périmètre, réactivation) — non livré dans cette feature, à traiter ultérieurement.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Tables projet + `platform_role` + migration idempotente des accès plats | ✅ |
| T002 | Backend | `get_allowed_scope` / `is_project_admin`, routes projet/join/scope, filtrage 2 dimensions, gardes admin + audit | ✅ |
| T003 | Frontend | Écrans créer/rejoindre/administrer projet, état vide, matrice rôle `platform_role` + projet | ✅ |

## Requirements

### Functional Requirements

- **FR-001**: Le système DOIT modéliser un **projet** comme unité de gouvernance regroupant des membres (rôle scopé projet) et un périmètre de Landing Zones et/ou workspaces Databricks.
- **FR-002**: Un projet DOIT être en relation **1:1 avec une Business Application** existante du référentiel groupe (`id = business_app_id`) ; aucune saisie libre de projet non rattaché à une BA.
- **FR-003**: Le système DOIT supporter deux rôles **scopés projet** : `viewer` (lecture des pages DCM sur le périmètre du projet) et `admin` (`viewer` + gestion des membres/rôles + demande d'extension de périmètre).
- **FR-004**: Un utilisateur DOIT pouvoir appartenir à **plusieurs projets**, avec un rôle potentiellement différent par projet.
- **FR-005**: Microsoft Entra ID NE DOIT servir que de **gate d'authentification** via un **groupe unique `DCM-Users`** ; toute l'autorisation (projets, rôles, périmètres) DOIT vivre dans les tables DCM comme source de vérité unique.
- **FR-006**: Le rôle plateforme DOIT être réduit à `platform_role` ∈ {`user`, `super_admin`} ; `super_admin` (platform_admin) reste au-dessus des projets.
- **FR-006a**: Lors de la migration/lecture, le mapping de compatibilité DOIT être : ancien `super_admin`/`admin` global ⇒ `platform_role = super_admin` ; `data_architect`/`manager`/`viewer` ⇒ `platform_role = user` ; `platform_role` NULL ⇒ dérivé de l'ancien `role`.
- **FR-007**: Le système DOIT calculer le périmètre autorisé d'un utilisateur comme l'**union des LZ et des workspaces Databricks** de tous les projets où il est **membre actif** (`get_allowed_scope`).
- **FR-008**: Le filtrage des routes métriques DOIT combiner les deux dimensions : `WHERE :unrestricted OR source_lz_id IN (:lz_ids) OR workspace_id IN (:workspace_ids)`.
- **FR-009**: Un `platform_role = super_admin` DOIT bénéficier d'un périmètre `unrestricted` (toutes LZ / workspaces).
- **FR-010**: Un utilisateur sans aucun projet actif (périmètre vide) DOIT recevoir **200 + collection vide** sur les routes métriques (pas 403) ; les routes d'administration non autorisées renvoient **403**.
- **FR-011**: Le système DOIT permettre de **créer un projet** (nom, Business Application, membres+rôles, LZ et/ou workspaces DBX) ; le projet naît en `pending_validation`. Le **créateur** DOIT être automatiquement ajouté comme membre `admin` du projet lors de son activation (indépendamment des membres saisis).
- **FR-011a**: Le système DOIT **rejeter (409)** toute création de projet pour une Business Application ayant déjà un projet (actif ou `pending_validation`) — contrainte 1:1 — avec un message invitant l'utilisateur à **demander l'adhésion** au projet existant (FR-013).
- **FR-012**: La **création** d'un projet DOIT être validée par un **platform_admin** avant de passer `active` ; aucun provisioning Entra n'est effectué.
- **FR-013**: Un utilisateur DOIT pouvoir **rejoindre un projet existant** en demandant un rôle ; la demande (`dcm_project_join_request`, `pending`) est routée vers les **admins du projet** pour approbation.
- **FR-014**: Un **admin de projet** DOIT pouvoir demander une **extension de périmètre** (nouvelle LZ / workspace DBX) ; la demande (`dcm_project_scope_requests`, `pending`) DOIT être validée par un **platform_admin** avant application.
- **FR-015**: Un **admin de projet** NE DOIT pouvoir agir que sur **son propre projet** (gestion membres/rôles, demandes) — jamais sur un autre projet (403).
- **FR-016**: Le système DOIT fournir une **migration** des accès plats (`dcm_user_lz_access`) vers des projets par défaut (1 projet ↔ 1 BA), idempotente, en dry-run par défaut avec option `--apply`.
- **FR-016a**: La migration DOIT **loguer et rapporter** les LZ non résolvables vers une Business Application sans faire échouer la migration globale.
- **FR-017**: La migration DOIT **auto-promouvoir** en `admin` le membre le plus ancien (à défaut le premier ajouté) de chaque projet créé.
- **FR-018**: Le chevauchement de périmètre DOIT être **autorisé** : une même LZ peut appartenir à plusieurs projets, qui voient alors les mêmes données de cette LZ.
- **FR-019**: Le système DOIT interdire toute action laissant un projet `active` **sans aucun `admin` actif** : la dernière suppression/rétrogradation `admin` est rejetée en **409** (un platform_admin reste habilité à contourner).
- **FR-020**: Toute décision d'administration (validation de création/extension, approbation d'adhésion, changement de rôle) DOIT écrire une entrée dans `dcm_audit_log`.
- **FR-020a**: Les demandes en attente (création, adhésion, extension de périmètre) DOIVENT être notifiées **in-app uniquement** — liste des demandes en attente + badge pour l'approbateur concerné (platform_admin ou project admin) ; **aucun** email ni canal externe.
- **FR-020b**: Après le rejet d'une demande (adhésion ou extension de périmètre), l'utilisateur DOIT pouvoir **resoumettre librement** une nouvelle demande ; chaque resoumission crée une nouvelle ligne `pending` indépendante (le rejet n'est pas définitif, pas de cooldown).
- **FR-021**: Le frontend DOIT offrir les parcours self-service (créer, rejoindre, administrer un projet, demander une extension), un **état vide** invitant à créer/rejoindre, et une **matrice d'accès** combinant `platform_role` + rôle projet, avec des libellés lisibles (noms, pas d'identifiants).

### Key Entities

- **dcm_projects** — projet (1:1 BA) : `id (=business_app_id)`, `name`, `business_app_id`, `status` (`pending_validation`/`active`/`archived`), `entra_group_id` (nullable, toujours NULL en V2), `created_by`, timestamps, `validated_by/at`.
- **dcm_project_lz_scope** — périmètre Landing Zone : `(project_id, lz_id)`, `granted_by/at` ; chevauchement autorisé.
- **dcm_project_dbx_scope** — périmètre workspace Databricks : `(project_id, workspace_id)`, `granted_by/at`.
- **dcm_project_members** — appartenance : `(project_id, user_id)`, `role` (`viewer`/`admin`), `added_by/at`.
- **dcm_project_join_request** — demande d'adhésion : `id`, `(project_id, user_id)`, `requested_role`, `status`, `decided_by/at`.
- **dcm_project_scope_requests** — demande d'extension de périmètre : `(project_id, …ref LZ/workspace…)`, `status`, validée par platform_admin.
- **dcm_app_users (modifiée)** — ajout `platform_role` (`user`/`super_admin`) ; `role` historique conservé pour transition/rollback.

## Success Criteria

- **SC-001**: 100 % des utilisateurs actuellement porteurs d'un accès plat (`dcm_user_lz_access`) conservent, après migration, un accès équivalent via appartenance à au moins un projet `active`.
- **SC-002**: La migration est **idempotente** — un second `--apply` produit **0 changement** (aucun doublon de projet, membre ou scope).
- **SC-003**: Un utilisateur ne voit **que** les données des LZ et workspaces Databricks des projets où il est membre actif ; un `super_admin` voit tout ; un utilisateur sans projet obtient une application vide navigable (réponses métriques 200 vides).
- **SC-004**: Aucune écriture Microsoft Graph / création de groupe Entra n'est effectuée par l'application ; l'unique dépendance Entra est l'appartenance au groupe `DCM-Users`.
- **SC-005**: Un admin de projet ne peut ni agir sur un autre projet (403) ni étendre seul son périmètre (toute extension passe par une validation platform_admin) ; la tentative de retrait du dernier admin échoue en 409.
- **SC-006**: Chaque décision d'administration est traçable dans `dcm_audit_log`.

## Assumptions

- Le référentiel Business Application (`dim_reference_landing_zone_business_application`, feature 014) est disponible et permet de résoudre `lz_id → business_app_id` pour la migration.
- Le groupe Entra `DCM-Users` est provisionné et géré en amont par la gouvernance IAM standard (aucune gestion de membership côté application).
- L'auto-provisioning `pending` existant (`_load_dcm_user`) reste le mécanisme d'onboarding au premier login ; aucun code de provisioning de groupe à écrire.
- Les ~20 routes métriques existantes dépendent de `get_allowed_lz_ids` ; la compatibilité est préservée en ré-exprimant ce point d'entrée via `get_allowed_scope` pour limiter le blast radius.
- L'ancien `role` global et `get_allowed_lz_ids` (LZ seule) sont conservés en lecture le temps de la transition pour permettre un rollback ; leur retrait est hors de cette Epic.
