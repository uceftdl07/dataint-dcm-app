# API Contract — Projects & Access Governance (`/v1/projects*`, `/auth/me`)

**Feature**: 015-project-access-governance | **Date**: 2026-08-21
Contrat **figé par T002 (backend)**, consommé par T003 (frontend). Champs exposés en **camelCase** (alias Pydantic) ; snake_case en Python. Toute déviation doit d'abord mettre à jour ce fichier + [data-model.md](../data-model.md) puis notifier la branche aval.

## Conventions

- Base path : `/v1`. Auth : gate Entra `DCM-Users` ; identité résolue → `dcm_app_users` (`platform_role`).
- Erreurs : `400` payload invalide · `403` non autorisé (admin) · `404` introuvable · `409` conflit (duplicat BA, dernier admin).
- Périmètre vide (0 projet actif) : routes **métriques** ⇒ `200` + collection vide ; routes **admin** non autorisées ⇒ `403`.

## `GET /auth/me` (enrichi)

> **Déviation assumée (T002)** : contrairement aux routes `/v1/projects*` (camelCase),
> `/auth/me` est **snake_case** — cet endpoint préexiste au feature 015 et exposait déjà
> `id`, `entra_oid`, `email`, `display_name`, `role`, `is_active`, `lz_ids` en snake_case.
> On conserve cette convention pour ne pas casser les consommateurs existants. Le frontend
> (T003) lit donc `platform_role` / `projects[].project_id` / `projects[].role` en snake_case.

```jsonc
{
  "id": "u-123",
  "display_name": "Jane Doe",
  "role": "viewer",
  "platform_role": "user",              // user | super_admin
  "is_active": true,
  "lz_ids": ["lz-a"],
  "projects": [
    // role: viewer | admin ; status: pending_validation | active | archived
    { "project_id": "ba-42", "name": "BA Payments", "role": "admin", "status": "active" }
  ]
}
```

## Projects

| Méthode | Path | Rôle requis | Notes |
|---|---|---|---|
| `GET` | `/v1/projects` | authentifié | projets dont l'appelant est membre (super_admin : tous) |
| `POST` | `/v1/projects` | authentifié | crée `pending_validation` ; **409** si la BA a déjà un projet (actif ou pending) — FR-011a ; créateur auto-membre `admin` à l'activation (FR-011) |
| `GET` | `/v1/projects/{id}` | membre | détail + `lzScope[]` + `dbxScope[]` |
| `POST` | `/v1/projects/{id}/validate` | platform_admin | `pending_validation` → `active` (403 sinon) |

`POST /v1/projects` body :
```jsonc
{ "businessAppId": "ba-42", "name": "BA Payments", "lzScope": ["lz-a"], "dbxScope": ["ws-1"] }
```

## Members (décidés par project admin)

| Méthode | Path | Rôle requis | Notes |
|---|---|---|---|
| `GET` | `/v1/projects/{id}/members` | membre | inclut `displayName` lisible (FR-017) |
| `PATCH` | `/v1/projects/{id}/members/{userId}` | project admin | change `role` ; **409** si retrait/rétrogradation du dernier `admin` actif (FR-014) |
| `DELETE` | `/v1/projects/{id}/members/{userId}` | project admin | idem garde 409 |

## Join requests (décidées par project admin)

| Méthode | Path | Rôle requis | Notes |
|---|---|---|---|
| `POST` | `/v1/projects/{id}/join-requests` | authentifié | `pending` ; resoumission libre après rejet (FR-020b) |
| `GET` | `/v1/projects/{id}/join-requests` | project admin | file d'attente in-app (FR-020a) |
| `POST` | `/v1/join-requests/{reqId}/decide` | project admin | `{ "decision": "approved" \| "rejected" }` ; approuvé ⇒ ajoute membre |

## Scope requests (validées par platform_admin)

| Méthode | Path | Rôle requis | Notes |
|---|---|---|---|
| `POST` | `/v1/projects/{id}/scope-requests` | project admin | `{ "scopeType": "lz" \| "dbx_workspace", "scopeRef": "lz-b" }` |
| `GET` | `/v1/scope-requests` | platform_admin | file d'attente in-app |
| `POST` | `/v1/scope-requests/{reqId}/decide` | platform_admin | approuvé ⇒ ajoute la ligne de périmètre correspondante |

## Filtrage métrique (2 dimensions)

Toutes les routes métriques existantes appliquent `add_scope_filter` :

```sql
WHERE (:unrestricted OR source_lz_id IN (:lz_ids) OR workspace_id IN (:workspace_ids))
```

- `unrestricted = true` pour `platform_role = super_admin`.
- `lz_ids` / `workspace_ids` = union des périmètres des projets `active` de l'appelant.
- Union vide et non-unrestricted ⇒ `[]` (aucune ligne) ⇒ `200` + collection vide.
- `get_allowed_lz_ids` conservé (retourne `None` si unrestricted, sinon `lz_ids`) pour limiter le diff des ~20 routes (D3).

## Audit

Chaque décision (validation projet/extension, approbation adhésion, changement de rôle) écrit une ligne `dcm_audit_log` (FR-020).
