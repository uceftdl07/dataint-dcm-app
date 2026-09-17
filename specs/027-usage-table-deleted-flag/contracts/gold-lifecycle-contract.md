# Contract — Colonnes gold de cycle de vie (`is_deleted`)

**Feature**: 027-usage-table-deleted-flag | **Statut**: ajout rétro-compatible (P14/P15 — bump mineur)

Contrat de données consommé par le backend (feature 024), le builder de forecast et le moteur de recommandations.

---

## `gold_dbx_usage_table_catalog`

| Colonne | Type | Nullable | Valeurs | Commentaire Unity Catalog attendu |
|---|---|---|---|---|
| `lifecycle_state` | `STRING` | non | `ACTIVE`, `DELETED`, `UNKNOWN` | État de cycle de vie au catalogue. ACTIVE : présente dans `system.information_schema.tables`. DELETED : absente du référentiel ET dernière opération d'audit = `deleteTable`. UNKNOWN : absente du référentiel sans preuve de suppression (privilège manquant ou périmètre non collecté) — traitée comme non supprimée. |
| `is_deleted` | `BOOLEAN` | **non** | `true`, `false` | Raccourci de `lifecycle_state = 'DELETED'`. Jamais NULL : `UNKNOWN` vaut `false`, pour qu'un `WHERE NOT is_deleted` ne filtre jamais silencieusement. |
| `deleted_at` | `TIMESTAMP` | oui | — | Horodatage de l'événement `deleteTable` retenu. NULL dès que `is_deleted = false`. |

### Garanties

1. **Non-suppression de lignes** — une ligne écrite n'est jamais retirée de la table. Un état `DELETED` établi survit à la sortie de l'événement d'audit de sa fenêtre de rétention.
2. **Réversibilité** — une table recréée sous le même nom qualifié repasse à `ACTIVE` / `is_deleted = false` / `deleted_at = NULL` au run suivant.
3. **Idempotence** — deux runs consécutifs sans changement au catalogue produisent un état identique (P6).
4. **Colonnes de registre NULL** — pour une ligne `DELETED` jamais vue au référentiel, `table_type`, `owner`, `domain`, `cost_center`, `classification`, `created_at`, `created_by`, `last_altered_at` sont NULL. `is_data_product` reste `false` (non-NULL).

---

## `gold_dbx_usage_table_governance`

| Colonne | Type | Nullable | Source |
|---|---|---|---|
| `lifecycle_state` | `STRING` | non | recopiée de `table_catalog` |
| `is_deleted` | `BOOLEAN` | non | recopiée de `table_catalog` |
| `deleted_at` | `TIMESTAMP` | oui | recopiée de `table_catalog` |

### Changement de comportement (rétro-compatible sur le schéma, visible sur les valeurs)

| Colonne | Avant | Après |
|---|---|---|
| `recommended_action` | calculée pour toute table | `NULL` si `is_deleted = true` |
| `severity` | calculée pour toute table | `NULL` si `is_deleted = true` |

Les mesures brutes (`days_since_last_read`, `is_unused`, `is_orphan`, `is_stale_but_consumed`, `downstream_fanout`, `is_critical`) restent calculées sans condition.

---

## `gold_dbx_usage_forecast_daily`

Schéma **inchangé**. Garantie ajoutée :

> Aucune ligne n'est produite pour un `object_id` (nom qualifié `catalog.schema.table_name`) dont la clé correspondante porte `is_deleted = true` dans `gold_dbx_usage_table_catalog` — ni à l'horizon futur, ni par densification de l'historique d'apprentissage.

Les lignes d'horizon **passé** déjà écrites (piste d'audit prévision vs réel) ne sont pas supprimées rétroactivement.

---

## `gold_dbx_usage_recommendations`

Schéma **inchangé**. Garantie ajoutée :

> Aucune ligne `status = 'OPEN'` avec `object_type = 'DATA_PRODUCT'` ne cible une table dont `is_deleted = true`. Les lignes `OPEN` préexistantes transitionnent en `RESOLVED` au run suivant via le mécanisme d'état existant.

Les lignes `object_type = 'CONSUMER'` (règle FINOPS) ne sont pas filtrées : leur grain ne porte pas de clé table.

---

## Tables de fait — contrat de non-changement

`gold_dbx_usage_table_daily`, `gold_dbx_usage_table_popularity_daily`, `gold_dbx_usage_consumer_daily`, `gold_dbx_usage_table_query_performance_daily` :

> Aucune colonne ajoutée, aucune ligne retirée. L'historique d'usage d'une table supprimée reste intégralement présent. Le filtrage incombe au consommateur, par jointure sur `gold_dbx_usage_table_catalog` (cf. clé de jointure canonique dans [data-model.md](../data-model.md)).

**Interdiction explicite** : ne pas dénormaliser `is_deleted` sur ces tables — l'écriture MERGE incrémentale (3 jours glissants) laisserait la valeur figée sur l'historique antérieur.
