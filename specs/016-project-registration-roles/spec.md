# feature : Registration par projet sur la page login + refonte des rôles à 3 niveaux

**Feature Branch**: `016-project-registration-roles` — branches filles `{domain}/016-{slug}`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-08-31

**Input**: La partie registration des utilisateurs par landing zone doit être remplacée par la registration par projet. Sur la page de login/inscription, remplacer le bloc « Register a landing zone » par un formulaire « Join or Register a project ». Pour **Register** : email du requester, project name (choisi dans la liste de BA), members + rôles (ajout d'utilisateurs avec rôle viewer ou admin), et la liste des landing zones et workspaces auxquels le projet veut accéder — par défaut les LZ/workspaces associés à sa BA, avec possibilité d'en retirer ou d'en ajouter. Pour **Join** : email du user + projet (liste des projets DCM) pour la demande d'adhésion. L'onglet « My Landing Zones » n'est plus utile et doit être supprimé. Dans les rôles, ne garder que 3 rôles : **project admin** (scope projet), **project viewer** (scope projet), et **platform admin** (scope plateforme).

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | ✅ | packages/dcm-frontend |
| Backend | ✅ | ✅ | packages/dcm-backend, packages/dcm-commons |
| DataEng | ❌ | ❌ | — |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 2 |
|---|---|
| Mode | one_per_domain |
| Domaines avec ticket | frontend, backend |

## Clarifications

### Session 2026-08-31

- Q: Mapping des 3 rôles plats hérités (data_architect, manager, admin) vers le modèle à 3 rôles ? → A: `admin` → **project admin** ; `manager` & `data_architect` → **project viewer** ; `pending` → **aucun rôle effectif**.
- Q: Rôle du requester (créateur) dans le formulaire Register ? → A: Requester **auto-ajouté comme project admin** ; la liste des membres sert aux **autres** personnes.
- Q: Routage d'une demande Join quand le projet est encore `pending_validation` (pas d'admin confirmé) ? → A: Vers le **créateur/requester** du projet tant que le projet n'est pas validé.
- Q: Suppression de « My Landing Zones » — périmètre backend ? → A: Retirer/déprécier **uniquement** le chemin `lz_registration` ; conserver les demandes `dcm_access` fonctionnelles.
- Q: Email du requester/user sur la page login pré-auth ? → A: **Saisie libre** (le visiteur n'est pas encore un utilisateur DCM authentifié).

## Contexte

Aujourd'hui, un nouvel arrivant sur la page de login DCM peut soit « Request DCM access », soit « Register a landing zone » (via [LandingRequestChooserModal.tsx](../../packages/dcm-frontend/src/components/LandingRequestChooserModal.tsx) + [LzRegistrationRequestModal.tsx](../../packages/dcm-frontend/src/components/LzRegistrationRequestModal.tsx)). L'accès et le périmètre sont pensés **par landing zone** (onglet « My Landing Zones » → [MyLandingZones.tsx](../../packages/dcm-frontend/src/pages/MyLandingZones.tsx), route `/my-access`, [access_requests.py](../../packages/dcm-backend/app/api/routes/access_requests.py)), et le modèle de rôles est un modèle **plat à 6 rôles** (`pending, viewer, data_architect, manager, admin, super_admin` — [role_permissions.py](../../packages/dcm-backend/app/auth/role_permissions.py)).

La feature 015 (`015-project-access-governance`) a introduit le modèle **« projet »** à deux niveaux : `platform_role ∈ {user, super_admin}` + rôle **projet** `{viewer, admin}`, avec les écrans self-service ([Projects.tsx](../../packages/dcm-frontend/src/pages/Projects.tsx), [ProjectDetail.tsx](../../packages/dcm-frontend/src/pages/ProjectDetail.tsx)) et les tables projet. **016 finit la bascule** : la registration se fait **par projet** dès la page de login, l'entrée « landing zone » disparaît, et le modèle de rôles est **réduit à exactement 3 rôles** exposés à l'utilisateur — project admin (scope projet), project viewer (scope projet), platform admin (scope plateforme). Ce qui n'est pas encore possible aujourd'hui : s'inscrire/rejoindre un **projet** depuis l'écran de login, et n'avoir que 3 rôles cohérents dans toute l'UI et l'autorisation backend.

## Dependency Analysis

Constats de la vérification code (Q6 de l'intake) et décision retenue.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| Endpoints projet (`/projects*`, register/join) | backend | pas de `packages/dcm-backend/app/api/routes/projects.py` sur cette branche (015 T002 non mergé) | Ticket Backend de cet Epic (T002) — s'appuie sur les tables projet de 015 T001 |
| Tables projet + colonne `platform_role` + migration accès plats | dataeng | 015 T001 (`dcm_projects`, `dcm_project_members`, `dcm_project_*_scope`, `dcm_project_join_request`, `dcm_project_scope_requests`, `platform_role`) | **Hors Epic** : livré par 015 T001 — prérequis figé, aucun ticket DataEng ici |
| Liste des BA + LZ/workspaces par défaut d'une BA | backend | données de référence LZ (`ba_name`) déjà exposées, consommées par [Projects.tsx](../../packages/dcm-frontend/src/pages/Projects.tsx) `deriveBusinessAppOptions` | Réutilisation de l'existant côté backend/front |
| Réduction du modèle de rôles à 3 | backend | 6 rôles stockés dans [role_permissions.py](../../packages/dcm-backend/app/auth/role_permissions.py) `DCM_STORED_ROLES` | Ticket Backend : collapse de l'ensemble effectif ; mapping des rôles hérités via la migration 015 (FR-006a) |

## Prerequisites

- **Small branches / small PRs** : la Story Frontend touche `packages/dcm-frontend` uniquement ; la Story Backend touche `packages/dcm-backend` (+ `dcm-commons` si un enum/modèle bouge). Chaque PR reste centrée sur une préoccupation.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- **Dépendance bloquante 015** : les tables projet et les endpoints `/projects*` (015 T001 + T002) doivent être disponibles sur `develop` avant merge de cet Epic ; sinon la Story Frontend consomme une **API mockée en dev** (pattern 015 T003) et la Story Backend intègre/aligne les endpoints projet.
- `[NEEDS CLARIFICATION]` levés (recommandé avant l'étape `plan` de spec-kit).

## User stories

### User Story 1 — Frontend : registration/join projet sur la page login + suppression « My Landing Zones » + UI 3 rôles (Priority: P1)

Sur la page de login/inscription, l'utilisateur non enregistré remplace le choix « Register a landing zone » par **« Join or Register a project »**. En **Register**, il saisit l'email du requester, choisit un **project name dans la liste des Business Applications** (pas de texte libre), ajoute des **membres avec un rôle** (viewer ou admin), et sélectionne les **landing zones + workspaces Databricks** du projet — pré-remplis avec ceux associés à la BA, avec ajout/retrait possible. En **Join**, il saisit son email + choisit un **projet dans la liste des projets DCM** pour envoyer une demande d'adhésion. L'onglet **« My Landing Zones »** disparaît de la navigation et des routes. Les sélecteurs de rôles et libellés n'exposent plus que **3 rôles** : project admin, project viewer, platform admin.

**Why this priority** : c'est la surface visible de la bascule — sans elle, l'utilisateur ne peut pas s'inscrire par projet et l'ancien parcours LZ subsiste.
**Independent Test** : testable en isolation avec réseau mocké (Vitest) — soumission register (payload BA + membres + scopes), soumission join (email + projet), absence de la route `/my-access` et de l'item de nav, matrice de rôles à 3 valeurs.

**Acceptance Scenarios**

1. **Given** un visiteur non enregistré sur la page login, **When** il ouvre le chooser d'inscription, **Then** il voit « Join or Register a project » (plus « Register a landing zone »).
2. **Given** le formulaire Register, **When** il choisit une **Business Application** (liste, pas de texte libre) et ajoute des membres avec rôle viewer/admin, **Then** les LZ + workspaces de la BA sont pré-sélectionnés et modifiables (ajout/retrait) avant soumission.
3. **Given** le formulaire Join, **When** il saisit son email et choisit un **projet DCM** dans la liste, **Then** une demande d'adhésion est soumise.
4. **Given** l'application, **When** l'utilisateur parcourt la navigation, **Then** l'onglet « My Landing Zones » (`/my-access`) est **absent** pour tous les rôles.
5. **Given** un sélecteur de rôle (création/gestion projet), **When** il liste les rôles, **Then** il n'affiche que **project admin**, **project viewer** (scope projet) et **platform admin** (scope plateforme), avec des libellés lisibles.

### User Story 2 — Backend : endpoints register/join projet et modèle d'autorisation à 3 rôles (Priority: P1)

Le backend expose la registration/adhésion **par projet** consommée par la page login (création de projet en `pending_validation` avec BA, membres+rôles, LZ + workspaces ; demande d'adhésion routée vers les admins du projet), et **réduit le modèle de rôles à 3** : project admin (scope projet), project viewer (scope projet), platform admin (`super_admin`, scope plateforme). Les rôles plats hérités (`data_architect`, `manager`, `admin`) ne sont plus des rôles effectifs ; le mapping de compatibilité s'appuie sur la migration 015 (`platform_role`).

**Why this priority** : porte les règles d'autorisation et le contrat consommé par le Frontend ; sans lui, la page login n'a pas d'endpoint projet et les 3 rôles ne sont pas appliqués côté serveur.
**Independent Test** : testable via pytest — endpoints register/join projet (201/202, 409 BA déjà prise, 403 hors projet), ensemble effectif des rôles limité à `{viewer, admin}` (projet) + `{user, super_admin}` (plateforme).

**Acceptance Scenarios**

1. **Given** une registration projet valide depuis la page login, **When** l'API la reçoit, **Then** le projet est créé en `pending_validation` avec BA + membres/rôles + scopes LZ/workspaces.
2. **Given** une BA ayant déjà un projet, **When** une nouvelle registration cible cette BA, **Then** l'API renvoie **409** avec un message invitant à **rejoindre** le projet existant.
3. **Given** une demande de join (email + projet), **When** l'API la reçoit, **Then** une `dcm_project_join_request` `pending` est créée et routée vers les admins du projet.
4. **Given** le modèle d'autorisation, **When** on énumère les rôles effectifs, **Then** seuls **3 rôles** sont exposés (project admin, project viewer, platform admin) ; les rôles plats hérités sont mappés, jamais assignables.

## Acceptance Criteria

1. **Given** la page login, **When** un visiteur s'inscrit, **Then** il le fait **par projet** (Register ou Join) — aucun parcours « Register a landing zone ».
2. **Given** l'app, **When** on inspecte la navigation et les routes, **Then** « My Landing Zones » / `/my-access` n'existent plus.
3. **Given** l'UI et l'autorisation backend, **When** on liste les rôles, **Then** il n'y a **que 3 rôles** (project admin, project viewer, platform admin) avec libellés lisibles.
4. Gates des packages verts (lint → types → tests → build) pour `dcm-frontend` et `dcm-backend`.

## Out of scope (cet Epic)

- **DataEng** : tables projet, colonne `platform_role`, migration des accès plats — **livrés par 015 T001** (prérequis figé). Aucun ticket DataEng dans cet Epic ; si une migration complémentaire de purge des rôles plats est nécessaire, elle sera un ticket séparé.
- Provisioning Entra / SCIM par projet (gouvernance restant côté DCM, cf. 015).
- Refonte des écrans projet existants ([Projects.tsx](../../packages/dcm-frontend/src/pages/Projects.tsx), [ProjectDetail.tsx](../../packages/dcm-frontend/src/pages/ProjectDetail.tsx)) au-delà de l'alignement 3 rôles et du parcours login.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | Frontend | Page login « Join or Register a project », suppression « My Landing Zones », UI limitée à 3 rôles | ✅ |
| T002 | Backend | Endpoints register/join projet + modèle d'autorisation réduit à 3 rôles | ✅ |
| — | DataEng | Tables projet + `platform_role` + migration | ❌ hors Epic (015 T001) |

## Requirements & Success Criteria

- **FR-001** : La page login/inscription DOIT remplacer le bloc « Register a landing zone » par une entrée **« Join or Register a project »**.
- **FR-002** : Le formulaire **Register** DOIT demander : email du requester (**saisie libre** — le visiteur n'est pas authentifié), **project name choisi dans la liste des Business Applications** (pas de texte libre), membres avec rôle **viewer** ou **admin** (ajout/retrait), et les **landing zones + workspaces Databricks** du projet — pré-remplis avec ceux associés à la BA, avec ajout/retrait possible. Le **requester est automatiquement project admin** du projet créé ; la liste des membres concerne les **autres** personnes.
- **FR-003** : La soumission Register DOIT créer un projet en `pending_validation` (contrainte 1:1 BA → **409** si la BA a déjà un projet, avec message invitant à rejoindre).
- **FR-004** : Le formulaire **Join** DOIT demander l'email du user (**saisie libre**) + un **projet choisi dans la liste des projets DCM**, et créer une demande d'adhésion routée vers les **admins du projet** ; tant que le projet est en `pending_validation` (pas d'admin confirmé), la demande est routée vers le **créateur/requester** du projet.
- **FR-005** : L'onglet **« My Landing Zones »** (`/my-access`, [MyLandingZones.tsx](../../packages/dcm-frontend/src/pages/MyLandingZones.tsx), item de nav) DOIT être supprimé de l'application ; le parcours de self-registration LZ (`lz_registration`) DOIT être retiré de la page login **et déprécié côté backend** — seul le chemin `lz_registration` de [access_requests.py](../../packages/dcm-backend/app/api/routes/access_requests.py) est retiré ; les demandes `dcm_access` restent fonctionnelles.
- **FR-006** : Le modèle de rôles DOIT être réduit à **exactement 3 rôles** : **project admin** (scope projet), **project viewer** (scope projet), **platform admin** (scope plateforme = `super_admin`). Les rôles plats hérités (`data_architect`, `manager`, `admin`, `pending`) NE DOIVENT plus être des rôles effectifs assignables.
- **FR-007** : Le backend DOIT appliquer ce modèle à 3 rôles dans l'autorisation ; les rôles hérités DOIVENT être mappés (via `platform_role` / migration 015) et jamais ré-exposés en création. Mapping : `admin` → **project admin** ; `manager` & `data_architect` → **project viewer** ; `pending` → **aucun rôle effectif**.
- **FR-008** : Tous les libellés de rôles affichés DOIVENT être lisibles (noms, pas d'identifiants bruts).
- **SC-001** : Un nouvel utilisateur peut s'inscrire **ou** rejoindre un projet depuis la page login, sans aucun chemin de registration par landing zone.
- **SC-002** : Aucune route `/my-access` ni item « My Landing Zones » n'est atteignable, quel que soit le rôle.
- **SC-003** : Les sélecteurs de rôles (UI) et l'énumération des rôles effectifs (backend) ne présentent que **3 valeurs**.

## Assumptions

- Le socle projet de 015 (tables + endpoints `/projects*`) est la base consommée ; en dev, l'API projet peut être **mockée** (pattern 015 T003) tant que 015 T002 n'est pas mergé sur `develop`.
- « platform admin » ≡ `platform_role = super_admin` du modèle 015 ; « project admin »/« project viewer » ≡ rôle projet `admin`/`viewer`.
- La liste des Business Applications et les LZ/workspaces par défaut d'une BA proviennent des données de référence LZ existantes (`ba_name`), déjà utilisées par les écrans projet.
