-- Spike — Gouvernance des groupes d'accès DCM (modèle « projet »)
-- Branche : spike/access_groupe_strategy
-- NON déployé — prototype pour arbitrage. À porter dans our_catalogs_spn.py si validé.
--
-- Conventions reprises de our_catalogs_spn.py :
--   STRING / BOOLEAN / TIMESTAMP, USING DELTA, clés/contraintes validées à la couche API.
-- Placeholder {catalog}.{schema} = résolu par qualified_table(settings, ...) côté backend.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Projets — unité de gouvernance (groupe Entra ID = miroir)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dcm_projects (
    id              STRING    NOT NULL,   -- = business_app_id (projet ≡ Business Application, 1:1)
    name            STRING    NOT NULL,   -- par défaut = ba_name de la Business Application
    business_app_id STRING    NOT NULL,   -- référence Business Application (référentiel groupe) ; = id
    status          STRING    NOT NULL,   -- pending_validation | active | archived
    entra_group_id  STRING,               -- miroir Entra (NULL tant que non provisionné)
    created_by      STRING    NOT NULL,   -- dcm_app_users.id du demandeur
    created_at      TIMESTAMP NOT NULL,
    updated_at      TIMESTAMP NOT NULL,
    validated_by    STRING,               -- platform_admin ayant validé
    validated_at    TIMESTAMP
)
USING DELTA;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Périmètre Landing Zone du projet (une LZ peut appartenir à plusieurs projets)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dcm_project_lz_scope (
    project_id STRING    NOT NULL,   -- dcm_projects.id
    lz_id      STRING    NOT NULL,   -- dcm_landing_zones.lz_id
    granted_by STRING,
    granted_at TIMESTAMP NOT NULL
)
USING DELTA;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Périmètre workspace Databricks du projet
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dcm_project_dbx_scope (
    project_id   STRING    NOT NULL,   -- dcm_projects.id
    workspace_id STRING    NOT NULL,   -- id workspace Databricks
    granted_by   STRING,
    granted_at   TIMESTAMP NOT NULL
)
USING DELTA;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Membres d'un projet — rôle scopé projet (viewer | admin)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dcm_project_members (
    project_id STRING    NOT NULL,   -- dcm_projects.id
    user_id    STRING    NOT NULL,   -- dcm_app_users.id
    role       STRING    NOT NULL,   -- viewer | admin (scopé projet)
    added_by   STRING,
    added_at   TIMESTAMP NOT NULL
)
USING DELTA;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Demandes d'adhésion à un projet — approuvées par un admin du projet
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dcm_project_join_requests (
    id             STRING    NOT NULL,   -- UUID
    project_id     STRING    NOT NULL,   -- dcm_projects.id
    user_id        STRING    NOT NULL,   -- dcm_app_users.id demandeur
    requested_role STRING    NOT NULL,   -- viewer | admin
    status         STRING    NOT NULL,   -- pending | approved | rejected
    justification  STRING,
    requested_at   TIMESTAMP NOT NULL,
    decided_by     STRING,               -- project admin ayant tranché
    decided_at     TIMESTAMP
)
USING DELTA;

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Demandes d'extension de périmètre projet (nouvelle LZ / workspace DBX)
--    Émises par un admin du projet, VALIDÉES par un platform_admin (super_admin).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS {catalog}.{schema}.dcm_project_scope_requests (
    id             STRING    NOT NULL,   -- UUID
    project_id     STRING    NOT NULL,   -- dcm_projects.id
    scope_type     STRING    NOT NULL,   -- lz | dbx_workspace
    scope_ref      STRING    NOT NULL,   -- lz_id ou workspace_id demandé
    status         STRING    NOT NULL,   -- pending | approved | rejected
    justification  STRING,
    requested_by   STRING    NOT NULL,   -- project admin demandeur
    requested_at   TIMESTAMP NOT NULL,
    decided_by     STRING,               -- platform_admin ayant tranché
    decided_at     TIMESTAMP
)
USING DELTA;
