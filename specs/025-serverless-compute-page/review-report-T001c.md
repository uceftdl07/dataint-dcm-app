# Review report — T001c : liste blanche de produits sur `pipeline_cost_daily` et `cluster_cost_daily`

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T001c (spec 025) — §10.1 + §10.4 du spike, **un seul défaut appliqué deux fois**
**Diff staged** : 15 fichiers, **+1 482 / −56** — code `packages/` 11 fichiers (+637 / −24),
documentation `docs/` + `specs/` 4 fichiers (+845 / −32, dont ce rapport)
**Implémentation** : déléguée à `dp-data-databricks-engineer` (domaine `dataeng`), relue
intégralement ici, plus 3 correctifs de ma main (cf. § « Ce que j'ai corrigé après le subagent »)

## Gates

`dcm-review.sh --package packages/dcm-databricks-pipeline --base develop`

| Gate | Résultat brut | Arbitrage |
|---|---|---|
| `pytest` | ✅ **PASS** | **771 tests** (753 avant → **+18**, 1 renforcé, **0 retiré**) |
| `ruff check` | FAIL | Pointe `tests/test_dlt_workflow.py:251` — **fichier non touché par T001c**. Sur les 10 fichiers du diff : `All checks passed!` |
| `mypy` | FAIL | Pointe `pipelines/sqs_to_volume_drain.py:46` — **fichier non touché**. Sur les 10 fichiers du diff : 1 erreur, **déjà présente à HEAD** (`test_entrypoint.py:450` → `:452`, décalée par 2 imports ajoutés) |
| `ruff format --check` | FAIL | **Parité exacte avec HEAD** : les 5 mêmes fichiers seraient reformatés avant et après (`entrypoint.py`, `specs.py`, `test_cluster_cost_daily.py`, `test_entrypoint.py`, `test_specs.py`). Le fichier neuf `test_sql_helpers.py` est propre |

Arbitrage appliqué : celui déjà tranché pour toute la spec (`tasks.md` → « Portes qualité »),
soit **aucune régression sur les fichiers touchés, prouvée fichier par fichier HEAD vs
worktree**. Preuve refaite ici par `git archive HEAD` dans un répertoire temporaire et
exécution des mêmes commandes sur les deux états. Les deux FAIL sont de la dette préexistante
concentrée hors périmètre.

## Ce que ça change

Un seul défaut, deux occurrences : **une population définie par un identifiant de
`usage_metadata` sans prédicat de `billing_origin_product`**.

| Table | Prédicat ajouté | Effet mesuré sur l'historique |
|---|---|---|
| `pipeline_cost_daily` | `billing_origin_product IN ('DLT')` | **113 085 lignes / 37 100,15 $** de faux DLT à retirer ; 10 499 identifiants `SQL` contre 9 298 `DLT`, donc plus de la moitié de la population listée n'était pas du DLT |
| `cluster_cost_daily` | `billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')` | **0 ligne retirée**, **134 jours-cluster** corrigés de **791,02 $** de coût de service managé sur **97 clusters réels** |

Trois décisions de conception, détaillées dans `tasks.md` → « T001c — décisions tranchées » :

1. **Liste blanche, pas liste noire** — `AI_FUNCTIONS` est apparu le 2025-11-07 et `DATABASE`
   le 2025-09-09 dans ce compte : une liste noire écrite en 2025-08 les aurait admis en
   silence. Le faux positif coûteux en FinOps est la sur-facturation.
2. **Purge par paramètre de run** (`one_off_purge`), pas par `absent_row_delete_guard` dans la
   spec — l'interdiction portée par `WAREHOUSE_UTILIZATION_DAILY_SPEC` est respectée, le
   registre n'est jamais muté (`dataclasses.replace` sur une dataclass frozen), et le retour au
   régime permanent est l'**état par défaut**. Le paramètre est délibérément **absent** de
   `resources/job_dcm_gold_dbx_compute.yml`, ce qu'un test verrouille.
3. **`forecast_daily` : résidu accepté, mesuré et borné** — `FORECAST_HORIZON_DAYS = 7` et le
   filtre `horizon_date` du backend (`compute_metrics_forecast.py:80-83`, période par défaut
   `today-29 → today`) font sortir les ≈ 7 800 lignes périmées de la vue par défaut vers le
   **2026-10-15**. Donner un `watermark_column` à `FORECAST_DAILY_SPEC` est **rejeté** :
   `horizon_date` est prospectif là où un watermark borne une fenêtre rétrospective.

## Validation sur donnée réelle — `dev_local`

Exigence de l'utilisateur : *« pour la partie data à la fin d'une tâche déploie, teste et
valide la donnée »*. Fait, avec une limite nommée plus bas.

`databricks bundle validate` puis `deploy -t dev_local` (profil OAuth `dcm-dev`) : OK.

### 1. Le SQL réellement généré par le code livré, joué en lecture seule

Les deux builders ont été appelés avec un faux `spark` pour **capturer la requête produite**,
puis cette requête exacte a été exécutée en `SELECT` agrégé via la Statements API. Ce n'est
donc pas une réécriture à la main de la logique : c'est le code livré, sur la donnée réelle.

| Cible | Attendu (calculé depuis `curated`) | Rendu par le code livré | ✅ |
|---|---|---|---|
| `pipeline_cost_daily` | 439 883 lignes / 9 298 pipelines / 347 264,22 $ | **439 883 / 9 298 / 347 264,22 $** | ✅ identique |
| `cluster_cost_daily` | 5 389 217 lignes / 3 211 139,3x $ / 0 `serverless` | **5 389 217 / 3 211 139,35 $ / 0** | ✅ identique |

Et les 439 883 lignes attendues côté pipelines valent exactement 552 968 − 113 085, ce qui
recoupe la mesure d'orphelines par une seconde voie.

### 2. Le run réel : `gold_cluster_cost_daily`, `full_refresh`

`bundle run --only gold_cluster_cost_daily --params full_refresh=true` → **TERMINATED
SUCCESS en 115 s**. `--only` a bien isolé la tâche (21 tâches `SKIPPED DISABLED`), ce qui
écarte au passage `gold_job_cluster_cost_daily`, qui échouerait tant que la migration T001b
n'est pas faite.

| Contrôle | Avant | Après | Prédit | ✅ |
|---|---:|---:|---|---|
| lignes | 5 389 217 | **5 389 217** | 0 retirée | ✅ |
| clusters distincts | 5 209 802 | **5 209 802** | inchangé | ✅ |
| `SUM(cost_usd)` | 3 211 930,37 $ | **3 211 139,35 $** | −791,02 $ | ✅ **−791,02 $** |
| `sku_group = 'serverless'` | 129 | **0** | improductible | ✅ |
| `sku_group = 'photon'` | 202 270 | **202 295** | +25 | ✅ |
| `sku_group = 'classic'` | 5 186 818 | **5 186 922** | +104 | ✅ |

Trace Delta, qui confirme la thèse au niveau du stockage — version **424**, `MERGE` :

```
numTargetRowsUpdated = 5 389 217 | numTargetRowsInserted = 0 | numTargetRowsDeleted = 0
```

`0 inserted` : la nouvelle définition ne produit aucune ligne que la table n'avait pas.
`0 deleted` : rien n'avait à être supprimé — c'est la signature exacte de « 0 orpheline, 134
lignes corrigées en valeur », et la démonstration que la purge n'a pas sa place ici.

Chaîne aval relancée ensuite (`--only gold_cluster_cost_rolling+,gold_cluster_efficiency_daily+`,
`full_refresh=true`), l'ordre étant porté par le `depends_on` du job — 9 tâches.

`gold_cluster_cost_rolling` : **SUCCESS en 120 s**, et **0 ligne `sku_group = 'serverless'`** sur
les 4 fenêtres (225 / 318 / 600 / 1 342 lignes). Trois valeurs de `_generated_at` y subsistent,
ce qui est le comportement **attendu** de cette table : son `absent_row_delete_guard` est
`t._generated_at < date_add(current_date(), -7)`, donc les lignes récentes que le recalcul ne
produit plus survivent 7 jours. C'est la contre-épreuve de la décision n°2 ci-dessus — cette
grâce fonctionne ici parce que la table a plusieurs générations, alors que
`pipeline_cost_daily` n'en a **qu'une**, où elle aurait supprimé 0 ligne en rapportant un succès.

`gold_cluster_efficiency_daily` en `full_refresh` recalcule des percentiles fenêtrés sur
**29 310 974 lignes** de `curated_dbx_compute_node_timeline` (451 959 clusters, rétention
**2026-07-06 → 2026-09-09**, soit ~65 jours — pas deux ans, contrairement à ce que la première
version de ce paragraphe affirmait ; mesuré le 2026-09-10). Tâche **serverless**
(`environment_key: gold_compute_env`, `PERFORMANCE_OPTIMIZED`), donc sans événements de cluster à
inspecter ; timeout du job à 4 h, aucun timeout par tâche. Encore en cours au moment d'écrire ce
rapport, avec 6 tâches en attente derrière (`cluster_efficiency_rolling`, `cluster_governance`,
`job_efficiency_*`, `pipeline_efficiency_*`, `recommendations`). C'est un rafraîchissement de
**conséquence**, pas une validation du livrable T001c, qui porte sur `cluster_cost_daily` et est
complète ci-dessus.

**Prédiction posée avant que le MERGE n'écrase la table**, donc falsifiable. La correction ne se
propage à `estimated_savings_usd` que via `cost_daily_table`, dans la formule
`cost_usd × (1 − recommended_core_count / current_core_count)` appliquée aux seuls jours-cluster
sous-utilisés. Mesuré :

| Grandeur | Valeur |
|---|---:|
| jours-cluster corrigés, tout l'historique | **134** (97 clusters, 791,02 $) |
| dont dans la fenêtre `node_timeline` | **70** (336,70 $) |
| dont portant une `estimated_savings_usd` non NULL | **11** |
| `estimated_savings_usd` sur ces 11 lignes, avant | **200,46 $** |
| prédit après (`ratio × coût corrigé`) | **106,61 $** |
| delta prédit | **−93,85 $** |

Les 134 / 97 / 791,02 $ sont ici **reproduits par une troisième voie indépendante** (agrégation
des lignes de facturation hors liste blanche, jointe à la dimension cluster dédupliquée et
filtrée sur `cluster_source IN ('JOB','UI','API','PIPELINE','PIPELINE_MAINTENANCE')`), après la
prédiction en lecture seule et le run réel.

> #### ⚠️ Errata 2026-09-10 — la prédiction n'est pas testable par ce run, et deux chiffres de ce paragraphe étaient faux
>
> Ce paragraphe se terminait par : « *Le total table avant est 465 994 lignes / 451 959 clusters /
> **19 802,14 $** d'économies estimées : il ne descendra à 19 708,29 $ que si le `full_refresh` ne
> bouge rien d'autre […]. **Le test qui fait foi est donc celui sur les 11 lignes**, pas le total.* »
> **Les deux affirmations sont retirées.** Vérifié après coup par voyage dans le temps Delta
> (`VERSION AS OF`) sur `gold_dbx_compute_recommendations`, qui donne l'état « avant » exact au lieu
> de le reconstruire :
>
> | Grandeur | Publiée ci-dessus | **Mesurée (time travel)** |
> |---|---:|---:|
> | lignes de la table | 465 994 | **246 343** |
> | objets distincts | 451 959 | **230 651** |
> | `SUM(estimated_savings_usd)` | 19 802,14 $ | **144 514,21 $** |
>
> Aucun de ces trois chiffres n'a jamais décrit cette table : **451 959 est le nombre de clusters de
> `curated_dbx_compute_node_timeline`**, cité correctement quinze lignes plus haut, puis recopié par
> contamination dans une ligne qui parlait d'une autre table. Les deux autres ont suivi. La leçon est
> celle déjà tirée au §2 de « Ce que j'ai corrigé » : **un chiffre voisin dans le même paragraphe est
> le premier candidat à l'erreur**, et un état « avant » se lit dans l'historique Delta, il ne se
> reconstruit pas.
>
> Surtout, **la prédiction des 11 lignes n'est pas départageable par ce run**. Ce qui a réellement
> bougé entre les deux versions :
>
> | Population | Lignes déplacées | Delta | Compatible avec T001c ? |
> |---|---:|---:|---|
> | `CLUSTER` / `RIGHTSIZING` | 35 | **−87,63 $** | **non, pas en totalité** |
> | dont **à la hausse** | **19** | — | **impossible** |
> | dont à la baisse | 16 | — | oui |
> | `WAREHOUSE` | 26 | **−433,16 $** | **non** — T001c ne touche pas ces tables |
>
> Une liste blanche qui ne fait que **retirer** des lignes de facturation ne peut que faire *baisser*
> un coût, donc *baisser* une économie estimée : **les 19 hausses ont nécessairement une autre
> cause**, et les 26 lignes `WAREHOUSE` la nomment — le run de chaîne a rafraîchi en même temps
> `cluster_efficiency_daily`, dont les percentiles ont été recalculés sur la rétention courante de
> ~65 jours (§ ci-dessus). **Le run a changé deux variables à la fois.**
>
> L'accord apparent entre le **−93,85 $** prédit et le **−87,63 $** observé est donc une
> **coïncidence d'agrégation** (16 baisses compensées par 19 hausses d'origine étrangère), pas une
> confirmation. Il aurait été facile — et faux — de la présenter comme telle.
>
> Statut de la prédiction : **ni confirmée ni réfutée**. Son mécanisme reste validé par les preuves
> qui, elles, isolent une seule variable : l'égalité au centime du §1 sur le SQL généré, et le
> `MERGE` v424 à `0 inserted / 0 deleted` du §2. Pour la trancher il faudrait rejouer
> `recommendations` **sans** rafraîchir `cluster_efficiency_daily` — hors périmètre de T001c, et sans
> intérêt propre puisque la formule est déjà vérifiée en amont.
>
> Retenir la règle générale : **une prédiction n'est falsifiable que si le run qui la teste ne change
> qu'une chose.** `DESCRIBE HISTORY` + `operationMetrics` et `VERSION AS OF` sont les instruments qui
> révèlent le facteur de confusion ; ici, `numTargetRowsDeleted = 0` suffisait à prouver qu'un MERGE
> ne pouvait pas avoir rétréci la table de 465 994 à 246 343 lignes.

`gold_pipeline_cost_rolling` n'est **délibérément pas** relancé : son amont
`pipeline_cost_daily` n'a pas été purgé (§3 ci-dessous), le relancer ne ferait que recalculer
depuis une donnée encore fausse. Sa relance appartient au même lot que la purge.

### 3. 🔴 Ce qui n'a **pas** pu être exécuté : la purge de `pipeline_cost_daily`

`databricks jobs submit` avec `one_off_purge=true` + `full_refresh=true` a été **refusé par le
classifieur de permissions**. C'est le run qui supprime 113 085 lignes ; le refus est
cohérent avec les deux refus déjà consignés (`DROP TABLE`, `ALTER TABLE … RENAME`). **Aucune
formulation de contournement n'a été cherchée** — le refus demande que l'utilisateur décide, et
contourner un contrôle est interdit par CLAUDE.md et les règles cyber.

Ce que cela laisse et ne laisse pas comme risque :

- le **code** est validé sur donnée réelle (§1 ci-dessus, au centime et à la ligne près) ;
- la **table** `gold_dbx_compute_pipeline_cost_daily` reste dans son état d'avant, avec ses
  113 085 lignes de faux DLT. Elle n'est **pas** dans un état intermédiaire : rien n'a été
  écrit dessus ;
- l'action reste à faire, à l'identique, par l'utilisateur ou avec son accord. La procédure
  exacte est dans le docstring de `entrypoint._apply_one_off_purge` et le payload prêt à
  soumettre a été construit depuis la tâche déployée.

`cluster_cost_daily`, lui, n'avait besoin d'aucune suppression : il est validé de bout en bout.

## Ce que j'ai corrigé après le subagent

Le subagent a relevé **7 affirmations fausses dans mon propre brief** — dont le diagnostic
§10.4, l'exhaustivité de `sku_group`, la prémisse d'orphelines côté clusters, et le fait que la
grâce de 7 j ne pouvait pas servir de levier de purge. Vérification faite, il avait raison sur
tous les points portants. Corrigés de ma main en conséquence :

1. **`proposition.md` §10.4, réécrit une deuxième fois.** Ma v3, commitée en `f812263`, était
   fausse sur la cause (« la table ingère des endpoints » — les 3 963 `cluster_id` d'endpoints
   étaient déjà écartés par le `WHERE cluster_type <> 'OTHER'`, qui **masquait** le défaut), sur
   le montant (1 286,28 $ au lieu de 791,02 $) et sur l'effet (129 lignes « retirées » au lieu
   de 0). Un errata `11 bis` le dit explicitement, plutôt que de réécrire l'histoire.
2. **Le « piège de méthode » du §10.4, inversé.** J'avais conclu que la mesure par cluster était
   l'artefact et la mesure par ligne la bonne. C'est le contraire : le grain du gold est le
   **jour-cluster**, ma requête par ligne répondait donc à une question que la table ne pose
   pas. La leçon réécrite est « mesurer au grain de la table cible ».
3. **`job_cluster_cost_daily.py:129-137`**, docstring de ma main qui annonçait « le correctif
   est le même que côté pipeline (T001c) : porter `billing_origin_product` dans le grain, pas
   ajouter un filtre » — or T001c a fait exactement l'inverse. Réécrit, remesuré sur
   l'historique (**5** produits non-`JOBS` portent `job_id`, pas 2 ; **659,96 $** sur
   1 819 847,46 $), et la différence de fond est nommée : cette table est un rollup
   d'**orchestration** (un job possède ce qu'il déclenche), les deux autres des rollups de
   **ressource**. Nouvelle mesure au passage : **zéro** ligne de facturation ne porte à la fois
   `job_id` et `dlt_pipeline_id`, donc la disjonction annoncée dans ce docstring tient.
4. **§10.1 : trois chiffres voisins étaient mélangés.** 113 085 / 37 100,15 $ (lignes gold que
   le correctif ne produit plus, grain complet), 37 100,58 $ (contamination côté `curated`) et
   113 072 / 37 101,73 $ (somme des sous-totaux par produit, qui compte deux fois les 19 lignes
   d'éventail et ignore `compute_kind`). Les trois sont désormais publiés avec leur définition.

## Findings

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py:236: 🟡 risk: `one_off_purge` est un levier de suppression accessible a tout run manuel des 23 tables gold de ce job. Les trois refus fail-fast (full_refresh obligatoire, watermark obligatoire, garde-fou deja present) plus l'absence volontaire du parametre dans le YAML plus le filet « sortie vide = pas de suppression » couvrent les cas connus, et la trace est la version Delta. Assume : c'est le prix a payer pour ne pas armer un garde-fou permanent sur une table de facturation, ce que specs.py interdit explicitement
specs/025-serverless-compute-page/review-report-T001c.md:1: 🟡 risk: la purge de pipeline_cost_daily (113 085 lignes) est refusee par le classifieur, donc T001c est livre avec une moitie validee sur donnee reelle et une moitie validee en lecture seule uniquement. La table concernee reste dans son etat d'avant, pas dans un etat intermediaire
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_daily.py:224: 🟢 note: la branche `sku_group = 'serverless'` est desormais inatteignable et conservee comme temoin, avec un test qui interdit de la retirer. Un lecteur pressé la prendra pour du code mort ; le commentaire et le test disent pourquoi elle reste
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/grain_resolution.py:103: 🟢 note: troisieme occurrence du meme defaut (un id de usage_metadata sans predicat de produit), volontairement hors perimetre : 1 paire sur 179 043, aucun effet mesurable. A traiter si le ratio bouge
resources/job_dcm_gold_dbx_compute.yml:1: 🟢 note: aucun parametre de job optionnel n'a ete ajoute pour `one_off_purge`, par choix. La consequence est qu'une purge passe forcement par `databricks jobs submit`, dont le run n'apparait pas dans la liste de l'IHM (verifie, CLI v1.10.0) : la trace qui fait foi est la version Delta
```

0 🔴 blocker · 2 🟡 risk · 3 🟢 note

## Checklist

| Point | Résultat |
|---|---|
| Secret / `.env` / credential dans le diff | **aucun** — `grep -inE "dapi[0-9a-f]\|DATABRICKS_TOKEN\|client_secret\|password\|api[_-]?key\|token *=\|dbfs:/\|dbutils\.fs"` sur le diff staged → 1 seule occurrence, **cette ligne-ci**, qui cite le motif de recherche. Aucune autre |
| Authentification Databricks | profil OAuth `dcm-dev` uniquement (keyring OS, `auth_type: databricks-cli`). Le profil `[DEFAULT]` porte un PAT prohibé : **jamais utilisé** |
| Anti-patterns `dcm-python` | aucun : pas d'import relatif, pas de `print`, docstrings Google, `from __future__ import annotations`, typage complet sur les 3 fonctions ajoutées |
| Critères d'acceptation | §10.1 et §10.4 couverts par du code **et** des tests ; le 3ᵉ (`grain_resolution.py:103`) est explicitement hors périmètre, en finding |
| Périmètre ⊆ intake | ✅ `pipelines/gold_dbx_compute/` + ses tests, `docs/spike/`, `specs/025-…`. Aucun autre package |
| Tests pour tout changement de comportement | ✅ +18 tests. Les deux prédicats sont testés sur l'**expression entière** (les deux lignes du `WHERE`), pas sur un fragment — un `in query` sur la seule première ligne restait vrai alors que le prédicat manquait. Assertions négatives (`NOT IN` absent) pour verrouiller la liste blanche |
| Small PR | ✅ 11 fichiers de code, +637 / −24, un seul sujet |
| DDL / DML sur la plateforme | aucun DDL. Un `MERGE` non destructif (0 suppression, trace Delta v424). La suppression, elle, est **refusée par le classifieur** et non exécutée |
| `--no-verify` | non |
| Déploiement `-t prod` | non — `dev_local` uniquement |

## Verdict

Le correctif fait ce qu'il annonce, et les deux moitiés du défaut sont traitées **différemment
parce qu'elles le sont** : purge côté pipelines, `full_refresh` seul côté clusters. La moitié
clusters est validée de bout en bout sur donnée réelle, chiffre par chiffre, y compris au niveau
de la trace Delta. La moitié pipelines est validée sur le SQL réellement généré par le code
livré, mais son écriture est bloquée par le classifieur de permissions — signalé comme risque,
non contourné, et la table reste dans un état cohérent. Les gates de package échouent sur de la
dette préexistante hors périmètre, avec parité HEAD prouvée fichier par fichier. Trois
affirmations fausses de ma propre main ont été corrigées, dont une déjà commitée.

**Errata du 2026-09-10** (encadré au §2) : deux chiffres de ce rapport décrivaient une autre table
que celle annoncée, et la prédiction sur les 11 lignes de `recommendations` est **retirée du statut
de preuve** — le run qui devait la tester rafraîchissait aussi les percentiles d'efficacité, donc il
changeait deux variables. Le verdict reste **PASS** : la prédiction portait sur une **conséquence
aval**, jamais sur le livrable, et les deux preuves qui isolent une seule variable — l'égalité au
centime sur le SQL généré (§1) et le `MERGE` v424 à `0 inserted / 0 deleted` (§2) — sont intactes.

**Verdict**: **PASS**
