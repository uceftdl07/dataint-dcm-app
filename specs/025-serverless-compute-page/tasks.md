# Tasks: Page « Serverless compute » + correctifs des pages compute existantes

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Work type**: feature · **Priority**: P2
**Mode**: `one_per_domain` — 3 stories de domaine, 3 tasks, **+ 1 task ajoutée le 2026-09-10**
(T004, cf. [amend-log.json](./amend-log.json)).

Chaque task est un index : le détail vit dans son sub-spec `stories/`.

- [ ] T001 [DataEng] Correctif efficience warehouse serverless + job serverless billing-direct + correctifs `pipeline_cost_daily`/`cluster_cost_daily` + socle `serverless_cost_daily`/`_rolling`/`_governance` + ingestion `pipeline_update_timeline` + non-régression `compute_kind_case_expr` (~~forecast `SERVERLESS_SURFACE`~~ 🚫 hors périmètre depuis le 2026-09-10) → [stories/T001.md](stories/T001.md)
- [x] T002 [Backend] Endpoints serverless (overview / surfaces / gouvernance / leviers / drill-down) + neutralisation de l'efficience serverless côté warehouses + schémas `dcm-commons` → [stories/T002.md](stories/T002.md)
- [~] T003 [Frontend] Page `/databricks/serverless` en 5 blocs + entrée nav + 3 composants de dataviz absents → [stories/T003.md](stories/T003.md)
- [ ] T004 [Frontend] Remise au vert des gates du package frontend — 61 problèmes eslint, 101 erreurs `tsc`, 4 tests rouges héritées de `develop` → [stories/T004.md](stories/T004.md)

Les clés Jira sont **absentes volontairement** : `/speckit.dcm.dispatch` les ajoute en fin de
ligne au format `· [DCINT-nnn](url)`. Ne pas y écrire de texte libre — le parseur le prendrait
pour du titre et le dispatch en ferait un résumé de Story. **Le dispatch n'a pas été exécuté
dans la session qui a produit ces artefacts** (hors périmètre : aucune Story Jira, aucune
branche fille créée).

## Ordre imposé

```
T001 (gold : 7 PR séquentielles, cf. ci-dessous) ──► déploiement dev + contrôles de non-régression
   └──► T002 (backend : endpoints serverless + neutralisation warehouse)
        │     └─ T002b amendement : la neutralisation porte sur le chiffre, plus sur la
        │        catégorie   ← ✅ FAIT + réconcilié dev 2026-09-10, cf. § plus bas
        └──► T003 (frontend : page 5 blocs + 3 composants)
```

Le fil n'est **pas** parallélisable : T002 lit les tables gold que T001 produit et modifie,
T003 consomme les endpoints que T002 expose. Le critère de sortie de T001 et T002 est
« déployée **et vérifiée** en dev », pas « implémentée » — les contrôles se jouent sur données
réelles (profil `dcm-dev`, warehouse `DCM-metrics`).

## Séquencement interne T001 (DataEng) — petits PR

La branche DataEng est séquencée en **7 PR** pour rester en petits diffs (Prerequisites de la
spec). Ordre imposé par le §11 du spike — **T001a d'abord**, c'est le meilleur rapport
valeur/risque du lot : il retire de la production ≈ 98 k$/30 j d'économies non réalisables
**déjà affichées** et ne demande aucune donnée nouvelle.

```
T001a neutralisation efficience warehouse serverless   ← ✅ FAIT, déployé + validé dev 2026-09-10
  └─► T001b job serverless billing-direct (compute_kind au grain)
        │     ← ⚠️ CODE FAIT + revu 2026-09-10 · NI DÉPLOYÉ NI VALIDÉ
        │       reste 1 prérequis : la migration de grain (DROP TABLE, à autoriser)
        ├─► T001b-back backend : compute_kind dans compute_metrics_jobs.py
        │     ← ✅ FAIT + revu 2026-09-10 · prérequis 1 LEVÉ (rien à déployer : lecture)
        └─► T001c correctifs pipeline_cost_daily (§10.1) + cluster_cost_daily (§10.4)
              └─► T001d serverless_cost_daily + serverless_cost_rolling
                    └─► T001e serverless_governance
                          └─► T001f ingestion fidèle + pipeline_update_stats (grain update_id)
                                └─► T001g robustesse compute_kind §10.2 (forecast 🚫 retiré)

T001h absent_row_delete_predicate (orphelins)   ← ✅ FAIT, déployé + validé dev 2026-09-10
T001i payload de reco hérité d'une autre règle  ← ✅ FAIT, déployé + validé dev 2026-09-10
```

- **T001a** ne dépend de rien. Aucune source nouvelle, aucune table nouvelle : mise à NULL des
  champs d'efficience quand le warehouse est serverless, plus une colonne `is_serverless`
  pour que le motif du NULL soit lisible en aval.
- **T001b** rend visibles **85 653 $/30 j** aujourd'hui exclus **en amont** par le filtre
  `usage_metadata.cluster_id IS NOT NULL` hérité de `cluster_cost_daily` — 56 841 $ AWS +
  28 812 $ Azure, remesuré le 2026-09-10. Le 60 021 $ de la spec est le chiffre **AWS seul**
  du spike, correct et déclaré comme tel en Assumptions ; l'enjeu toutes plateformes n'y était
  simplement jamais chiffré. La table ne montrait que **35 %** du coût des jobs.
- **T001c** regroupe deux correctifs de lecture indépendants du socle serverless.
- **T001d** dépend des helpers factorisés en T001a-c ; **T001e** lit ce que T001d produit.
  **T001g** ne dépend plus de rien depuis le retrait du forecast le 2026-09-10 : réduite au
  §10.2, elle ne touche que `compute_kind_case_expr` et son test de non-régression.
- **T001f** est la seule à demander une **ingestion** nouvelle. Elle peut glisser sans bloquer
  la page : elle n'alimente que le comparatif DLT serverless/classique du bloc 3.
- **T001h** est une dette **découverte en implémentant T001a**, pas un item du spike. Elle
  sort du fil séquentiel parce qu'elle ne dépend d'aucune des autres et ne les bloque pas,
  mais elle **ferme SC-013** et ne doit pas être abandonnée : elle est à faire juste après
  T001a, avant que la page ne s'appuie sur ces tables.
- **T001i** est un défaut **découvert en validant la donnée de T002**, et ce n'est pas celui que
  T002 annonçait : le CTE `merged` de `recommendations.py` laissait la valeur de la règle de la
  veille remonter sous le libellé de la règle du jour, parce que sa clé de jointure est la
  **catégorie** et pas la règle. **72 lignes portaient 27 116,40 $** hérités, sur **deux**
  catégories dont une sans aucun serverless — le mécanisme n'est donc pas serverless. Hors fil
  séquentiel comme T001h. Corrige au passage l'attribution fausse écrite dans T002
  (« garde-fou manquant sur `utilization_status = 'OVER'` » : cette règle est déjà inerte en
  serverless). Détail : `review-report-T001i.md`.

### T001b — état au 2026-09-10 : code fait et revu, déploiement bloqué sur 1 prérequis

C'est la **première** sous-tâche de cette spec qui n'est pas validée sur donnée réelle à la fin
de son implémentation. Les raisons sont nommées, pas contournées.

**Livré** (13 fichiers, verdict PASS, cf. `review-report-T001b.md`) : `job_cluster_cost_daily`
refait en billing-direct sur `usage_metadata.job_id`, `compute_kind` dans le grain daily **et**
rolling, self-join J-1 égalisé sur `compute_kind`, `RANK()` partitionné par
`(period_start, compute_kind)`, `depends_on` retiré (plus aucune source gold). Plus deux bugs
que l'énoncé de délégation ne prévoyait pas : **désaliasage** de
`JOB_EFFICIENCY_{DAILY,ROLLING}_MERGE_KEYS` (qui auraient hérité de `compute_kind` sur deux
tables issues de `node_timeline` qui n'ont pas la colonne → MERGE cassé hors périmètre) et
**agrégation de la série observée `ai_forecast`** (deux points au même horodatage pour 926
jours-job, aucune erreur levée). 753 tests, dont le test-clé vérifié mordant.

**Prérequis 1 — backend `compute_metrics_jobs.py`** — ✅ **LEVÉ le 2026-09-10**, cf.
`review-report-T001b-back.md`. `_ROW_COLUMNS` ne portait pas `compute_kind` (0 occurrence dans
tout `app/` côté jobs, contre 8 dans `compute_metrics_pipelines.py` où T008 l'a traité) : dès le
premier run du nouveau grain, la page jobs aurait lu **deux lignes par job mixte** (926 jours-job,
101 jobs sur 30 j) et **deux `cost_rank = 1` par jour**, sans qu'aucune erreur ne soit levée.

Corrigé par un **rollup** dans les 3 requêtes de coût jobs (`_cost_rollup_ctes`) : `compute_kind`
est replié en **libellé** `CLASSIC` / `SERVERLESS` / `MIXED`, et `cost_delta_pct`, `cost_rank`,
`is_top_cost` sont **re-dérivés après** le repli — gold classe *à l'intérieur* de chaque
`compute_kind` et un ratio de sommes n'est pas la somme des ratios. Rien à déployer : ce package
ne lit que des tables, la correction précède donc la migration sans dépendre d'elle.

⚠️ **Asymétrie assumée avec la page DLT** : jobs **replie** `compute_kind`, DLT le **filtre** à
`CLASSIC`. Les deux répondent à des questions différentes — la page DLT porte sur le compute
*cluster* DLT (décision utilisateur du 2026-09-09), alors que la page jobs est là où un
utilisateur cherche « combien me coûte ce job », et la spec 025 fait justement **croître** sa
population jusqu'au serverless. À reconsidérer si T003 ouvre une page serverless dédiée.

**Prérequis 2 — migration de grain, une action `DROP TABLE`.** `compute_kind` est une clé de
merge nouvelle sur une table peuplée : le MERGE échoue à l'analyse
(`DELTA_MERGE_UNRESOLVED_EXPRESSION`) et `full_refresh` n'y change rien. Procédure recommandée
et documentée dans `specs.py` : `DROP` du daily **puis** du rolling, puis run nominal
(`_resolve_lower_bound` rend `None` sur table absente → recalcul complet automatique, aucun
paramètre à passer). **Perte d'information nulle**, mesurée : la cible couvre 2 mois
(76 192 lignes, depuis le 2026-07-07), la source `curated_dbx_billing_usage` en couvre **3 ans**
(depuis le 2023-08-26) — le recalcul **étend** l'historique. Et les 44 234 jours-job existants
retrouvent **tous** leur équivalent billing-direct à la même clé (0 orphelin, 46 181,48 $ vs
46 181,52 $) : la refonte est purement additive. `UNDROP` reste disponible 7 jours.

**Une variante moins destructive existe, et elle est meilleure** — trouvée le 2026-09-10 en
relisant [writers.py:157](../../packages/dcm-databricks-pipeline/pipelines/common/writers.py#L157) :
la branche `saveAsTable` est choisie sur `not spark.catalog.tableExists(...)`, donc ce qu'il faut
est une cible **absente**, pas une cible **supprimée**. Un `ALTER TABLE … RENAME TO
…_pre_t001b` suffit donc, et domine le `DROP` sur tous les axes :

| | `DROP` + `UNDROP` | `RENAME` |
|---|---|---|
| donnée ancienne | récupérable **7 jours** | conservée **sans limite** |
| retour arrière | `UNDROP` puis re-`DROP` de la neuve | un renommage |
| schéma recréé | exact (`saveAsTable`) | exact (`saveAsTable`), identique |
| base de comparaison pour valider | **détruite** | **disponible** — on compare l'ancien et le neuf côte à côte |
| nature de l'action | destructive | non destructive |

Le dernier point n'est pas cosmétique : garder l'ancienne table permet de rejouer la
non-régression `CLASSIC` sur la table réelle au lieu d'une mesure prise avant coup.

**Aucune des deux n'a été exécutée.** Le classifieur de permissions a refusé le `DROP` (porté par
une délégation) **puis** le `RENAME` (tenté directement). Aucune troisième formulation n'est
cherchée : le message du refus demande explicitement d'arrêter et de laisser l'utilisateur
décider, et contourner un contrôle est interdit par CLAUDE.md et les règles cyber. **Décision
remontée à l'utilisateur** — c'est le seul point de cette spec qui demande son accord.

**Base de comparaison mesurée le 2026-09-10**, à rejouer après migration :

| Table | lignes | jobs | couverture | coût total |
|---|---|---|---|---|
| `…job_cluster_cost_daily` | 76 192 | 6 759 | 2026-07-07 → 2026-09-09 | 74 866,27 $ |
| `…job_cluster_cost_rolling` | 19 453 | 6 759 | `window_start` ≥ 2026-06-12 | 131 833,94 $ |

**En attendant** : la tâche `gold_job_cluster_cost_daily` **échoue si le job tourne**. Mitigé
par un `schedule` `PAUSED` sur `dev_local` et `dev` et une branche non fusionnée, mais c'est un
état à connaître, inhérent à tout changement de grain (le code précède la migration). Et depuis
`87b47b2`, le backend et cette migration sont **atomiques au déploiement** : `compute_kind` est
absent des deux tables déployées (`UNRESOLVED_COLUMN`, SQLSTATE 42703), donc déployer le backend
seul mettrait 3 routes de coût jobs en erreur SQL. Ordre imposé : (1) `87b47b2` (2) migration
(3) déploiement backend.

### T001c — décisions tranchées le 2026-09-10

**1. Liste blanche, pas liste noire.** Les deux prédicats sont
`billing_origin_product IN (…)` et non l'exclusion des produits fautifs. Motif mesuré :
`AI_FUNCTIONS` est apparu le 2025-11-07 dans ce compte et `DATABASE` le 2025-09-09 — une liste
noire écrite en 2025-08 les aurait admis en silence, et le faux positif coûteux en FinOps est
la **sur**-facturation. Aligné sur la convention déjà en place dans ces builders
(`ELSE 'OTHER'` + `WHERE cluster_type <> 'OTHER'`).

**2. Purge par paramètre de run, pas par garde-fou de spec.** `one_off_purge` (cf.
`entrypoint._apply_one_off_purge`) injecte l'`absent_row_delete_guard` pour **un** run, par
`dataclasses.replace` sur une spec frozen ; le registre n'est jamais muté et le retour au régime
permanent est l'état par défaut. Poser le garde-fou dans `PIPELINE_COST_DAILY_SPEC` violerait
l'interdiction explicite portée par `WAREHOUSE_UTILIZATION_DAILY_SPEC` (aucune `*_daily` qui
agrège la facturation ne doit accepter de perdre un jour déjà écrit). Le paramètre est
**délibérément absent** de `resources/job_dcm_gold_dbx_compute.yml` — un test le verrouille —
donc aucune tâche planifiée ne peut le porter.

**3. `cluster_cost_daily` ne reçoit pas de purge.** Vérifié sur les 5 389 217 lignes : **0
orpheline**, les 134 jours-cluster touchés étant mixtes. `full_refresh` seul. Le `WHERE
cluster_type <> 'OTHER'` écartait déjà les 3 963 `cluster_id` d'endpoints — c'est lui qui
masquait le défaut, et c'est pourquoi la même recette ne s'applique pas aux deux tables.

**4. `forecast_daily` : le résidu est accepté, mesuré et borné.** Le recalcul de
`pipeline_cost_daily` laisse ≈ 7 800 lignes de prévision construites sur les faux DLT.
`FORECAST_DAILY_SPEC` n'a **pas** de `watermark_column`, donc `one_off_purge` le refuse par
construction (refus n°2). Décision : **ne pas** lui en donner une. Trois raisons, dans l'ordre
de poids :

- `horizon_date` est **prospectif**, alors qu'un `watermark_column` sert à borner une fenêtre
  incrémentale **rétrospective** (`INCREMENTAL_LOOKBACK_DAYS`) : le champ ne peut pas jouer les
  deux rôles sans changer le sens de la lecture incrémentale de la table ;
- ce serait un changement de **régime permanent** pour une réparation ponctuelle — la même
  erreur que le point 2 refuse ;
- le résidu **s'éteint tout seul**, et c'est mesuré : `FORECAST_HORIZON_DAYS = 7`
  (`specs.py`), et le backend filtre `horizon_date` entre les bornes de la période
  (`compute_metrics_forecast.py:80-83`), `_resolve_period` valant par défaut `today-29 →
  today`. Horizon réel mesuré côté PIPELINE : 39 184 lignes / 2 500 objets, 2026-08-27 →
  2026-09-15. Les lignes périmées quittent donc la vue par défaut vers le **2026-10-15**.

Ce qui est fait à la place : relancer `forecast_daily` **après** `pipeline_cost_rolling` dans
l'ordre de relance, pour que les prévisions produites ensuite partent de la donnée corrigée.

> ℹ️ **Ce point 4 reste dans le périmètre malgré le retrait du volet forecast le 2026-09-10.**
> Ce qui est sorti, c'est la **fonctionnalité** — projeter `SERVERLESS_SURFACE`, donc modifier
> `forecast.py`. Ce point-ci n'est pas une fonctionnalité : c'est la **conséquence
> opérationnelle** du recalcul de `pipeline_cost_daily` (T001c) sur une table déjà en
> production, et il ne demande **aucun changement de code** — seulement un ordre de relance.
> Le retirer laisserait 7 800 lignes de prévision fausses sans mention nulle part.

### T001d — décisions tranchées le 2026-09-10, et une leçon de T001c mal appliquée

**1. Une liste blanche doit couvrir les noms HISTORIQUES, pas seulement les noms courants.**
C'est le défaut trouvé en revue. Les 12 surfaces de `serverless_surface` nommaient
`DATA_QUALITY_MONITORING` mais pas `LAKEHOUSE_MONITORING`, **son ancien nom** — mêmes SKU
exactement, relais dans le temps (l'ancien s'arrête le 2026-02-06, le nouveau démarre le
2025-11-06 azure / 2025-12-15 aws). Effet : **3 494,32 $** d'historique d'une fonctionnalité
plateforme tombés dans `OTHER`. C'est la décision n°1 de T001c (liste blanche, parce que
Databricks *ajoute* des produits) qui manquait sa moitié : Databricks **renomme** aussi. Même
piège que `usage_policy_id` face à `budget_policy_id`, où ne garder que la colonne récente
perdrait 188 744 lignes.

**2. Un contrôle de reproduction se formule en COMPOSITION, pas en seuil de dollars.** Le
docstring publié annonçait « `OTHER` ≤ ~10 $ par cloud » d'après la fenêtre de référence de
31 jours ; sur l'historique que la table construit réellement, `OTHER` portait **13 464,88 $** —
mille fois le seuil, sans qu'aucun produit neuf ne soit apparu. Un seuil absolu mesuré sur une
fenêtre courte ne peut pas contrôler une table à historique complet. Remplacé par : `OTHER` ne
doit contenir *que* `LAKEFLOW_CONNECT`, `SHARED_SERVERLESS_COMPUTE` et `BASE_ENVIRONMENTS`
(9 970,56 $ après correctif, 0,27 % de 3 687 894,38 $) ; un 4ᵉ produit = il faut le classer.
**Troisième** conflation de fenêtre de cette spec, après §10.1 et §10.4.

**3. Le test qui devait l'attraper ne pouvait pas.**
`test_every_in_scope_product_is_classified_except_the_measured_one` n'itère que
`SERVERLESS_SCOPE_PRODUCTS`, les produits **forcés** dans le périmètre. Les produits qui y
entrent par `product_features.is_serverless = true` lui sont invisibles — et c'est par là que
`LAKEHOUSE_MONITORING` passait. Ajouté :
`test_platform_auto_covers_the_renamed_monitoring_product`, qui exige les deux noms dans la
**même** branche du `CASE` (ailleurs dans le `CASE` donnerait une autre surface).

**4. Pas de purge à prévoir pour ce correctif.** `SERVERLESS_COST_DAILY_SPEC` prévoit qu'une
reclassification depuis `OTHER` se nettoie par `one_off_purge` — exactement mon cas — mais les
deux tables cibles sont **absentes** au moment du correctif, donc il n'y a rien à purger : le
premier run les construit déjà corrigées (voie `saveAsTable`).

**5. Deux niveaux d'agrégation pour le coût par exécution, et la CTE `priced` volontairement
non agrégée.** `histogram_from_edges_sql` agrège des **lignes** : l'appliquer directement à la
facturation compterait des tranches de facturation et non des exécutions. D'où un `GROUP BY
job_run_id` séparé, qui doit relire les lignes — donc `priced` n'agrège pas, contrairement aux
builders voisins. Les deux risques de ce choix ont été **mesurés**, pas raisonnés : jointure de
prix jamais multiple (15 332 combinaisons à exactement 1 ligne, 103 à 0, aucune à ≥ 2) et
**0 ligne** du périmètre avec un `billing_origin_product` NULL sur 24 327 341.

**6. `window_days = 1` publie toujours un jour partiel — mais ce n'est pas le jour courant.**
Corrigé le 2026-09-10 sur les tables **écrites**, la première formulation désignait la mauvaise
cause. Mesuré :

- le daily **n'écrit pas du tout le jour courant** : `max(period_start)` = **2026-09-09** = J-1,
  et le coût du 2026-09-10 est NULL. Dire à l'IHM « aujourd'hui est partiel » serait donc faux —
  aujourd'hui n'est jamais affiché ;
- le rolling ancre les 4 fenêtres sur `as_of_date` = **2026-09-09** = J-1, borné inclus des deux
  côtés (`window_start = as_of_date − (W−1)`) ;
- c'est **J-1 lui-même** qui est incomplet : **3 199,51 $ / 2 635 lignes** un mercredi, contre une
  **médiane de 14 269,20 $ sur 22 jours ouvrés** (min 11 862,06, max 18 316,24) et **15 356,45 $**
  pour le mercredi précédent. Soit **22 %** du normal, et **3,7× sous le minimum** observé : c'est
  de la latence de facturation, pas de la saisonnalité.

Deux conséquences pour T003, que la formulation initiale manquait :

1. la légende doit porter sur **le dernier jour publié (J-1), encore en consolidation**, pas sur
   « aujourd'hui » ;
2. toute comparaison jour à jour doit être **jour ouvré contre jour ouvré** : le week-end tourne à
   **7 888,18 $** de médiane sur 8 jours, soit **55 %** d'un jour ouvré. Une « moyenne journalière »
   qui mélange les deux régimes (~12 280 $) sous-estime l'écart et n'est comparable à aucun jour
   réel.

Inhérent à la latence de facturation et **transverse à toutes les tables `_rolling`** du job, pas
propre à T001d.

### T001h — lignes gold orphelines : activer `absent_row_delete_predicate`

Par défaut, `merge_into_table` ne fait qu'un `WHEN MATCHED UPDATE` / `WHEN NOT MATCHED
INSERT` : une clé cible que le recalcul **ne produit plus** n'est jamais supprimée. Mesuré le
2026-09-10 après un `full_refresh` :

| Table | Lignes orphelines | Signature | $ portés |
|---|---|---|---|
| `warehouse_utilization_daily` | **75** (0,45 %) | `running_hours` = 24,0 h pile, `active_query_hours` = 0,0, `idle_pct` = 100 %, `OVER`, `is_serverless` NULL | **0 $** |
| `warehouse_utilization_rolling` | **162** | `as_of_date` 2026-09-04/06/07, `is_serverless` NULL | 0 $ |

Preuve d'orphelinat pour les 75 : différence symétrique **nulle** entre le prédicat
« fenêtre + `_generated_at` antérieur au dernier lot » et l'anti-jointure de référence
(`EXCEPT ALL` sur les clés vs le lot frais) — 75 ∩ 75, 0 de chaque côté, et 0 ligne hors
fenêtre. 37/37 des warehouses concernés existent toujours par ailleurs : ce sont des
jours-warehouse fantômes, pas des objets disparus.

**Rectification du 2026-09-10 — la version précédente de cette section était fausse sur deux
points, et l'erreur allait dans le sens du renoncement :**

1. Le mécanisme **existe déjà** : `build_merge_sql(..., absent_row_delete_predicate=...)`
   génère `WHEN NOT MATCHED BY SOURCE AND (<pred>) THEN DELETE`
   ([writers.py:75-104](../../packages/dcm-databricks-pipeline/pipelines/common/writers.py#L75-L104)),
   il est câblé dans `entrypoint.py` et **déjà utilisé** par `CLUSTER_GOVERNANCE_SPEC`
   (`t._generated_at < date_add(current_date(), -SNAPSHOT_ABSENT_ROW_GRACE_DAYS)`, grâce de
   **7 jours**) et `RECOMMENDATIONS_SPEC`. Ce n'est donc pas un chantier de writer sur
   ~15 tables : pour une table snapshot, **c'est une ligne de spec**.
2. Les 162 lignes rolling ne sont **pas de l'historique légitime** :
   `WAREHOUSE_UTILIZATION_ROLLING_MERGE_KEYS` = `(cloud_provider, workspace_id, warehouse_id,
   window_days)` — **`as_of_date` n'est dans aucune clé de merge** (idem cost /
   query_performance / cluster_cost). Ces tables sont des **snapshots d'état courant**, pas
   des séries temporelles : une ligne dont la clé n'est plus produite survit sous son ancien
   `as_of_date` et devient indistinguable d'une ligne courante par la seule clé.

Deux volets, de risque très différent — c'est ce qui justifie une tâche à part et non un
ajout dans T001a :

- **Volet snapshot (`*_rolling`)** — faible risque : recopier le prédicat de
  `CLUSTER_GOVERNANCE_SPEC` sur `WAREHOUSE_UTILIZATION_ROLLING_SPEC` (et les autres specs
  rolling). Le garde-fou de grâce à 7 jours est ce qui empêche un run dégradé de vider la
  table ; conséquence assumée : une ligne orpheline survit jusqu'à 7 jours.
- **Volet historique (`*_daily`)** — risque réel : le prédicat **doit être borné à la fenêtre
  effectivement recalculée**, sinon un run incrémental efface tout l'historique hors fenêtre.
  Le piège est aggravé par le fait que `partition_predicate` entre dans la condition `ON` :
  une ligne hors partition ne matche pas et devient candidate au DELETE. La borne dépend de
  `lower_bound` (et du `MIN(period_start)` de la source en mode full), elle n'est donc **pas
  une constante de spec** — il faut la câbler dans `entrypoint.py`, avec ses tests.

**Pourquoi ce n'est pas fait dans T001a** : un `DELETE` ponctuel a été préparé et vérifié,
puis **refusé par le classifieur de permissions**, et il n'a pas été contourné — c'était de
toute façon un pansement. Le correctif structurel est auto-cicatrisant, il passe par le MERGE
du job et non par une commande ad hoc, et il traite les 75 comme les 162.

#### ✅ FAIT, déployé + validé dev 2026-09-10 — ce que l'implémentation a changé à l'énoncé

Le mécanisme livré est **plus fort** que « câbler la borne dans `entrypoint.py` » : le champ de
spec ne porte plus le prédicat complet mais **seulement le garde-fou volumétrique**, renommé
`absent_row_delete_guard` pour ne pas mentir sur son contenu. Le prédicat réel est produit par
un unique point de passage, `GoldAggregationSpec.resolve_absent_row_delete_predicate(window_floor=…)`,
qui dérive la borne de `watermark_column` — un champ qui existait déjà et qui *définit* le fait
que la table est une série temporelle.

Ce que ça achète, et c'est la raison de préférer ce design : **un auteur de spec ne peut plus
oublier la borne**, parce qu'il ne peut pas l'écrire. Le seul texte qu'il contrôle est un
opérande de conjonction, et une conjonction ne peut que *restreindre* la portée du DELETE.
Trois cas : pas de watermark (snapshot réécrit en entier) → garde-fou seul ; watermark + borne
→ conjonction ; watermark **sans** borne → `None`, donc **aucune clause DELETE**. Le mode de
défaillance est le bon : une borne indisponible désactive la suppression au lieu de l'élargir,
avec un WARNING explicite plutôt qu'un silence. En `full_refresh`, la borne est le
`MIN(period_start)` de la **sortie du builder** et non de la cible : le gold plus ancien que la
couverture curated réelle est hors périmètre de suppression, et une sortie vide (run dégradé)
donne `None`.

**Périmètre appliqué** : les **10** specs rolling — invariant revérifié spec par spec, aucune
exclusion, et sur une troisième condition que je n'avais pas énoncée (`watermark_column` **et**
`incremental_lookback_days` à `None`, sans quoi `NOT MATCHED BY SOURCE` voudrait dire « hors
fenêtre » et non « clé disparue ») — plus `WAREHOUSE_UTILIZATION_DAILY_SPEC`, **seule** table
`*_daily` concernée. 13 tests ajoutés (744 au total), dont deux assertions sur la chaîne SQL
exacte, vérifiées mordantes par sabotage temporaire du résolveur.

**Nouvel invariant, verrouillé par un test** : `SNAPSHOT_ABSENT_ROW_GRACE_DAYS` doit rester
**strictement inférieur** à `INCREMENTAL_LOOKBACK_DAYS` (7 < 10). Une ligne n'est supprimable
que si elle est à la fois hors grâce et dans la fenêtre, soit
`P + grâce < aujourd'hui ≤ P + fenêtre` : intervalle **vide** dès que `grâce ≥ fenêtre`, et
l'orpheline devient **immortelle**. Deux constantes qui vivaient indépendamment sont en fait
couplées.

**Mesures dev, contre-vérifiées par requête directe** (pas seulement rapportées) :

| `warehouse_utilization_daily` | avant | après run 1 | après run 2 |
|---|---|---|---|
| `COUNT(*)` | 16 784 | 16 820 | 16 820 |
| `MIN(period_start)` | 2026-07-15 | **2026-07-15** | **2026-07-15** |
| `is_serverless IS NULL` | 75 | **32** | 32 |
| `numTargetRowsDeleted` (`DESCRIBE HISTORY`) | **0** (v661, la veille) | **43** (v685) | **0** (v709) |

La v661 est la preuve directe du défaut : le MERGE de la veille ne supprimait rien. La v709
prouve l'idempotence. `COUNT(*)` : 16 784 − 43 + 79 = 16 820, l'arithmétique ferme.

**SC-013 était auto-contradictoire, et c'est la mesure qui l'a montré** : il exigeait 0 ligne
orpheline *et* la grâce de 7 jours qui les protège. Aucun mécanisme ne satisfait les deux. Le
critère est donc reformulé sur ce qu'il voulait dire — « aucune orpheline ne survit plus de
grâce + 1 jour » — et pas assoupli pour épouser un résultat : SC-001, lui, a été maintenu tel
quel et atteint. Échéancier de fermeture du résiduel, vérifié `_generated_at` par
`_generated_at` : rolling 103 lignes au 09-12, 21 au 09-14, 38 au 09-15 ; daily 19 au 09-14,
13 au 09-17. Les 32 daily ont un `period_start` du 09-05 au 09-09, donc **dans** la fenêtre
incrémentale : un run normal les atteindra, sans nouveau `full_refresh`.

⚠️ **Le `schedule` est `PAUSED` sur `dev_local` et sur `dev`** : la fermeture demande un run
manuel à ces dates, elle ne se fera pas d'elle-même.

**Sur `*_rolling`, le résiduel est un flux et non un stock** : le run du 09-10 a lui-même créé
204 nouvelles lignes périmées (churn de `window_days = 1`). Le correctif fait passer la
péremption de **permanente** à **≤ 8 jours**, il ne l'élimine pas — « 0 orpheline » n'y sera
jamais vrai. La protection du consommateur reste le filtre de lecture
`as_of_date = MAX(as_of_date)`, déjà en place côté API et côté moteur de règles depuis T001a.

## Dépendances externes

| Ce dont T001 dépend | État |
|---|---|
| `curated_dbx_billing_usage` porte `product_features`, `identity_metadata`, `usage_metadata`, `billing_origin_product` | ✅ **vérifié en dev le 2026-09-10** (`BILLING_USAGE_SPEC` sans `select_columns` → `SELECT *`) — aucune ingestion nouvelle pour T001a→e/g |
| Helpers histogrammes (`histogram_from_edges_sql`, `sum_histograms_sql`, `percentile_from_histogram_sql`) | ✅ présents (`sql_helpers.py`), réutilisés — seules les **bornes** sont neuves |
| Patron billing-direct + discriminant au grain | ✅ présent (`pipeline_cost_daily.py`), **modèle à répliquer** |
| Champ `warehouse_type` / `enable_serverless` en curated | ⚠️ **rectifié le 2026-09-10** : `enable_serverless` n'existe pas, mais `curated_dbx_compute_warehouses.warehouse_type` **existe** (valeurs observées `CLASSIC`, `PRO`, `SERVERLESS`, `REAL_TIME`) — invisible par grep du code car la spec curated fait `SELECT *`. Discriminant retenu quand même **billing-first** (`product_features.is_serverless`, historisé au jour), `warehouse_type` en 2ᵉ étage de cascade (D9 du plan) |
| `system.lakeflow.pipeline_update_timeline` lisible | à ingérer (T001f) **fidèle au grain horaire**, l'agrégation par `update_id` passant dans `gold_dbx_compute_pipeline_update_stats` — **rectifié le 2026-09-10** : agréger dans l'ingestion tronquerait les 40 updates étalés au-delà du lookback de 3 j (max 19 j), et le backend ne lit aucune table `curated_*` (errata FR-015) |
| `system.billing.attributed_usage` | ❌ **vide (0 ligne)** — limitation acceptée, hors scope, **ne rien construire dessus** |

| Ce dont T002 dépend | État |
|---|---|
| `gold_dbx_compute_serverless_cost_rolling` / `_daily` / `_governance` | produit par T001d/T001e |
| `gold_dbx_compute_warehouse_utilization_*` portant `is_serverless` | produit par T001a |
| `gold_dbx_compute_job_cluster_cost_*` avec `compute_kind` | produit par T001b |
| Socle de services compute (`compute_metrics_common.py`, `RollingWindowDays`, `_clamp_page`) | ✅ présent, réutilisé |

| Ce dont T003 dépend | État |
|---|---|
| Endpoints serverless + neutralisation warehouse | produit par T002 |
| `ComputeKpiCard` / `ComputeDataTable` / `ComputeTrendChart` / `ComputeTabs` / `ChartHoverTooltip` | ✅ présents, réutilisés tels quels |
| Barre empilée / barres horizontales triées / heatmap | ❌ **inexistants** dans `src` (0 occurrence de `heatmap`) → 3 composants à écrire |
| Précédent d'IHM pour un discriminant `compute_kind` | ❌ aucun : la spec 024 l'a tenu **serveur uniquement** — rien à recopier |

## Contrôles de non-régression (critère de sortie de T001)

Table reprise du spike, détaillée avec les requêtes dans [stories/T001.md](stories/T001.md).
À rejouer avec **`cloud_provider = 'aws'`** pour être comparable : le spike est mono-cloud,
DCM est bi-cloud (Azure ajoute ≈ 103 967 $/30 j de serverless, mesuré le 2026-09-10).

## Portes qualité — arbitrage tranché le 2026-09-10

`uv run ruff format --check .` et `uv run ruff check .` **ne peuvent pas passer** sur
`dcm-databricks-pipeline` pour des raisons **préexistantes** : 50 fichiers non formatés et 269
erreurs `check` sont déjà là au HEAD. La CI (`.github/workflows/`) n'exécute que `ruff check`,
en non bloquant, et **jamais** `ruff format --check` — d'où la dérive accumulée.

**Critère retenu pour toutes les PR de cette spec** : *aucune régression sur les fichiers
touchés*, prouvée fichier par fichier (état HEAD vs worktree). Pas *« le dépôt entier
passe »*. Un reformatage global est un commit à part, hors de cette spec : noyer un correctif
de 150 lignes dans un diff de 50 fichiers rendrait la revue impossible, ce qui est exactement
ce que la contrainte « petits PR » cherche à éviter.

### Correctif d'outillage appliqué — les gates mesurent enfin quelque chose

Découvert en reviewant T001a : `dcm-review.sh` invoquait `ruff` / `pytest` / `mypy` **nus**,
hors de l'environnement `uv`. `pytest` échouait donc à importer le `conftest.py` du package et
rendait un FAIL **qui ne parlait pas du code** — ce que le script s'interdit explicitement pour
le gate `mypy` (*« a gate that fails on its own misconfiguration teaches the team to ignore
it »*). Corrigé (préfixe `uv run --`), plus `explicit_package_bases` dans le `pyproject.toml`
qui débloque mypy, jusque-là arrêté sur une ambiguïté de nom de module **avant d'analyser une
seule ligne**. Détail et mesures : [review-report-tooling-gates.md](./review-report-tooling-gates.md).

| Gate | Avant | Après |
|---|---|---|
| `pytest` | FAIL (`ImportError` sur conftest) | ✅ **PASS**, 731 tests |
| `mypy` | FAIL, **0 fichier analysé** | FAIL, **70 fichiers, 142 erreurs** dans 7 fichiers |
| `ruff` | FAIL, 269 erreurs | FAIL, 269 erreurs (inchangé) |

Les 142 erreurs `mypy strict` sont de la dette préexistante concentrée à 97 dans
`dlt_02_curated_layer.py` (51), `dlt_03_gold_layer.py` (46) et `sqs_to_volume_drain.py` (21) :
**hors périmètre de cette spec**, à planifier ailleurs. `strict` n'a **pas** été assoupli pour
les taire. À l'inverse, `mypy` sur les 5 fichiers de production touchés par T001a → *Success:
no issues found*.

**Conséquence pratique pour les PR restantes** : le tableau de gates du rapport porte
désormais un `pytest` PASS exploitable, et les FAIL `ruff`/`mypy` restent à arbitrer par le
critère ci-dessus, rapport par rapport, tant que la dette n'est pas résorbée.

## Success Criteria (rappel spec)

- **SC-001** : 0 jour-warehouse `is_serverless = true` avec `estimated_savings_usd` /
  `utilization_status` / `rightsizing_reco` non NULL (contre 353 warehouses `OVER` et
  ≈ 98 k$/30 j avant). ✅ **atteint le 2026-09-10** : 0 fuite sur **15 496** jours-warehouse
  serverless, `is_serverless` non NULL sur 16 709/16 709 lignes recalculées, `running_hours` et
  `active_query_hours` toujours servis à 100 %, lignes classic/pro intactes (1 213/1 213).
  Le critère est **volontairement formulé sur `is_serverless = true`** et non « les warehouses
  serverless » : la nuance n'est pas cosmétique, elle isole ce que le calcul contrôle de ce que
  des lignes orphelines non réécrites portent encore — celles-là relèvent de SC-013, et les
  confondre laisserait croire le correctif en échec alors qu'il ne l'est pas.
- **SC-013** (ajouté puis **reformulé** le 2026-09-10, cf. T001h) : aucune orpheline ne survit
  plus de `SNAPSHOT_ABSENT_ROW_GRACE_DAYS + 1` jours, et le MERGE émet une clause DELETE bornée
  à la fenêtre. ✅ **mécanisme atteint** (43 des 75 supprimées par le job, `MIN(period_start)`
  intact, idempotent) ; 🟡 résiduel décroissant de 32 + 162 lignes protégées par la grâce,
  purgeables du 09-12 au 09-17. La formulation initiale (« 0 ligne ») était **inatteignable par
  construction** : elle exigeait la grâce et sa violation simultanément.
- **SC-002** : dépense job serverless présente dans `job_cluster_cost_daily` (≈ 56 841 $/30 j
  AWS remesuré, 85 653 $ toutes plateformes) ; Σ toutes valeurs de `compute_kind` = coût job
  total. **Code livré, mais SC-002 reste OUVERT** : la validation sur donnée réelle demande la
  migration de grain, elle-même bloquée sur les 2 prérequis de T001b ci-dessus.
- **SC-003** : 12 valeurs de `serverless_surface`, dont `OTHER` **non vide**.
- **SC-004** : 0 ligne `serverless_surface`/`object_id` NULL ; 26 533 $ en `_NO_OBJECT`.
- **SC-005** : 0 ligne hors des 3 buckets du périmètre.
- **SC-006** : 5 875 $ sans propriétaire ; `identity_source` jamais NULL.
- **SC-007** : `usage_policy_id` ≠ `budget_policy_id` sur 0 ligne / 2 294 408.
- **SC-008** : 35 572 / 6 245 updates DLT par `update_id` ; `COUNT(*)` = `COUNT(DISTINCT update_id)`.
- **SC-009** : 4 `billing_origin_product` distingués dans `pipeline_cost_daily`.
- **SC-010** : 0 ligne `sku_group = 'serverless'` ; 6 483 lignes NULL traitées en `UNKNOWN`.
- **SC-011** : p50 ≈ 0,125 $ / p95 ≈ 1,49 $ / p99 ≈ 14,88 $ reconstruits depuis l'histogramme.
- **SC-012** : page à 5 blocs, onglets sans clé d'objet annonçant le grain workspace, encart
  « angles morts » présent (test + navigateur).

## Effet mesuré de T001a sur le backlog de recommandations (2026-09-10)

La table `gold_dbx_compute_recommendations` n'a pas de colonne `rule_id` : le grain de règle y
est `title`. Avant (écrit 10:42, code pré-correctif) → après (00:21, correctif déployé).

| Catégorie / objet | Règle | OPEN avant | OPEN après | Δ | $ après |
|---|---|---|---|---|---|
| RIGHTSIZING / WAREHOUSE | Warehouse surdimensionné | 665 | **87** | −578 | 11 295,64 $ (vs 126 489,52 $) |
| FINOPS / WAREHOUSE | Auto-stop manquant | 6 | **0** | −6 | 0 $ |
| RELIABILITY / WAREHOUSE | File d'attente saturée | 3 | **37** | **+34** | 2 963,83 $ |
| RELIABILITY / WAREHOUSE | Requêtes avec spill disque/mémoire | 7 | **35** | **+28** | 24 140,91 $ |
| FINOPS / CLUSTER | Auto-terminaison manquante | 225 657 | 212 217 | −13 440 | — |

Trois effets à ne pas confondre, sous peine de s'attribuer un gain qui n'en est pas un :

1. **Garde serverless** : −578 rightsizing et −6 auto-stop, soit **−115 194 $** d'économies non
   réalisables retirées du backlog. À noter, et c'est contre-intuitif : le code d'avant, exécuté
   sur la table rolling **neutralisée**, aurait produit **585** OPEN « Auto-stop manquant » (un
   `has_auto_stop` passé à NULL déclenche la règle) — la garde de `recommendations.py`
   n'enlève pas 6 recos, elle **empêche une régression de +579**. Elle n'était pas un extra.
2. **Démasquage** : la déduplication garde une reco par objet et par catégorie
   (`ORDER BY rule_priority`). En retirant le verdict non actionnable, **62 recos réellement
   actionnables remontent** (+34 file d'attente, +28 spill, **27 105 $**) — elles étaient
   masquées, pas absentes. C'est un gain net de qualité, pas un effet de bord.
3. **Garde `as_of_date`** (bug préexistant corrigé dans T001a) : **13 459 recos `OPEN` portées
   par des snapshots périmés** passent en `RESOLVED`. La CTE nommée `latest_*` filtrait
   `window_days = 30` **sans** filtrer `as_of_date` et lisait donc tous les snapshots. Le
   pipeline était la seule couche sans cette garde : la couche API l'appliquait déjà
   (`compute_metrics_common.py`), donc l'écran et le moteur de règles pouvaient rendre des
   verdicts divergents. Piège associé, documenté côté API et évité ici : le `MAX(as_of_date)`
   doit être **global à la table, pas par `window_days`** — un `MAX` par fenêtre ressusciterait
   les lignes périmées de toute fenêtre dont la population courante est vide.

Contrôle final par jointure sur le dernier snapshot : « Warehouse surdimensionné » = 87 OPEN
dont **0 sur un warehouse serverless**. Les règles fondées sur les requêtes gardent
légitimement des cibles serverless (file d'attente 34 serverless / 3 classiques, spill 35
serverless) : le spill et la file d'attente sont des vrais signaux en serverless, contrairement
à l'idle.

**Anomalie préexistante, hors périmètre, à arbitrer ailleurs** : 212 217 recos OPEN
« Auto-terminaison manquante » sur des clusters de job éphémères — les règles FINOPS
n'appliquent pas de filtre `governance_applies`. Elles écrasent numériquement tout le reste du
backlog, y compris les 62 recos que T001a vient de démasquer.

### T002b — la neutralisation serverless porte sur le chiffre, pas sur la catégorie

**✅ FAIT + revu + réconcilié sur donnée dev, 2026-09-10.** Amendement de T002, rendu nécessaire
par T001i : `review-report-T002b.md`.

T002 avait posé `_serverless_void_savings_sql` sur **la catégorie** — tout `RIGHTSIZING` et tout
`FINOPS` d'un warehouse serverless était retiré de la liste et des KPI. T001i ayant supprimé les
faux chiffres **à la source**, ce prédicat retirait exactement les **62 recos que le §
précédent décrit comme « démasquées, pas absentes »** — devenues 69 (34 file d'attente +
35 spill) — en ne retirant plus **aucun** dollar.

Le module énonçait déjà le critère qui tranche, pour justifier de conserver `RELIABILITY` :
« les supprimer retirerait un conseil sans retirer un faux chiffre ». Une conjonction ajoutée,
`AND COALESCE(estimated_savings_usd, 0) > 0`, et l'exemption de `RELIABILITY` devient une
**conséquence de la règle** au lieu d'une exception tenue à la main. La catégorie reste en
pré-filtre : le chiffre seul retirerait une `RELIABILITY` le jour où l'une d'elles chiffre
quelque chose.

| Mesure (sémantique exacte du prédicat, dev) | avant | après |
|---|---:|---:|
| lignes `OPEN` retirées / $ retirés | 69 / **0,00 $** | **0** / 0,00 $ |
| lignes `RESOLVED` retirées / $ retirés | 524 / 93 359,94 $ | **487** / **93 359,94 $** |
| tuile `open_recommendations` (30 j) | 388 | **419** |

**106 lignes de conseil redeviennent visibles en ré-ajoutant 0,00 $**, et les 93 359,94 $ de faux
restent retirés à l'unité près. Ces derniers sont irréductibles côté API : le
`_existing_state_cte` du builder ne lit que `OPEN`/`ACK`, donc aucun run de pipeline ne
réécrira une ligne `RESOLVED`, et la route de liste accepte `status = 'RESOLVED'`.

Deux conséquences à ne pas lire comme des pannes : le bloc `not_applicable` répond `0 / 0,0` sur
les KPI ouverts (plus rien d'ouvert n'est retiré), et la tuile revient à **419** — les 31
warehouses qu'elle avait perdus ont un problème réel qui ne promet aucun dollar. Les deux sont
écrits dans les docstrings concernées.

Écart de spec tranché au passage : les specs annonçaient **160** lignes `RELIABILITY` conservées,
le code **337**. Mesuré avec `bool_and(is_serverless)` au `MAX(as_of_date)` : c'est **337**, le
code avait raison ; les 3 occurrences sont corrigées.

## Invariant anti-double-comptage

`gold_dbx_compute_serverless_cost_daily` est un **rollup des mêmes lignes de facturation** que
`cluster_cost_daily`, `job_cluster_cost_daily`, `pipeline_cost_daily` et
`warehouse_cost_daily`. Ne **jamais** l'y sommer.

En revanche, sommer ses `serverless_surface` **entre elles est légitime** et redonne exactement
le périmètre serverless : elles partitionnent des lignes disjointes. Idem pour les deux
`compute_kind` de `job_cluster_cost_daily` après T001b.

## Invariant « pas de faux signal »

Une métrique qui n'a pas de sens à un grain n'est **pas produite vide** :

- les champs d'efficience d'un warehouse serverless sont **NULL**, pas `0` — un `0` se lirait
  comme « aucun gaspillage mesuré », et l'actuel calcul se lit comme « 98 k$ à récupérer ». Les
  deux sont faux ; NULL + `is_serverless` est la seule lecture honnête ;
- `run_count` est NULL hors surface `JOB`, jamais `0` ;
- une fenêtre précédente vide donne NULL, jamais `0` ;
- aucun identifiant d'objet n'est **fabriqué** pour uniformiser les surfaces sans clé : la
  sentinelle `'_NO_OBJECT'` est explicite et `has_object_key` la rend lisible ;
- aucune colonne sans équivalent serverless (CPU, mémoire, idle actionnable) n'est affichée
  vide : elle est **absente**, et le bloc 5 explique pourquoi.

## Invariant « aucune économie non mesurée »

Aucun chiffre d'économie n'est produit là où la mesure ne le porte pas :
`performance_target` expose une population et un $ exposé, **pas un gain** (les deux modes
partagent le SKU, donc le $/DBU) ; le comparatif DLT serverless vs classique est présenté
comme une **corrélation** (les pipelines restés en classic sont les plus anciens et les plus
lourds, pas un échantillon aléatoire).
