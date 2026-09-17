# T004 — Pagination serveur des vues d'ensemble compute

**Domain**: backend + frontend
**Package**: packages/dcm-backend, packages/dcm-frontend
**Branch**: (aucune — correctif demandé sur la branche courante)
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T003
**Work type**: bugfix

## Description

Les onglets *Overview* des pages Cluster et SQL Warehouse ne montraient que **50** objets
alors que le parc en compte bien plus. La cause n'est pas un défaut d'affichage : les deux
services appliquaient `LIMIT 50` **sans `OFFSET`**, et le front paginait, cherchait et
triait ensuite ces 50 lignes dans le navigateur. Le défaut est donc plus large que « 50
lignes visibles » : un cluster classé 51ᵉ au coût était **introuvable par son nom**, et
trier sur `Lifetime` ne triait que les 50 plus chers.

Correctif : porter les deux vues d'ensemble sur le même schéma de pagination serveur que
l'onglet *Cost*, déjà correct — `search` / filtres / `sort` / `page` / `page_size` envoyés
à l'API, `COUNT(*) OVER()` pour le total, `LIMIT ? OFFSET ?` pour la page.

Le plafond n'a **pas** été relevé : à `window_days=90` la table rolling contient
≈1,4 M lignes (mesuré : 9 899 / 98 474 / 422 968 / 1 378 333 lignes d'overview pour
1 / 7 / 30 / 90 jours, et 1 824 warehouses distincts). Aucune valeur de `LIMIT` ne rend un
filtre navigateur correct.

## Files to create/modify

- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_warehouses.py`
- UPDATE `packages/dcm-backend/app/api/routes/compute_metrics.py`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_services.py`
- UPDATE `packages/dcm-frontend/src/types/api.ts` (`total`, `page`, `page_size`)
- UPDATE `packages/dcm-frontend/src/api/dcmApiClient.ts` (params des 2 overviews)
- UPDATE `packages/dcm-frontend/src/hooks/query-keys.ts`
- UPDATE `packages/dcm-frontend/src/hooks/useComputeClustersQueries.ts`
- UPDATE `packages/dcm-frontend/src/hooks/useComputeWarehousesQueries.ts`
- CREATE `packages/dcm-frontend/src/lib/compute/server-pagination.ts`
- UPDATE `packages/dcm-frontend/src/pages/ComputeClusters.tsx` + `.test.tsx`
- UPDATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.tsx` + `.test.tsx`
- UPDATE `packages/dcm-frontend/src/test/fixtures/compute-clusters.ts`,
  `compute-warehouses.ts`

## Sub-tasks

- [x] Supprimer `_OVERVIEW_ITEMS_LIMIT = 50` des deux services.
- [x] `fetch_clusters_overview` / `fetch_warehouses_overview` : `search`, filtres,
      `sort`, `sort_direction`, `page`, `page_size`, `COUNT(*) OVER() AS _total`,
      `LIMIT ? OFFSET ?`, `total` / `page` / `page_size` dans la réponse (y compris dans
      le payload vide du soft-fail).
- [x] `ORDER BY` **interpolé** dans le SQL → passe par une allowlist par vue ; une clé
      inconnue retombe sur le coût. Testé en envoyant `cost_usd; DROP TABLE t` et
      `1; DELETE FROM t` : le texte injecté n'atteint jamais la requête.
- [x] `NULLS LAST` dans les deux sens : le tri navigateur classait une valeur absente à
      `-Infinity`, donc en **première** page en tri croissant.
- [x] Départage final unique (`cluster_id` / `warehouse_id`) : sans lui, deux lignes de
      même coût peuvent s'échanger entre deux requêtes `LIMIT/OFFSET`, donc le même objet
      apparaît en page 2 **et** 3 tandis qu'un autre n'apparaît jamais.
- [x] Recherche warehouse sur le **nom de workspace** préservée (elle passait par
      `resolveWithId(...).label` côté navigateur) : `dim_dbx_workspace` joint en SQL et
      `ws.workspace_name` rendu cherchable **sans être sélectionné** — aucun changement de
      payload, aucun changement de rendu.
- [x] Sémantique du filtre « avec échecs » reproduite telle quelle :
      `COALESCE(p.failure_rate_pct, 0) >= ?`, un warehouse sans ligne de performance étant
      lu comme 0 par le filtre navigateur qu'il remplace.
- [x] Front : suppression des passes `filtered*` / `sorted*` et de `useClientPagination`
      sur ces deux tables, remplacées par `serverPaginationProps` — une table paginée
      serveur ne peut pas réutiliser `useClientPagination`, qui redécouperait la page et
      annoncerait « 25 sur 25 ».
- [x] Retour en page 1 à chaque changement de plage, de filtre, de recherche ou de tri :
      la page est découpée serveur, une requête plus étroite peut laisser la page 7 vide.
- [x] La table reste montée quand le serveur ne renvoie rien alors qu'un filtre est actif :
      sa barre d'outils porte le champ de recherche qu'il faut atteindre pour élargir.
- [x] `fetch_warehouses_overview` n'avait **aucun** test : 3 ajoutés.
- [x] Gates : `pytest`, `ruff`, `tsc`, `vitest`, `vite build`.

## Acceptance Criteria

- [x] Les deux vues d'ensemble exposent `total` / `page` / `page_size` et servent la page
      demandée via `LIMIT ? OFFSET ?`.
- [x] Le pied de table annonce le total de la portée filtrée, pas le nombre de lignes
      renvoyées.
- [x] Recherche, filtres et tri portent sur **toute** la fenêtre : un objet au-delà de la
      première page est atteignable par son nom.
- [x] Une clé de tri hors allowlist ne modifie pas le SQL et retombe sur le coût.
- [x] Une recherche sans résultat laisse le champ de recherche accessible.

## Tests

```bash
cd packages/dcm-backend && uv run pytest tests/test_compute_metrics_services.py tests/test_compute_metrics_routes.py -q
cd packages/dcm-frontend && npx vitest run src/pages/ComputeClusters.test.tsx src/pages/ComputeSqlWarehouses.test.tsx
```

## Out of scope

- Les onglets *Cost*, *Query performance* et *Slow queries*, déjà paginés serveur.
- La page `Clusters.tsx` héritée.

## Notes

- Avertissements Sonar S107 (nombre de paramètres) et S8410 (`Annotated`) sur les deux
  routes et services d'overview : **acceptés**, ils s'appliquent déjà mot pour mot à
  `list_clusters_cost` / `fetch_clusters_cost`, dont ce correctif reprend la forme.
- `_clamp_page` borne `page_size` à 200 ; les routes déclarent `Query(ge=1, le=200)`.
- Les services d'overview retombent sur un payload vide à la moindre exception DB
  (`… soft-fail`) : une clé manquante dans une ligne mockée rend donc une page vide
  silencieuse, pas une erreur — piège rencontré en test, d'où `_total` dans les fixtures.
