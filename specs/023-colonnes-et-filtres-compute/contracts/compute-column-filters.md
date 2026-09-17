# Contract: filtres par colonne et valeurs distinctes

Les 5 pages du périmètre portent **11 tableaux** `ComputeDataTable` et **109 colonnes**.
Les 11 tableaux sont **tous** paginés côté serveur (vérifié : `page` / `page_size` sur les
11 routes) — donc aucun ne peut se contenter d'un filtre côté client
(cf. [research.md](./research.md) R4).

| Vue (`view`) | Route | Page front |
|---|---|---|
| `clusters-overview` | `GET /compute/clusters/overview` | `ComputeClusters` |
| `clusters-cost` | `GET /compute/clusters/cost` | `ComputeClusters` |
| `clusters-efficiency` | `GET /compute/clusters/efficiency` | `ComputeClusters` |
| `clusters-governance` | `GET /compute/clusters/governance` | `ComputeClusters` |
| `warehouses-overview` | `GET /compute/warehouses/overview` | `ComputeSqlWarehouses` |
| `warehouses-cost` | `GET /compute/warehouses/cost` | `ComputeSqlWarehouses` |
| `warehouses-query-performance` | `GET /compute/warehouses/query-performance` | `ComputeSqlWarehouses` |
| `warehouses-slow-queries` | `GET /compute/warehouses/slow-queries` | `ComputeSqlWarehouses` |
| `recommendations` | `GET /compute/recommendations` | `recommendations-table` |
| `lakeflow-jobs` | `GET /lakeflow/jobs` | `LakeflowJobs` |
| `lakeflow-job-runs` | `GET /lakeflow/jobs/{id}/runs` | `LakeflowJobDetail` |

## 1. Paramètre de filtre sur les routes de liste

Ajouté aux 11 routes :

| Paramètre | Type | Répétable | Forme |
|---|---|---|---|
| `column_filter` | `str` | **oui** (`list[str]`) | `<clé de colonne>:<valeur>` |

```
GET /compute/warehouses/overview?window_days=7
    &column_filter=workspace:1234567890
    &column_filter=size:MEDIUM
    &column_filter=failure:1
```

Règles :

1. Découpage sur le **premier** `:` seulement — un nom de warehouse ou de job peut en
   contenir, une clé de colonne jamais.
2. La clé est validée contre l'allowlist **de la vue** ; inconnue → **422** avec la liste
   des clés acceptées. Elle n'atteint jamais le SQL en texte libre.
3. La valeur part toujours en paramètre lié `?`.
4. Plusieurs `column_filter` se combinent en `AND`. Deux occurrences de la **même** clé →
   **422** : cette itération est mono-valeur par colonne, et accepter silencieusement la
   dernière ferait disparaître un filtre que l'utilisateur croit actif.
5. Une valeur vide (`workspace:`) équivaut à l'absence de filtre — c'est ce qu'envoie une
   combo qu'on vient de vider.
6. Un changement de filtre **ramène à la page 1**, côté appelant : sinon l'`offset` tombe
   au-delà du nouveau total et la page est vide sans raison visible.

### Paramètres historiques conservés

`search`, `warehouse_size`, `min_failure_rate_pct`, `utilization_status`,
`min_latency_p95_ms`, `has_spill`, `severity`, `status`, `category` continuent d'être
acceptés et **se normalisent vers la même liste de filtres interne** que `column_filter`
(décision R6). Conséquences contractuelles :

- `warehouse_size=MEDIUM` et `column_filter=size:MEDIUM` produisent le même `WHERE` et le
  même total ;
- fournir les deux avec la **même** valeur est accepté (idempotent) ;
- fournir les deux avec des valeurs **différentes** → **422**, jamais un « le dernier
  gagne » silencieux.

## 2. Endpoint de valeurs distinctes

```
GET /api/v1/databricks/compute/filter-options
    ?view=<vue>&column=<clé>[&q=<terme>][&limit=<n>]
    + les paramètres de scope de la vue (source_lz_ids, workspace_ids, cloud_provider…)
    + window_days pour les vues à fenêtre glissante
```

Réponse :

```json
{
  "view": "warehouses-overview",
  "column": "workspace",
  "kind": "enum",
  "label": "Workspace",
  "options": [
    { "value": "1234567890", "label": "prod-analytics", "count": 42 },
    { "value": "9876543210", "label": "dev-sandbox", "count": 7 }
  ],
  "truncated": false
}
```

| Champ | Sens |
|---|---|
| `kind` | `enum` \| `text` \| `numeric` — dicte le comportement de la combo |
| `options[].value` | ce que l'IHM renvoie tel quel dans `column_filter` |
| `options[].label` | ce qu'elle affiche (`workspace_name` plutôt qu'un id) |
| `options[].count` | lignes du périmètre portant la valeur ; **absent** pour `numeric` |
| `truncated` | `true` = le `LIMIT` a coupé, l'IHM affiche « affinez la recherche » |

Contraintes :

- `limit` par défaut **50**, plafond **200**. Le parc dev compte 1 824 warehouses : une
  liste déroulante n'a pas à transporter le parc entier.
- `kind = "text"` avec une cardinalité au-delà du `limit` : `q` devient **obligatoire**,
  réponse `options: []` + `truncated: true` sans `q` — plutôt qu'un échantillon arbitraire
  de 50 noms dont l'utilisateur ne saurait pas qu'il est arbitraire.
- `kind = "numeric"` : `options` sont les **seuils déclarés côté serveur**, sans `count`.
  Le serveur seul sait quelle expression SQL le seuil applique ; l'IHM ne les invente ni
  ne les interpole (P9).
- Le calcul applique **exactement** les mêmes filtres de scope que la vue (périmètre
  autorisé, `cloud_provider`, `window_days`) et **aucun** `column_filter` : les valeurs
  proposées décrivent le périmètre, pas la sélection en cours — sinon poser un filtre
  viderait les listes des autres colonnes.
- `view` ou `column` inconnus → **422**.

## 3. Allowlist par vue

`—` = colonne non filtrable, et pourquoi.

### `clusters-overview`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `workspace` | `enum` | `COALESCE(ws.workspace_name, c.workspace_id)`, valeur = `workspace_id` |
| `cluster` | `text` | `COALESCE(c.cluster_name, c.cluster_id)` |
| `cluster_type` | `enum` | `c.cluster_type` |
| `cost` | `numeric` | `c.cost_usd >= ?` — 1, 10, 100, 1 000 $ |
| `utilization` | `numeric` | `e.cpu_avg_pct >= ?` — 10, 25, 50, 75 % |
| `governance` | `enum` | `g.severity` |
| `cost_prev`, `cluster_lifetime`, `cluster_lifetime_prev` | — | valeurs de comparaison ; filtrer sur un passé sans filtrer le présent n'a pas d'usage identifié |

### `clusters-cost`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `workspace` | `enum` | idem |
| `cluster` | `text` | idem |
| `cluster_type` | `enum` | `cluster_type` |
| `sku_group` | `enum` | `sku_group` |
| `cost` | `numeric` | `cost_usd >= ?` — 1, 10, 100, 1 000 $ |
| `dbu` | `numeric` | `dbu_quantity >= ?` — 10, 100, 1 000 |
| `cost_prev`, `dbu_cost` | — | comparaison / ratio dérivé |

### `clusters-efficiency`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `workspace` | `enum` | idem |
| `cluster` | `text` | idem |
| `cluster_type` | `enum` | `cluster_type` |
| `driver_node`, `worker_node`, `recommended_node` | `enum` | types de nœuds |
| `autoscaling` | `enum` | `autoscale_enabled` → `Enabled` / `Fixed` |
| `status` | `enum` | `utilization_status` — **alias** de `utilization_status` |
| `nodes` | `numeric` | `worker_count >= ?` — 1, 2, 8, 32 |
| `cluster_lifetime` | `numeric` | `uptime_hours >= ?` — 1, 8, 24, 168 h |
| `idle` | `numeric` | `idle_pct >= ?` — 25, 50, 75, 90 % |
| `cpu_avg`, `cpu_p95`, `mem_avg`, `mem_p95` | `numeric` | `>= ?` — 10, 25, 50, 75, 90 % |
| `estimated_savings` | `numeric` | `estimated_savings_usd >= ?` — 1, 10, 100 $ |
| `cluster_lifetime_prev`, `idle_prev` | — | comparaison |

### `clusters-governance`

| Clé | Kind | Expression |
|---|---|---|
| `cluster` | `text` | `COALESCE(cluster_name, cluster_id)` |
| `owner_tag` | `enum` | `owner_tag`, avec une option explicite « (aucun) » pour `NULL` |
| `cost_center_tag` | `enum` | idem |
| `dbr` | `enum` | `dbr_version` |
| `severity` | `enum` | `severity` — **alias** de `severity` |
| `action` | — | rendu de bouton, pas une donnée |

### `warehouses-overview`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `workspace` | `enum` | `COALESCE(ws.workspace_name, c.workspace_id)` |
| `warehouse` | `text` | `COALESCE(c.warehouse_name, c.warehouse_id)` — **alias** de `search` |
| `size` | `enum` | `c.warehouse_size` — **alias** de `warehouse_size` |
| `cost` | `numeric` | `c.cost_usd >= ?` — 1, 10, 100, 1 000 $ |
| `queries` | `numeric` | `c.query_count >= ?` — 1, 100, 1 000, 10 000 |
| `failure` | `numeric` | `p.failure_rate_pct >= ?` — 1, 5, 10, 25 % — **alias** de `min_failure_rate_pct` |
| `latency` | `numeric` | `p.latency_p95_ms >= ?` — 1 000, 5 000, 30 000 ms |

### `warehouses-cost`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `warehouse` | `text` | **alias** de `search` |
| `size` | `enum` | **alias** de `warehouse_size` |
| `dbu` | `numeric` | `dbu_quantity >= ?` — 10, 100, 1 000 |
| `cost` | `numeric` | `cost_usd >= ?` — 1, 10, 100, 1 000 $ |
| `queries` | `numeric` | `query_count >= ?` |
| `cost_per_query` | `numeric` | `cost_per_query_usd >= ?` — 0,01, 0,1, 1 $ |
| `delta` | — | `Δ vs prev window`, dérivé ; filtrer sur le delta demanderait un signe et un seuil, hors périmètre mono-valeur |

### `warehouses-query-performance`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `warehouse` | `text` | `COALESCE(warehouse_name, warehouse_id)` — **disponible seulement après T001** |
| `queries` | `numeric` | `query_count >= ?` |
| `failure` | `numeric` | **alias** de `min_failure_rate_pct` |
| `p50`, `p95`, `p99` | `numeric` | `latency_p{50,95,99}_ms >= ?` — 1 000, 5 000, 30 000 ms ; `p95` est l'**alias** de `min_latency_p95_ms` |
| `queue` | `numeric` | `queue_time_p95_ms >= ?` — 100, 1 000, 10 000 ms |
| `spill` | `enum` | `spill_query_count > 0` → `Avec spill` / `Sans spill` — **alias** de `has_spill` |
| `cache` | `numeric` | `cache_hit_pct >= ?` — 25, 50, 75 % |

### `warehouses-slow-queries`

| Clé | Kind | Expression |
|---|---|---|
| `warehouse` | `text` | `COALESCE(warehouse_name, warehouse_id)` |
| `user` | `enum` | `executed_by` |
| `status` | `enum` | `execution_status` |
| `reason` | `enum` | `slow_reason` |
| `duration` | `numeric` | `duration_ms >= ?` — 30 s, 5 min, 30 min |
| `statement`, `start`, `error`, `open` | — | id opaque, horodatage (couvert par la période), texte d'erreur libre, lien |

### `recommendations`

| Clé | Kind | Expression |
|---|---|---|
| `object` | `text` | `COALESCE(object_name, object_id)` |
| `category` | `enum` | `category` — **alias** de `category` |
| `severity` | `enum` | `severity` — **alias** de `severity` |
| `status` | `enum` | `status` — **alias** de `status` |
| `savings` | `numeric` | `estimated_savings_usd >= ?` — 1, 10, 100, 1 000 $ |
| `title` | `text` | `title` |
| `since` | — | horodatage, couvert par la période |

### `lakeflow-jobs`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `status` | `enum` | dernier état du job |
| `alpha` | `text` | nom du job — **alias** de `search` |
| `trigger` | `enum` | type de déclencheur |
| `run_type` | `enum` | type de run |
| `runs` | `numeric` | `run_count >= ?` — 1, 10, 100 |
| `success`, `success_24h`, `success_7d` | `numeric` | taux de succès **`<= ?`** — 99, 95, 90, 50 % : sur un taux de succès l'intérêt est le seuil **bas** (« montre-moi ce qui échoue »), et c'est le serveur qui porte ce sens |
| `p50`, `p95`, `p99`, `duration`, `last_duration` | `numeric` | `>= ?` — 1 min, 10 min, 1 h |
| `wait` | `numeric` | attente `>= ?` — 10 s, 1 min, 10 min |
| `retries` | `numeric` | `retry_count >= ?` — 1, 3, 10 |
| `history`, `last_run` | — | sparkline, horodatages |

`success*` en `<=` est la seule exception au prédicat `>=` des `numeric` : elle est
**déclarée dans l'allowlist**, pas dans l'IHM, et c'est précisément ce que le champ `sql`
du descripteur permet.

### `lakeflow-job-runs`

| Clé | Kind | Expression / seuils |
|---|---|---|
| `status` | `enum` | état du run |
| `run_type` | `enum` | type de run |
| `trigger` | `enum` | déclencheur |
| `duration` | `numeric` | `>= ?` — 1 min, 10 min, 1 h |
| `lag` | `numeric` | retard `>= ?` — 1 min, 10 min, 1 h |
| `retries` | `numeric` | `>= ?` — 1, 3, 10 |
| `tasks` | `numeric` | nombre de tâches `>= ?` — 1, 5, 20 |
| `run_id`, `start_time`, `end_time`, `error`, `actions` | — | id, horodatages, texte libre, boutons |

## 4. Récapitulatif

| Vue | Colonnes | Filtrables |
|---|---|---|
| `clusters-overview` | 9 | 6 |
| `clusters-cost` | 8 | 6 |
| `clusters-efficiency` | 18 | 16 |
| `clusters-governance` | 6 | 5 |
| `warehouses-overview` | 7 | 7 |
| `warehouses-cost` | 7 | 6 |
| `warehouses-query-performance` | 9 | 9 |
| `warehouses-slow-queries` | 9 | 5 |
| `recommendations` | 7 | 6 |
| `lakeflow-jobs` | 17 | 15 |
| `lakeflow-job-runs` | 12 | 7 |
| **Total** | **109** | **88** |

Les 21 colonnes sans filtre sont, sans exception, des **rendus** (bouton, lien, sparkline),
des **identifiants opaques**, des **horodatages** déjà couverts par le sélecteur de période,
ou des **valeurs de comparaison** au passé. Aucune colonne portant une donnée
discriminante n'est laissée sans filtre.

### Inventaire confronté au code — vérifié le 2026-09-07

Cet inventaire est le point d'entrée de T004 et de T006 : s'il dérive du code, les deux tasks
construisent une allowlist qui ne correspond à aucune colonne affichée. Confrontation faite
après que T005 a déclaré les 109 largeurs, dans les deux sens :

| Contrôle | Résultat |
|---|---|
| `id` de colonne déclarés dans les 5 fichiers | **109** — identique au récapitulatif |
| Clé au contrat absente du code | **aucune**, sur les 11 vues |
| `id` du code absent du contrat | **aucun**, sur les 11 vues |
| Total filtrables recompté en parsant les 11 tables ci-dessus | **88** — identique au récapitulatif |

**Ce que la confrontation a mis en évidence, et qui contraint l'implémentation de T004 :**
7 clés se répètent entre onglets de `ComputeClusters.tsx` (`workspace`, `cluster`,
`cluster_type`, `cost`, `cost_prev`, `cluster_lifetime`, `cluster_lifetime_prev`) et 5 entre
onglets de `ComputeSqlWarehouses.tsx` (`warehouse`, `size`, `cost`, `queries`, `failure`).
Ce ne sont pas des doublons : le même nom porte une **expression SQL différente** selon la vue
— `cost` vaut `c.cost_usd` sur `clusters-overview` (jointure) et `cost_usd` sur `clusters-cost`
(table de coût). `FILTERABLE_COLUMNS` doit donc être indexée par **(vue, colonne)** et jamais
par colonne seule : un index global ferait résoudre `cost` par la dernière vue enregistrée,
et le `WHERE` porterait sur une table absente de la requête — erreur SQL, ou pire, un filtre
qui s'applique à la mauvaise colonne. C'est aussi la raison pour laquelle T005 sépare les
largeurs par `tableId`.
