# Feature Specification: DCM Administration Module on Unity Catalog

**Feature Branch**: `006-dcm-admin-unity-catalog`  
**Created**: 2026-05-27  
**Status**: Draft  
**Input**: Demande tech lead "DCM — Spécification complète : Module Administration", adaptée au repo actuel qui utilise Databricks SQL Warehouse / Unity Catalog au lieu de Lakebase PostgreSQL.

---

## Compréhension du besoin

### Objectif

Créer le module **Administration DCM** pour gérer les utilisateurs, accès Landing Zones, règles d'alertes, canaux de notification, collecteurs, seuils KPI, rétention, fenêtres de maintenance et journal d'audit.

Le besoin initial mentionne Lakebase PostgreSQL, `asyncpg` et une migration SQL `dcm-backend/app/db/migrations/002_admin_schema.sql`. Cette cible n'est pas applicable dans ce repo. La cible correcte est :

- **Backend** : `packages/dcm-backend`, FastAPI, `DatabricksWarehousePool`, Databricks SQL connector.
- **Stockage** : Unity Catalog, catalog/schema configurés par `DCM_DATABRICKS_CATALOG` et `DCM_DATABRICKS_SCHEMA`.
- **Création des tables admin** : `our_catalogs_spn.py`, à relancer avec le SPN pour créer/valider les tables dans Unity Catalog.
- **Frontend** : `packages/dcm-frontend`, React 18 + TypeScript + Tailwind CSS.
- **Auth** : Entra ID JWT Bearer, RBAC DCM, dépendances `get_current_user`, `require_role`, `get_allowed_lz_ids`.

### Règle principale

Toutes les routes `/api/v1/admin/*` doivent être réservées aux utilisateurs `role = "admin"`, sauf l'endpoint de statut collecteur `POST /api/v1/admin/collectors/status`, qui est appelé par les collecteurs avec `X-Collector-Key`.

Toute écriture admin doit créer une entrée dans `dcm_audit_log`.

### Adaptation Unity Catalog

Les tables demandées par la spec tech lead doivent exister dans Unity Catalog avec les mêmes noms logiques :

- `dcm_app_users`
- `dcm_user_lz_access`
- `dcm_landing_zones`
- `dcm_notification_channels`
- `dcm_alert_rules`
- `dcm_alert_firings`
- `dcm_collector_status`
- `dcm_kpi_config`
- `dcm_retention_policies`
- `dcm_maintenance_windows`
- `dcm_audit_log`

Le DDL doit être porté en Databricks SQL / Delta :

- `UUID` devient `STRING`.
- `VARCHAR` / `TEXT` deviennent `STRING`.
- `TIMESTAMPTZ` devient `TIMESTAMP`.
- `JSONB` devient `STRING` contenant du JSON sérialisé.
- `TEXT[]` / `UUID[]` deviennent `ARRAY<STRING>`.
- `NUMERIC` devient `DOUBLE`, sauf si une précision métier stricte est validée plus tard.
- Les contraintes PostgreSQL (`CHECK`, FK, PK) ne doivent pas être supposées comme sécurité runtime dans Unity Catalog. Les validations doivent être appliquées côté API.

### Hors périmètre

- Créer une migration Lakebase/PostgreSQL.
- Réintroduire `asyncpg`.
- Décommissionner ou modifier l'infrastructure Databricks.
- Implémenter un moteur complet d'envoi notification avec secrets réels en clair.
- Faire confiance uniquement au frontend pour la sécurité.

---

## User Scenarios & Testing

### User Story 1 - Initialiser les tables Admin dans Unity Catalog (Priority: P1)

En tant que développeuse DCM, je veux relancer `our_catalogs_spn.py` pour créer les tables admin dans le catalog/schema Unity Catalog cible, afin que le backend puisse stocker la configuration admin.

**Why this priority**: aucun endpoint admin ne peut fonctionner sans tables admin disponibles dans UC.

**Independent Test**: exécuter `python our_catalogs_spn.py` avec le SPN et vérifier que les 11 tables `dcm_*` existent dans `SHOW TABLES`.

**Acceptance Scenarios**:

1. **Given** le SPN a les droits sur le schema UC, **When** `our_catalogs_spn.py` est relancé, **Then** les tables admin absentes sont créées.
2. **Given** les tables existent déjà, **When** le script est relancé, **Then** il reste idempotent et ne supprime aucune donnée.
3. **Given** `dcm_kpi_config` ou `dcm_retention_policies` sont vides, **When** le script s'exécute, **Then** les valeurs par défaut sont insérées sans dupliquer les lignes existantes.
4. **Given** les variables optionnelles de bootstrap admin sont fournies, **When** le script s'exécute, **Then** le premier utilisateur admin est inséré ou mis à jour.

---

### User Story 2 - Gérer utilisateurs, rôles et accès Landing Zones (Priority: P1)

En tant qu'admin DCM, je veux lister les utilisateurs, changer leur rôle, désactiver un compte et définir les Landing Zones accessibles.

**Why this priority**: le RBAC et le filtrage par LZ sont le socle des autres fonctionnalités admin et des pages data.

**Independent Test**: appeler les endpoints users avec un token admin et vérifier les changements dans `dcm_app_users` / `dcm_user_lz_access`.

**Acceptance Scenarios**:

1. **Given** un token admin valide, **When** `GET /api/v1/admin/users` est appelé, **Then** la réponse contient les utilisateurs avec leurs `lz_ids`.
2. **Given** un admin ajoute un email Entra ID, **When** `POST /api/v1/admin/users` est appelé avec `role = "admin"` ou un autre rôle DCM, **Then** l'utilisateur est créé dans `dcm_app_users` et `dcm_audit_log` contient `user.create`.
3. **Given** un utilisateur viewer, **When** son rôle est patché vers `data_architect`, **Then** son rôle est mis à jour et `dcm_audit_log` contient `user.role.update`.
4. **Given** l'admin essaie de désactiver son propre compte, **When** `PATCH /deactivate` est appelé, **Then** l'API retourne HTTP 400.
5. **Given** une liste complète de LZ est envoyée, **When** `PUT /lz-access` est appelé, **Then** les anciens accès sont remplacés atomiquement.

---

### User Story 3 - Administrer le registre Landing Zones (Priority: P1)

En tant qu'admin DCM, je veux enregistrer, modifier et désactiver les Landing Zones actives pour piloter le périmètre de monitoring.

**Independent Test**: créer une LZ `azure-lz-prod-fr`, la lister, puis la désactiver sans supprimer l'historique.

**Acceptance Scenarios**:

1. **Given** un `lz_id` conforme au pattern `^[a-z0-9][a-z0-9\-]{2,98}[a-z0-9]$`, **When** l'admin crée une LZ, **Then** elle apparaît dans `GET /api/v1/admin/landing-zones`.
2. **Given** le `lz_id` existe déjà, **When** l'admin recrée la LZ, **Then** l'API retourne HTTP 409.
3. **Given** une LZ avec utilisateurs associés, **When** elle est listée, **Then** `user_count` reflète les accès dans `dcm_user_lz_access`.

---

### User Story 4 - Configurer les alertes et notifications DCM (Priority: P1)

En tant qu'admin DCM, je veux créer des canaux de notification puis des règles d'alertes qui évaluent les métriques collectées.

**Why this priority**: les règles d'alertes dépendent des canaux de notification, donc le module notification doit être livré avant le module alert rules.

**Independent Test**: créer un canal Teams, créer une règle pipeline, tester la règle et consulter l'historique de firings.

**Scope notification validé**: le module D est limité à **Teams** et **email** pour cette version. Les canaux Slack et webhook présents dans la demande initiale sont hors périmètre.

**Acceptance Scenarios**:

1. **Given** un canal Teams ou email, **When** il est créé, **Then** sa config est stockée en JSON sérialisé sans secret en clair.
2. **Given** une règle avec `metric_domain = "pipeline"` et `condition_field = "failure_rate_pct"`, **When** la règle est testée, **Then** l'API retourne `would_fire`, `measured_value` et les résultats par LZ.
3. **Given** une règle supprimée, **When** son historique est consulté, **Then** les firings liés sont conservés ou supprimés selon la décision technique validée dans le plan.

---

### User Story 5 - Suivre les collecteurs et la fraîcheur des données (Priority: P1)

En tant qu'admin DCM, je veux voir le dernier run de chaque collecteur par LZ, avec statut, durée, métriques collectées et erreur éventuelle.

**Independent Test**: envoyer un upsert collecteur avec `X-Collector-Key`, puis vérifier que le panneau admin affiche frais/périmé/en erreur.

**Acceptance Scenarios**:

1. **Given** un collecteur poste son statut avec la bonne clé, **When** le payload est valide, **Then** `dcm_collector_status` est upserté.
2. **Given** une clé invalide, **When** le collecteur poste son statut, **Then** l'API retourne HTTP 401/403.
3. **Given** `last_run_at` est plus vieux que 2h, **When** les statuts sont listés, **Then** `is_stale` vaut `true`.

---

### User Story 6 - Paramétrer KPI, rétention et maintenance (Priority: P2)

En tant qu'admin DCM, je veux modifier les seuils visuels KPI, les durées de rétention et les fenêtres de maintenance.

**Independent Test**: modifier un seuil KPI, vérifier `GET /api/v1/kpi-config`, créer une fenêtre active et vérifier `GET /api/v1/maintenance-windows/active`.

**Acceptance Scenarios**:

1. **Given** un patch KPI valide, **When** il est sauvegardé, **Then** les paires warning/critical restent cohérentes.
2. **Given** une rétention inférieure à 7 jours, **When** elle est sauvegardée, **Then** l'API refuse la valeur.
3. **Given** une fenêtre de maintenance active, **When** l'endpoint public est appelé, **Then** elle est retournée pour le moteur d'alertes.
4. **Given** une fenêtre de plus de 7 jours, **When** elle est créée, **Then** l'API la refuse.

---

### User Story 7 - Auditer toutes les actions admin (Priority: P1)

En tant que responsable DCM, je veux consulter et exporter le journal d'audit pour tracer les actions sensibles.

**Independent Test**: effectuer plusieurs mutations admin, lister `GET /api/v1/admin/audit-log`, filtrer par action et exporter CSV.

**Acceptance Scenarios**:

1. **Given** une écriture admin réussie, **When** l'action est terminée, **Then** une ligne est créée dans `dcm_audit_log`.
2. **Given** des filtres acteur/action/date, **When** l'audit log est consulté, **Then** les résultats sont ordonnés par `created_at DESC`.
3. **Given** l'export CSV est demandé, **When** les filtres sont appliqués, **Then** le fichier respecte les mêmes critères.

---

### User Story 8 - Utiliser l'interface Admin (Priority: P2)

En tant qu'admin DCM, je veux accéder à une page `/admin` structurée par onglets afin de gérer les 9 domaines sans changer d'application.

**Independent Test**: se connecter avec un utilisateur admin, ouvrir `/admin`, naviguer dans les 9 panneaux, effectuer au moins une mutation et vérifier l'audit.

**Acceptance Scenarios**:

1. **Given** un utilisateur non admin, **When** il ouvre `/admin`, **Then** il est redirigé ou bloqué.
2. **Given** un admin, **When** il ouvre `/admin`, **Then** les onglets Utilisateurs, Landing Zones, Règles alertes, Notifications, Collecteurs, Seuils KPI, Rétention, Maintenance et Journal audit sont visibles.
3. **Given** un admin sauvegarde une modification, **When** l'appel API réussit, **Then** l'UI reflète l'état serveur et affiche un feedback clair.

---

## Edge Cases

- Tables UC existantes avec schéma incomplet : le script doit signaler l'écart plutôt que masquer l'erreur.
- SPN sans privilège `CREATE TABLE` : erreur explicite indiquant le catalog/schema cible.
- Absence de premier admin : prévoir bootstrap par variables d'environnement ou insertion contrôlée.
- Auth désactivée en dev local : uniquement via `DCM_AUTH_DISABLED=true`, jamais par défaut.
- Valeurs JSON invalides dans config channel ou audit states : refuser côté API.
- Secrets notification : stocker uniquement des références de secrets, jamais la valeur brute.
- LZ supprimée ou désactivée mais encore référencée par des règles : conserver la référence et afficher un état clair.
- Règle d'alerte sans canal : autoriser seulement si la spec produit confirme un mode "no notification"; sinon refuser.
- Concurrence sur remplacement d'accès LZ : opération atomique côté endpoint.
- `All LZs` dans règles ou maintenance : représenté par `NULL` ou tableau vide selon convention API, mais documenté et stable.
- Export audit volumineux : limiter ou paginer pour éviter un timeout.

## Requirements

### Functional Requirements

- **FR-001**: Le repo MUST créer les tables admin via `our_catalogs_spn.py`, pas via une migration Lakebase/PostgreSQL.
- **FR-002**: Le script de création UC MUST être idempotent et conserver les données existantes.
- **FR-003**: Les tables admin MUST utiliser les noms `dcm_*` définis dans cette spec.
- **FR-004**: Les valeurs par défaut KPI MUST être insérées dans `dcm_kpi_config` sans doublons.
- **FR-005**: Les valeurs par défaut de rétention MUST être insérées dans `dcm_retention_policies` sans doublons.
- **FR-006**: Un mécanisme de bootstrap MUST permettre de créer le premier admin sans exposer de secret.
- **FR-007**: Toutes les routes `/api/v1/admin/*` MUST appliquer `require_role("admin")`, sauf `POST /api/v1/admin/collectors/status`.
- **FR-008**: `POST /api/v1/admin/collectors/status` MUST vérifier `X-Collector-Key` avec `DCM_COLLECTOR_API_KEY`.
- **FR-009**: Toutes les écritures admin MUST appeler un helper `log_action`.
- **FR-010**: `log_action` MUST écrire dans `dcm_audit_log` avec acteur, action, cible, before/after JSON et IP si disponible.
- **FR-011**: Les rôles autorisés MUST être `viewer`, `data_architect`, `manager`, `admin`.
- **FR-012**: L'API MUST permettre à un admin de créer un utilisateur DCM par email Entra ID, rôle et accès LZ optionnels.
- **FR-013**: L'API MUST empêcher un admin de désactiver son propre compte.
- **FR-014**: Les accès LZ utilisateur MUST être remplaçables atomiquement.
- **FR-015**: Les endpoints Landing Zones MUST valider le pattern `lz_id`.
- **FR-016**: Les endpoints notification MUST accepter uniquement `teams` et `email` pour cette version.
- **FR-017**: Les configs notification MUST stocker les secrets sous forme de références.
- **FR-018**: Les règles d'alerte MUST valider les couples `metric_domain` / `condition_field`.
- **FR-019**: Les règles d'alerte MUST supporter `gt`, `lt`, `gte`, `lte`, `eq`.
- **FR-020**: Le test d'une règle MUST retourner `would_fire`, `measured_value`, `threshold`, `evaluated_at` et les résultats par LZ.
- **FR-021**: Les statuts collecteurs MUST exposer `is_stale` calculé.
- **FR-022**: `GET /api/v1/kpi-config` MUST être accessible aux utilisateurs authentifiés non admin.
- **FR-023**: Les seuils KPI MUST valider la cohérence warning/critical, avec conformité inversée.
- **FR-024**: Les politiques de rétention MUST refuser toute valeur `< 7`.
- **FR-025**: Les fenêtres de maintenance MUST refuser `ends_at <= starts_at` et les durées `> 7 jours`.
- **FR-026**: `GET /api/v1/maintenance-windows/active` MUST être accessible au moteur d'alertes hors admin.
- **FR-027**: L'audit log MUST être filtrable par acteur, action, target type et dates.
- **FR-028**: L'audit log MUST être exportable en CSV.
- **FR-029**: Le frontend MUST fournir une page `/admin` protégée par `RequireAdmin`.
- **FR-030**: Le frontend MUST afficher une entrée sidebar Administration seulement pour `role = "admin"`.
- **FR-031**: Les routes data existantes MUST intégrer le filtrage LZ autorisé avant exposition des données.

### API Surface

Les endpoints à créer ou adapter sont :

- `GET /api/v1/admin/users`
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}`
- `PATCH /api/v1/admin/users/{user_id}/role`
- `PATCH /api/v1/admin/users/{user_id}/deactivate`
- `PUT /api/v1/admin/users/{user_id}/lz-access`
- `POST /api/v1/admin/users/{user_id}/lz-access/{lz_id}`
- `DELETE /api/v1/admin/users/{user_id}/lz-access/{lz_id}`
- `GET /api/v1/admin/landing-zones`
- `GET /api/v1/admin/landing-zones/{lz_id}`
- `POST /api/v1/admin/landing-zones`
- `PATCH /api/v1/admin/landing-zones/{lz_id}`
- `PATCH /api/v1/admin/landing-zones/{lz_id}/deactivate`
- `GET /api/v1/admin/notification-channels`
- `POST /api/v1/admin/notification-channels`
- `PATCH /api/v1/admin/notification-channels/{channel_id}`
- `DELETE /api/v1/admin/notification-channels/{channel_id}`
- `POST /api/v1/admin/notification-channels/{channel_id}/test`
- `GET /api/v1/admin/alert-rules`
- `GET /api/v1/admin/alert-rules/{rule_id}`
- `POST /api/v1/admin/alert-rules`
- `PATCH /api/v1/admin/alert-rules/{rule_id}`
- `DELETE /api/v1/admin/alert-rules/{rule_id}`
- `POST /api/v1/admin/alert-rules/{rule_id}/test`
- `GET /api/v1/admin/alert-rules/{rule_id}/firings`
- `GET /api/v1/admin/collectors/status`
- `GET /api/v1/admin/collectors/status/{lz_id}`
- `POST /api/v1/admin/collectors/status`
- `GET /api/v1/admin/kpi-config`
- `PATCH /api/v1/admin/kpi-config`
- `GET /api/v1/kpi-config`
- `GET /api/v1/admin/retention-policies`
- `PATCH /api/v1/admin/retention-policies`
- `GET /api/v1/admin/retention-policies/stats`
- `GET /api/v1/admin/maintenance-windows`
- `POST /api/v1/admin/maintenance-windows`
- `PATCH /api/v1/admin/maintenance-windows/{window_id}`
- `DELETE /api/v1/admin/maintenance-windows/{window_id}`
- `GET /api/v1/maintenance-windows/active`
- `GET /api/v1/admin/audit-log`
- `GET /api/v1/admin/audit-log/export`

### Key Entities

- **DCM App User**: utilisateur connu du portail, lié à `entra_oid`, `email`, `display_name`, `role`, `is_active`.
- **User LZ Access**: association entre utilisateur et Landing Zone.
- **Landing Zone**: registre admin des LZ actives, cloud, région, environnement, BA, collecteurs et notes.
- **Notification Channel**: destination d'alertes Teams ou email.
- **Alert Rule**: règle d'évaluation sur métriques pipeline, cluster, cost, security ou governance.
- **Alert Firing**: historique d'un déclenchement de règle.
- **Collector Status**: dernier statut connu d'un collecteur par LZ.
- **KPI Config**: seuils visuels pour colorer les cartes KPI.
- **Retention Policy**: durée de conservation par table métrique.
- **Maintenance Window**: période où les alertes peuvent être suspendues.
- **Audit Log**: trace immuable des actions admin.

## Success Criteria

### Measurable Outcomes

- **SC-001**: `python our_catalogs_spn.py` crée ou valide les 11 tables admin dans Unity Catalog.
- **SC-002**: Les seeds KPI et rétention sont présents après exécution du script.
- **SC-003**: Un admin peut lister, modifier rôle, désactiver et remplacer les accès LZ d'un utilisateur.
- **SC-004**: Chaque écriture admin crée une ligne d'audit consultable.
- **SC-005**: Un utilisateur non admin ne peut pas appeler les routes `/api/v1/admin/*`.
- **SC-006**: Un collecteur peut upserter son statut uniquement avec la clé dédiée.
- **SC-007**: La page `/admin` expose les 9 modules demandés et bloque les non-admins.
- **SC-008**: `GET /api/v1/kpi-config` et `GET /api/v1/maintenance-windows/active` restent accessibles aux consommateurs non admin prévus.
- **SC-009**: Les routes data existantes ne retournent pas de données hors LZ autorisées.

## Assumptions

- Le catalog/schema cible est celui déjà utilisé par `our_catalogs_spn.py`.
- Le backend écrit dans Unity Catalog via Databricks SQL Warehouse ; les requêtes utilisent les placeholders `?`.
- Les IDs UUID sont générés côté Python et stockés en `STRING`.
- Les colonnes JSON sont stockées en `STRING` et sérialisées/désérialisées par l'API.
- Les validations qui étaient des contraintes PostgreSQL sont reprises côté Pydantic/service.
- Le premier admin sera fourni via variables d'environnement de bootstrap ou inséré par procédure contrôlée.
