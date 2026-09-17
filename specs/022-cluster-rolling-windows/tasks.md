# Tasks: Pages Cluster sur les fenêtres glissantes `gold_dbx_compute_*_rolling`

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Work type**: feature · **Priority**: P2
**Mode**: `one_per_domain` — 3 stories, une par domaine avec ticket (dataeng, backend, frontend).
**Merge order**: [merge-strategy.md](./merge-strategy.md)

Chaque task est un index : le détail vit dans son sub-spec `stories/`.

- [x] T001 DataEng fenêtre précédente et autoscaling en gold → [stories/T001-fenetre-precedente-et-autoscaling-en.md](stories/T001-fenetre-precedente-et-autoscaling-en.md)
- [x] T002 Backend API clusters par fenêtre glissante → [stories/T002-api-clusters-par-fenetre-glissante.md](stories/T002-api-clusters-par-fenetre-glissante.md)
- [ ] T003 Frontend page Cluster par plage et tendances → [stories/T003-page-cluster-par-plage-et-tendances.md](stories/T003-page-cluster-par-plage-et-tendances.md)
- [ ] T004 [Backend] Pagination serveur des vues d'ensemble compute → [stories/T004-pagination-serveur-des-vues-densemble.md](stories/T004-pagination-serveur-des-vues-densemble.md)
- [ ] T005 [Frontend] Valeurs des indicateurs au survol des graphes → [stories/T005-valeurs-au-survol-des-graphes.md](stories/T005-valeurs-au-survol-des-graphes.md)
- [x] T006 [DataEng] Fenêtre incrémentale gold qui gèle le jour de queue → [stories/T006-fenetre-incrementale-gold-qui-gele.md](stories/T006-fenetre-incrementale-gold-qui-gele.md)

T004 et T005 sont deux correctifs demandés **après** la relecture de T003 ; ils ne
figuraient pas dans le découpage initial. T004 déborde de `dcm-frontend` (les deux
services backend d'overview) et T005 déborde du périmètre « pages Cluster » (tiroir
warehouse, `LakeflowOverview`) : les deux demandes portaient explicitement sur les pages
compute *et* warehouse, ce qui prime sur le « out of scope » de T003.

T004 touche deux packages, mais `dcm-parse-tasks.sh` n'attribue qu'**un** domaine par
task : le tag `[Backend]` nomme la cause racine (`LIMIT 50` sans `OFFSET` dans les deux
services) — la liste de fichiers de la story reste la référence pour le périmètre réel.

T006 n'est pas une demande : c'est un **défaut trouvé en vérifiant les volumes** des trois
tables `gold_dbx_compute_cluster_*_daily`. La fenêtre incrémentale gold ne recalculait
jamais un jour déjà écrit, donc figeait le jour de queue de chaque run au moment où la
source curated était la moins complète. Il est rattaché à cette feature parce qu'il fausse
directement les fenêtres glissantes qu'elle expose.

## Ordre imposé

```
T001 (gold) ──► déploiement dev + vérification ──► T002 (API) ──► T003 (UI)
```

Les trois tasks ne sont **pas** parallélisables : T002 lit les colonnes que T001 crée,
T003 consomme les champs que T002 expose. Démarrer T002 avant que les tables enrichies
soient peuplées en dev ferait passer ses tests sur des colonnes inexistantes.

## Dépendances externes

| Ce dont T001 dépend | État |
|---|---|
| `curated_dbx_compute_clusters.min_autoscale_workers` / `max_autoscale_workers` / `worker_count` / `cluster_name` | disponible, distribution mesurée ([research.md](./research.md) R2) |
| Droit de `DROP` + reconstruire les 2 tables gold efficiency en dev puis prod | requis avant T002 ([quickstart.md](./quickstart.md)) |

## État d'avancement (dispatch non exécuté — pas de Jira sur cette feature)

| Task | Code + tests | Vérification dev réelle |
|---|---|---|
| T001 | écrit, 34 tests pipeline verts | **vérifiée en dev** : backfill `full_refresh` run `436955739280464` `SUCCESS` en 167 min, puis les 5 contrôles d'acceptation de [quickstart.md](./quickstart.md) §4 tous verts |
| T002 | écrit, 82 tests backend verts (78 + 4 de régression) | **vérifiée en dev** : les 7 endpoints interrogés au niveau HTTP sur les 4 fenêtres contre la donnée réelle — 2 défauts trouvés et corrigés (ci-dessous) |
| T003 | écrit, 20 tests page + 7 tests graphe verts, `tsc`/`vitest`/`build` sans régression | reste à vérifier dans le navigateur contre l'API vérifiée |
| T004 | écrit, 89 tests backend compute + 8 tests page warehouse verts | reste à vérifier dans le navigateur (pagination au-delà de la page 1 sur la donnée réelle) |
| T005 | écrit, 10 tests graphes verts | reste à vérifier dans le navigateur (positionnement de l'encart au survol) |
| T006 | écrit, 446 tests pipeline verts | **vérifiée en dev** : run `360068623859212` (incrémental, sans `full_refresh`) `SUCCESS` en 25,4 min ; borne remontée au 2026-08-20 comme prédit, 2026-08-27 réparé de 2 242 → **9 107** cluster-jours et de 652 → **3 752 $**, fenêtres glissantes 30 j et 90 j remontées de ≈3 100 $ |

Le critère de sortie de T001 et T002 est « déployée **et vérifiée** en dev », pas
« implémentée » — d'où les cases cochées seulement maintenant.

### Ce que la vérification dev de T001 a établi

Contrôles [quickstart.md](./quickstart.md) §4, après le backfill :

| Contrôle | Avant backfill | Après |
|---|---|---|
| §4.2 `active_hours > uptime_hours` | 0 / 0 / 144 860 / 261 855 | **0 sur les 4 fenêtres** |
| §4.3 fenêtre précédente (SC-004), `w=7` et `w=30` | non joué | **`lost_value = phantom = mismatch = 0`** |
| §4.4 `uptime_hours_prev_window = 0` | non joué | **0 ligne** (P9 respecté) |
| §4.5 groupe `autoscale_enabled IS NULL` | 32 496 / 189 727 / 399 262 | **groupe disparu**, les 2 modes partitionnent le parc |
| §4.6 arithmétique des fenêtres + `cluster_name` | `cluster_name` partiel | **`bad_arith = 0`, `cluster_name` à 100 %** sur les 4 fenêtres |

### Les 2 défauts que la vérification de T002 a révélés

Aucun des deux n'était visible en test unitaire : ils ne se manifestent qu'avec le vrai
driver Databricks et la vraie sérialisation FastAPI.

1. **`Decimal` arrivait au navigateur en chaîne JSON.** Les routes annotent leur retour
   `-> dict[str, Any]`, que FastAPI utilise comme `response_model` : Pydantic v2 sérialise
   donc un `Decimal` en **string**. Les colonnes `P95_cpu_usage` / `P95_memory_usage`
   ajoutées par T003 auraient levé un `TypeError` (`formatPct` appelle `toFixed`), et
   `Lifetime` / `DBU` s'affichaient sans arrondi. Corrigé dans `_json_safe`
   (`compute_metrics_common.py`), le point de passage unique de tous les payloads compute —
   ce qui rend au passage vrais les types TS déjà déclarés. 2 tests de régression, dont un
   qui vérifie la sortie après passage par Pydantic.
2. **`cost_usd_prev_window` valait `0` et jamais `NULL`**, violant le critère P9 de T003.
   `cluster_cost_rolling` agrège la fenêtre précédente en `SUM(CASE … ELSE 0 END)` : la
   colonne n'est structurellement jamais `NULL`, donc « aucun prédécesseur » et « a coûté
   zéro » sont indiscernables. La même ligne affichait « Prev cost $0 » à côté de « Prev
   lifetime — » (l'efficience, elle, passe par un `LEFT JOIN`, R1). Corrigé par
   `_normalize_prev_cost`, qui aligne la valeur sur la conclusion que gold tire déjà pour le
   ratio (`NULLIF(cost_usd_prev_window, 0)` pour `cost_delta_pct`). Seuil `<= 0` et non
   `== 0` : même règle que le diviseur de `_pct_delta`, et un avoir rendrait le coût
   précédent négatif. 2 tests de régression.

Le front n'a eu besoin d'aucune modification : les deux corrections sont à la frontière
backend.
