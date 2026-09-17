# Contract — Exposition API/UI du filtre `include_deleted`

**Feature**: 027-usage-table-deleted-flag (US2) | **Porteur d'implémentation**: feature [024-usage-tracking-governance](../../024-usage-tracking-governance/spec.md), branche `dataeng/024-usage-tracking-governance`

> **Statut** : contrat figé, **implémenté par 024, pas par 027**. Le code applicatif concerné (21 endpoints `/api/v1/uc-usage/*` et les pages `UsageTablesUc` / `UsageGovernance`) vit sur la branche 024 et n'est pas encore sur `develop`. Le modifier depuis 027 provoquerait un conflit de fusion frontal pour aucun gain (cf. [research.md §R7](../research.md)).
>
> **Ordre d'exécution** : 027 merge sur `develop` → 024 se resynchronise (`git merge origin/develop`) → 024 ajoute le filtre avant sa PR.
>
> La route `/api/v1/data-product-usage` présente sur `develop` lit `gold_data_product_usage`, table héritée qui n'est plus produite : **hors périmètre**, aucun changement.

---

## Point d'accroche côté 024

Les services 024 déclarent déjà `GOLD_TABLE_CATALOG = "gold_dbx_usage_table_catalog"` dans `app/api/services/uc_usage_common.py`. Le filtrage se fait par jointure sur cette table, déjà lue — aucune nouvelle dépendance de données.

```sql
LEFT JOIN gold_dbx_usage_table_catalog c
       ON c.cloud_provider = f.cloud_provider
      AND c.catalog = f.catalog AND c.schema = f.schema AND c.table_name = f.table_name
WHERE COALESCE(c.is_deleted, false) = false   -- si include_deleted absent ou false
```

`COALESCE` obligatoire : une clé de fait absente du registre ne doit pas être filtrée silencieusement.

---

## Paramètre de requête

| Nom | Type | Défaut |
|---|---|---|
| `include_deleted` | `boolean` | `false` |

### Endpoints concernés (grain portant une clé table)

`/overview` · `/tables` · `/tables/{table_full_name}/top-consumers` · `/details` · `/charts/tables` · `/charts/finops` · `/charts/writes` · `/charts/cost-changes` · `/finops/kpis` · `/finops/cost-by-table` · `/finops/trends` · `/attention` · `/recommendations` · `/recommendations/charts` · `/governance/kpis` · `/governance/charts` · `/governance/registry` · `/filters/options`

### Endpoints exempts (grain consommateur, aucune clé table à filtrer)

`/consumers` · `/charts/consumers`. Le paramètre y est ignoré s'il est fourni.

### Sémantique

| Valeur | Comportement |
|---|---|
| absent ou `false` | Les tables dont `is_deleted = true` sont exclues : des listes, des KPI, des tendances, des classements, des totaux de pagination, des graphiques et des prévisions. |
| `true` | Les tables supprimées sont incluses, accompagnées de leurs champs de cycle de vie. |

**Règle de cohérence (FR-008)** : le filtre s'applique **avant** toute agrégation. Un total, un `popularity_rank` ou un « X sur N » calculé avec `include_deleted=false` ne doit jamais compter une table supprimée.

**Cas `/recommendations`** : le filtre ne porte que sur les lignes `object_type = 'DATA_PRODUCT'`. Les lignes `CONSUMER` restent visibles — elles ne portent pas de clé table (exclusion déjà actée en 024).

---

## Champs de réponse ajoutés

Sur toute ressource dont le grain porte une clé table :

| Champ | Type JSON | Nullable | Description |
|---|---|---|---|
| `is_deleted` | `boolean` | non | `true` si la table n'existe plus au catalogue |
| `deleted_at` | `string` (ISO 8601) | oui | Horodatage de la suppression constatée, `null` si non supprimée |
| `lifecycle_state` | `string` | non | `ACTIVE` \| `DELETED` \| `UNKNOWN` |

Ces champs sont **toujours** présents, y compris avec `include_deleted=false` (où `is_deleted` vaut alors systématiquement `false`) : un champ présent conditionnellement force le client à du branchement défensif.

Modèles Pydantic : `Field(description=...)` obligatoire (P3 — les descriptions alimentent OpenAPI).

---

## Compatibilité (P15)

Ajout **non cassant** : nouveau paramètre optionnel avec défaut, nouveaux champs de réponse additifs.

Le défaut `false` modifie le contenu des réponses par rapport à une implémentation qui ignorerait le drapeau — mais 024 n'étant pas encore en production, aucun consommateur n'est cassé. D'où l'intérêt de l'intégrer avant la PR 024 plutôt qu'en correctif ensuite.

---

## Attentes frontend (pages `UsageTablesUc` et `UsageGovernance` de 024)

| Exigence | Détail |
|---|---|
| Défaut | Tables supprimées masquées, sans action de l'utilisateur |
| Commande | Un contrôle explicite « Inclure les tables supprimées » dans le bloc de filtres des deux pages |
| Marquage visuel | Une table supprimée affichée porte un indicateur explicite et sa date de suppression |
| Cohérence de parcours | Le choix reste appliqué lors de la navigation entre les vues d'une même page |
| Réactivité | Le basculement met à jour les données sans rechargement manuel — `include_deleted` doit entrer dans la clé TanStack Query (`hooks/query-keys.ts`) |
| Conventions | Client API central, hook TanStack Query, route déclarée dans `app-routes.ts`, tests Vitest à réseau mocké, aucun `any` (P16) |

---

## Critères d'acceptation vérifiables

1. `GET /api/v1/uc-usage/tables` sans `include_deleted` ne retourne aucun élément avec `is_deleted = true`.
2. Le même appel avec `include_deleted=true` retourne les tables supprimées, `deleted_at` renseigné.
3. Le total de pagination varie entre les deux appels exactement du nombre de tables supprimées du périmètre.
4. Les KPI de `/overview` et de `/governance/kpis` calculés sans `include_deleted` excluent les tables supprimées.
5. `/recommendations` sans `include_deleted` ne retourne aucune ligne `DATA_PRODUCT` ciblant une table supprimée, et retourne toujours les lignes `CONSUMER`.
6. Le schéma OpenAPI documente `include_deleted` et les trois champs de réponse.
