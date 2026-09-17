# API Contract — `/api/v1/uc-usage`

Contrat des endpoints exposés par la Story Backend (T001) et consommés par la Story
Frontend (T002). Types des entités : voir [data-model.md](../data-model.md).

## Conventions communes

**Préfixe** : `/api/v1/uc-usage`, tag `uc-usage`, monté depuis
`packages/dcm-backend/app/main.py` selon le pattern `include_router(...)` existant.

**Sécurité** : routeur déclaré avec `dependencies=[Depends(require_unrestricted_scope)]`
(D3 de [research.md](../research.md)). Aucun paramètre de scope LZ/workspace/cloud n'est
accepté — les tables sources n'en portent pas.

**Paramètres communs**

| Paramètre | Type | Obligatoire | Note |
|---|---|---|---|
| `period_start`, `period_end` | `date` (ISO) | **oui** (endpoints datés) | 422 si absent ou `start > end` |
| `catalog` | `str` | non | |
| `schema` | `str` | non | |
| `tables` | `str[]` (répétable) | non | `table_full_name` complets |
| `page` | `int >= 1` | non | défaut 1 — endpoints de liste |
| `page_size` | `int` 1..200 | non | défaut 25 — endpoints de liste |

**Enveloppe de liste**

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 25,
  "period": { "start": "2026-08-11", "end": "2026-09-10" }
}
```

`period` n'est présent que sur les endpoints de liste **datés** (`/tables`,
`/consumers`) : il répète la période reçue, il ne la fabrique pas. Les endpoints de
liste **snapshot** (`/governance/registry`, `/recommendations`) renvoient la même
enveloppe **sans la clé** `period` — ils ne reçoivent aucune période et leurs tables
sources n'en portent pas (cf. « Endpoints snapshot » ci-dessous). Le type frontend est
donc `period?: Period`.

**Codes de retour**

| Code | Cas |
|---|---|
| 200 | succès, y compris période sans données (`items: []`, `total: 0`) |
| 401 / 403 | non authentifié / scope restreint (`require_unrestricted_scope`) |
| 422 | `period_*` absent ou incohérent, `page_size` hors bornes, valeur d'enum inconnue |
| 503 | table gold absente — `{"status":"degraded","table":"…","code":"<table>_missing","error":"…"}` (D6) |

**Endpoints snapshot** (`/governance/kpis`, `/governance/registry`, `/recommendations`,
`/attention`, `/filters/options`) :
`period_*` n'est pas requis — les tables `table_governance` / `table_catalog` /
`recommendations` n'ont pas de `period_start`. Côté UI ils attendent néanmoins un
périmètre et un clic sur **Appliquer**, comme les endpoints datés ; seul
`/filters/options` est émis au chargement des pages, pour peupler le sélecteur de
périmètre (FR-017, amendé le 2026-09-15). `/attention` n'a plus d'appelant du tout, cf.
sa section.

`recommendations` porte bien `first_seen_date` / `last_seen_date`, mais ces colonnes ne
bornent **pas** la liste : une anomalie `OPEN` depuis six mois est précisément celle qu'il
faut traiter, la filtrer par période la masquerait. Même règle que
`compute_metrics_recommendations.py`, où les lignes `OPEN` restent visibles quelle que
soit la période du bandeau.

---

## Page « Usage des tables UC »

### `GET /overview`

FR-001. Params : période (**requise**), `catalog`, `schema`, `tables`.
Retourne `UsageOverview` : les 6 KPI, `trends` (3 séries `ForecastSeries` à 7 points au
plus), `written_bytes_series` (observé, `NULL` préservés) et `attention` (3 items —
**non consommé** par l'UI depuis le retrait du bloc « Points d'attention », cf. FR-001).

Règles vérifiables : `unused_tables` ignore la période ; une métrique sans ligne de
forecast est **absente** de `trends`, jamais présente à zéro.

### `GET /tables`

FR-002 à FR-004. Params communs + `search` (str), `sort` ∈
`popularity` (défaut) | `cost` | `latency` | `failure_rate`.
Retourne une page de `TableUsageRow`.

Règles vérifiables : tri par défaut `request_count` desc ; `latency_p95_ms` est interpolé
sur les compteurs de `latency_bucket_counts` additionnés sur la période (jamais un `AVG`
ni un `MAX` des P95 quotidiens) ; `failure_rate_pct` recalculé par
`SUM(failed)/SUM(total)`.

### `GET /tables/{table_full_name}/top-consumers`

FR-004, FR-008(spec draft). Params : période. **Non paginé**, `LIMIT 5` en dur.
Retourne `{ "items": TopConsumerRow[], "period": {...} }`.

Règle : `consumer_type` est un vocabulaire ouvert — une valeur inconnue est renvoyée
telle quelle.

### `GET /consumers`

FR-005. Params communs + `search`, `consumer_type` (str libre, pas d'enum fermée),
`sort` ∈ `cost` (défaut) | `requests` | `distinct_tables`.
Retourne une page de `ConsumerUsageRow`.

Règles : `rank` recalculé sur `SUM(estimated_cost_usd)` de la période (`consumer_rank`
n'est jamais lu) ; `distinct_tables` recalculé par `COUNT(DISTINCT table_full_name)` ;
le filtre `tables` s'applique par **intersection** (consommateur ayant lu au moins une
des tables sélectionnées).

### `GET /finops/kpis`

FR-006. Params communs. Retourne `FinopsKpis`.

Règle : `avg_cost_per_request_usd` est accompagné de `"is_lower_bound": true`
(dénominateur `request_count` trop large, `costed_request_count` non exposé au grain
popularité).

### `GET /finops/cost-by-table`

FR-006. Params communs + `search` (sur `table_full_name`), `sort` ∈ `cost` (défaut) |
`cost_per_request` | `requests` | `read_bytes` | `forecast` | `table_name`, `direction`,
`column_filter` (mêmes opérateurs que `/tables` et `/consumers`).
Retourne une page de `CostByTableRow`.

Règles : `forecast_cost_usd_7d` vaut `null` pour une table sans ligne de forecast — jamais
`0`. `cost_per_request_usd` et `forecast_cost_usd_7d` sont calculés **en SQL**, ce qui les
rend triables et filtrables comme les colonnes agrégées ; `total` est compté sur l'ensemble
filtré, sinon la pagination annoncerait des pages vides. Les 6 colonnes affichées sont
exactement l'allowlist `COST_BY_TABLE_COLUMNS` — une colonne hors liste rend `422`.

### `GET /finops/trends`

Params : `catalog`, `schema`, `tables`, `metrics[]` ⊂ `request_count`,
`distinct_consumers`, `estimated_cost_usd`, `data_read_bytes`.
Retourne `{ "series": ForecastSeries[] }`. **Pas de paramètre d'horizon** : l'API borne
`horizon_date` à `[aujourd'hui, aujourd'hui + 7j[`, ce que la table produit à chaque run.
Sans cette borne haute, « +7d » désignerait tout le futur laissé en table par les runs
précédents.

`observed` s'arrête à la **veille** : le jour en cours n'est chargé que partiellement, et
le tracer donnerait à lire un effondrement là où il n'y a qu'une journée inachevée. La
prévision reprend donc exactement là où le réalisé s'arrête, sans trou ni date en double.
La série porte **un point par jour calendaire** de la période, `null` pour un jour sans
mesure — jamais `0`, et jamais un jour omis (une table lue 3 jours sur 30 se lirait sinon
comme une activité continue).

`distinct_consumers` est **sommée sur les tables** du périmètre, côté réalisé comme côté
prévision : elle compte les couples `(consommateur, table)` actifs, pas les consommateurs.
Le compte de têtes est le KPI `distinct_consumers` de `/overview`, calculé en
`COUNT(DISTINCT consumer_id)` (facteur ~80 entre les deux, mesuré en dev).

La somme d'un périmètre est un **minorant** : le pipeline ne publie pas la projection d'une
série trop courte ni celle d'un modèle divergent (garde-fous de la branche
`dataeng/026-usage-forecast-guards`).

C'est cet endpoint, et non le bloc `trends` de `/overview`, que l'UI lit pour les 3
cartes de tendance : il n'exige pas de période, donc les cartes s'affichent dès
l'ouverture de la page. `overview.trends` porte les mêmes séries et reste servi pour
qu'un consommateur d'API obtienne la vue d'ensemble en un seul appel.

### `GET /filters/options`

Alimente les sélecteurs catalogue / schéma / table(s) des deux pages. **Snapshot**, lu
sur `table_catalog` : les vues paginent côté serveur, les valeurs proposables ne peuvent
donc pas être déduites des lignes affichées.

Params : `catalog`, `schema`, `search`, `limit`.
Retourne `{ "catalogs": str[], "schemas": str[], "tables": FilterTableOption[],
"truncated": bool, "limit": int }` — `truncated` à `true` invite le sélecteur à chercher
plutôt qu'à dérouler.

### `GET /attention`

Params communs + `limit` (défaut 3, max 10). Retourne
`{ "items": Recommendation[] }` — `status='OPEN'`, tri `severity` desc.

**Aucun appelant frontend** depuis le retrait du bloc « Points d'attention » sur demande
utilisateur (FR-001, amendé le 2026-09-15). L'endpoint et ses tests pytest restent en
place ; à supprimer explicitement s'il ne doit pas resservir.

---

## Page « Gouvernance & Recommandations »

### `GET /governance/kpis`

FR-012. Params : `catalog`, `schema`, `tables` (**pas de période** — snapshot).
Retourne `GovernanceKpis` : `unused_tables`, `stale_but_consumed_tables`,
`critical_tables`.

### `GET /governance/registry`

FR-012. Params : `catalog`, `schema`, `tables`, `search`, `page`, `page_size`,
`sort` ∈ `severity` (défaut) | `table_name` | `fanout`.
Retourne une page de `GovernanceRegistryRow`.

Règles : `owner` est `null` (jamais `""`) quand le tag UC est absent ; `last_operation`
est un vocabulaire fermé à 3 valeurs ; `severity` est en minuscules ; le statut UI se
dérive de `recommended_action`, pas d'un texte libre.

### `GET /recommendations`

FR-011, FR-013, FR-014. Params : `catalog`, `schema`, `tables`, `category`, `severity`,
`object_type`, `page`, `page_size`.
Retourne une page de `Recommendation` + un bloc de comptages
`{"open_high": n, "open_medium": n, "open_total": n}`.

Règles : `status='OPEN'` forcé, aucune déduplication par `(object_id, category)` ; le
filtre catalogue/table ne s'applique qu'aux lignes `object_type='DATA_PRODUCT'` (jointure
sur `table_catalog`), les lignes `CONSUMER` restant visibles ;
`estimated_savings_usd` est `null` hors LIFECYCLE « inutilisée » ; `severity` est en
majuscules.

**Pas de `PATCH /recommendations/{id}/status`** — hors scope (le pipeline réécrit
`status` à chaque run).

---

## Matrice endpoint → source gold

| Endpoint | Tables lues |
|---|---|
| `/overview` | `table_daily`, `table_popularity_daily`, `table_query_performance_daily`, `table_governance`, `forecast_daily`, `recommendations` |
| `/tables` | `table_catalog`, `table_popularity_daily`, `table_query_performance_daily`, `table_daily` |
| `/tables/{…}/top-consumers` | `table_daily` |
| `/consumers` | `consumer_daily`, `table_daily` |
| `/finops/kpis`, `/finops/cost-by-table` | `table_popularity_daily`, `table_daily`, `forecast_daily` |
| `/finops/trends` | `forecast_daily` |
| `/filters/options` | `table_catalog` |
| `/attention`, `/recommendations` | `recommendations`, `table_catalog` |
| `/governance/kpis`, `/governance/registry` | `table_governance`, `table_catalog` |
