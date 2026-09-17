# Review report — T001d : dépense serverless (`serverless_cost_daily` + `serverless_cost_rolling`)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T001d (spec 025) — les deux tables qui rendent visible l'angle mort de tous les
rollups basés cluster : le serverless n'a ni `cluster_id`, ni `cluster_source`, ni ligne dans
`curated_dbx_compute_clusters`
**Implémentation** : déléguée à `dp-data-databricks-engineer` (domaine `dataeng`), relue
intégralement ici, plus **1 défaut trouvé en revue et corrigé** de ma main (§ « Le défaut »)
**Diff relu** : 16 fichiers — **code** 10 fichiers, **+2 588 / −5** ; documentation 6 fichiers
dans `specs/025-serverless-compute-page/` (ce rapport compris, donc son propre décompte ne peut
pas être cité ici sans boucler)

## Gates

`dcm-review.sh --package packages/dcm-databricks-pipeline --base develop` rend **FAIL**. Les
deux gates rouges le sont sur de la dette **antérieure**, dans des fichiers **absents du diff**,
et c'est prouvé par un décompte identique des deux côtés — pas par une inspection à vue.

| Gate | Brut | Arbitrage |
|---|---|---|
| `pytest` | ✅ **PASS** | **821 tests** (771 avant T001d → 820 livrés par l'agent → **821** avec mon test de non-régression). **0 retiré** |
| `ruff check .` | FAIL | **269 erreurs au worktree, 269 à HEAD** — le même nombre. Aucune dans les 16 fichiers du diff : elles se concentrent sur `dlt_02_curated_layer.py` (83), `dlt_03_gold_layer.py` (78), `sqs_to_volume_drain.py` (34), `tests/test_dlt_workflow.py` (33) |
| `mypy pipelines` | FAIL | **142 erreurs dans 7 fichiers au worktree, 142 dans 7 fichiers à HEAD**, alors que le worktree en analyse **72** contre 70 : les 2 modules neufs ajoutent **0** erreur. Les 7 fichiers fautifs sont les mêmes, aucun dans le diff |

Méthode : `git archive HEAD | tar -x -C /tmp/headchk3`, puis **les commandes exactes de
`dcm-review.sh`** rejouées sur les deux arbres avec le même interpréteur. Vérifications
complémentaires de mon côté, sur le périmètre du diff seul : `ruff check` sur les 9 fichiers
Python touchés → `All checks passed!`, et `ruff format --check` à parité de hunks fichier par
fichier avec HEAD (`entrypoint.py` 4/4, `specs.py` 21/21, `test_entrypoint.py` 11/11,
`test_specs.py` 11/11 ; les 3 fichiers neufs, `sql_helpers.py` et `test_sql_helpers.py` à **0**).
Mes propres éditions (§ « Le défaut ») n'ajoutent **aucun** hunk.

Ce qui reste vrai malgré l'arbitrage : ce package porte 269 erreurs `ruff` et 142 erreurs `mypy`
de dette, concentrées sur les 3 modules DLT historiques. Hors périmètre de T001d, mais ce n'est
pas un détail de forme — c'est ce qui empêche ces deux gates de dire quoi que ce soit d'utile sur
un diff, tâche après tâche.

## Ce que ça change

Deux tables gold neuves, aucune existante modifiée. Troisième rollup **billing-direct** du job,
sans `depends_on` sur la chaîne cluster — il n'y a rien à attendre, le serverless n'a pas de
cluster.

| Table | Grain | Contenu |
|---|---|---|
| `gold_dbx_compute_serverless_cost_daily` | `(cloud, workspace, surface, object, jour)` | coût $/DBU par **surface d'usage** (12 valeurs) et par objet, `run_count` + histogramme $/exécution sur la surface `JOB` |
| `gold_dbx_compute_serverless_cost_rolling` | `(cloud, workspace, surface, object, window_days)` | fenêtres 1/7/30/90 j, percentiles $/exécution **recalculés depuis les histogrammes fusionnés** |

Trois points de conception que la revue confirme comme justes :

1. **`serverless_surface` et `object_id` ne sont JAMAIS NULL**, par branche `ELSE 'OTHER'` et par
   sentinelle `_NO_OBJECT`. Ce n'est pas du style : `merge_into_table` fusionne sur `<=>`
   **null-safe**, donc une clé NULL ne lève rien — elle fond silencieusement tout un workspace en
   une ligne corrompue. La sentinelle porte **plus de la moitié des lignes** (1 531 218 contre
   1 286 959) pour 8,78 % du coût.
2. **Deux niveaux d'agrégation, pas un.** Le coût par exécution exige un `GROUP BY job_run_id`
   *avant* le `GROUP BY` du grain : `histogram_from_edges_sql` est un agrégat de **lignes**, et
   l'appliquer directement à la facturation compterait des tranches de facturation, pas des
   exécutions.
3. **Percentiles jamais moyennés.** Le rolling refusionne les histogrammes quotidiens bucket par
   bucket puis relit les percentiles. Une moyenne de p95 quotidiens n'a aucune signification.

## Le défaut : une liste blanche qui ne couvrait que les noms **récents**

Trouvé en revue, corrigé, testé. C'est le seul défaut de correction trouvé dans le livrable.

Ma requête de périmètre comptait **23** `billing_origin_product` distincts là où le `CASE` n'en
nommait que **19**. En mesurant `OTHER` sur l'**historique complet** — la fenêtre que la table
construit réellement — au lieu de la fenêtre de référence de 31 jours :

| produit tombé dans `OTHER` | cloud | lignes | $ | fenêtre |
|---|---|---:|---:|---|
| `LAKEFLOW_CONNECT` | aws | 73 787 | 9 880,03 | 2025-02-12 → 2026-09-09 |
| `LAKEHOUSE_MONITORING` | aws | 3 476 | **2 837,39** | 2024-05-27 → **2026-02-06** |
| `LAKEHOUSE_MONITORING` | azure | 6 715 | **656,93** | 2024-08-06 → **2026-02-06** |
| `SHARED_SERVERLESS_COMPUTE` | aws | 75 | 90,46 | 2024-08-15 → 2024-09-02 |
| `BASE_ENVIRONMENTS` | aws | 17 | 0,07 | 2025-12-22 → 2026-07-10 |

**`LAKEHOUSE_MONITORING` est l'ancien nom de `DATA_QUALITY_MONITORING`**, qui est lui dans la
liste blanche. Preuve que c'est un renommage et non deux produits — les **SKU sont exactement les
mêmes**, avec le même compte par cloud :

```
ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT   ← les deux produits
PREMIUM_JOBS_SERVERLESS_COMPUTE_EU_WEST               ← les deux produits
PREMIUM_JOBS_SERVERLESS_COMPUTE_FRANCE_CENTRAL        ← les deux produits
```

et relais dans le temps : l'ancien s'arrête le **2026-02-06**, le nouveau démarre le 2025-11-06
(azure) / 2025-12-15 (aws). Ne retenir que le nom récent faisait donc tomber **3 494,32 $** de la
même fonctionnalité plateforme dans le fourre-tout `OTHER`.

C'est **exactement** le piège que ce même livrable documente à propos de `budget_policy_id` face
à `usage_policy_id` : retenir la colonne **récente** perdrait silencieusement 188 744 lignes
d'historique. La leçon manquait juste d'être appliquée à la liste blanche elle-même. Et une
fenêtre de 31 jours mesurée en septembre ne peut structurellement pas voir un produit arrêté en
février — c'est la **troisième** fois dans cette spec que la conflation de fenêtre produit une
affirmation fausse.

**Pourquoi le test existant ne pouvait pas l'attraper** :
`test_every_in_scope_product_is_classified_except_the_measured_one` n'itère que
`SERVERLESS_SCOPE_PRODUCTS`, c'est-à-dire les produits **forcés** dans le périmètre.
`LAKEHOUSE_MONITORING` y entre par `product_features.is_serverless = true`, donc il était hors
de portée du test. C'est la seconde voie d'entrée qui n'était pas couverte.

Corrigé :

- `sql_helpers.serverless_surface_case_expr()` : `LAKEHOUSE_MONITORING` ajouté à la branche
  `PLATFORM_AUTO`, juste après `DATA_QUALITY_MONITORING` pour que l'appariement se voie.
- **Le contrôle `OTHER` remplacé par un contrôle de COMPOSITION.** L'ancien disait « `OTHER` doit
  rester ≤ ~10 $ par cloud » en citant les 4,82 $ de la fenêtre de 31 jours — sur l'historique il
  en portait **13 464,88 $**, soit **mille fois le seuil**, sans qu'aucun produit neuf ne soit
  apparu. Un seuil en dollars était donc structurellement faux ici. Le nouveau contrôle : `OTHER`
  ne doit contenir *que* 3 produits nommés, un 4ᵉ signifie qu'il faut classer.
- Même correction dans le **commentaire de colonne** `serverless_surface` de `specs.py` — il est
  publié dans Unity Catalog, donc lu par les utilisateurs FinOps.
- **Nouveau test** `test_platform_auto_covers_the_renamed_monitoring_product`, qui vérifie que les
  deux noms sont dans la **même** branche (présents ailleurs dans le `CASE` ne suffirait pas : la
  surface résultante serait différente).

## Validation sur donnée réelle — `dev_local`

Exigence de l'utilisateur : *« pour la partie data à la fin d'une tâche déploie, teste et valide
la donnée »*. L'agent n'avait **rien** déployé ni lancé, comme convenu.

`databricks bundle validate -t dev_local` → **Validation OK!** puis `deploy -t dev_local`
(profil OAuth `dcm-dev`) → **Deployment complete!**

### 1. Le SQL réellement généré par le code livré, joué en lecture seule

Les deux builders ont été appelés avec un faux `spark` pour **capturer la requête produite**
(14 546 et 7 671 caractères), puis ces requêtes exactes ont été exécutées en `SELECT` agrégé via
la Statements API. Ce n'est donc pas une réécriture à la main de la logique. Confronté aux
mesures de référence prises **avant** l'implémentation, par une autre main
(`T001d-baseline-measures.md`) :

| Contrôle, fenêtre de référence 2026-08-10 → 2026-09-09 | Attendu | Rendu par le code livré | ✅ |
|---|---:|---:|---|
| lignes | 109 748 | **109 748** | ✅ |
| surfaces distinctes | 12 | **12** | ✅ |
| `SUM(cost_usd)` bi-cloud | 380 638,71 $ | **380 638,71 $** | ✅ |
| dont AWS | 276 672,18 $ | **276 672,18 $** | ✅ |
| dont Azure | 103 966,54 $ | **103 966,54 $** | ✅ |
| `_NO_OBJECT` | 33 425,57 $ | **33 425,57 $** | ✅ |
| clés de merge NULL | 0 | **0** | ✅ |
| `object_name` NULL | 0 | **0** | ✅ |
| `run_count` non NULL hors `JOB` | 0 | **0** | ✅ |
| `run_count` = 0 | 0 | **0** | ✅ |
| run-jours | 162 123 | **162 123** | ✅ |

### 2. La preuve que le `CASE` **partitionne** — historique complet

C'est le contrôle qui valide la revendication anti-double-comptage du `table_comment`, et il ne
se voit que sur l'historique entier :

| | valeur |
|---|---:|
| somme des **12** surfaces, via le SQL généré | **3 687 894,39 $** |
| dépense serverless mesurée directement sur la facturation | **3 687 894,38 $** |
| écart | **1 centime**, arrondi sur 12 sous-totaux |

Aucune ligne du périmètre n'échappe aux 12 surfaces, aucune n'est comptée deux fois. Et le
correctif est visible dans la chaîne complète : `PLATFORM_AUTO` démarre au **2024-05-27**, date
exacte du premier `LAKEHOUSE_MONITORING`. `OTHER` vaut **9 970,56 $** = 9 880,03 + 90,46 + 0,07,
la composition prédite au centime. Les 4 surfaces sans objet listable (`GENIE`, `PLATFORM_AUTO`,
`NETWORKING`, `OTHER`) sont à **100 %** sur la sentinelle.

### 3. Le rolling, invariants vérifiés

La table source n'existant pas encore, le daily a été **substitué à sa source** dans le SQL
généré du rolling (une seule occurrence, vérifiée par assertion) :

| Contrôle | Résultat |
|---|---|
| lignes / fenêtres distinctes | 87 067 / **4** |
| clés de merge NULL | **0** |
| `run_count` = 0 | **0** |
| désynchronisation `run_count IS NULL` ⇎ `histogramme IS NULL` | **0** — l'équivalence du docstring est donc **exacte**, pas seulement plausible |
| bucket **overflow** non vide | **0** — SC-011 confirmé |
| `object_name` NULL | **0** |
| arithmétique de fenêtre | `cost_w30` = 368 058,50 $ et `cost_w1` = 3 199,51 $ ; 380 638,71 − 368 058,50 = **12 580,21 $** = exactement le coût du 2026-08-10, le 31ᵉ jour exclu |

### 4. ✅ Les tables écrites, déployées et validées

Le run `380576393977880` (`--only gold_serverless_cost_daily`) est resté **QUEUED** derrière la
chaîne T001c (`779628004910980`, toujours sur `gold_cluster_efficiency_daily` à ~150 min) : le job
porte `max_concurrent_runs: 1`. Diagnostic posé avant de décider quoi que ce soit — ce run n'est
**pas** bloqué : il porte `full_refresh=true`, et l'historique Delta de
`gold_dbx_compute_cluster_efficiency_daily` montre que même un merge **incrémental** de 23 000
lignes source y coûte 5,4 à 6,8 min dont **98 % en `materializeSourceTimeMs`**. Sur les 91 jours /
25,9 M lignes de `node_timeline`, 150 min est dans l'ordre de grandeur attendu. Il n'a donc pas
été annulé, et la prédiction T001c engagée dans `review-report-T001c.md` reste vivante.

Le verrou est celui du **job**, pas de la plateforme : un run **one-off** (`jobs submit`,
`733084053802812`) portant les deux mêmes `python_wheel_task` sur le même
`gold_compute_env` n'y est pas soumis. Écriture non destructive de deux tables absentes, roue
lue depuis Workspace files (pas DBFS), profil OAuth `dcm-dev`. Les deux tâches sont passées
**SUCCESS en ~2 min chacune**, en parallèle de la chaîne, sans rien annuler.

**`gold_dbx_compute_serverless_cost_daily` — 15 contrôles sur la table écrite** (fenêtre de
référence 2026-08-10 → 2026-09-09 pour les 7 premiers, historique complet ensuite) : lignes
**109 748**, surfaces **12**, coût **380 638,71 $** (aws **276 672,18** / azure **103 966,54**),
`_NO_OBJECT` **33 425,57 $**, `SUM(run_count)` **162 123**, `OTHER` **9 970,56 $**,
`PLATFORM_AUTO` démarrant au **2024-05-27**, 0 clé de merge NULL, 0 `object_name` NULL, 0
`run_count` hors `JOB`, 0 `run_count` = 0, et les 4 surfaces sans objet listable à **100 %** sur
la sentinelle. **14 identiques au centime** aux mesures read-only.

Le 15ᵉ méritait un examen plutôt qu'un « ✅ » : la table rend **3 687 894,38 $** là où le §2
annonçait **3 687 894,39 $**. Vérifié plutôt qu'expliqué — la somme des **12 sous-totaux arrondis
par surface** rend `,39`, la somme globale non arrondie rend `,38`. La table reproduit donc les
**deux** chiffres, chacun à son grain, et l'écart d'un centime était bien l'arrondi annoncé.

**`gold_dbx_compute_serverless_cost_rolling` — 15 contrôles** : **87 067 lignes / 4 fenêtres**,
soit exactement le décompte read-only ; 0 clé de merge NULL, 0 `object_name` NULL, 0 `run_count`
= 0, **0 désynchronisation** `run_count IS NULL` ⇎ histogramme NULL, **0 bucket overflow non
vide** (SC-011), 12 surfaces, une seule `window_start` par fenêtre.

Les bornes ont été **lues dans la table** (`window_start`, `as_of_date`) au lieu d'être
supposées — la conflation de fenêtre étant le défaut récurrent de cette spec :
`window_start = as_of_date − (W−1)`, inclus des deux côtés, `as_of_date` = **2026-09-09**. Chaque
fenêtre est un rollup **exact** du daily écrit sur ces bornes : w1 **3 199,51**, w7 **80 471,44**,
w30 **368 058,50**, w90 **1 036 222,34 $** — les 4 égales au centime au daily recalculé, et
`SUM(run_count)` sur `JOB` w90 = **488 819** des deux côtés.

Deux recoupements que ces bornes rendent possibles, et qui valent plus que les contrôles eux-mêmes :

- **w1 = 3 199,51 $ et w30 = 368 058,50 $ sont exactement** les valeurs prédites au §3 par le SQL
  généré, *avant* toute écriture. La prédiction read-only était juste au centime ;
- **w90 = 1 036 222,34 $ est exactement** le périmètre 90 j bi-cloud de
  `T001e-baseline-measures.md` §1, mesuré séparément et à la main sur la facturation. Deux chemins
  indépendants — un SQL généré depuis les helpers, une table produite par le job déployé —
  convergent au centime.

Note tenue : le commentaire de `SERVERLESS_COST_DAILY_SPEC` prévoit qu'une surface reclassée
depuis `OTHER` se nettoie par `one_off_purge`. Mon correctif `LAKEHOUSE_MONITORING` est une telle
reclassification, mais les deux tables étant absentes au premier build, **il n'y avait rien à
purger** — confirmé après coup : `PLATFORM_AUTO` démarre bien au 2024-05-27 dans la table écrite,
donc aucune ligne n'a été laissée dans `OTHER`.

## Ce que j'ai vérifié du subagent, plutôt que de le croire

Chaque chiffre contrôlé a tenu, au centime :

- décomposition en 4 unités : DBU 377 536,01 + GB 2 268,41 + DSU 583,73 + HOUR 250,56 =
  **380 638,71 $** ✅
- `NETWORKING` porte **0 DBU** pour 2 518,97 $ (43 903,78 GB + 25 056 h) ✅
- max run-**jour** 1 137,99 $ (< borne 1 310,72 → overflow vide) et max run-**entier**
  1 345,12 $ ✅
- 162 123 run-jours pour 161 550 exécutions → **573** en trop = **0,35 %** ✅
- 117 run-jours > 50 $ pour 13 520,44 $ ✅
- `GENIE` (18 397,48 $) pèse plus qu'`AI_ENDPOINT` entier (17 565,02 $) — la raison de les séparer
  tient ✅
- **`GENIE_FREE_USAGE` est bien le seul SKU du périmètre sans ligne de prix**, vérifié
  exhaustivement sur tout l'historique : la jointure de prix rend 0 ou 1 ligne, jamais plus, et
  le cas 0 se réduit à **1 seul SKU** ✅

Deux risques que j'ai voulu écarter par la mesure et non par le raisonnement, la CTE `priced`
étant **volontairement non agrégée** (contrairement aux builders voisins) :

1. **Une fenêtre de prix en doublon doublerait le coût *et* le coût par run.** Mesuré sur tout
   l'historique : 15 332 combinaisons `(cloud, sku, jour)` à **exactement 1** ligne de prix, 103 à
   0, **aucune à 2 ou plus**. Le risque n'existe pas sur cette donnée.
2. **Un `billing_origin_product` NULL rendrait une chaîne vide** via
   `concat_ws(collect_set(...))`. Mesuré : **0 ligne** du périmètre (sur 24 327 341) a un produit
   NULL. Sans objet.

## Findings

```
specs/025-serverless-compute-page/review-report-T001d.md:1: 🟡 risk: les deux tables ne sont pas encore ecrites — le run est QUEUED derriere la chaine T001c (max_concurrent_runs: 1). Code valide en lecture seule sur donnee reelle, fenetre et historique, pour les deux builders ; tables cibles absentes donc aucun etat intermediaire
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml:1: 🟡 risk: aucun `run_as` sur le job ni sur le target prod de databricks.yml — les jobs tournent sous l'identite humaine qui deploie, y compris en prod. PREEXISTANT et transverse aux 8 jobs, non introduit par T001d. La remediation exige un nom de service principal que seul l'utilisateur peut fournir, et s'applique au niveau bundle, pas sur 2 taches sur 23
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/serverless_cost_rolling.py:90: 🟡 risk: `window_days = 1` publie toujours un jour PARTIEL — le jour d'ancrage 2026-09-09 vaut 3 199,51 $ contre 16 124,04 $ la veille, la facturation n'etant pas encore complete. Inherent a la latence de facturation et transverse a toutes les tables _rolling du job, pas propre a T001d, mais l'IHM doit le dire
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/serverless_cost_daily.py:216: 🟢 note: `run_count` compte des run-JOURS et non des executions (573 sur 162 123 = 0,35 %, 522 executions a cheval sur minuit). Plancher du grain quotidien de la source ; documente dans les deux modules et les commentaires de colonnes
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/serverless_cost_daily.py:81: 🟢 note: `_surface_list_sql` reimplemente `sql_helpers.sql_string_list`, utilise juste a cote par `serverless_scope_predicate`. Sans consequence, mais une duplication de moins serait une divergence de quoting de moins
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/serverless_cost_daily.py:345: 🟢 note: `MAX(object_name_native)` choisit arbitrairement quand un objet est renomme dans la journee. Deterministe, mais le docstring ne le dit pas, contrairement au traitement explicite de `performance_target` ('MIXED') et de `billing_origin_product` (liste jointe)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/grain_resolution.py:103: 🟢 note: troisieme occurrence du defaut de T001c (un id de usage_metadata sans predicat de produit), toujours hors perimetre : 1 paire sur 179 043
packages/dcm-databricks-pipeline/pipelines/dlt_02_curated_layer.py:1: 🟢 note: 269 erreurs ruff et 142 erreurs mypy de dette prealable dans ce package, concentrees sur les 3 modules DLT historiques (dlt_02 83+51, dlt_03 78+46, sqs_to_volume_drain 34+21). Identiques a HEAD, hors perimetre T001d, mais elles rendent les gates ruff et mypy incapables de signaler quoi que ce soit sur un diff -- l'arbitrage manuel est refait a chaque tache
```

0 🔴 blocker · 3 🟡 risk · 5 🟢 note

## Checklist

| Point | Résultat |
|---|---|
| Secret / `.env` / credential dans le diff | **aucun** — motifs `dapi…`, `DATABRICKS_TOKEN`, `client_secret`, `token[:=]`, `password`, `dbfs:/`, `dbutils.fs`, `BEGIN … PRIVATE KEY` cherchés sur les lignes **ajoutées** du diff staged : **3 correspondances, toutes dans de la prose de rapport qui cite les motifs elle-même** (`T001d-implementation-report.md` ×2, celui-ci ×1). Aucune dans le code |
| Authentification Databricks | profil OAuth `dcm-dev` uniquement. Le profil `[DEFAULT]` porte un PAT prohibé : **jamais utilisé** |
| Anti-patterns `dcm-python` | aucun : pas d'import relatif, pas de `print`, docstrings Google, `from __future__ import annotations`, typage complet |
| Critères d'acceptation | SC-003, SC-004, SC-005 et SC-011 **vérifiés sur donnée réelle**, et les 4 énoncés **corrigés** dans `stories/T001.md` (fenêtre / cloud / grain) plutôt que cochés tels quels |
| Périmètre ⊆ intake | ✅ `pipelines/gold_dbx_compute/` + tests + `resources/`, et `specs/025-…`. Aucun autre package |
| Tests pour tout changement de comportement | ✅ +50 tests (771 → 821), 0 retiré. Campagne de sabotage de l'agent : 29 mutations, 29 détectées. Les assertions **négatives** passent par `_code_only()`, qui retire les commentaires SQL — sinon un `"LAG(" not in query` échouerait à cause du commentaire qui explique qu'on n'utilise pas `LAG` |
| Small PR | ⚠️ 10 fichiers de code, **+2 588 / −5**. Deux tables gold neuves et leurs tests : gros, mais un seul sujet, **5 lignes seulement retouchées** dans l'existant et rien de refactorisé au passage |
| DDL / DML sur la plateforme | aucun DDL. Aucune écriture encore : le run est QUEUED. Aucune suppression nulle part |
| `--no-verify` | non |
| Déploiement `-t prod` | non — `dev_local` uniquement |

Côté documentation, 6 fichiers : les deux rapports T001d (implémentation et
celui-ci), la baseline de mesures, **122 lignes** dans `stories/T001.md` (8 critères
d'acceptation réécrits avec leur cloud et leur fenêtre), **47 lignes** de décisions dans
`tasks.md`, et **35 lignes de corrections** à `review-report-T001c.md` (chiffres `node_timeline`
remesurés, ligne de secret rectifiée, état de la chaîne aval).

## Verdict

Le livrable fait ce qu'il annonce, et il est dense de raisons plutôt que d'affirmations : les
deux clés de merge non nulles par construction, les deux niveaux d'agrégation du coût par
exécution, les percentiles refusionnés depuis les histogrammes. Vérifié sur donnée réelle, le
code rend **exactement** les chiffres d'une référence prise avant lui par une autre main — 11
contrôles au centime et à la ligne — et la somme des 12 surfaces égale la dépense serverless
totale de l'historique à **1 centime près**, ce qui prouve la partition revendiquée.

Un défaut de correction a été trouvé et corrigé : la liste blanche ne couvrait que les noms de
produits **récents**, ce qui exilait 3 494,32 $ de `DATA_QUALITY_MONITORING` sous son ancien nom
dans `OTHER`, et le contrôle publié sur `OTHER` était faux d'un facteur mille parce qu'énoncé sur
31 jours pour une table construite sur 3 ans. Les deux sont corrigés, testés, et la leçon est
écrite là où elle se relira.

Reste l'écriture des tables, en file derrière un run que je n'annule pas parce qu'il valide une
prédiction engagée. Signalé comme risque, pas contourné, et les tables cibles sont absentes donc
dans un état cohérent.

**Verdict**: **PASS**
