# Review report — T001b-back (repli de `compute_kind` sur les routes de coût jobs)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T002 (domaine `backend`), tranche **T001b-back** — le prérequis 1 nommé dans
`review-report-T001b.md`, finding 🟡 n° 1.
**Packages** : `packages/dcm-backend` (principal), `packages/dcm-commons`,
`packages/dcm-frontend` (type seulement) · **Diff staged** : 5 fichiers, +361 / −22
**Stack** : python (module `app`) + un type TS

## Ce que ça corrige

[639ac8e](../../) (T001b) a mis `compute_kind` **dans le grain** de
`gold_dbx_compute_job_cluster_cost_{daily,rolling}`. Trois requêtes du backend lisaient ces
tables comme si le grain était le job : dès le premier run du nouveau grain, la page jobs aurait
affiché **deux lignes par job mixte** (926 jours-job, 101 jobs sur 30 j) et **deux
`cost_rank = 1` par fenêtre**, en comptant ce job **deux fois** dans `active_jobs` — sans qu'aucune
erreur ne soit levée. C'était le finding 🟡 n° 1 de T001b.

Corrigé par un rollup (`_cost_rollup_ctes`) partagé par les 3 requêtes : `compute_kind` est replié
en **libellé** `CLASSIC` / `SERVERLESS` / `MIXED`.

### Ce qui est re-dérivé, et pourquoi ça n'est pas sommable

| Champ | Traitement | Motif |
|---|---|---|
| `cost_usd`, `dbu_quantity`, `cluster_count`, `cost_usd_prev_window` | `SUM` | additifs |
| `cost_delta_pct` | **re-calculé après** le repli | un ratio de sommes n'est pas la somme des ratios |
| `cost_rank`, `is_top_cost` | **re-calculés après** le repli | gold classe *à l'intérieur* de chaque `compute_kind` : deux lignes peuvent porter le rang 1 |
| `job_name` | `MAX` | même lookup `latest_attrs` pour les 2 lignes, donc déjà identique ; `MAX` préfère un nom connu à un NULL, ce que `FIRST` ne garantit pas |
| `compute_kind` | `CASE WHEN COUNT(DISTINCT …) > 1 THEN 'MIXED' ELSE MAX(…) END` | libellé, pas dimension de ligne |

Formules recopiées à l'identique de `job_cluster_cost_rolling.py:165-172`, seuil
`_TOP_COST_RANK_THRESHOLD = 10` aligné sur `TOP_COST_RANK_THRESHOLD` (`specs.py:287`) —
dupliqué et non importé, le backend ne dépendant pas du package pipeline, avec le commentaire
qui rend la dérive visible d'un seul endroit.

**`ranked=False` sur `fetch_job_detail`** : un rang est une propriété d'une **population**, et
cette route restreint `where` à un seul job. Y recalculer `RANK()` rendrait **1 pour tous les
jobs**. La route rend donc `NULL` — « non calculé ici », alors que `1` serait une réponse fausse.
Le champ est déjà nullable au contrat et rien ne l'affiche sur la route de détail.

**`active_jobs` dé-doublonné** : `SUM(CASE WHEN cost_usd > 0 …)` comptait un job mixte deux fois,
remplacé par `COUNT(DISTINCT … concat_ws('|', cloud_provider, workspace_id, job_id) …)`.

### Portée : 3 routes sur 4, vérifié une par une

Le critère T002 demande de « vérifier route par route quel consommateur somme sans grouper ».
Inventaire complet des lecteurs des tables de coût jobs :

| Fonction | Table | Nommait `compute_kind` ? | Traitement |
|---|---|---|---|
| `fetch_jobs_cost` | `_rolling` | oui, via `SELECT *` | rollup + rangs |
| `fetch_jobs_overview` | `_rolling` | oui, via `SELECT *` | rollup + rangs + KPI dé-doublonné |
| `fetch_job_detail` | `_rolling` | oui, via `SELECT *` | rollup, `ranked=False` |
| `fetch_job_cost_trend` | `_daily` | **non** | déjà correct : `GROUP BY bucket` + `SUM`, agrège donc sur `compute_kind` sans le nommer. **Non touché**, verrouillé par un test |
| `fetch_jobs_efficiency`, `fetch_job_uptime_trend` | tables `efficiency_*` | non | **hors sujet** : ces tables viennent de `node_timeline` et n'ont pas la colonne — c'est précisément ce que le désaliasage des `JOB_EFFICIENCY_*_MERGE_KEYS` a protégé en T001b. Verrouillé par un test qui échoue si `compute_kind` y apparaît |

## ⚠️ Le point le plus important : backend et migration sont **atomiques au déploiement**

Le rapport T001b écrivait « correctif backend OBLIGATOIRE **AVANT** la migration de grain, pas
après ». C'est vrai de l'ordre du **code** et faux de l'ordre du **déploiement** — je le corrige
ici. Mesuré sur `dev` (profil OAuth `dcm-dev`, warehouse `DCM-metrics`) :

```
it.information_schema.columns  WHERE table_name = 'gold_dbx_compute_job_cluster_cost_rolling'
  → 15 colonnes, has_compute_kind = 0
it.information_schema.columns  WHERE table_name = 'gold_dbx_compute_job_cluster_cost_daily'
  → has_compute_kind = 0

SELECT compute_kind FROM …gold_dbx_compute_job_cluster_cost_rolling LIMIT 1
  → [UNRESOLVED_COLUMN.WITH_SUGGESTION] … cannot resolve `compute_kind`.
    Did you mean one of [`cost_rank`, `cost_usd`, `job_id`, `workspace_id`, `cluster_count`] ?
    SQLSTATE 42703
```

Donc, aujourd'hui, sur les tables réellement déployées :

- **backend déployé seul** → les 3 routes de coût jobs renvoient une erreur SQL, pas des doublons ;
- **migration faite seule** → doublons silencieux, deux rangs 1, KPI surcompté ;
- **les deux ensemble** → correct.

C'est exactement le motif de la note T002 « ne démarre qu'après vérification en dev de T001 :
lire une colonne qui n'est pas encore écrite produirait des tests verts sur un contrat faux ».
Mes 90 tests sont verts et *mockent* la base — ils ne prouvent rien sur le schéma réel. Le
schéma réel, je l'ai donc interrogé, et il dit non.

**Mitigation, factuelle** : rien n'est déployé, la branche n'est pas fusionnée, et le `schedule`
du job gold est `PAUSED` sur `dev_local` **et** `dev`. L'ordre d'exécution reste : (1) ce commit,
(2) `DROP` + recalcul des 2 tables, (3) déploiement backend. L'inversion de l'ordre séquentiel de
T002 (« après vérification en dev de T001 ») est **assumée** : le prérequis est le code, pas la
donnée, et c'est le seul ordre qui évite la fenêtre de doublons.

## Asymétrie assumée avec la page DLT

La page jobs **replie** `compute_kind` ; la page DLT le **filtre** à `CLASSIC`
(`compute_metrics_pipelines.py:_CLASSIC_ONLY`, décision utilisateur du 2026-09-09). Ce n'est pas
une incohérence oubliée, c'est deux questions différentes :

- la page DLT porte sur le compute **cluster** DLT — un pipeline serverless n'y a pas sa place ;
- la page jobs est là où un utilisateur cherche « combien me coûte ce job », et
  `stories/T002.md:180-183` dit que `job_cluster_cost_*` change « de grain **et de population** ».
  T001b existe précisément pour faire entrer 85 653 $/30 j dans cette population.

`PipelineCostItem.compute_kind` laisse donc passer le grain gold (un pipeline peut apparaître
deux fois) alors que `JobCostItem.compute_kind` est un libellé. Les deux docstrings se citent
mutuellement pour que la divergence soit lisible sans avoir à comparer les deux modules. À
reconsidérer si T003 ouvre une page serverless dédiée.

## Une de mes affirmations était fausse

En ajoutant `compute_kind` à `JobCostItem` j'ai écrit que Pydantic « jetait silencieusement » la
colonne. **Faux** : `JobCostItem` est exporté par `dcm_commons.schemas` mais n'est utilisé comme
`response_model` **nulle part** — `grep` sur tout `packages/` ne rend que l'export lui-même, et
les routes de `compute_metrics.py` sont annotées `-> dict[str, Any]` sans `response_model`. Aucune
validation ne filtre le payload : la colonne passait déjà.

Ça ne rend pas l'ajout inutile, ça en change la nature : le schéma est le **contrat déclaré**,
que `api.ts` recopie côté client, et il était devenu faux. Mais comme rien ne l'applique, un
`grep` ne l'aurait jamais montré — d'où le test ci-dessous.

## Tests — 11 ajoutés, mordants vérifiés un par un

90 tests dans `test_compute_metrics_jobs.py` (79 avant, **+11**), suite backend **698 passed**.

| Test | Ce qu'il garde |
|---|---|
| `…collapse_compute_kind_back_to_one_row_per_job` (×2) | le `GROUP BY` du repli, et `window_days` dedans |
| `…rederive_the_rank_and_the_ratio_after_the_rollup` (×2) | la dérivation exacte de `cost_rank`, `is_top_cost`, `cost_delta_pct` |
| `…overview_kpi_counts_a_mixed_job_once` | `COUNT(DISTINCT …)` sur `active_jobs` |
| `…overview_still_joins_the_efficiency_snapshot_on_the_window` | `window_days` survit au repli, sinon le `LEFT JOIN e` ne résout plus |
| `…job_detail_rolls_up_but_never_ranks` | `ranked=False` sur la route par job |
| `…job_cost_trend_already_aggregates_over_compute_kind` | la tendance n'a pas besoin d'être touchée |
| `…jobs_efficiency_never_mentions_compute_kind` (×2) | les tables `node_timeline` restent hors sujet |
| `…job_cost_row_columns_all_exist_on_the_declared_contract` | **toute** colonne servie est déclarée sur `JobCostItem` |

**4 sabotages appliqués un par un**, suite complète relancée à chaque fois, restauration
contrôlée par **SHA-256** :

| # | Sabotage | Résultat |
|---|---|---|
| S1 | `cost_rank` repris de gold (`MAX(cost_rank)`) au lieu d'être recalculé | ✅ 2 tests rouges |
| S2 | `active_jobs` revient au `SUM(CASE)` par ligne | ✅ 1 test rouge |
| S3 | `window_days` retiré du `GROUP BY` | ✅ 3 tests rouges |
| S4 | `compute_kind` retiré de `JobCostItem` | ✅ 1 test rouge |

**S1 ne mordait pas au premier essai**, et c'est le point utile de cette revue. J'avais écrit
`assert "RANK() OVER (" in sql` : l'expression de `is_top_cost` contient la même sous-chaîne, donc
l'assertion restait vraie alors que `cost_rank` n'était plus recalculé du tout. Corrigé en
assertant l'expression **entière** rendue, `) AS cost_rank` incluse, plus l'absence de
`{SUM,MAX,MIN,AVG,FIRST}(cost_rank|cost_delta_pct|is_top_cost)`. Le test échoue maintenant sur les
deux paramétrages. C'est le même défaut que celui signalé en 🟢 sur T001b (un test qui compare par
référence) : une assertion trop lâche protège de rien, et seul le sabotage le révèle.

## Gates

Le script `dcm-review.sh` juge le **package entier contre `develop`** et rend **FAIL** sur
ruff / mypy / pytest. J'ai attribué chaque échec avant d'écrire un verdict, plutôt que de
reprendre le sien ou de l'ignorer :

| Gate | Script (package entier) | Imputable à ce diff | Vérification |
|---|---|---|---|
| **ruff** | FAIL — 208 erreurs | **0** | réparties sur 48 fichiers non touchés (`insert_test_data.py` 48, `routes/activities.py` 10, …) ; `ruff check` sur mes 2 fichiers → **All checks passed**. Un fichier à 0 erreur ne peut pas contribuer au total |
| **mypy** | FAIL — 74 erreurs / 31 fichiers | **0** | `grep compute_metrics_jobs.py` sur la sortie mypy → **0** ; `mypy` sur le fichier seul → Success. `commons` → Success |
| **pytest** | FAIL | **0** | seul rouge : `test_connection.py::test_connect_timeout_has_actionable_message`, **prouvé rouge au HEAD** plus tôt dans la session (fuite d'environnement du vrai warehouse id). Hors ce test : **698 passed** |
| **format** | — | **0 régression**, parité stricte | mesurée **avec le `pyproject.toml` de chaque package des deux côtés** : `compute_metrics_jobs.py` 36→36, `test_…jobs.py` 156→156, `schemas/compute_metrics.py` 11→11 |
| **tsc** (frontend) | — | **0 régression** | 101 erreurs worktree = **101** au HEAD, comparé par `git stash` du seul `api.ts`. `eslint src/types/api.ts` → propre |
| **vitest** (`ComputeJobs.test.tsx`) | — | ✅ 20 passed | `api.ts` ne porte que des types, effacés à l'exécution |
| **pytest commons** | — | ✅ 122 passed | 2 erreurs de **collecte** hors sujet : `freezegun` et `respx` absents de mon environnement, sur 2 modules non touchés |

**J'ai dû corriger une vraie régression de format en cours de route** : la dette de
`compute_metrics_jobs.py` était passée de 36 à **45** lignes (ruff veut deux lignes vides avant le
bloc de commentaire qui précède `_cost_rollup_ctes`). Le critère est bien **HEAD vs worktree**, pas
« déjà non formaté au HEAD » — c'est la question faible qui m'avait coûté 3 régressions sur T001h.
Mes deux premières mesures étaient d'ailleurs **invalides** : lancées depuis la racine du dépôt,
ruff n'utilisait pas le `pyproject.toml` du package et comparait deux configurations différentes.
Refaites correctement.

Aucun secret dans le diff : `grep -inE "dapi[0-9a-f]|DATABRICKS_TOKEN|client_secret|password|api[_-]?key|token *=|dbfs:/|dbutils\.fs"` sur le diff staged → aucune occurrence. Aucun `--no-verify`, aucun DDL, lectures Databricks par le seul profil OAuth `dcm-dev`.

## Findings

```
packages/dcm-backend/app/api/services/compute_metrics_jobs.py:98: 🟡 risk: ce commit et la migration de grain T001b sont ATOMIQUES au deploiement, ce que le rapport T001b ne disait pas (il parlait d'ordre du code). Mesure sur dev : les 2 tables gold n'ont PAS compute_kind (15 colonnes, UNRESOLVED_COLUMN.WITH_SUGGESTION / SQLSTATE 42703), donc backend deploye seul = 3 routes de cout jobs en erreur SQL. Mitige : rien de deploye, branche non fusionnee, schedule PAUSED sur dev_local ET dev. Ordre impose : (1) ce commit (2) DROP + recalcul (3) deploiement backend
packages/dcm-backend/app/api/services/compute_metrics_jobs.py:82: 🟡 risk: asymetrie assumee — la page jobs REPLIE compute_kind, la page DLT le FILTRE a CLASSIC. Justifie (deux questions differentes, cf. stories/T002.md:180-183 « change de grain ET de population »), documente dans les 2 docstrings qui se citent, mais c'est une divergence de traitement entre deux pages voisines : a reconsiderer si T003 ouvre une page serverless dediee
packages/dcm-commons/dcm_commons/schemas/compute_metrics.py:313: 🟡 risk: JobCostItem n'est utilise comme response_model NULLE PART (routes annotees dict[str, Any]) — le schema est un contrat purement declaratif, que rien n'applique a l'execution. Une colonne servie sans etre declaree ne casse rien et ne se voit pas. Couvert ici par test_job_cost_row_columns_all_exist_on_the_declared_contract, qui est le seul lien entre le SQL et le contrat ; les 3 autres grains (clusters, warehouses, pipelines) n'ont pas d'equivalent
packages/dcm-backend/app/api/services/compute_metrics_jobs.py:114: 🟢 note: _TOP_COST_RANK_THRESHOLD = 10 duplique TOP_COST_RANK_THRESHOLD du package pipeline (specs.py:287). Volontaire — le backend ne depend pas du package pipeline — mais rien ne detecte la derive si l'un des deux change
packages/dcm-frontend/src/types/api.ts:2034: 🟢 note: compute_kind ajoute au type ComputeJobCostItem (donc herite par ComputeJobsOverviewItem) mais AUCUN rendu : ni colonne, ni badge, ni entree dans field-descriptions.ts. Le libellé MIXED n'est visible de personne aujourd'hui. C'est du ressort de T003, signale pour ne pas etre perdu
packages/dcm-backend/tests/test_compute_metrics_jobs.py:552: 🟢 note: les 11 tests assertent sur la CHAINE SQL rendue, avec une base mockee — ils ne prouvent rien sur le schema reel, comme la note T002 l'annonce. C'est pourquoi le schema deploye a ete interroge separement (cf. section atomicite). La validation sur donnee reelle reste due et arrive avec la migration
```

0 🔴 blocker · 3 🟡 risk · 3 🟢 note

## Verdict

Le diff fait ce que le prérequis 1 demandait, sur les **3** routes concernées et pas une de plus,
et laisse volontairement `fetch_job_cost_trend` intacte parce qu'elle agrégeait déjà. Les 11 tests
mordent, vérifié par 4 sabotages dont **un qui ne mordait pas** et a été corrigé. Deux de mes
affirmations ont été redressées : « Pydantic jette la colonne » (faux, rien ne valide) et
« correctif backend avant la migration » (vrai du code, faux du déploiement — c'est **atomique**,
prouvé par `UNRESOLVED_COLUMN` sur les tables réelles).

Le verdict du script est **FAIL** sur ruff / mypy / pytest ; les trois sont **intégralement**
de la dette du package : **0** erreur ruff et **0** erreur mypy dans les fichiers touchés, et le
seul test rouge est prouvé rouge au HEAD. Format et `tsc` en parité stricte, mesurée avec la bonne
configuration après une première mesure invalide et une vraie régression corrigée.

Ce commit **n'est pas déployé** — il n'y a rien à déployer, ce package ne fait que lire — et sa
validation sur donnée réelle est **indissociable** de la migration de grain T001b, laquelle attend
une autorisation de `DROP TABLE` remontée à l'utilisateur.

**Verdict**: **PASS**
