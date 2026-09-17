# Contract: vues de liste warehouse sur les fenêtres glissantes

Routes concernées, préfixe `/api/v1/databricks/compute` :

| Route | Table gold lue après T002 |
|---|---|
| `GET /warehouses/overview` | `gold_dbx_compute_warehouse_cost_rolling` + `..._query_performance_rolling` + `..._recommendations` + `dim_dbx_workspace` |
| `GET /warehouses/cost` | `gold_dbx_compute_warehouse_cost_rolling` |
| `GET /warehouses/query-performance` | `gold_dbx_compute_warehouse_query_performance_rolling` |

**Inchangées** : `GET /warehouses/slow-queries` (lit `warehouse_slow_queries`),
`GET /warehouses/{id}` et `GET /warehouses/{id}/cost-trend` (détail et série temporelle,
grain quotidien assumé).

## Paramètre ajouté

| Paramètre | Type | Défaut | Comportement |
|---|---|---|---|
| `window_days` | `1 \| 7 \| 30 \| 90` | `1` | `IntEnum`, pas `Query(enum=…)` : une valeur hors liste est rejetée en **422**, pas ramenée à une autre fenêtre |

Pourquoi un `IntEnum` : `Query(enum=[…])` ne décore que le schéma OpenAPI. `window_days=5`
serait accepté, ajouterait `window_days = 5` au `WHERE`, et rendrait une page vide sans
erreur — un contrat qui mentirait silencieusement. Un `Literal[1, 7, 30, 90]` ne convient
pas non plus : il refuse la chaîne `"7"` que le navigateur envoie.

`period_start`/`period_end` restent **acceptés** mais sont ignorés par ces 3 routes : la
fenêtre est portée par le gold « as of » `as_of_date` (cf. [research.md](./research.md) R3).

## Bloc `window`

Présent à la racine des 3 réponses, forme identique à celle des clusters :

```json
{
  "window": { "window_days": 7, "from_date": "2026-08-31", "to_date": "2026-09-06" }
}
```

Quand la fenêtre demandée n'a aucune ligne dans le périmètre autorisé, `from_date` et
`to_date` valent `null` — et non les bornes calculées depuis `today` : il n'y a rien à
couvrir, l'IHM doit le dire.

## `GET /warehouses/overview`

```json
{
  "kpis": {
    "total_cost_usd": 12345.67,
    "cost_delta_pct": -4.2,
    "active_warehouses": 128,
    "query_count": 998877,
    "failed_count": 421,
    "open_recommendations": 9
  },
  "items": [
    {
      "cloud_provider": "azure",
      "source_lz_id": null,
      "workspace_id": "1234567890",
      "warehouse_id": "abc123def456",
      "warehouse_name": "wh-analytics-prod",
      "warehouse_size": "MEDIUM",
      "cost_usd": 421.5,
      "query_count": 18422,
      "failure_rate_pct": 0.8,
      "latency_p95_ms": 4210.0
    }
  ],
  "total": 128,
  "page": 1,
  "page_size": 25,
  "window": { "window_days": 7, "from_date": "2026-08-31", "to_date": "2026-09-06" }
}
```

- `cost_delta_pct` des KPI compare la fenêtre à la **fenêtre précédente de même longueur**,
  via `cost_usd_prev_window` déjà agrégé en gold — plus d'appel `_previous_period` avec une
  seconde requête, la comparaison est lue et non recalculée (P12).
- Le tri reste allowlisté (`_OVERVIEW_SORT_COLUMNS`), avec `warehouse_id` en clé de
  départage finale : sans clé unique terminale, deux warehouses de même coût peuvent
  s'échanger entre deux requêtes `LIMIT/OFFSET`, l'un apparaissant deux fois et l'autre
  jamais.
- La population change de « facturé le jour d'ancrage » à « coût non nul sur la fenêtre » :
  équivalente à `window_days = 1`, plus large à 7/30/90.

## `GET /warehouses/cost`

```json
{
  "items": [
    {
      "cloud_provider": "azure",
      "source_lz_id": null,
      "workspace_id": "1234567890",
      "warehouse_id": "abc123def456",
      "warehouse_name": "wh-analytics-prod",
      "warehouse_size": "MEDIUM",
      "dbu_quantity": 812.4,
      "cost_usd": 421.5,
      "cost_usd_prev_window": 439.9,
      "cost_delta_pct": -4.2,
      "query_count": 18422,
      "cost_per_query_usd": 0.0229,
      "top_consumer": "user@example.com",
      "as_of_date": "2026-09-06",
      "window_start": "2026-08-31"
    }
  ],
  "total": 128, "page": 1, "page_size": 25,
  "window": { "window_days": 7, "from_date": "2026-08-31", "to_date": "2026-09-06" }
}
```

Rupture assumée : `cost_usd_prev_day` → `cost_usd_prev_window`, `period_start` →
`as_of_date` + `window_start`.

`cost_usd_prev_window` est `null` — jamais `0` — quand la fenêtre précédente n'existe pas
(cf. [data-model.md](./data-model.md) §2), et `cost_delta_pct` est alors `null` aussi.

## `GET /warehouses/query-performance`

```json
{
  "items": [
    {
      "cloud_provider": "azure",
      "source_lz_id": null,
      "workspace_id": "1234567890",
      "warehouse_id": "abc123def456",
      "warehouse_name": "wh-analytics-prod",
      "query_count": 18422,
      "failed_count": 148,
      "failure_rate_pct": 0.8,
      "latency_p50_ms": 320.0,
      "latency_p95_ms": 4210.0,
      "latency_p99_ms": 18400.0,
      "queue_time_avg_ms": 42.0,
      "queue_time_p95_ms": 610.0,
      "spill_query_count": 12,
      "cache_hit_pct": 61.4,
      "bytes_scanned": 918273645,
      "rows_scanned": 44556677,
      "top_slow_statement_id": "01ef…",
      "as_of_date": "2026-09-06",
      "window_start": "2026-08-31"
    }
  ],
  "total": 214, "page": 1, "page_size": 25,
  "window": { "window_days": 7, "from_date": "2026-08-31", "to_date": "2026-09-06" }
}
```

`warehouse_name` est **le seul champ ajouté** ici, et c'est celui qui rend
`<WarehouseCell name={null} …>` obsolète côté front.

Les percentiles de la table `*_rolling` sont recalculés en gold depuis les histogrammes
quotidiens sommés — pas une moyenne de percentiles quotidiens, qui n'aurait aucun sens.
L'API les lit tels quels.

## Typage des nombres

Tous les champs numériques traversent `_json_safe` (`compute_metrics_common.py`), qui
convertit `Decimal` en `float`. Sans lui, Pydantic v2 sérialise un `Decimal` en **chaîne**
JSON — défaut trouvé et corrigé en vérifiant 022 T002, dont la conséquence était un
`TypeError` sur `toFixed` côté front. Toute colonne numérique nouvellement exposée doit
passer par ce point unique.
