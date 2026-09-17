# T007 — `curated_dbx_compute_warehouses` et `curated_dbx_lakeflow_jobs` en full load

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: `dataeng/023-warehouse-name-gold` (même branche que T001 : c'est la même chaîne)
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: rien côté code. Bloque la **vérification** de T001, pas son implémentation.
**Work type**: fix

## Pourquoi cette task existe

T001 a été implémentée, déployée et exécutée en dev : le code est correct, il résout tous les
noms que la source curated est capable de fournir. Les contrôles d'acceptation ont pourtant
mesuré **16 à 22 % de noms résolus** là où SC-001 en attend plus de 95 %.

La cause n'est pas dans le gold. Mesures en dev le 2026-09-07 :

| Mesure | Valeur |
|---|---|
| Warehouses distincts dans `system.compute.warehouses` | **1429** (235 workspaces, depuis 2023-08-14) |
| Warehouses distincts dans `curated_dbx_compute_warehouses` | **293** (depuis 2026-07-15) |
| Warehouses distincts dans `gold_…_query_performance_daily` | **691** |
| Gold ∩ curated, sur les 3 clés | **193** |
| Gold ∩ curated, sur `warehouse_id` seul | **193** — identique, donc **aucun** défaut de clé de jointure |
| Gold AWS ∩ `system.compute.warehouses` | **459 / 459** — couverture **100 %** atteignable |
| Gold AWS ∩ curated | 136 |

Et la preuve directe de la cause :

```
manquants | ct_avant_debut_ingestion | plus_recent_manquant
323       | 323                      | 2026-07-14T06:50:52
```

**323 sur 323** des warehouses manquants ont leur `change_time` le plus récent *antérieur* au
démarrage de l'ingestion curated, le plus tardif d'entre eux étant la veille exacte.

`WAREHOUSES_SPEC` (`pipelines/system_tables/specs.py:307`) porte
`watermark_column="change_time"` et `initial_lookback_days=INITIAL_BACKFILL_DAYS` (= 30).
Or `system.compute.warehouses` est une **dimension à évolution lente**, pas un journal
d'événements : le `change_time` d'une ligne peut avoir des années et la ligne décrire
pourtant l'état courant. Un premier run borné à `now - 30 jours` écarte définitivement tout
warehouse non modifié dans cette fenêtre, et le watermark n'avançant que vers l'avant, aucun
run ultérieur ne les rattrape.

> **Prémisse corrigée le 2026-09-07, en cours d'implémentation.** Cette story affirmait que
> `COMPUTE_CLUSTERS_SPEC` ne portait aucun watermark et que `WAREHOUSES_SPEC` était l'exception
> fautive du fichier. **C'est l'inverse** : `COMPUTE_CLUSTERS_SPEC` (`specs.py:252`) porte
> `watermark_column="change_time"` + `initial_lookback_days`, et warehouses était *alignée* sur
> ce patron. S'aligner sur les clusters aurait donc voulu dire **garder** le watermark.
> Le correctif est inchangé — il repose sur la mesure 323/323, pas sur cette comparaison — mais
> l'AC 1 est à lire « aligné sur les vraies specs full load du fichier » (`NODE_TYPES_SPEC`,
> `BILLING_LIST_PRICES_SPEC`, `WORKSPACES_LATEST_SPEC`, registres UC). Portée réelle du défaut
> mesurée en [research.md](../research.md) R1ter.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/system_tables/test_specs.py`

Ajoutés par la **seconde extension** (repli `run_name`, cf. ci-dessous) :

- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_daily.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/dlt_03_gold_layer.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_job_cluster_cost_daily.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/test_dlt_03_gold_layer.py`

## Sub-tasks

- [x] **Test d'abord** : `WAREHOUSES_SPEC.watermark_column is None` et
      `initial_lookback_days is None`, avec un nom de test qui **énonce la raison**
      (dimension à évolution lente, pas un journal) — sinon le prochain qui verra une table
      avec `change_time` remettra un watermark.
- [x] Retirer `watermark_column="change_time"` et `initial_lookback_days=INITIAL_BACKFILL_DAYS`
      de `WAREHOUSES_SPEC`. Conserver `merge_keys` et `azure_fetch_batch_size=AZURE_BATCH_NESTED`.
- [x] Commenter la spec sur le modèle des specs full-load voisines, en disant **pourquoi**
      cette table n'a pas de watermark alors qu'elle a une colonne de date : c'est un miroir
      d'état courant dont l'historique remonte à 2023, et un watermark y perd la longue traîne.
      Citer la mesure (1429 warehouses en source, 293 en curated) pour que le constat soit
      vérifiable et non une affirmation.
- [x] Décider explicitement de `purge_eligible` et **justifier** le choix : les autres specs
      full-load du fichier le portent, mais elles sont des référentiels sans historique
      (`node_types`, `list_prices`, registres UC). `system.compute.warehouses` conserve
      plusieurs lignes par warehouse (2583 lignes pour 1429 warehouses), et le gold s'appuie
      sur `change_time <= period_start` pour résoudre le nom **à la date du jour agrégé** :
      une purge qui ne garderait que l'état courant casserait cette résolution historique.
      Ne pas le mettre par simple mimétisme.
- [x] Vérifier qu'aucun autre `IngestionSpec` du fichier ne présente le même défaut : une
      table de dimension avec un `watermark_column`. Signaler ce qui est trouvé **sans le
      corriger** ici (hors périmètre) — c'est un constat à remonter, pas un chantier à ouvrir.
- [x] Gates : `uv run pytest`, `uv run ruff check`, `uv run mypy` sur les fichiers touchés.

### Extension arbitrée le 2026-09-07 — `LAKEFLOW_JOBS_SPEC`

La sous-tâche de relevé ci-dessus a trouvé deux specs porteuses du même patron. Mesure du
symptôme réel en dev ([research.md](../research.md) R1ter) :

| Table gold | Nom résolu | Suite |
|---|---|---|
| `cluster_cost_daily` / `_rolling` / `cluster_governance` (`cluster_name`) | **100 %** | `COMPUTE_CLUSTERS_SPEC` **non corrigée** : défaut latent sans effet mesuré, et la table est bien plus volumineuse. Relire en entier chaque run coûterait sans rien gagner |
| `job_cluster_cost_daily` (`job_name`) | **70,2 %** | `LAKEFLOW_JOBS_SPEC` **corrigée ici** |

Les clusters échappent au défaut parce qu'un cluster de job est éphémère : recréé à chaque
exécution, son `change_time` est toujours dans la fenêtre de 30 jours. Une définition de job,
comme un warehouse, vit des années sans être touchée — même mécanisme de perte, même correctif.

- [x] Même traitement que `WAREHOUSES_SPEC` sur `LAKEFLOW_JOBS_SPEC` (`specs.py:408`) : retirer
      `watermark_column` et `initial_lookback_days`, garder `merge_keys` et
      `azure_fetch_batch_size`, commenter le pourquoi avec la mesure des 70,2 %.
- [x] Même décision sur `purge_eligible`, avec sa propre justification : vérifier si un
      consommateur gold résout `job_name` à une date passée. C'est le cas
      (`job_cluster_cost_daily.py:161`), donc même conclusion — mais la borne **n'est pas la
      même** que celle des warehouses, et il ne fallait pas la recopier : le code jobs écrit
      `change_time < period_start + INTERVAL 1 DAY`, pas `change_time <= period_start`.
      Ne pas conclure par analogie avec les warehouses.
- [x] Test dédié, du même modèle que celui des warehouses, dont le **nom énonce la raison**.
- [x] Vérifier le volume de `system.lakeflow.jobs` avant de conclure que le full load est
      négligeable, comme les 2583 lignes l'ont été pour les warehouses. Si le volume rend
      l'affirmation fausse, **le dire** plutôt que de la recopier.
      → **fait, et l'affirmation était fausse** : 813 516 lignes contre 40 827 dans la fenêtre,
      ~20× de lecture par run. Sûr malgré tout, pour une raison vérifiée dans `readers.py` et
      non supposée — cf. [research.md](../research.md) R1ter.

#### Correction du 2026-09-07 — la mesure des 70,2 % visait la mauvaise table

`job_name` sur `gold_dbx_compute_job_cluster_cost_daily` était un **proxy**, pas le symptôme :
`rg gold_dbx_compute_job_cluster_cost packages/dcm-backend/app` ne renvoie rien — **aucun
service n'en lit la colonne**. À ce titre elle relevait du même statut que
`COMPUTE_CLUSTERS_SPEC` (défaut latent), ce qui aurait dû faire tomber la justification de
l'extension.

Ce n'est pas le cas, parce que le vrai consommateur est ailleurs et **pire touché**. La page
Lakeflow Jobs lit `gold_dbx_workflow_*` et affiche `workflow_name`, résolu par
`_lakeflow_latest_jobs()` (`dlt_03_gold_layer.py:103`) depuis `curated_dbx_lakeflow_jobs`, via
les deux vues `_wf_runs_bridge` et `_wf_task_runs_bridge` dont dérivent les 8 tables workflow.
Un job absent du curated ressort en `LEFT JOIN` à `NULL`, et `lakeflow_jobs.py:1056` retombe
sur `str(row["workflow_id"])` : **un identifiant affiché à la place du nom**, exactement le
symptôme de la demande côté warehouses.

Mesuré en dev avant reconstruction du gold (curated déjà en full load) :

| Table lue par la page | Lignes | `workflow_name` résolu |
|---|---|---|
| `gold_dbx_workflow_success_rate` — **la liste des jobs** | 418 569 | **29,9 %** |
| `gold_dbx_workflow_runs` | 1 058 670 | 62,3 % |
| `gold_dbx_workflow_tasks` | 2 736 597 | 69,1 % |

L'extension est donc justifiée, mais son critère de recette change de table : c'est
`workflow_name` sur `gold_dbx_workflow_success_rate` qu'il faut mesurer, pas `job_name`.

- [x] Reconstruire les tables workflow (pipeline DLT `dcm_dlt_pipeline`, rafraîchissement
      **sélectif** — pas le pipeline entier, qui rebâtirait aussi raw et curated) puis
      remesurer `workflow_name`.

### Constats remontés, non corrigés ici

La sous-tâche de relevé demandait de *signaler sans corriger*. Deux constats en sont sortis, en
plus de `COMPUTE_CLUSTERS_SPEC` :

> **Les deux constats ci-dessous ont été corrigés le 2026-09-07, dans T001** — le constat #2
> était faux sur sa conclusion, et SC-001 était bien exposé. Justification et mesure en
> [research.md](../research.md) R9c ; sous-tâches dans
> [T001](T001-warehouse-name-en-gold.md), section « Extension arbitrée du 2026-09-07 ». Les deux
> énoncés sont conservés tels qu'écrits, avec les lignes de code d'alors.

1. **Deux conventions de borne temporelle cohabitent** pour résoudre un libellé à une date
   passée. Famille warehouse : `change_time <= period_start` (`warehouse_cost_daily.py:151`,
   `warehouse_query_performance_daily.py:179`, `warehouse_utilization_daily.py:460`) — l'état
   **au matin** du jour agrégé. Famille cluster/job : `change_time < period_start + INTERVAL 1
   DAY` (`cluster_cost_daily.py:172`, `job_cluster_cost_daily.py:161`) — le dernier état **de
   la journée**. Les deux sont défendables ; ce qui ne l'est pas, c'est que rien n'explique
   pourquoi elles diffèrent.
   → **corrigé** : les 3 builders warehouse sont passés à la borne journée entière, il ne reste
   qu'une convention dans le dépôt.
2. **Conséquence mesurable de la variante warehouse** : une entité dont le premier
   `change_time` tombe *dans* la journée (donc le jour de sa création) n'a aucune ligne
   satisfaisant `<= period_start`, et sort avec `warehouse_name = NULL` ce jour-là précisément.
   Un jour par warehouse, sur les tables **quotidiennes** uniquement. Les `*_rolling` passent
   par `latest_attrs` et n'ont pas cette borne, donc **SC-001 n'est pas exposé** — c'est
   pourquoi ce n'est pas traité ici. T001 a délibérément aligné sa nouvelle CTE sur la
   convention de sa famille plutôt que d'introduire une troisième variante.
   → **faux, et c'est ce constat qui bloquait SC-001.** `latest_attrs` n'applique pas la borne,
   mais il **lit une valeur produite sous elle** : le nom de la ligne quotidienne au
   `period_start` le plus récent du warehouse. Pour un warehouse éphémère créé et utilisé le même
   jour, ce nom est `NULL`, et les 4 fenêtres en héritent. « Cette CTE n'a pas le prédicat » ne
   dit rien de la valeur qu'elle propage. Mesuré : 71 lignes sur `utilization` w90 et 20 sur
   `query_performance` w90, **100 % résolues** par la borne journée entière, 0 absente du curated.

### Seconde extension arbitrée le 2026-09-07 — le repli `run_name`

Après le passage en full load **et** la reconstruction sélective du gold, `workflow_name` est
passé de 29,9 % à **73,58 %** sur `success_rate` et `job_name` de 70,2 % à **94,9592 %** sur
`job_cluster_cost_daily` : mieux, mais **sous** le seuil de 95 % de l'AC. Le résidu n'est pas un
reste d'ingestion. Mesuré **à la source**, `system.lakeflow.job_run_timeline` contre
`system.lakeflow.jobs` :

| `run_type` | Couples `(job_id, run_id)` | Présents dans `jobs` |
|---|---|---|
| `JOB_RUN` | 15 433 | **100 %** |
| `WORKFLOW_RUN` | 171 611 | **0 %** |
| `SUBMIT_RUN` | 49 648 | **0 %** |

Seul un run issu d'une **définition de job persistée** a une ligne dans `system.lakeflow.jobs` :
c'est un plafond de conception, pas une perte. Aucun full load n'y change quoi que ce soit.

Une **seconde** source de nom existe pourtant, déjà ingérée et jamais lue :
`curated_dbx_lakeflow_job_run_timeline.run_name`. Mesuré sur les deux clouds, elle est
renseignée sur **exactement et seulement** les `SUBMIT_RUN` :

| `run_type` | Lignes | `run_name` non NULL |
|---|---|---|
| `SUBMIT_RUN` | 110 780 | **110 780 — 100,0000 %** |
| `JOB_RUN` | 923 906 | **0** |
| `WORKFLOW_RUN` | 192 902 | **0** |

Les deux sources de nom sont donc **disjointes par construction**, ce qui rend
`COALESCE(jobs.name, run_name)` **exact** et non heuristique — et rend inutile tout prédicat sur
`run_type` : en ajouter un serait une fausse précision, périmée au prochain type ajouté par
Databricks. Propriété verrouillée par un test sur les trois chemins.

Le `GROUP BY` de déduplication reste **obligatoire** malgré l'unicité mesurée : aucun des
106 602 `job_id` porteurs d'un nom n'en porte deux (`MAX(COUNT(DISTINCT run_name)) = 1`), mais
**2 `job_id` portent 2 `run_id`** — sans agrégation au grain job, ces lignes dupliqueraient les
lignes de coût jointes. Même famille de piège que le fan-out ×43 déjà documenté dans
`_lakeflow_latest_jobs()`.

`curated_dbx_lakeflow_job_task_run_timeline` **ne porte pas** `run_name` (la table système
l'expose, le spec curated ne la sélectionne pas) : le pont tâche passe donc par une lecture au
grain job (`_lakeflow_submit_run_names()`), alors que `_wf_runs_bridge` sort `run_name` de son
propre `groupBy` sans relecture. La duplication de la règle entre les deux chemins est
**assumée** : l'unifier obligerait `_wf_runs_bridge` à relire et rejoindre une table qu'il groupe
déjà, soit une régression de coût pour un gain de style. Mitigée par des docstrings qui se
citent mutuellement et un test par chemin.

- [x] Repli `COALESCE(job_name, run_name)` dans le builder gold compute
      (`job_cluster_cost_daily.py`, CTE `submit_run_names` **non bornée** par `lower_bound` :
      c'est un référentiel de nom, pas une source de fait) et dans les deux ponts DLT
      (`_wf_runs_bridge`, `_wf_task_runs_bridge`).
- [x] `run_name` **ne sort pas** du schéma des deux ponts : les deux ont un `select` final
      explicite, sinon la colonne s'ajouterait aux 8 tables gold qui en dérivent.
- [x] Commentaire de colonne `job_name` / `workflow_name` mis à jour sur les 2 specs compute et
      les 7 `_ddl` DLT — c'est la seule documentation visible dans Catalog Explorer.
- [x] Paragraphe ajouté au commentaire `purge_eligible` de `LAKEFLOW_JOBS_SPEC` : ce repli **ne
      rattraperait pas** une perte par purge (100 % sur les runs soumis, 0 % sur les runs issus
      d'une définition), pour que personne ne le lise comme un feu vert à purger.
- [x] **L'ordre des opérations est contraignant**, et un rejeu nominal ne suffit pas — même
      classe d'erreur que celle qui a coûté un run sur T001. Le builder compute écrit par
      `merge_into_table` sur une fenêtre incrémentale : les lignes historiques garderaient
      `job_name` NULL. Il faut **un** run avec `full_refresh=true`
      (`only=[gold_job_cluster_cost_daily, gold_job_cluster_cost_rolling]`, 4 min mesurées).
      `full_refresh` n'élargit ici que la **lecture** (`_resolve_lower_bound` → `None`),
      l'écriture reste un MERGE : aucune troncature, rejouable sans risque.
      Côté DLT **aucun** full refresh : les 8 tables workflow sont des vues matérialisées
      `@dlt.table` + `dlt.read` (batch), qu'un changement de requête invalide — le
      rafraîchissement **sélectif** suffit et les noms sont rétroactifs. Ne jamais full-refresher
      le pipeline entier : il contient des tables streaming (`raw_metrics`, dims par
      `apply_changes`) dont l'état serait détruit.
- [x] `refresh_selection` exige des noms **pleinement qualifiés** sur ce pipeline UC : les noms
      nus rendent `INVALID_REFRESH_SELECTION.INVALID_IDENTIFIER`, levée en
      `deployment.DeploymentException` ~14 s avant toute exécution du graphe.

Mesures après déploiement, `full_refresh` compute et rafraîchissement sélectif DLT :

| Table | Avant repli | Après repli | AC |
|---|---|---|---|
| `gold_dbx_compute_job_cluster_cost_daily` (`job_name`) | 94,9592 % | **99,7403 %** | > 95 % ✅ |
| `gold_dbx_compute_job_cluster_cost_rolling` (`job_name`) | — | **97,9607 %** | ✅ |
| `gold_dbx_workflow_task_health` (`workflow_name`) | — | **99,9360 %** | ✅ |
| `gold_dbx_workflow_tasks` | 69,1 % | **99,8003 %** | ✅ |
| `gold_dbx_workflow_runs` | 62,3 % → 73,58 % | **83,2118 %** | plafond source |
| `gold_dbx_workflow_success_rate` | 29,9 % → 34,55 % | **57,6195 %** | plafond source |

Le résidu est **intégralement** expliqué, et c'est le plafond de la source, pas un défaut
résiduel. Décomposé par `run_type` sur `gold_dbx_workflow_runs` :

| `run_type` | Lignes gold | Non nommées |
|---|---|---|
| `JOB_RUN` | 814 635 | **0** |
| `SUBMIT_RUN` | 106 604 | **0** |
| `WORKFLOW_RUN` | 185 863 | **185 863** |

814 635 + 106 604 = 921 239, soit **exactement** le compte nommé mesuré. Un `WORKFLOW_RUN` est un
run lancé depuis un notebook : il n'a de nom **dans aucune source** — ni définition de job, ni
`run_name`. Le seul moyen de le nommer serait d'en fabriquer un, ce que P9 interdit. C'est donc
un plafond assumé et documenté, pas un reste à corriger : `success_rate` restera sous 95 % tant
que la source n'expose pas de nom pour ce type de run.

## Acceptance Criteria

- [x] `WAREHOUSES_SPEC` et `LAKEFLOW_JOBS_SPEC` sont en full load, sans watermark, alignées sur
      les vraies specs full load du fichier (`NODE_TYPES_SPEC`, `BILLING_LIST_PRICES_SPEC`,
      `WORKSPACES_LATEST_SPEC`, registres UC) — **pas** sur `COMPUTE_CLUSTERS_SPEC`, qui porte
      le défaut.
- [x] Après ingestion en dev, `job_name` est résolu sur > 95 % de `job_cluster_cost_daily`
      (référence à battre : 70,2 %). → **99,7403 %**. Le full load seul ne suffisait pas
      (94,9592 %, sous le seuil) : il a fallu le repli `run_name` de la seconde extension.
- [x] Après ingestion en dev, `curated_dbx_compute_warehouses` couvre les 1429 warehouses de
      `system.compute.warehouses` côté AWS (et l'équivalent Azure). → **1429 / 1429 côté AWS,
      0 manquant**, 1937 warehouses distincts tous clouds confondus.
- [x] Le nom d'un run **soumis par API** est résolu depuis `run_name`, et celui d'un run issu
      d'une définition de job depuis `curated_dbx_lakeflow_jobs` : les deux sources sont
      disjointes, un `COALESCE` suffit et **aucun prédicat sur `run_type`** n'est écrit — prouvé
      par test sur les 3 chemins (builder compute, `_wf_runs_bridge`, `_wf_task_runs_bridge`).
- [x] La CTE / le `groupBy` de repli est **dédoublonné au grain job** : 2 `job_id` mesurés
      portent 2 `run_id`, et sans agrégation ils dupliqueraient les lignes de coût jointes.
- [x] Le repli **n'introduit aucune colonne** dans les schémas gold : `run_name` reste interne
      aux ponts, prouvé par test sur leur `select` final.
- [x] Le résidu non nommé est **entièrement attribué** : 185 863 lignes, toutes `WORKFLOW_RUN`,
      un type de run qui n'a de nom dans aucune source. Aucune valeur de repli fabriquée (P9).
      `gold_dbx_workflow_success_rate` reste donc à 57,6195 % — **plafond de source assumé**, et
      non un critère manqué.
- [x] Après réexécution des 4 tâches gold, SC-001 est atteint : `pct_nomme > 95` sur les 4
      fenêtres de `gold_…_query_performance_rolling` et de `gold_…_utilization_rolling`
      ([quickstart.md](../quickstart.md) §4.2).
- [x] La résolution historique reste correcte : un warehouse renommé porte, à un `period_start`
      donné, le nom qu'il avait **à cette date** — la bascule en full load ne doit pas aplatir
      l'historique de `change_time`.
- [x] Aucune régression sur les autres tables curated : le `for_each` du job
      `dcm_system_tables` continue de passer.

## Notes cyber

Aucun secret, aucun nouvel accès, aucun DBFS. La table est lue par le même chemin qu'avant :
seule la borne temporelle de lecture change. Déploiement et exécution sous **OAuth**
(profil `dcm-dev`, `auth_type: databricks-cli`) — aucun PAT.

Volume : 2583 lignes relues par run côté AWS. Le coût est négligeable devant les tables
d'événements du même job (`access.audit` ~4,5 M lignes/jour), ce qui est précisément pourquoi
`initial_lookback_days` existait — cette borne protège les **grosses** tables, elle n'a
aucune justification sur celle-ci.
