# T007 — « All-purpose clusters » + lecture Lifetime/Utilization sur Jobs & Pipelines

**Domain**: frontend (+ backend, 2 routes)
**Package**: packages/dcm-frontend, packages/dcm-backend
**Branch**: `frontend/024-nav-compute-3-onglets-all-purpose-jobs` — **pas de dispatch**, tasks
enchaînées sur la branche existante (consigne utilisateur du 2026-09-09)
**Jira**: aucune clé — task non dispatchée
**Depends on**: T004 (tables `*_efficiency_rolling`), T006 (pages à 3 sous-onglets)
**Work type**: feature

## Description

Amendement du 2026-09-09, formulé après revue de l'IHM livrée par T006. Trois demandes :

1. L'onglet « Clusters » s'appelle **All-purpose clusters** (la page ne liste plus que ce
   `cluster_type` depuis T001a) et sa colonne **Cluster type** disparaît — elle répète
   désormais la même valeur sur chaque ligne, donc n'informe plus.
2. Sur **Jobs** et **Pipelines DLT**, la colonne `Δ vs prev window` s'appelle **Prev cost**.
3. Ces deux pages gagnent **Lifetime**, **Prev lifetime** et **Utilization**, et perdent
   **DBU** sur leur sous-onglet Overview.

Périmètre tranché avec l'utilisateur : **calqué sur l'All-purpose**. Concrètement l'Overview
de Jobs/Pipelines lit exactement comme celui des all-purpose (coût, coût précédent, uptime
cumulé, uptime précédent, verdict de sizing), et le sous-onglet **Cost** ne prend que le
renommage — il **garde DBU**, qui est sa lecture de facturation. `Utilization` est le badge
`utilization_status` (Optimal / Overprovisioned / Underprovisioned, « — » si non mesuré), pas
un calcul côté IHM.

Conséquence backend : les **2 routes overview** (job, pipeline) doivent servir l'uptime et le
verdict, qui vivent dans les tables d'efficacité — d'où une jointure. Les routes `cost` et
`efficiency` ne changent pas.

## Files to create/modify

- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_jobs.py` — `LEFT JOIN` de
  `gold_dbx_compute_job_efficiency_rolling` sur la requête de lignes de l'overview
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_pipelines.py` — idem au grain
  `dlt_pipeline_id`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py` — `_billed_only`
  sur `overview` et `cost` (ni `efficiency` ni `governance`)
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_jobs.py`, `…_pipelines.py`,
  `test_compute_metrics_services.py` (les fetchers de clusters y sont testés)
- UPDATE `src/config/navigation.ts` — libellé et titre « All-purpose clusters »
- UPDATE `src/pages/ComputeClusters.tsx` — suppression des 3 colonnes `cluster_type`, du
  helper `clusterTypeBadge`, de la clé de tri correspondante ; titre de page
- UPDATE `src/types/api.ts` — `ComputeJobsOverviewItem` / `ComputePipelinesOverviewItem`
- UPDATE `src/pages/ComputeJobs.tsx`, `src/pages/ComputePipelines.tsx` — colonnes Overview
- UPDATE `src/test/fixtures/compute-jobs.ts`, `compute-pipelines.ts`
- UPDATE `src/pages/ComputeClusters.test.tsx`, `ComputeJobs.test.tsx`, `ComputePipelines.test.tsx`

## Sub-tasks

- [x] **Backend d'abord** : `LEFT JOIN` (jamais `INNER`) sur l'efficacité, clé
      `(cloud_provider, workspace_id, <grain>, window_days)`. Un grain facturé sans mesure
      **reste listé**, avec `null` sur les 3 champs.
- [x] Garde de fraîcheur **par table** : chaque snapshot a son propre
      `as_of_date = (SELECT MAX(as_of_date) …)`. Épingler l'un sur l'autre viderait les
      colonnes d'utilisation le jour où les deux rollups divergent d'une journée.
- [x] Colonnes **qualifiées** dans la requête jointe (`j.` / `p.` / `e.`) : `job_name`,
      `window_start`, `as_of_date`… existent des deux côtés. `_sort_clause` et
      `_search_clause` prennent donc un `prefix`.
- [x] `uptime_hours_delta_pct` dérivé côté service via `_uptime_delta_pct` (helper existant),
      pas recalculé dans l'IHM.
- [x] Tests backend : présence du `LEFT JOIN` et absence d'`INNER JOIN`, `window_days` dans la
      clé, les 2 gardes de fraîcheur, dérivation 46,8 / 41,0 → +14,1 %, et un grain non mesuré
      qui reste listé.
- [x] Tests frontend : en-têtes exactes des 2 Overview, `not.toContain('DBU')`, ligne mesurée
      (`1d 22h 48m`, `1d 17h`, `+14.1%`, `Optimal`), ligne non mesurée = 4 « — » et aucun
      `NaN` ; en-têtes du Cost avec `Prev cost` **et** `DBU` ; 3 listes d'en-têtes de
      `ComputeClusters` sans `Type`.
- [x] Vérification sur donnée dev réelle des 2 routes overview (voir « Vérification »).
- [x] **`Lifetime` (Overview) = `Uptime` (Efficiency)**, même grain, même fenêtre : vérifié sur
      les 4 fenêtres et les 2 familles en dev (0 divergence), fixtures alignées, et un test par
      page lit la valeur sur les 2 onglets et compare.
- [x] **Ne lister que les grains facturés, sur les 3 familles** — Pipelines, Jobs, all-purpose
      Clusters (`_billed_only`, décision utilisateur du 2026-09-09, étendue de proche en proche).
      Sur chaque famille, `cost` et `overview` filtrent sur
      `COALESCE(cost_usd, 0) > 0 OR COALESCE(dbu_quantity, 0) > 0` ; `efficiency` **non**, et
      `governance` **non** côté clusters. Le bloc `kpis` reste calculé sur le snapshot complet :
      son sens ne change pas.
- [x] Portes : `pytest`, `ruff check`, `tsc --noEmit`, `eslint`, `vitest run`, `npm run build`.
- [ ] Vérification navigateur (mutualisée avec celle de T006, même écran).

## Notes

- **DBU reste dans le payload** de l'overview (`dbu_quantity`) alors que la colonne disparaît :
  d'autres lecteurs de la route s'en servent, et retirer une clé servie est un changement de
  contrat pour un gain nul.
- La jointure ne change ni la population ni le tri : elle ajoute 3 colonnes de lecture. Les
  totaux servis restent ceux du rollup de coût — vérifié en dev (voir ci-dessous).
- `Lifetime` est un **uptime cumulé** sur la fenêtre (heures de cluster additionnées), pas la
  durée de vie d'un cluster : au grain job/pipeline le cluster meurt avec le run. Le libellé
  est celui demandé, et il est aligné sur l'All-purpose où la colonne porte déjà ce nom.

## Écarts constatés

- **Le signal couleur du delta disparaît** sur les 2 Overview. L'ancienne colonne
  `Δ vs prev window` utilisait un `DeltaCell` rouge/vert ; `Prev cost` affiche la valeur
  précédente en chiffre principal et le delta en petit dessous, sans couleur — c'est le rendu
  de l'All-purpose, donc le prix du « calqué sur l'All-purpose ». `DeltaCell` a été supprimé
  des 2 pages (plus aucun appelant).
- **Trois surfaces disent encore « Clusters »** et n'ont pas été touchées, hors périmètre
  demandé : `src/pages/Dashboard.tsx` (carte de raccourci), `src/pages/DatabricksComingSoon.tsx`
  et `src/components/tour/tour-steps.ts`. À renommer si le libellé doit être global.
- **Fixtures d'overview alignées sur celles d'efficacité** (2026-09-09, après revue) : elles
  portaient un uptime différent de celui de l'onglet Efficiency pour le **même** grain
  (job `job-1042` : 46,8 h contre 41,5 h ; pipeline `dlt-7781` : 46,8 h contre 63,25 h). Or les
  deux onglets lisent la même colonne du même snapshot : la fixture énonçait un état que le
  backend ne peut pas produire. Les 4 champs joints de la ligne mesurée sont désormais des
  copies de la fixture d'efficacité, et un test par page lit la valeur sur les 2 onglets et
  compare (`cellsByHeader`).
- **Couverture de l'efficacité DLT, visible directement dans la colonne `Lifetime`** : sur
  l'Overview Pipelines, trié par coût, seules **7 à 12 des 100 premières lignes** portent un
  uptime. Décomposition des **6 062** lignes servies (fenêtre 30 j, `as_of` 2026-09-09) :

  | Forme de la ligne | Lignes | Coût | `Lifetime` renseigné |
  |---|---|---|---|
  | Compute classique (facturation avec `cluster_id`) | 181 | 1 902,89 $ | **174** (96 %) |
  | Serverless (facturation sans `cluster_id`) | 2 936 | 21 685,84 $ | 0 — impossible |
  | Aucune facturation dans la fenêtre (0 $ / 0 DBU) | 2 945 | 0,00 $ | 0 — rien à mesurer |

  Ce n'est **pas** la jointure (0 divergence mesurée dans les deux sens, 4 fenêtres) ni une
  perte de mapping T004b : `uptime_hours` vient de `node_timeline`, qui n'échantillonne que des
  clusters classiques, et un pipeline serverless n'a pas de cluster. Là où la mesure peut
  exister elle est là (174/181, résidu de 7 pipelines à moins de 0,55 $). Côté jobs la
  couverture est franche : 100/100 lignes de la page portent un uptime.

  Deux constats qui dépassent cette task : **97 % du DLT facturé en dev est serverless** (et
  92 % du coût), et **3 097 des 6 062 lignes coûtent exactement 0 $** — massivement des vues
  matérialisées (`MV-…vw_appropriation_cd`), chacune avec son propre `dlt_pipeline_id`. Elles
  gonflent le compteur du footer autant qu'elles vident les colonnes. Le second point a été
  tranché ici (voir ci-dessous) ; restent ouverts : distinguer serverless de classique par un
  drapeau en gold pour que « — » soit expliqué (T001c), ou ingérer
  `system.lakeflow.pipeline_update_timeline` pour donner une durée d'update aux serverless
  (T004b — ce serait une **autre** métrique que l'uptime de cluster, à nommer comme telle).
- **La population servie par les 4 routes de liste a changé** — les 2 Pipelines et les 2 Jobs
  (choix utilisateur : « filtrer les lignes à 0 $ », puis « fais pareil pour job »). Les grains
  dont le coût **et** les DBU sont nuls sur la fenêtre ne sont plus listés : à 30 j,
  **6 062 → 2 965** pipelines et **6 759 → 4 896** jobs. C'est un changement volontaire de
  contrat de lecture, pas un effet de bord — le compteur du footer cessait d'être un compteur de
  grains actifs.
  - Le test porte **aussi sur les DBU**, et pas seulement sur le coût : un grain qui a consommé
    sans être facturé (crédits, SKU gratuit) a bien tourné, l'exclure masquerait du compute
    réel. En dev le cas est vide aujourd'hui (`active_*` = `total` aux 4 fenêtres et sur les 2
    familles), mais la règle reste la bonne.
  - **Effet secondaire recherché** : les cartes KPI `active_pipelines` / `active_jobs` comptaient
    déjà `cost_usd > 0`. Elles et le footer affichaient donc deux nombres différents pour la même
    liste (pipelines : 1 546 contre 2 028 à 1 j ; jobs : 982 contre 1 701). Ils coïncident
    maintenant.
  - `efficiency` **n'est filtrée dans aucune des 2 familles** : sa table n'a ni `cost_usd` ni
    `dbu_quantity` (le filtre y jetterait une `UNRESOLVED_COLUMN`), et un grain mesuré doit
    rester visible sur cet onglet même si la fenêtre ne lui a rien facturé. Un test par famille
    verrouille l'absence des deux colonnes dans ce SQL.
  - Le helper est **dupliqué** dans les 3 services (`_billed_only`) plutôt que factorisé : c'est
    la convention déjà en place pour `_sort_clause` et `_search_clause`, qui existent aussi en
    plusieurs copies parce que les colonnes de grain et les alias diffèrent (`p.` / `j.` / `c.`).
  - **Les warehouses ne sont pas filtrés** : hors demande.
- **Étendu aux all-purpose clusters** (demande du 2026-09-09, après les jobs) : `overview` et
  `cost` filtrent, `efficiency` et **`governance` non**. Ce dernier point est un choix, pas un
  oubli : la gouvernance existe pour montrer ce que personne ne surveille — un cluster zombie ou
  inutilisé est *exactement* la ligne qu'un filtre sur le coût cacherait. Un test paramétré le
  verrouille sur les 2 onglets.
  - `cost_rank` **n'est pas renuméroté**. Il vient de gold et porte déjà des ex æquo et des
    trous : à 1 j, 185 lignes all-purpose dans le snapshot, 94 facturées, rangs de 1 à 95 pour
    93 valeurs distinctes. Le filtre retire donc des lignes qui n'avaient pas de rang à perdre,
    et l'onglet Cost s'ouvre toujours sur 1, 2, 3…
  - Mécanique différente des 2 autres familles : les clusters passent par `_overview_filters` /
    `column_filter_predicates` (liste de prédicats + params). `_billed_only()` est inséré en
    **tête** de cette liste ; comme il ne porte aucun paramètre lié, l'ordre des `?` restants
    est inchangé — c'est ce qui rend l'insertion sûre.
- **Aucun reformatage** des fichiers touchés : `ruff format` et `prettier` signalent une dérive
  sur ces fichiers **déjà présente sur `HEAD`** (mesurée fichier par fichier). Les portes
  réellement appliquées ici sont `ruff check` / `eslint` / `tsc` / les tests. La dérive
  introduite par cette task a été ramenée à zéro (mesure identique working copy vs `HEAD`).

## Vérification

Backend :

| Porte | Résultat |
|-------|----------|
| `uv run pytest` sur les 3 fichiers de tests touchés | **237 passés** |
| `uv run pytest` (suite complète) | **680 passés, 1 échec** — `test_connection.py::test_connect_timeout_has_actionable_message`, **antérieur à la task** : `packages/dcm-backend/.env` pose `DCM_DATABRICKS_HTTP_PATH`, que le `Settings(...)` explicite du test ne surcharge pas. Vérifié en stashant les modifications backend : échoue à l'identique |
| `ruff check` sur les 4 fichiers backend | propre |

Contrat servi, **donnée dev réelle** (TestClient sur l'app, entrepôt dev, GET en lecture seule) :

- `jobs/overview` : les 4 clés `uptime_hours`, `uptime_hours_prev_window`,
  `uptime_hours_delta_pct`, `utilization_status` présentes ;
- **la jointure ne réduit pas la population** : `jobs/overview` = `jobs/cost` = **6 759**,
  `pipelines/overview` = `pipelines/cost` = **6 062** — mesuré **avant** `_billed_only`, venu
  après et qui ramène `cost` et `overview` au même total réduit dans chaque famille (4 896 jobs,
  2 965 pipelines à 30 j — voir plus bas) ;
- **pas de fan-out** : ids uniques sur la page servie (la clé de jointure porte `window_days`) ;
- un grain non mesuré porte `null` sur les 3 champs joints, **jamais `0`** — dont le cas dur
  connu, pipeline `05e63a07-be8b-4500-8c5b-8cc60d25f594`, facturé **941,47 $** sur 30 j ;
- `sort=name` et `search=` résolvent encore (colonnes qualifiées).

`Lifetime` vs `Uptime`, les deux sens, fenêtres 1 / 7 / 30 / 90 j :

| Contrôle | jobs | pipelines |
|---|---|---|
| Lignes d'Overview mesurées → même `uptime_hours` que `/efficiency` | 8/8 identiques au chiffre près | 2/2 |
| Lignes de `/efficiency` retrouvées sur `/overview` avec le même uptime | **0 divergence** sur les 4 fenêtres | **0 divergence** |
| Lignes de la page d'Overview portant un uptime | 100/100 | 7 à 12 /100 (résidu SC-005) |

Exemples : job `989642031100157` → 2 940,333333 h / 2 080,633385 h des deux côtés ; pipeline
`c6936f17-eaf8-4be5-9a34-ed785b14ce71` → 316,766667 h / 251,683322 h des deux côtés.

Filtre `_billed_only`, **donnée dev réelle** (les 4 fenêtres, les 2 familles, `page_size=100`,
première **et** dernière page — le tri `cost_desc` met les grains les moins chers en fin de
liste, c'est là qu'une fuite du filtre se verrait) :

| Fenêtre | Pipelines avant | après | Jobs avant | après | Lignes à 0 $ / 0 DBU servies |
|---|---|---|---|---|---|
| 1 j | 2 028 | **1 546** | 1 701 | **982** | 0 (p. 1 et dernière page, 2 familles) |
| 7 j | 2 501 | **2 135** | 3 309 | **2 375** | 0 |
| 30 j | 6 062 | **2 965** | 6 759 | **4 896** | 0 |
| 90 j | 12 983 | **10 264** | 6 759 | **6 759** | 0 |

- `cost` et `overview` servent le **même** `total` à chaque fenêtre et sur chaque famille (filtre
  appliqué identiquement, avec le préfixe `p.` / `j.` côté overview) ;
- `total` = KPI `active_pipelines` / `active_jobs` aux 4 fenêtres — le footer et la carte
  disent enfin la même chose. Le coût KPI est inchangé par construction : son agrégat ne porte
  pas le filtre, et une ligne à 0 $ ne pesait rien dans la somme (pipelines 30 j :
  23 588,73 $ ; jobs 30 j : 46 181,48 $) ;
- le grain le moins cher encore servi à 30 j est à **0,001455 $** (pipeline `MV-…`) et
  **0,000026 $** (job `woh-standard-monthfill-fix`) — le filtre coupe bien à zéro strict, pas à
  un seuil ;
- **à 90 j les jobs ne perdent aucune ligne** (6 759 → 6 759) : sur trois mois tout job connu du
  rollup a fini par être facturé. C'est le contrôle qui montre que le filtre suit la fenêtre et
  ne coupe pas une population fixe ;
- `search` résout encore et se combine au filtre (`bronze` → 17 pipelines, `ingest` → 69 jobs,
  identique sur les 2 routes de chaque famille), `sort=name` aussi (colonnes qualifiées).

All-purpose clusters, même protocole :

| Fenêtre | Overview | Cost | Efficiency (non filtré) | KPI `active` | KPI `zombie` | Coût |
|---|---|---|---|---|---|---|
| 1 j | **112** | **112** | 175 | 112 | 5 | 490,77 $ |
| 7 j | **243** | **243** | 274 | 243 | 18 | 11 164,94 $ |
| 30 j | **395** | **395** | 402 | 395 | 29 | 56 086,95 $ |
| 90 j | **704** | **704** | 548 | 704 | 50 | 157 223,19 $ |

`governance` = **7 149** lignes, jamais filtrée et sans fenêtre. Aucune ligne à 0 $ servie
(première et dernière page, 4 fenêtres), le cluster le moins cher encore listé est à 0,0001 $ à
90 j, et la première page de Cost affiche toujours les rangs 1 à 5.

### Pourquoi les onglets n'affichent pas le même nombre de lignes

Question posée le 2026-09-09. Trois causes distinctes, aucune n'étant un défaut de pagination :

1. **Overview et Cost lisent la même table** (`*_cost_rolling`) et portent désormais le même
   filtre : leurs totaux sont **égaux par construction**, vérifié sur les 3 familles et les 4
   fenêtres. S'ils divergent dans l'IHM, c'est l'état de recherche : chaque sous-onglet garde son
   propre champ (`search` / `costSearch` / `effSearch` dans `ComputeJobs.tsx`), donc un filtre
   saisi dans un onglet ne s'applique pas aux autres. Sur les clusters s'ajoute une différence de
   **portée** de la recherche, antérieure à cette task : l'Overview cherche dans 6 colonnes (nom,
   id, type, owner, nom et id de workspace), l'onglet Cost dans 2 (nom, id) — mesuré, `analytics`
   rend 1 ligne sur Overview et 0 sur Cost.
2. **Efficiency lit une autre table** (`*_efficiency_rolling`), alimentée par
   `system.compute.node_timeline` et conservée uniquement là où `uptime_hours > 0` (vérifié :
   100 % de ses lignes ont un uptime). Elle n'est pas filtrée sur le coût, donc ce n'est **pas**
   un sous-ensemble de Cost. Fenêtre 30 j :

   | Famille | Facturés (Overview/Cost) | Mesurés (Efficiency) | Facturés non mesurés | Mesurés non facturés |
   |---|---|---|---|---|
   | Jobs | 4 896 | 4 846 | 70 | 20 |
   | Pipelines DLT | 2 965 | 174 | **2 791** | 0 |
   | All-purpose | 395 | 402 | — | +7 |

   L'écart énorme du DLT est le serverless (pas de cluster à échantillonner) ; les petits écarts
   des jobs et des clusters vont dans les deux sens — un grain peut être mesuré sur la fenêtre et
   facturé juste en dehors, ou l'inverse.
3. **Governance n'a pas de fenêtre du tout** : c'est un instantané de l'état courant
   (7 149 lignes), sans rapport avec les 1/7/30/90 j des trois autres onglets.

Frontend (depuis `packages/dcm-frontend`) :

| Porte | Résultat |
|-------|----------|
| `npx tsc --noEmit` | **101** erreurs = baseline, **0** dans un fichier de T007 |
| `npx eslint --max-warnings 0` sur les 10 fichiers touchés | **0** problème |
| `npx vitest run` | **389 passés / 4 échecs**, les 4 identiques à `origin/develop` |
| `ComputeJobs` + `ComputePipelines` + `ComputeClusters` | 59/59 |
| `npm run build` | OK (4,2 s) |
