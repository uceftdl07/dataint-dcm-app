# Tasks: Fenêtres glissantes SQL Warehouses, colonnes redimensionnables et filtres par colonne

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Work type**: feature · **Priority**: P2
**Mode**: `one_per_domain` — 3 stories de domaine (dataeng, backend, frontend), 6 tasks.
**Merge order**: [merge-strategy.md](./merge-strategy.md)

Chaque task est un index : le détail vit dans son sub-spec `stories/`.

- [x] T001 [DataEng] `warehouse_name` en gold sur utilisation et performance → [stories/T001-warehouse-name-en-gold.md](stories/T001-warehouse-name-en-gold.md)
- [x] T007 [DataEng] `curated_dbx_compute_warehouses` **et** `curated_dbx_lakeflow_jobs` en full load, **+ repli `run_name`** → [stories/T007-curated-warehouses-en-full-load.md](stories/T007-curated-warehouses-en-full-load.md)
- [x] T002 [Backend] API warehouse par fenêtre glissante → [stories/T002-api-warehouse-par-fenetre-glissante.md](stories/T002-api-warehouse-par-fenetre-glissante.md)
- [x] T003 [Frontend] Page SQL Warehouses par plage, nom et ordre → [stories/T003-page-warehouses-par-plage.md](stories/T003-page-warehouses-par-plage.md)
- [ ] T005 [Frontend] Largeurs de colonne fixes et redimensionnables → [stories/T005-largeurs-de-colonne.md](stories/T005-largeurs-de-colonne.md)
- [x] T004 [Backend] Filtres par colonne et valeurs distinctes → [stories/T004-filtres-par-colonne.md](stories/T004-filtres-par-colonne.md)
- [ ] T006 [Frontend] Combo de filtre dans l'en-tête de colonne → [stories/T006-combo-de-filtre-den-tete.md](stories/T006-combo-de-filtre-den-tete.md)

Les tasks sont listées dans l'**ordre d'exécution**, pas dans l'ordre des numéros : T005 est
écrite avant T004 parce qu'elle n'a aucune dépendance serveur et qu'elle conditionne T006.
La numérotation vient du Work Breakdown de la spec et n'a pas été réattribuée — la renuméroter
casserait les références croisées de `spec.md`, `plan.md` et `contracts/`.

T004 et T006 touchent **11 tableaux** et **109 colonnes**, pas les seules pages warehouse :
c'est le périmètre arbitré par le demandeur (« les 5 pages à colonnes »), inventorié dans
[contracts/compute-column-filters.md](./contracts/compute-column-filters.md).

## Ordre imposé

```
Fil A : T001 (gold) ──► T007 (curated) ──► déploiement dev + vérification ──► T002 (API) ──► T003 (UI)
Fil B :                                            T005 (largeurs) ──► T004 (API filtres) ──► T006 (UI filtres)
```

T007 s'est insérée **après** l'implémentation de T001, pas avant : c'est le contrôle
d'acceptation §4.2 joué en dev qui a révélé que le curated ne couvrait que 28 % du périmètre.
Le code de T001 n'est pas en cause et n'est pas à reprendre — il faut que sa source soit
complète pour que son résultat soit exploitable.

Le fil A n'est **pas** parallélisable : T002 lit la colonne que T001 crée, T003 consomme les
champs que T002 expose. Le critère de sortie de T001 et T002 est « déployée **et vérifiée**
en dev », pas « implémentée » — les deux défauts trouvés en 022 T002 étaient invisibles en
test unitaire.

T007 a par ailleurs **grandi en cours de route**, sur arbitrage explicite : en cherchant la
portée réelle du défaut de watermark, deux autres specs le portaient. Une seule en souffre
(`LAKEFLOW_JOBS_SPEC`, 29,8 % de `job_name` perdus), l'autre non (`COMPUTE_CLUSTERS_SPEC`,
100 % de résolution parce que ses clusters sont éphémères). Le mécanisme et les mesures sont en
[research.md](./research.md) R1ter ; `COMPUTE_CLUSTERS_SPEC` reste volontairement non corrigée.

T005 peut avancer pendant la vérification dev du fil A. Les deux fils ne partagent qu'un
fichier, `compute-data-table.tsx`, et seulement à partir de T005 : T003 ne modifie que les
déclarations de colonnes de sa page.

Le reste de T005 — les 6 contrôles de quickstart §5ter — demande un **navigateur**, donc une
passe humaine : ni les tests ni les gates ne peuvent établir qu'une largeur de départ est
*lisible*. Ce qui est automatisable l'est (les largeurs atterrissent sur `<colgroup>`, glisser
ne trie pas, `←`/`→`/`Home` agissent, la persistance survit au remontage, deux `tableId` ne se
mélangent pas : 14 tests dans `compute-data-table.test.tsx`). La case de T005 reste donc
décochée jusqu'à cette passe.

Même règle pour **T006** : tout ce qui est automatisable l'est (26 tests neufs — ouverture,
clavier, débounce, périmètre de la requête, liste tronquée, liste indisponible, retour page 1,
compte et effacement des filtres, synchronisation barre d'outils ↔ combo dans les deux sens), et
il ne reste qu'un critère à voir dans un navigateur : SC-003 depuis l'IHM. Les deux cases
décochées de la liste ci-dessus ne signalent donc **pas** du code à écrire, mais une passe
humaine à jouer une fois, sur les 6 contrôles de quickstart §5ter communs à T003, T005 et T006.

## Dépendances externes

| Ce dont T001 dépend | État |
|---|---|
| `curated_dbx_compute_warehouses.warehouse_name` | ✅ **résolu** : T007 (full load) a comblé la couverture, **plus** l'alignement de borne de T001 (R9c). Mesuré le 2026-09-07 : 0 warehouse du snapshot courant absent du curated |
| `MERGE WITH SCHEMA EVOLUTION` sur les 4 tables gold | suffisant : colonne nullable ajoutée, **aucun `DROP`**, aucun `full_refresh` requis (R2) — **confirmé en dev**, la colonne est apparue sur les 4 tables |

| Ce dont T002 dépend | État |
|---|---|
| Fenêtres 1/7/30/90 dans les 3 `warehouse_*_rolling` | **déjà peuplées** en dev — rien à calculer (R3) |
| `warehouse_name` sur `query_performance_rolling` | ✅ **vérifié en dev le 2026-09-07** : 100 % des lignes nommées sur les 4 fenêtres. T002 est débloquée |

| Ce dont T004 dépend | État |
|---|---|
| Pagination serveur sur les 11 vues | **vérifiée** : `page` / `page_size` sur les 11 routes |

## État d'avancement (dispatch non exécuté — pas de Jira sur cette feature)

| Task | Code + tests | Vérification dev réelle |
|---|---|---|
| T001 | ✅ 15 fichiers, 460 tests verts, ruff + mypy verts sur les fichiers touchés (périmètre étendu le 2026-09-07 : borne `change_time`, 3 builders + 3 tests) | ✅ **verte, les 5 contrôles §4** : §4.1 (colonne + commentaire ×4), §4.2 **SC-001 atteint** — `query_performance` 100 % ×4 fenêtres, `utilization` 97,7 / 99,1 / 99,1 / 99,2 %, §4.3, §4.4 (202/202/202), §4.5 (2 renommages tracés). Il a fallu **trois** causes distinctes, pas une : T007 (ingestion), la borne minuit (R9c), et un `full_refresh` **après** le correctif de borne (R9b) |
| T007 | ✅ `WAREHOUSES_SPEC` **et** `LAKEFLOW_JOBS_SPEC` en full load, **+ repli `run_name`** (2ᵉ extension arbitrée), 473 tests verts. Régression de gate assumée : **+3 erreurs mypy** dans `dlt_03_gold_layer.py` (l. 142 `no-untyped-def`, l. 170 `name-defined "spark"`, l. 619 `no-untyped-call`) — 3 classes que ce fichier porte déjà 6×/6×/9× et que le jumeau `_lakeflow_latest_jobs()` produit à l'identique ; ni `# type: ignore` ni `# noqa` ajouté. Ruff : **0** sur le fichier | ✅ **verte** : ingestion des 17 tables verte (run 140235606823863), curated **1429/1429** warehouses AWS, `job_name` **99,7403 %** (daily) / **97,9607 %** (rolling), `workflow_name` **99,94 %** (task_health), **99,80 %** (tasks), **83,21 %** (runs), **57,62 %** (success_rate). Résidu **100 % attribué** : 185 863 lignes, toutes `WORKFLOW_RUN`, sans nom dans aucune source — plafond assumé |
| T002 | ✅ 6 fichiers, helpers descendus dans `_common`, garde `as_of_date` opt-in, **+96 tests** (573 ajouts, 1 seule suppression dans les tests : les tests clusters passent inchangés). `ruff` : **0** sur les 6 fichiers. `pytest` : 440 passés, 1 échec **pré-existant et dépendant du poste** (`test_connection.py`, le `.env` local définit `DCM_DATABRICKS_HTTP_PATH`) | ✅ **verte, les 9 contrôles §5** — joués en **SQL généré par le service** et non en HTTP (`connection.py` n'offre que SPN-à-secret ou PAT, tous deux prohibés : quickstart §6.1). **32 statements, 32 SUCCEEDED.** `span_days` = 1/7/30/90 exactement, `warehouse_name` **100 %** ×4 fenêtres, `total` croissant 205 → 583 → 719 → 1020, garde `as_of_date` reconfirmée : **463 lignes au lieu de 205** sans elle, dont 258 périmées |
| T003 | ✅ 7 fichiers (3 hors liste prévue, tracés dans la story), chips + `window_days` dans la clé de cache, Workspace avant Warehouse, `warehouse_name` sur les 3 onglets, `Δ vs prev window`. **+8 tests → 16/16** sur `ComputeSqlWarehouses.test.tsx`, aucune régression de gate (cf. ci-dessous). 3 écarts assumés documentés : sélecteur de dates de l'en-tête *route-scoped* donc non retirable par onglet — **levé depuis**, retiré pour la route entière (cf. section dédiée) —, scission de type `*Snapshot` pour `/warehouses/{id}` qui reste quotidien, libellé `no data over this range`. **+ suite sur demande** : bloc de dates de l'en-tête retiré des 2 pages compute, chips propres à l'onglet Slow queries, bornes ancrées sur aujourd'hui, +9 tests (cf. section dédiée) | ⏳ reste la vérification navigateur (mutualisée avec les 6 contrôles §5ter de T005), **+ absence du bloc de dates et chips Slow queries à confirmer à l'écran** |
| T005 | ✅ échelle de largeurs + `<colgroup>` + poignées, 109 colonnes déclarées sur 11 tableaux, 35 nouveaux tests verts, aucune régression de gate (cf. ci-dessous). **+ suite après revue navigateur** : masquage du débordement et valeur complète au survol sur 5 fichiers, +3 tests nets (cf. section dédiée) | ⏳ reste les 6 contrôles navigateur de quickstart §5ter |
| T004 | ✅ 10 fichiers (2 hors liste prévue, tracés dans la story : `compute_metrics_recommendations.py` et le handler `ColumnFilterError` de `app/main.py`), allowlist de **88 colonnes sur 11 vues** (43 `numeric`, 34 `enum`, 11 `text`, 21 alias historiques), `column_filter` sur les 11 routes de liste + 2 routes `filter-options` jumelles, **+68 tests** (40 service, 28 route). `pytest` : **508 passés, 1 échec pré-existant** (`test_connection.py`, cf. T002). `ruff check app tests` : **156 = référence HEAD, delta 0** | ✅ **verte, les 9 contrôles §5bis — en HTTP réel** cette fois, via un remplaçant de pool qui exécute chaque statement sous le profil OAuth `dcm-dev` de la CLI (ni PAT ni secret SPN) : la vraie app FastAPI répond in-process, donc validation + routage + sérialisation + `exception_handler` sont couverts, ce que le substitut SQL de T002 laissait dehors. **9/9** (55 statements), **parité 26/26** (93 statements) — les 12 paires exploitables donnent totaux **et** items identiques, contradiction → 422 —, et la colonne `status` de Lakeflow reprise sur ses 6 valeurs réelles **7/7** (28 statements) parce que le premier balayage la trouvait d'accord **à 0 des deux côtés**, ce qui ne prouvait rien. **SC-003 atteint** (ligne 51, page 3 → `total = 1`). Un défaut trouvé et corrigé au passage : `enabled: false` sur les options quand la table source est absente en dev |
| T006 | ✅ 9 fichiers (3 hors liste prévue, tracés dans la story : `compute-column-widths.ts` n'est pas touché mais `lib/compute/column-filters.ts`, `ComputeRecommendationsForecast.tsx` et `ComputeSqlWarehouses.test.tsx` le sont ; `useLakeflowJobsData.ts` remplace le `useLakeflowQueries.ts` annoncé, qui n'existe pas), entonnoir + combo portaillée sur les **88 colonnes filtrables** des 11 tableaux (109 `id` recomptés, 109 `width`, 88 `filterKey`), **+26 tests** (25 sur la combo, 1 sur la synchronisation bidirectionnelle de la page warehouses → 17/17). Aucune régression de gate (cf. ci-dessous). Écart de conception assumé : **un seul état de filtres par tableau**, dont les 21 paramètres historiques sont *dérivés* — c'est ce qui rend structurellement impossible le couple contradictoire que le serveur refuse en 422 | ⏳ reste la vérification navigateur : SC-003 vu de l'IHM, mutualisé avec les 6 contrôles §5ter |

**Gates de T006**, mesurés contre le même worktree de référence que T003/T004
(`/tmp/dcm-baseline`, arbre à HEAD sans les modifications non committées) :

| Gate | Baseline (HEAD propre) | Après T006 | Delta |
|---|---|---|---|
| `npx tsc --noEmit` | 101 erreurs | 101 erreurs | **0** |
| `npm run lint` | 61 problèmes (39 err, 22 warn) | 61 problèmes | **0**, après correction — voir la note ci-dessous |
| `npx vitest run` | 4 échecs / 293 | 4 échecs / **315 passés** | **mêmes 4 échecs** (`App`, `Dashboard` ×2, `Databricks`) **+26 tests neufs verts** |
| `ComputeSqlWarehouses.test.tsx` | 8/8 | **17/17** | **+9 depuis la baseline** (T003 en avait porté 8) |
| `npm run build` | ✓ | ✓ | — |

La ligne `lint` a d'abord été relevée à **0 de delta** par erreur : `eslint` était propre sur les
fichiers *modifiés*, mais un `npm run lint` complet donnait **63 problèmes (40 err, 23 warn)** —
les deux problèmes venaient de fichiers **créés** par T006, donc absents de la baseline et
invisibles dans un diff fichier par fichier :

- `compute-column-filter.tsx` — `react-hooks/exhaustive-deps` sur `options`, dépendance du
  `useMemo` du corps du panneau ; corrigé en mémoïsant `options`.
- `hooks/query-keys.ts` — `_ignored` non utilisé dans la déstructuration qui retire
  `column_filter` du périmètre de la clé ; corrigé en copie + `delete`, la règle du projet ne
  reconnaissant pas le préfixe `_`.

Les deux sont corrigés : `npm run lint` est revenu à **61**, delta réellement 0. À retenir pour
les prochaines tasks : sur un fichier neuf, un `eslint <fichier>` propre ne dit rien du delta.

### Suite — durées en composantes `5d 17h 28m 56s`

Demandé après coup : « pour toutes les metrics affichées en heure, affiche plutôt le format
xjxhxmxs. » Lettres arbitrées avec l'utilisateur : **`d`/`h`/`m`/`s`**, l'IHM étant entièrement en
anglais ; portée arbitrée : **les métriques en heures seulement**.

Un seul formateur concerné : `formatHours` ([lib/compute/format.ts](../../packages/dcm-frontend/src/lib/compute/format.ts)),
qui rendait `137.5 h` sur les 5 emplacements de l'uptime clusters (onglets Overview et Efficiency,
tiroir et sa courbe). Les trois autres formateurs de durée de l'app ne sont **pas** touchés, sur
décision explicite : `formatDurationSeconds` (runs Lakeflow, `1 h 05`) et les deux
`formatDurationMs` (latences de requêtes, où `450 ms` ne doit pas devenir `0s`).

Règles retenues : composantes nulles omises (`2h 30m`, `36s`, et `1d 10s` plutôt que
`1d 0h 0m 10s`), zéro réel rendu `0s` et non `—` — qui reste réservé à l'absence de mesure, un
cluster à zéro heure d'activité étant précisément ce que cherche l'onglet Efficiency —, et durée
négative traitée comme absente. Le paramètre `digits` du formateur disparaît, sans appelant.

Conséquence traitée, sinon la demande cassait l'affichage : dans une colonne `metric` (128 px, dont
32 de `px-4`), le pire cas à quatre composantes fait ~102 px pour 96 px utiles — il aurait été
tronqué. Ajout d'une entrée `duration: 160` à l'échelle de largeurs, posée sur les 4 colonnes
Lifetime / Prev lifetime des deux tableaux.

Gates en delta contre `/tmp/dcm-baseline` : `tsc` 101 = 101, `lint` 61 = 61, `vitest` mêmes 4
échecs pré-existants / **351 passés** (+4), `npm run build` ✓. À confirmer au navigateur : la
largeur des colonnes Lifetime sur un uptime à quatre composantes.

### Suite — coûts au centime sur les pages compute

Demandé après coup : « pour les coûts sur les pages front actuelles, ils sont arrondis à
l'entier. Je voudrais qu'ils soient arrondis à la deuxième décimale. »

Un seul formateur était en cause : `formatUsd` ([lib/compute/format.ts](../../packages/dcm-frontend/src/lib/compute/format.ts))
avec `maximumFractionDigits = 0` par défaut. Les autres modules (FinOps, Costs, Databases,
Databricks, Data product usage) passent déjà par `lib/domain/formatters.ts`,
`lib/databricks/view-data.ts` ou `lib/databases/database-utils.ts`, tous à 2 décimales : les
pages compute étaient les seules à arrondir à l'entier. Défaut passé à **2** ; les appels
explicites à 3 chiffres (coût DBU, coût par requête) sont inchangés, `minimumFractionDigits`
valant 2 par défaut pour l'USD. Le repli du `catch` a été corrigé au passage : il faisait un
`Math.round`, donc rendait l'entier quel que soit l'argument.

`lib/utils.ts::formatCurrency` portait le même arrondi à l'entier et **n'a aucun appelant**
(vérifié par recherche des imports nommés et par étoile) : aligné à 2 décimales plutôt que laissé
en piège pour le premier appelant.

Aucun test ne couvrait `formatUsd` — d'où l'absence de rupture au changement de défaut. Créé
`lib/compute/format.test.ts` : 7 tests sur les décimales par défaut, le coût inférieur au dollar
(qui s'affichait `$0`, indistinguable d'un coût nul), la précision à 3 chiffres, la valeur absente
qui rend un tiret et non `$0`, et les bornes de `lastNDaysPeriodIso`.

Gates en delta contre `/tmp/dcm-baseline` : `tsc` 101 = 101, `lint` 61 = 61, `vitest` mêmes 4
échecs pré-existants / **347 passés** (+7), `npm run build` ✓.

### Suite de T003 — retrait du sélecteur de dates sur les pages compute

Demandé après coup : « pour les pages cluster, comme les résultats affichés sont toujours les
plus récents, les filtres date du haut n'ont pas d'utilité et peuvent rendre l'utilisateur
confus. Le mieux serait de les retirer des pages compute où les données sont affichées avec des
plages de temps prédéfinies. » C'est l'écart assumé de T003 (« sélecteur de dates *route-scoped*
donc non retirable par onglet ») repris à la racine : retiré **par route**, pas par onglet.

La prémisse a été vérifiée côté serveur avant de retirer quoi que ce soit, endpoint par endpoint,
parce que « ces dates ne servent à rien » n'était vrai que sur une partie des écrans :

| Endpoint | `period_start` / `period_end` | Effet réel |
|---|---|---|
| 4 tableaux clusters, 3 onglets warehouses à fenêtre | reçus, renvoyés dans `period` | **inertes** — la ligne lue est choisie par `window_days` sur une table `*_rolling` |
| `fetch_warehouse_slow_queries` | `CAST(start_time AS DATE) BETWEEN` | **filtre** |
| `fetch_warehouse_detail`, les 3 courbes de tiroir (`*_cost_trend`, `cluster_lifetime_trend`) | `_date_where` | **filtre** |
| recommandations (`last_seen_date >=`), prévision (`horizon_date >=`) | bornes | **filtre** → page Recommendations **conservée** |
| lakeflow (`_resolve_period`) | deux bornes ⇒ `"custom"`, qui écrase le preset nommé | **filtre** → page Workflows **conservée** |

D'où le périmètre retenu : bloc de dates retiré sur `/databricks/cluster` et
`/databricks/sql-warehouse` seulement, avec deux conséquences à traiter, sans quoi le retrait
aurait cassé des écrans qui marchaient :

- Masquer le contrôle sans changer les appels aurait laissé un **couplage invisible** : une plage
  posée depuis Workflows aurait continué à décaler le tiroir clusters, sans rien à l'écran pour
  l'expliquer. Les deux pages calculent donc leurs bornes elles-mêmes, ancrées sur aujourd'hui
  (`lastNDaysPeriodIso`) : **365 jours** pour les recherches « dernière ligne dans la plage » du
  détail, **90 jours** pour les courbes du tiroir — le défaut de 30 jours de l'en-tête aurait
  masqué un instantané en retard de plus d'un mois.
- L'onglet **Slow queries** perdait son seul filtre temporel. Il reçoit ses propres chips
  `Last 7d` / `Last 30d` / `Last 90d`, défaut **30 jours** — exactement le comportement de
  l'ancien `defaultDays={30}`.

Deux choix contre-intuitifs, assumés :

- **Pas de chip `Daily` sur Slow queries**, alors que les trois autres onglets en ont une : là,
  `Daily` désigne le dernier instantané pré-agrégé et n'est jamais vide, tandis qu'un filtre de
  dates d'une seule journée sur une table de statements en retard afficherait « aucune requête
  lente » là où il faut lire « pas encore de données ».
- **Les presets `30d`/`90d`/`6m`/`1y` disparaissent avec le bloc de dates**, pas séparément :
  ils écrivent dans la *même* plage. Seuls, ils auraient été un contrôle qui ne filtre rien.

7 fichiers modifiés (4 de code, 3 de tests) + 1 helper : `lib/compute/format.ts`
(`todayIsoUtc`, `lastNDaysPeriodIso`), `lib/databricks/routes.ts`
(`showsGlobalHeaderDateRange`, dont `showsGlobalHeaderTimePresets` dépend désormais),
`components/Header.tsx`, les deux hooks `useCompute{Clusters,Warehouses}Queries.ts`
(`REFERENCE_SPAN_DAYS`, option `windowDays` sur les requêtes lentes) et les deux pages.

| Gate | Baseline (HEAD propre) | Après | Delta |
|---|---|---|---|
| `npx tsc --noEmit` | 101 erreurs | 101 erreurs | **0** |
| `npm run lint` | 61 problèmes | 61 problèmes | **0** |
| `npx vitest run` | 4 échecs / 293 | 4 échecs / **340 passés** | **mêmes 4 échecs** (`App`, `Dashboard` ×2, `Databricks`) **+9 tests neufs** |
| `routes.test.ts` · `Header.test.tsx` | 24 · 10 | **31** · **12** | plage absente sur les 2 routes, présente là où elle filtre, route plurielle héritée `/databricks/clusters` non captée par préfixe |
| `ComputeSqlWarehouses.test.tsx` · `ComputeClusters.test.tsx` | 17 · 20 | **19** · **21** | chips Slow queries → bornes envoyées et retour page 1 ; plages ancrées sur aujourd'hui, plus sur l'en-tête |
| `npm run build` | ✓ | ✓ | — |

Un piège de gate rencontré : `.at(-1)` dans un test passe en vitest mais **casse `tsc`** (la
`lib` du projet est antérieure à ES2022) — mesuré à 102 avant correction en indexation.

### Suite de T005/T006 — masquage du débordement de colonne

Demandé après coup, en voyant le résultat de T005 dans le navigateur : « les contenus dépassant
en taille la colonne dépassent. Il faudrait plutôt masquer ce qui dépasse et avoir le nom / la
valeur complète en passant le curseur dessus. » Ce n'est pas une régression de T005 mais son
angle mort : la largeur devenue fixe, tout contenu plus large sortait de sa colonne et recouvrait
la voisine.

Cause exacte : `compute-data-table.tsx` ne coupait que les cellules dont `cell()` rend une chaîne
ou un nombre. Toutes les cellules **composées** — la grande majorité — passaient à côté, et deux
d'entre elles portaient une borne en dur (`max-w-[240px]`, `max-w-xs`) qui contredit une colonne
redimensionnable.

Corrigé en 5 fichiers :

- `compute-data-table.tsx` — `overflow-hidden` sur **chaque** `<td>` (dernier rempart de la
  colonne) + une enveloppe `ComputeDataTableCellContent` qui coupe le texte et pose le `title`,
  lu **après rendu** sur le DOM : la plupart des cellules rendent un composant dont le texte
  n'est pas dans `props.children`, donc inextractible avant rendu. `title` aussi sur le libellé
  d'en-tête, un en-tête coupé rendant la colonne muette.
- `recommendations-table.tsx`, `ComputeSqlWarehouses.tsx`, `ComputeClusters.tsx` — `truncate` sur
  **chaque ligne** des cellules empilées, pas sur le bloc : les points de suspension d'un
  conteneur ne s'appliquent qu'à son propre texte, pas à ses enfants de type bloc. Le titre de
  recommandation garde ses deux lignes via `line-clamp-2` + `whitespace-normal`, l'enveloppe
  imposant un `nowrap` qui s'hérite.
- `LakeflowJobs.tsx` — `max-w-[240px]` → `min-w-0` : une borne fixe couperait à 240 px une
  colonne élargie à 400.

Écarté : un sélecteur descendant global (`[&_*]:truncate`) — il forcerait `nowrap` sur le
`line-clamp-2` voulu et écraserait les `min-w-[100px]` des cellules graphiques ; et un `title`
conditionné à `scrollWidth > clientWidth` — non mesurable en jsdom, et une largeur réduite à la
main peut couper n'importe quelle cellule.

| Gate | Baseline (HEAD propre) | Après | Delta |
|---|---|---|---|
| `npx tsc --noEmit` | 101 erreurs | 101 erreurs | **0** |
| `npm run lint` | 61 problèmes | 61 problèmes | **0** |
| `npx vitest run` | 4 échecs / 293 | 4 échecs / **318 passés** | **mêmes 4 échecs** **+3 tests nets** (1 test devenu faux remplacé par 4) |
| `compute-data-table.test.tsx` | — | **18/18** | cellule composée coupée + `title` complet, `overflow-hidden` sur tous les `td`, `title` d'en-tête, infobulle propre d'une cellule préservée |
| `npm run build` | ✓ | ✓ | — |

Le test `« n'enveloppe pas une cellule composite, dont l'infobulle serait rognée »` a été
**supprimé** : il figeait exactement le comportement que la demande corrige. Il est remplacé par
quatre tests qui vérifient le nouveau, et non contourné par un `skip`.

**Gates de T005, mesurés en delta contre la baseline de `quickstart.md` §1** — le total ne veut
rien dire ici, aucun gate n'étant vert à HEAD :

| Gate | Baseline | Après T005 | Delta |
|---|---|---|---|
| `npx tsc --noEmit` | 175 erreurs | 175 | **0 nouvelle, 0 disparue** (diff sur numéros de ligne normalisés) |
| `npm run lint` | 39 erreurs + 22 warnings | 61 problèmes | **identique** |
| `npx vitest run` | 4 échecs | 4 échecs / 281 passés | **mêmes 4 échecs** (`App`, `Databricks`, `Dashboard` ×2) **+ 35 tests neufs verts** |

**Gates de T003**, mesurés contre un worktree de référence sur **le même commit que HEAD**
(`/tmp/dcm-baseline`, `bd6426a`) — c'est-à-dire l'arbre sans les modifications non committées :

| Gate | Baseline (HEAD propre) | Après T003 | Delta |
|---|---|---|---|
| `npx tsc --noEmit` | 101 erreurs | 101 erreurs | **0** — mêmes 4 erreurs warehouse, seuls les numéros de ligne bougent |
| `npm run lint` | 61 problèmes (39 err, 22 warn) | 61 problèmes (39 err, 22 warn) | **0** |
| `npm run test` | 4 échecs / 293 | 4 échecs / 293, mêmes fichiers | **0** |
| `ComputeSqlWarehouses.test.tsx` | 8/8 | **16/16** | **+8 tests verts** |
| `npm run build` | ✓ | ✓ | — |

Le **101** ci-dessus ne contredit pas le **175** de `quickstart.md` §1 : ce dernier a été
relevé à un commit antérieur, avant que T001/T002/T005 ne soient committés. La bonne référence
pour juger une task en cours est le worktree au commit courant, pas le chiffre figé du
quickstart — à réutiliser tel quel pour T004 et T006.

## Défauts pré-existants corrigés au passage

Deux, tous deux trouvés en vérifiant le code et non demandés :

1. **`cost_usd_prev_window` jamais `NULL`** sur `warehouse_cost_rolling` — la colonne vient
   d'un `SUM(CASE … ELSE 0 END)` (l. 115), donc « pas de prédécesseur » et « a coûté zéro »
   sont indiscernables. Même défaut que celui trouvé sur les clusters en vérifiant 022 T002,
   déjà résolu là-bas par `_normalize_prev_cost`. Corrigé dans T002.
2. **`<WarehouseCell name={null} …>`** en dur dans l'onglet Performance
   (`ComputeSqlWarehouses.tsx:485`) — un `null` littéral, pas une donnée absente. La cause
   racine est l'absence de `warehouse_name` en gold : c'est T001 qui la lève, T003 qui
   supprime le `null`.
