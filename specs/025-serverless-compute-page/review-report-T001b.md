# Review report — T001b (job serverless en billing-direct)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T001 (domaine `dataeng`), sous-tâche **T001b** — T2 du spike. Ferme **SC-002**
côté pipeline (la validation sur donnée réelle reste due, cf. « Ce qui n'est pas fait »).
**Package** : `packages/dcm-databricks-pipeline` · **Diff staged** : 14 fichiers, +846 / −303
(13 fichiers de code/tests + ce rapport)
**Implémentation** : déléguée au subagent `dp-data-databricks-engineer` (délégation bloquante
imposée par CLAUDE.md pour le domaine `dataeng`), **sans autorisation DDL** — puis revue et
contre-mesurée ici.

## Le défaut corrigé, et sa taille réelle

`job_cluster_cost_daily` était un **rollup de `cluster_cost_daily`** et héritait de son filtre
`usage_metadata.cluster_id IS NOT NULL`. Un job serverless n'ayant **jamais** de `cluster_id`,
son coût était exclu en amont, silencieusement.

Mesuré ici sur 2026-08-11 → 2026-09-09 (30 j), depuis `curated_dbx_billing_usage` :

| `cloud_provider` | `CLASSIC` (déjà visible) | `SERVERLESS` (**exclu**) | jobs serverless |
|---|---|---|---|
| aws | 24 431,52 $ | **56 840,99 $** | 2 613 |
| azure | 21 750,77 $ | **28 812,18 $** | 1 076 |
| **total** | 46 182 $ | **85 653,17 $** | 3 689 |

**Le chiffre de la spec (60 021 $/30 j) n'est pas faux** — j'avais d'abord écrit qu'il l'était,
c'est inexact : la spec déclare explicitement, en Assumptions (l. 79, 505-506), que **tous** ses
chiffres de référence sont **AWS uniquement** et doivent être rejoués avec
`cloud_provider = 'aws'`. L'ordre de grandeur AWS est confirmé (56 841 $ sur une fenêtre de 30 j
stricte contre 60 021 $ sur 31-32 j).

Ce qui manquait est ailleurs : **la spec n'a jamais chiffré l'enjeu toutes plateformes**, et
Azure le **double presque**. La visibilité récupérée est de **85 653 $/30 j**, et la table ne
montrait que **35 %** du coût des jobs. Étiquette et total ajoutés dans `spec.md`.

## Gates

| Gate | Statut | Lecture |
|---|---|---|
| **pytest** | ✅ **PASS** — 753 tests (744 avant T001b, **+9**) | — |
| **ruff** (12 fichiers Python touchés) | ✅ **All checks passed** | vérifié moi-même |
| **ruff** (dépôt) | ⚠️ FAIL, 1 erreur `ANN001` — `tests/test_dlt_workflow.py:251`, **hors diff** | dette préexistante, cf. arbitrage `tasks.md` |
| **mypy** (fichiers de prod touchés) | ⚠️ 10 erreurs, **toutes dans `forecast.py:564-588`** — **identiques au HEAD** (10 avant / 10 après, décalées de 11 lignes par le diff) | vérifié par `git stash` puis re-run : rien n'est imputable à T001b, et rien n'est corrigé non plus |
| **mypy** (dépôt) | ⚠️ FAIL — `pipelines/sqs_to_volume_drain.py`, **hors diff** | dette préexistante |
| **format** | ✅ **0 régression**, 12/12, prouvée fichier par fichier (worktree ≤ HEAD) | 2 fichiers **améliorés** : `test_job_cluster_cost_daily.py` 15→0, `test_specs.py` 416→409 |

Le critère de format est bien la comparaison **HEAD vs worktree** — pas « déjà non formaté au
HEAD », question plus faible qui m'avait coûté 3 régressions à corriger à la main sur T001h. Le
subagent l'a appliquée correctement cette fois, et avait lui-même corrigé 2 régressions
transitoires (`test_forecast.py` 114→104, `test_entrypoint.py` 140→130).

## Deux bugs évités que mon énoncé ne mentionnait pas

Le subagent les a trouvés seul ; ce sont les deux apports les plus utiles du lot.

1. **`JOB_EFFICIENCY_DAILY/ROLLING_MERGE_KEYS` étaient des _alias_** des tuples de coût
   (`JOB_EFFICIENCY_DAILY_MERGE_KEYS = JOB_CLUSTER_DAILY_MERGE_KEYS`). Ajouter `compute_kind` au
   grain de coût l'aurait **silencieusement propagé** à deux tables alimentées par
   `node_timeline`, qui n'ont pas cette colonne → MERGE cassé sur une colonne inconnue, sur deux
   tables hors périmètre de T001b. Désaliasé, avec un commentaire qui **interdit de « réaligner »**
   les tuples. C'est exactement ce que T008 avait dû faire côté pipeline : le piège était posé et
   attendait.
2. **La série observée `ai_forecast` du grain JOB n'avait aucun `GROUP BY`.** `object_key` ne
   porte que 3 champs, donc avec `compute_kind` dans le grain source, 926 jours-job envoyaient
   **deux points au même horodatage dans la même série**. `SUM` + `GROUP BY` ajoutés, `compute_kind`
   volontairement **hors** de `object_key` : la prévision reste par job, toutes formes confondues.
   Aucune erreur n'aurait été levée.

## Cinq de mes affirmations étaient fausses

Je les liste parce que la revue vaut surtout par là — l'énoncé que j'avais rédigé était le
maillon faible :

| Mon énoncé | Réalité |
|---|---|
| « `pipeline_cost_rolling.py` a un commentaire sur les rangs à **ne pas** partitionner par `compute_kind` » | l'inverse : ses rangs **sont** partitionnés par `(window_days, compute_kind)`. Le « volontairement sans `compute_kind` » porte sur `latest_attrs`, la résolution du **nom** |
| constante `JOB_CLUSTER_COST_DAILY_MERGE_KEYS` | elle s'appelait `JOB_CLUSTER_DAILY_MERGE_KEYS` ; le nom que je donnais était le bon mais n'existait pas → renommée |
| « conserver le `COALESCE` de repli sur l'id pour `job_name` » | il n'y en a pas : `COALESCE(ja.job_name, sr.run_name)`, le repli est sur `run_name` et le nom peut rester NULL (runs `WORKFLOW_RUN`). Le repli sur l'id existe côté **pipeline** seulement. Conservé tel quel et **verrouillé par un test** qui échoue si quelqu'un l'ajoute |
| « T001b débloque 60 021 $/30 j » | 85 653 $ toutes plateformes. Le 60 021 $ AWS était correct et déclaré comme tel ; c'est mon **énoncé de délégation** qui l'a présenté comme l'enjeu total |
| « l'option `DROP` perd l'historique gold au-delà de la couverture curated » | **prémisse vide**, cf. section suivante |

Le rapport du subagent contient de son côté un chiffre qui **ne se reproduit pas** : « 131 jobs
mixtes ». Je mesure **101**, et sous les deux définitions possibles (`COUNT(DISTINCT job_id)` et
`COUNT(DISTINCT (cloud_provider, workspace_id, job_id))` donnent tous deux 101). Le chiffre
porté par le **code** est le 926 jours-job, lui exact — le 131 n'existe que dans la prose du
rapport.

## La migration de grain : décision documentée, pas exécutée

`compute_kind` est une clé de merge **nouvelle sur une table déjà peuplée** : le MERGE échoue à
l'analyse (`DELTA_MERGE_UNRESOLVED_EXPRESSION: Cannot resolve t.compute_kind in search
condition`) et `full_refresh` n'y change rien — le MERGE ne démarre pas
([writers.py:137-152](../../packages/dcm-databricks-pipeline/pipelines/common/writers.py#L137-L152)).

**Le fait décisif, mesuré :**

| | lignes | de | à |
|---|---|---|---|
| `gold_dbx_compute_job_cluster_cost_daily` | 76 192 | 2026-07-07 | 2026-09-09 |
| `curated_dbx_billing_usage` (la source) | 33 879 602 | **2023-08-26** | 2026-09-09 |

La cible couvre **2 mois**, la source **3 ans**. Ma prémisse « le `DROP` perd l'historique » était
donc **vide** : la table est intégralement recalculable et le recalcul **étend** l'historique de
~3 ans. La borne courte venait précisément de l'`INNER JOIN` sur `job_task_run_timeline`
(rétention ~1 an) que ce changement supprime. Il ne s'agit pas d'un arbitrage
« perte acceptable » : il n'y a **aucune perte d'information**.

Non-régression du sous-ensemble `CLASSIC` — le contrôle qui autorise le recalcul :

| | valeur |
|---|---|
| jours-job dans le gold actuel (30 j) | 44 234 |
| retrouvés à la même clé par la requête billing-direct | **44 234** |
| **orphelins** | **0** |
| coût ancien / nouveau | 46 181,48 $ / **46 181,52 $** (écart 9 × 10⁻⁷) |

La refonte est un **ajout**, pas un déplacement de coût entre jobs.

**Option rejetée** : `ALTER TABLE ADD COLUMN` + backfill à `'CLASSIC'`. Sémantiquement le
backfill serait fidèle (toute ligne préexistante venait de `cluster_cost_daily` avec
`cluster_id IS NOT NULL`), mais il produirait une table à **couverture mixte** : lignes CLASSIC
anciennes conservées, lignes SERVERLESS du même jour absentes avant la fenêtre incrémentale.
L'invariant « somme des `compute_kind` = coût job total facturé » deviendrait **faux sur tous les
jours antérieurs, sans qu'aucune colonne ne le signale**. Un graphe « coût par forme sur 90 j »
montrerait le serverless démarrer brutalement à la date de bascule, **indiscernable d'une vraie
migration métier**. Un historique plausible et faux est pire qu'un historique absent.

**Troisième voie identifiée** (blue/green sur un nouveau nom) : elle a un vrai mérite —
`job_cluster_cost_daily` est devenu un **nom faux**, cette table n'a plus rien à voir avec des
clusters. `gold_dbx_compute_job_cost_daily` serait symétrique de `pipeline_cost_daily`. Mais
c'est une task à part entière (specs, entrypoint, resources, backend, tests) et le renommage
touche le contrat lu par T002/T003. **Arbitrage** : hors périmètre T001b, à imposer le jour où
cette table sert des utilisateurs en prod.

## Ce qui n'est pas fait, et pourquoi

Contrairement à T001a et T001h, **ce commit n'est ni déployé ni validé sur donnée réelle.** Deux
raisons distinctes, aucune des deux cosmétique :

1. **Un prérequis backend manque** (cf. finding 🟡 n° 1). Lancer la migration avant lui ferait
   afficher des doublons silencieux sur la page jobs.
2. **La migration demande un `DROP TABLE`**, une action que je ne m'autorise pas à faire
   exécuter par un subagent : ma première délégation, qui portait cette autorisation, a été
   refusée par le classifieur de permissions. Je ne la reformule pas pour la faire passer — ce
   serait contourner un contrôle, ce que CLAUDE.md et les règles cyber interdisent
   explicitement. Elle est **remontée à l'utilisateur**.

**Conséquence à connaître** : entre ce commit et la migration, la tâche
`gold_job_cluster_cost_daily` **échoue si le job tourne**. Le `schedule` est `PAUSED` sur
`dev_local` **et** `dev` (`databricks.yml:99` et `:132`) et la branche n'est pas fusionnée, donc
aucun run automatique ne peut s'y heurter. C'est inhérent à tout changement de grain — le code
précède nécessairement la migration — mais ça doit être écrit, pas découvert.

## Tests — 9 ajoutés, mordants vérifiés

Le subagent a appliqué **11 sabotages** un par un, suite complète relancée à chaque fois,
restauration contrôlée par SHA-256. **Je n'ai pas pris sa table pour argent comptant** : j'ai
rejoué moi-même le sabotage le plus important, celui qui garde du bug silencieux — retrait de
`AND prev.compute_kind = e.compute_kind` du self-join J-1 :

```
FAILED tests/gold_dbx_compute/test_job_cluster_cost_daily.py::
       test_job_cluster_cost_daily_prev_day_self_join_is_equalized_on_compute_kind
1 failed, 752 passed
```

Puis restauré et revérifié (753 passed, diff-stat identique). Sans cette égalisation, un job
mixte apparie sa ligne `CLASSIC` de J à sa ligne `SERVERLESS` de J-1 ; `merge_into_table` fait
`dropDuplicates(merge_keys)` et en garde une **arbitrairement**, donc `cost_delta_pct` est
calculé un run sur deux contre l'autre forme de compute. Aucune erreur levée.

Faiblesse assumée et signalée par le subagent : côté rolling, un des deux tests compare
`SPEC.merge_keys` à la constante — donc **par référence**, il ne peut structurellement pas
mordre. Seul `test_job_cost_grain_carries_compute_kind` porte le tuple littéral. C'est la
convention du fichier, non changée ici.

## Vérifications de périmètre

- **`depends_on` retiré** sur `gold_job_cluster_cost_daily` : légitime, vérifié — `source_tables`
  de la spec ne contient plus **aucune** table gold (`CURATED_BILLING_USAGE`,
  `CURATED_BILLING_LIST_PRICES`, `CURATED_LAKEFLOW_JOB_RUN_TIMELINE`, `CURATED_LAKEFLOW_JOBS`).
  La tâche démarre en parallèle du chaînage coût → efficience → gouvernance : chemin critique
  raccourci.
- **Vestiges du rollup** : plus aucune occurrence de `cluster_id IS NOT NULL`, `job_clusters`,
  `job_task_run_timeline` ni `LATERAL VIEW` dans le SQL généré — les mentions restantes sont dans
  des commentaires qui expliquent ce qui a été retiré.
- **Clés de merge jamais NULL** : garanti par le filtre `job_id IS NOT NULL` + la branche `ELSE`
  du `CASE` sur `compute_kind`. C'est ce qui remplace la garantie que donnait l'`INNER JOIN`,
  sans son coût de couverture.
- **Produits couverts par `job_id IS NOT NULL`** : trois, pas un — `JOBS`, plus `AI_FUNCTIONS`
  (18,06 $) et `MODEL_SERVING` (0,97 $), soit **0,01 %** de 131 835 $. Non filtré volontairement
  (ce coût est bien celui du job), documenté, avec le correctif prévu si le poste grossit (porter
  `billing_origin_product` dans le grain, pas ajouter un filtre).

## Findings

```
packages/dcm-backend/app/api/services/compute_metrics_jobs.py:68: 🟡 risk: `_ROW_COLUMNS` ne porte PAS `compute_kind` (verifie : 0 occurrence de compute_kind dans tout app/ cote jobs, contre 8 dans compute_metrics_pipelines.py ou T008 l'a traite). Des le premier run du nouveau grain, la page jobs lira DEUX lignes par job mixte (926 jours-job / 101 jobs sur 30 j) et DEUX cost_rank = 1 par jour, sans aucune erreur levee. Correctif backend OBLIGATOIRE AVANT la migration de grain, pas apres
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py:1076: 🟡 risk: entre ce commit et la migration, la tache `gold_job_cluster_cost_daily` ECHOUE si le job tourne (MERGE non analysable). Mitige : schedule PAUSED sur dev_local ET dev, branche non fusionnee. Inherent a tout changement de grain, mais a ne pas decouvrir en run
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py:1085: 🟡 risk: la migration exige un `DROP TABLE` sur 2 tables dev. Perte d'information nulle (mesure : cible 2 mois vs source 3 ans, 0 orphelin sur 44 234 jours-job, UNDROP 7 j), mais action non executee ici : premiere delegation refusee par le classifieur, non reformulee, remontee a l'utilisateur
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_job_cluster_cost_rolling.py:1: 🟢 note: un des 2 tests de grain rolling compare SPEC.merge_keys a la constante donc PAR REFERENCE — il ne peut structurellement pas mordre. Seul test_job_cost_grain_carries_compute_kind porte le tuple litteral. Convention du fichier, non changee
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/forecast.py:564: 🟢 note: 10 erreurs mypy, IDENTIQUES au HEAD (verifie par git stash + re-run), donc ni introduites ni corrigees par T001b. Dette preexistante hors diff
specs/025-serverless-compute-page/spec.md:99: 🟢 note: le 60 021 $/30 j est correct et declare AWS-only en Assumptions, mais la spec ne chiffrait nulle part l'enjeu toutes plateformes : Azure ajoute 28 812 $, total 85 653 $/30 j, soit une table qui ne montrait que 35 % du cout des jobs. Etiquette + total ajoutes
```

0 🔴 blocker · 3 🟡 risk · 3 🟢 note

Le finding backend n'est **pas** classé 🔴 : il porte sur un autre package, hors du diff relu, et
sa conséquence ne peut pas se produire tant que la migration n'a pas eu lieu — laquelle est
maintenant explicitement conditionnée à son correctif. Le classer 🔴 bloquerait un commit dont
le contenu est correct, sans réduire le risque d'un iota.

## Verdict

Le diff fait ce que T001b demandait, et deux choses de plus qui étaient nécessaires et absentes
de mon énoncé (désaliasage des grains d'efficacité, agrégation de la série `ai_forecast`). Cinq
de mes affirmations ont été corrigées, dont la prémisse de la décision de migration. Gates :
pytest PASS 753, ruff et format propres sur les 12 fichiers touchés, mypy inchangé. Test-clé
vérifié mordant par moi-même. Les données réelles confirment le défaut (85 653 $/30 j exclus) et
la non-régression du sous-ensemble CLASSIC (0 orphelin sur 44 234).

Aucun contrôle affaibli : pas de `--no-verify`, pas de DDL, pas de secret, lectures Databricks
par profil OAuth `dcm-dev` uniquement. Le déploiement et la validation sur donnée réelle
**restent dus** et sont conditionnés à deux prérequis nommés ci-dessus — c'est écrit dans le
rapport plutôt que présenté comme fait.

**Verdict**: **PASS**
