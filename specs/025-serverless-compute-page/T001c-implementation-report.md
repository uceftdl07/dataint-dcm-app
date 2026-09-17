# Rapport d'implémentation — T001c (prédicat produit sur les deux rollups de coût)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (inchangée, aucun commit)
**Package** : `packages/dcm-databricks-pipeline` · **Spec** : `specs/025-serverless-compute-page/`
**Portée** : §10.1 et §10.4 de `docs/spike/serverless-compute-page/proposition.md`
**Diff** : 9 fichiers modifiés (+562 / −15) + 1 fichier de test nouveau (47 lignes)
**Plateforme** : lecture seule, profil OAuth `dcm-dev` uniquement. Aucun DDL, aucun DML,
aucun `bundle deploy`, aucun `jobs run-now`. `databricks auth describe -p dcm-dev` →
`Authenticated with: databricks-cli`, jeton en keyring OS : pas de PAT.

---

## Décision à trancher avant déploiement (elle ne se voit qu'ici)

**Le rollup `forecast_daily` gardera 7 800 lignes périmées que rien ne peut purger.**
Mesuré sur `gold_dbx_compute_forecast_daily` : 7 800 lignes `object_type = 'PIPELINE'` sur
**497 `dlt_pipeline_id`** que le filtre produit retire de `pipeline_cost_daily`. Cette spec a
`watermark_column = None` **et** aucun `absent_row_delete_guard` : elle est en upsert pur, donc
ces lignes ne disparaîtront jamais d'elles-mêmes — et le mécanisme `one_off_purge` livré ici les
**refuse explicitement** (deuxième refus : sans watermark, rien ne bornerait la suppression, un
run dégradé viderait la table entière). Trois issues, aucune n'est de mon ressort :

1. accepter le résidu (7 800 lignes de prévision sur des objets qui ne sont plus des pipelines) ;
2. donner un `watermark_column` à `FORECAST_DAILY_SPEC` (`horizon_date`) puis purger — changement
   de régime permanent d'une table hors périmètre T001c ;
3. purge SQL manuelle — exclue par tes contraintes (aucun DML) et par les miennes.

Sans arbitrage, l'issue (1) s'applique par défaut. C'est le seul point où la réparation reste
**incomplète**, et il est chiffré plutôt que passé sous silence.

Second point, borné celui-là : `pipeline_cost_rolling` porte aujourd'hui **13 983 lignes** sur
9 647 pipelines retirés. Il se nettoie seul, mais avec un délai — voir §6.

---

## 1. Ce qui change, fichier par fichier

### `pipelines/gold_dbx_compute/sql_helpers.py` (+84)

Le cœur de T001c : deux constantes et un helper, précédés du bloc de commentaire qui **justifie
la liste blanche dans le code** (et pas seulement ici).

```python
BILLING_PRODUCTS_CLUSTER_COMPUTE: tuple[str, ...] = ("JOBS", "ALL_PURPOSE", "DLT")
BILLING_PRODUCTS_DLT_PIPELINE: tuple[str, ...] = ("DLT",)

def billing_origin_product_predicate(products: tuple[str, ...]) -> str:
    if not products:
        raise ValueError("products must not be empty")
    return f"billing_origin_product IN ({sql_string_list(products)})"
```

**Liste blanche (`IN`) et non liste noire (`NOT IN ('MODEL_SERVING', 'AI_FUNCTIONS')`)**, trois
raisons, toutes écrites dans le fichier :

1. **Databricks ajoute des produits, une liste noire les fait entrer sans un signal.** Mesuré sur
   l'historique complet : `AI_FUNCTIONS` n'apparaît qu'au **2025-11-07**, `DATABASE` au
   **2025-09-09**. Une liste noire écrite en 2025-08 les aurait admis silencieusement. La liste
   blanche fait pencher le défaut du côté du **sous-comptage visible** (un produit absent de la
   page, qu'on remarque) plutôt que du **sur-comptage invisible**.
2. **Le sur-comptage est le faux positif coûteux côté FinOps** : compter les DBU d'un appel
   d'inférence comme du coût de cluster fait recommander le rightsizing d'un cluster dont le coût
   n'est pas son compute. L'erreur inverse est bornée et auditable par la requête de contrôle
   laissée dans le fichier.
3. **C'est la convention déjà en place dans ces builders** : `cluster_type_case_expr` et
   `compute_kind_case_expr` énumèrent les valeurs connues et replient le reste sur `OTHER`, que
   `cluster_cost_daily` exclut ensuite. Une liste noire introduirait la convention inverse dans la
   même requête.

Vérifié **avant** d'écrire le filtre : aucune ligne ne porte `billing_origin_product` NULL dans
les deux périmètres (historique complet depuis 2023-08-26), donc l'`IN` n'écarte rien par effet
de bord d'un NULL. Chaque constante porte ses volumes mesurés, et
`BILLING_PRODUCTS_DLT_PIPELINE` documente l'arbitrage **`LAKEFLOW_CONNECT`** (49 ids /
9 873,47 $ : de vrais pipelines d'ingestion managés, volontairement exclus, l'inclusion est un
changement d'une ligne).

`ValueError` sur tuple vide : `IN ()` est une erreur de syntaxe Spark, mais surtout une liste
blanche vide **viderait la table gold sans rien signaler**.

### `pipelines/gold_dbx_compute/cluster_cost_daily.py` (+43)

```sql
WHERE usage_metadata.cluster_id IS NOT NULL
  AND billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')
```

Le prédicat est calculé **dans `usage_filtered`, en amont du `GROUP BY`** — et le commentaire dit
pourquoi ce n'est pas indifférent : appliqué après agrégation, il n'écarterait plus des *lignes*
mais des *jours-cluster entiers*, dont ceux qui mélangent un vrai coût de cluster et un coût
étranger. Un test dédié verrouille cette position (S7).

Docstring module : ce que le filtre retire de la table, **791,02 $ sur 97 clusters**
(`AI_FUNCTIONS` 567,34 $ / 55 clusters, `MODEL_SERVING` 223,68 $ / 42), 2025-10-28 → 2026-09-09.

Bullet `sku_group` réécrit : `'serverless'` **n'est plus productible**, et c'est normal — un
cluster est par définition du compute provisionné ; les seules lignes `%SERVERLESS%` portant un
`cluster_id` venaient de `AI_FUNCTIONS` / `MODEL_SERVING`. **Mesure de contrôle** : en appliquant
le filtre sur tout l'historique, **0** ligne gold resterait `sku_group = 'serverless'`. La branche
du `CASE` est **conservée comme témoin**, avec un commentaire SQL qui interdit de la supprimer :
sa réapparition signalerait que Databricks facture un produit de compute cluster sur un SKU
serverless — pas un bug du builder. `'photon'` reste produit normalement.

### `pipelines/gold_dbx_compute/pipeline_cost_daily.py` (+27)

```sql
WHERE usage_metadata.dlt_pipeline_id IS NOT NULL
  AND billing_origin_product IN ('DLT')
```

Docstring module : le prix du billing-direct est qu'il faut **délimiter la population soi-même**.
`usage_metadata.dlt_pipeline_id` n'est pas réservé aux pipelines DLT — **10 972 ids non-DLT pour
37 100,58 $**, dont **10 499 requêtes `SQL`**, et **10 435** d'entre elles ont une ligne dans
`curated_dbx_lakeflow_pipelines` : elles apparaissaient donc **avec un nom de pipeline** dans la
table gold, indistinguables d'un vrai pipeline. Le paragraphe « Source » nomme désormais les deux
prédicats et dit explicitement que la table **ne couvre pas** tout ce qui porte un
`dlt_pipeline_id` — c'est délibéré, pas un oubli.

### `pipelines/gold_dbx_compute/specs.py` (+47, commentaires uniquement)

Aucun changement de structure : `table_comment` / `column_comments` seulement (ils partent en
`COMMENT ON` Unity Catalog, donc c'est ce que lit l'utilisateur final).

- `CLUSTER_COST_DAILY_TABLE_COMMENT` : population restreinte au coût facturé **comme** du compute
  cluster (produits `JOBS`, `ALL_PURPOSE`, `DLT`), le reste est exclu.
- `CLUSTER_COST_DAILY_COLUMN_COMMENTS["sku_group"]` : « classic ou photon », `serverless` n'est
  plus produite, et où lire le coût du compute réellement serverless
  (`job_cluster_cost_daily` / `pipeline_cost_daily`, `compute_kind = SERVERLESS`).
- `CLUSTER_COST_ROLLING_COLUMN_COMMENTS["sku_group"]` : même correction (le rollup héritait de
  l'énumération à trois valeurs).
- `PIPELINE_COST_DAILY_TABLE_COMMENT` : `billing_origin_product = 'DLT'` + « ne couvre pas tout ce
  qui porte un `dlt_pipeline_id` ».
- Corollaire ajouté à l'interdit `NE PAS etendre ce garde-fou` (lignes 2578-2584 après édition) :
  un changement de population **n'est pas** une raison d'armer le garde-fou en permanence ; le
  nettoyage passe par `one_off_purge`.

### `pipelines/gold_dbx_compute/entrypoint.py` (+124)

Le paramètre de run `one_off_purge` et sa mécanique — détaillés en §2.

---

## 2. La purge : décision, et le raisonnement complet sur l'avertissement de `specs.py`

### L'interdit, tel qu'il est écrit

`specs.py`, ligne **2549** au HEAD (2575 après mes éditions) :

> `NE PAS etendre ce garde-fou aux autres tables *daily* sans avoir verifie qu'elles ont la meme
> propriete : celles qui agregent directement la facturation ou node_timeline n'ont aucune raison
> de perdre un jour deja ecrit.`

Il est **fondé** et il **s'applique ici** : `pipeline_cost_daily` agrège directement la
facturation. Armer `absent_row_delete_guard` dans sa spec, ce serait accepter **définitivement**,
pour une réparation ponctuelle, qu'un run dégradé (curated indisponible) efface un jour déjà
écrit. Accessoirement, le test existant
`test_warehouse_utilization_daily_is_the_only_daily_spec_that_deletes` l'interdit aussi — et il
mord (sabotage S8).

### Ce que la purge doit réparer, mesuré et non supposé

Sur les tables gold réelles, en lecture seule (2026-09-10) :

| Table gold | Lignes | Lignes **orphelines** après le filtre | Lignes seulement **corrigées** |
|---|---:|---:|---:|
| `gold_dbx_compute_pipeline_cost_daily` | 552 968 | **113 085** (20,45 %) | 4 |
| `gold_dbx_compute_cluster_cost_daily` | 5 389 217 | **0** | 129 (sur 134 jours-cluster touchés) |

Détail pipeline : 20 265 `dlt_pipeline_id` distincts, dont **10 972** portent au moins un produit
non-DLT, **10 967** n'en portent *que* du non-DLT, **5** sont mixtes. Au grain de la table
(`+ compute_kind`), **10 971** ids ont au moins une ligne entièrement orpheline. Les orphelines
s'étalent du **2024-08-26 au 2026-09-09**, et la table couvre depuis le **2024-02-13** : soit
~940 jours, très au-delà de `INCREMENTAL_LOOKBACK_DAYS = 10`.

Détail cluster : **zéro orpheline**. Tous les jours-cluster impactés conservent de l'usage
légitime — la ligne reste, seule sa valeur (`cost_usd`, `dbu_quantity`, `sku_group`) était fausse.
Des 129 lignes étiquetées `serverless` aujourd'hui, 104 deviennent `classic` et 25 `photon`.

**Conséquence directe : `cluster_cost_daily` n'a besoin d'aucune purge**, seulement d'un
`full_refresh`. La purge ne concerne que `pipeline_cost_daily`.

### La solution retenue : un paramètre de run, rien de persisté

`PARAM_NAMES` accueille `one_off_purge`, **volontairement absent** de
`resources/job_dcm_gold_dbx_compute.yml` (fichier non modifié) : aucune tâche planifiée ne doit
pouvoir le porter, même à vide. `_apply_one_off_purge` rend une **copie** de la spec via
`dataclasses.replace` (frozen) : le registre `GOLD_SPECS` n'est jamais muté, et le run suivant
— sans le paramètre — est de nouveau en upsert pur. **Le retour au régime permanent est l'état par
défaut : il n'y a rien à retirer ensuite.** C'est exactement ce que l'interdit demande.

Trois refus, tous *fail-fast* (un run qui échoue est réparable, une purge partielle silencieuse ne
se voit pas) :

| Refus | Pourquoi |
|---|---|
| sans `full_refresh` | la suppression est bornée à la fenêtre recalculée par `resolve_absent_row_delete_predicate` = 10 jours ; elle laisserait ~930 jours non nettoyés **en rapportant un succès** |
| spec sans `watermark_column` | rien ne bornerait la suppression : un builder dégradé viderait la table (c'est ce refus qui bloque `forecast_daily`, cf. décision en tête) |
| spec portant déjà un garde-fou | elle se nettoie seule en régime permanent ; l'écraser changerait la sémantique d'une table qui n'a rien demandé |

### Pourquoi le seuil « début du run » et pas la grâce de 7 jours

Le garde-fou injecté est `t._generated_at < TIMESTAMP '<début du run>+00:00'`, **pas**
`SNAPSHOT_ABSENT_ROW_DELETE_GUARD` (`_generated_at < current_date() - 7`). Mesuré :

- `pipeline_cost_daily` : **une seule** valeur de `_generated_at` (2026-09-09T21:02:19.612Z) ;
- `cluster_cost_daily` : 5 valeurs, du 2026-08-30T21:03:25 au 2026-09-09T10:07:32.

La grâce de 7 jours supprimerait donc **0 ligne** sur `pipeline_cost_daily` — la table entière a
été écrite hier. Elle rapporterait un succès en ne réparant rien. Le seuil « début du run » cible
exactement les lignes écrites **avant ce run**, c'est-à-dire les orphelines, et rien d'autre.
L'horodatage est ancré en **UTC** (`+00:00`) : `_generated_at` vient de `current_timestamp()`, un
littéral sans zone dépendrait du réglage de session du warehouse.

`SNAPSHOT_ABSENT_ROW_GRACE_DAYS = 7 < INCREMENTAL_LOOKBACK_DAYS = 10` reste **intacte** (constante
non touchée) : la purge ne passe pas par elle.

### Filets conservés, traçabilité, réversibilité

- La suppression reste **conjuguée à la borne de fenêtre** par
  `resolve_absent_row_delete_predicate` ; en mode full la borne est le `MIN(period_start)`
  **réellement produit par le builder** (`_source_watermark_floor`), pas le `MIN` de la cible :
  l'historique gold plus ancien que la couverture curated n'est pas touché.
- **Sortie vide → aucune suppression** (`_absent_row_delete_predicate` renvoie `None` + warning) :
  le run dégradé ne peut pas vider la table.
- Traçabilité : un `_LOGGER.warning` annonce la purge dans les logs de la tâche, et
  `DESCRIBE HISTORY` donne le compte exact (`operationMetrics.numTargetRowsDeleted`) de la version
  produite. **Attention** — vérifié sur `databricks jobs submit --help` (CLI v1.10.0) : un run
  soumis ainsi **n'est pas enregistré comme job et n'apparaît pas dans l'IHM Jobs**. La trace qui
  fait foi est donc la version Delta, pas une page de job ; c'est écrit dans la docstring.
- Réversibilité : ces tables gold sont intégralement recalculables depuis curated, et le `MERGE`
  crée une version Delta (time travel).

### Procédure opérateur (aucun DDL, aucune modification du bundle)

1. `databricks jobs get <job_id> -p dcm-dev` → récupérer le `python_wheel_task` + `environments`
   déjà déployés de la tâche `gold_pipeline_cost_daily` ;
2. resoumettre ce même spec en run unique via `databricks jobs submit`, en ajoutant
   `one_off_purge: "true"` et `full_refresh: "true"` aux `named_parameters` ;
3. relire `numTargetRowsDeleted` dans `DESCRIBE HISTORY` (attendu : **113 085**, à ±1 run de
   décalage curated), puis enchaîner l'aval dans l'ordre du §6.

**Alternative non retenue, à ton arbitrage** : ajouter un paramètre de job `one_off_purge` dans
`resources/job_dcm_gold_dbx_compute.yml`. Plus confortable (`bundle run` suffirait), mais cela
expose le levier à **toutes** les tâches planifiées, y compris à vide. Je ne l'ai pas fait ; c'est
ta décision puisque c'est toi qui déploies.

---

## 3. Les tests mordent-ils ? Campagne de sabotage

Protocole : **un sabotage à la fois**, SHA-256 du fichier avant, patch d'une occurrence unique
(échec du harness si le motif n'est pas trouvé **exactement une fois**), **suite complète**
relancée, restauration dans un `finally`, SHA-256 après. Harness : `/tmp/t001c_sabotage.py`.
Référence verte : **771 passed**.

| # | Sabotage | Fichier | Résultat | Test(s) rouge(s) |
|---|---|---|---|---|
| S1 | prédicat produit **retiré** de `cluster_cost_daily` | `cluster_cost_daily.py` | 2 failed, 769 passed | `test_cluster_cost_daily_keeps_only_cluster_compute_products`, `test_cluster_cost_daily_filters_products_before_aggregating` |
| S2 | prédicat produit **retiré** de `pipeline_cost_daily` | `pipeline_cost_daily.py` | 3 failed, 768 passed | `test_pipeline_cost_daily_keeps_only_the_dlt_product`, `test_pipeline_cost_daily_filters_products_before_aggregating`, `test_pipeline_cost_daily_billing_direct_filters_non_null_pipeline_id` |
| S3 | liste blanche **inversée** en liste noire (`IN` → `NOT IN`) | `sql_helpers.py` | 5 failed, 766 passed | `test_billing_origin_product_predicate_formats_a_whitelist`, `..._is_never_a_blacklist`, `test_cluster_cost_daily_keeps_only_cluster_compute_products`, `test_pipeline_cost_daily_keeps_only_the_dlt_product`, `test_pipeline_cost_daily_billing_direct_filters_non_null_pipeline_id` |
| S4 | **purge neutralisée** (`_apply_one_off_purge` rend la spec inchangée) | `entrypoint.py` | 1 failed, 770 passed | `test_main_one_off_purge_deletes_orphans_bounded_by_the_recomputed_history` |
| S5 | refus « `full_refresh` manquant » supprimé | `entrypoint.py` | 1 failed, 770 passed | `test_main_one_off_purge_requires_full_refresh` |
| S6 | seuil de run remplacé par la grâce volumétrique 7 j | `entrypoint.py` | 1 failed, 770 passed | `test_main_one_off_purge_deletes_orphans_bounded_by_the_recomputed_history` |
| S7 | prédicat produit **déplacé après le `GROUP BY`** (2 patches) | `cluster_cost_daily.py` | 2 failed, 769 passed | `test_cluster_cost_daily_filters_products_before_aggregating`, `test_cluster_cost_daily_keeps_only_cluster_compute_products` |
| S8 | garde-fou de suppression rendu **permanent** sur `PIPELINE_COST_DAILY_SPEC` | `specs.py` | 5 failed, 766 passed | `test_warehouse_utilization_daily_is_the_only_daily_spec_that_deletes` + les 4 tests `one_off_purge` |
| S9 | commentaire `sku_group` : énumération 3 valeurs réinjectée | `specs.py` | 1 failed, 770 passed | `test_cluster_cost_comments_document_the_product_restriction_and_sku_group` |
| S10 | filtre produit retiré du `table_comment` pipeline | `specs.py` | 1 failed, 770 passed | `test_pipeline_cost_comments_document_the_product_restriction` |
| S11 | branche témoin `sku_group = 'serverless'` supprimée | `cluster_cost_daily.py` | 1 failed, 770 passed | `test_cluster_cost_daily_keeps_the_serverless_sku_group_branch_as_a_canary` |
| S12 | `one_off_purge` ajouté au YAML du job planifié | `resources/job_dcm_gold_dbx_compute.yml` | 1 failed, 770 passed | `test_one_off_purge_param_is_accepted_but_absent_from_the_scheduled_job` |

**Aucun sabotage n'est passé inaperçu.** Les trois minimums que tu exigeais sont couverts : filtre
retiré (S1, S2), prédicat inversé (S3), mécanisme de purge neutralisé (S4, complété par S5/S6).

### Vérification de restauration (SHA-256, identique avant/après pour chaque run)

| Fichier | SHA-256 |
|---|---|
| `pipelines/gold_dbx_compute/cluster_cost_daily.py` | `3ea47494a44240cbee49a76b12ad288515e6eac977b4907c5e166bc3f6e779f7` |
| `pipelines/gold_dbx_compute/pipeline_cost_daily.py` | `764059606e225cf934f3b0f83031bfc9deb002ccfab6ed09a7910904994a6b34` |
| `pipelines/gold_dbx_compute/sql_helpers.py` | `ae82f17e4a00682241cde0e8dd861433af5d4f32fe70facd645be7e2a0fb0dbb` |
| `pipelines/gold_dbx_compute/entrypoint.py` | `cf85a9beeecf2e6682fd5fd20fd97f91914a5e1d6daa42037315a89098e38c01` |
| `pipelines/gold_dbx_compute/specs.py` | `a75ed303946a5bfe7bb38923b1984010fe62945011d6d153289f642d34400ac2` |
| `resources/job_dcm_gold_dbx_compute.yml` | `0a0bf7f8efc3622579bcfde3024d84023692a68b4e396b3deb0ceebf85039389` |

Deux précisions d'honnêteté :

- **S4, S5 et S6 ont été rejoués deux fois** : après la retouche de format sur `entrypoint.py`
  (§4), puis après la correction de la docstring sur `jobs submit`. Les SHA ci-dessus sont ceux du
  fichier **livré**, pas d'une version intermédiaire.
- **S12 a temporairement modifié le YAML** que tu m'as demandé de ne pas toucher. Il a été restauré
  dans le `finally` et le SHA-256 avant/après est identique ; `git status` ne le liste pas comme
  modifié. C'était le seul moyen de prouver que le test d'absence du paramètre mord vraiment.

### Assertions : expression entière + négation

Chaque test de prédicat assert **l'expression complète sur ses deux lignes** :

```python
assert (
    "WHERE usage_metadata.cluster_id IS NOT NULL\n"
    "          AND billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')"
) in query
```

et l'assertion négative correspondante (`NOT IN` absent, `MODEL_SERVING` / `AI_FUNCTIONS` absents
côté cluster ; `'SQL'`, `LAKEFLOW_CONNECT`, `VECTOR_SEARCH` absents côté pipeline). L'assertion
pré-existante `test_pipeline_cost_daily_billing_direct_filters_non_null_pipeline_id` a été
**renforcée** : elle ne portait que sur `WHERE usage_metadata.dlt_pipeline_id IS NOT NULL` et
survivait donc au changement — c'est exactement le genre d'assertion trop lâche qui laisse passer
un défaut de population.

### Nouveaux tests (18 ajoutés, 1 renforcé, 0 supprimé — 753 → 771)

- `tests/gold_dbx_compute/test_sql_helpers.py` (**nouveau**, précédent :
  `tests/gold_dbx_usage/test_sql_helpers.py`) — 3 tests : chaînes exactes, jamais une liste noire,
  `ValueError` sur tuple vide.
- `test_cluster_cost_daily.py` — 3 tests : prédicats complets, filtrage **avant** agrégation
  (occurrence unique + index avant le `GROUP BY`), branche témoin `serverless`.
- `test_pipeline_cost.py` — 2 tests + 1 renforcé.
- `test_specs.py` — 2 tests sur les commentaires UC (avec négations sur les anciennes énumérations).
- `test_entrypoint.py` — 8 tests : absence du paramètre dans le YAML, purge nominale (borne
  `MIN(period_start)` réellement calculée, seuil `TIMESTAMP` UTC encadré par l'instant avant/après
  le run, `date_add(current_date()` absent), flag absent → upsert pur, registre non muté, refus
  sans `full_refresh` (aucune requête émise), refus sur `forecast_daily`, refus sur
  `warehouse_utilization_daily`, et **aucune suppression quand le recalcul est vide**.

---

## 4. Gates

Toutes les commandes ci-dessous ont été **exécutées** depuis `packages/dcm-databricks-pipeline`.

| Gate | Commande réellement lancée | Résultat |
|---|---|---|
| Tests | `.venv/bin/python -m pytest -q` | **771 passed** (base HEAD : 753) |
| Tests (commande CI) | `.venv/bin/python -m pytest tests --cov=. -q` | **771 passed** |
| Lint | `.venv/bin/python -m ruff check <9 fichiers + le nouveau>` | **All checks passed** |
| Types | `.venv/bin/python -m mypy <5 fichiers de prod>` | **Success: no issues found in 5 source files** |

`python3 -m pytest -q`, la commande littérale de ton brief, **ne peut pas fonctionner ici** :
cf. §5, point 1.

Le seul bruit résiduel est un avertissement de configuration ruff pré-existant (`ANN101`,
`ANN102` supprimées en amont, ignorées sans effet dans `pyproject.toml`) : présent à l'identique
au HEAD, non introduit par moi, et hors périmètre.

### Parité de format, mesurée **des deux côtés**

Ce dépôt n'est **pas** `ruff format`-propre (le CI ne lance que `pytest` ; `ruff check` et `mypy`
sont commentés, `dbx_main_workflow.yml` lignes 73-74). Le critère est donc la **parité** avec le
HEAD, mesurée par `ruff format --diff <f> | wc -l` sur les deux versions du même fichier :

| Fichier | worktree | HEAD | Verdict |
|---|---:|---:|---|
| `cluster_cost_daily.py` | 0 | 0 | = |
| `pipeline_cost_daily.py` | 0 | 0 | = |
| `sql_helpers.py` | 0 | 0 | = |
| `entrypoint.py` | 47 | 47 | = |
| `specs.py` | 262 | 262 | = |
| `test_cluster_cost_daily.py` | 27 | 27 | = |
| `test_entrypoint.py` | 130 | 130 | = |
| `test_pipeline_cost.py` | 0 | 0 | = |
| `test_specs.py` | 409 | 409 | = |
| `test_sql_helpers.py` (nouveau) | 0 | — | propre |

Première mesure : `entrypoint.py` **58 vs 47** et `test_entrypoint.py` **151 vs 130**. Trois de mes
appels étaient coupés sur plusieurs lignes alors qu'ils tiennent en une (≤ 100 caractères) ; je les
ai collapsés, et la parité est stricte partout. Les versions HEAD ont été obtenues par
`git show HEAD:<path>` écrit **dans l'arborescence du package** (et non `/tmp`) pour que ruff
résolve le même `pyproject.toml`, puis supprimées.

---

## 5. Ce que ton énoncé dit de faux

Sept points, tous vérifiés par exécution ou par mesure.

1. **`python3 -m pytest -q` ne peut pas passer dans ce dépôt.** Il échoue sur
   `ModuleNotFoundError: No module named 'pyspark'` : le `python3` du PATH est le venv **racine**
   (`/Users/.../dataint-dcm-app/.venv/bin/python3`), pas celui du package
   (`packages/dcm-databricks-pipeline/.venv`, Python 3.12.12, qui porte pytest/ruff/mypy/ty). La
   commande correcte est `.venv/bin/python -m pytest -q` depuis le package (ou `uv run`, comme le
   CI).
2. **Le fichier de test pipeline s'appelle `test_pipeline_cost.py`**, pas
   `test_pipeline_cost_daily.py`. Il couvre `pipeline_cost_daily` **et** `pipeline_cost_rolling`.
3. **L'interdit de `specs.py` est ligne 2549, pas 2551** (numérotation HEAD) ; il s'étend sur
   2549-2551.
4. **Le diagnostic de §10.4 est faux dans sa cause.** Il attribue le sur-comptage à des endpoints
   de serving « déguisés en clusters ». Les `cluster_id` des endpoints sont **absents** de
   `curated_dbx_compute_clusters` : ils étaient **déjà** écartés par le `WHERE cluster_type <>
   'OTHER'` de la sortie. Ce repli est précisément ce qui **masquait** le défaut. Le coût
   réellement sur-compté par la table gold est de **791,02 $ sur 97 clusters**, et non les
   1 286,28 $ annoncés — l'écart (681,04 $ + 15 208,15 $ des deux produits) portait des
   `cluster_id` inconnus, donc déjà exclus.
5. **`sku_group = 'serverless'` n'est pas un marqueur exhaustif du défaut.** 129 lignes gold le
   portent aujourd'hui, pour **134** jours-cluster réellement impactés par le filtre. Et après
   filtrage, **104** de ces 129 lignes deviennent `classic` (25 seulement `photon`) : le coût
   étranger se cachait majoritairement sous une étiquette d'apparence normale. Chercher le défaut
   par `sku_group` en aurait laissé passer une partie.
6. **La prémisse « purge d'orphelines » ne tient pas pour `cluster_cost_daily`** : **0** ligne
   orpheline (mesuré sur les 5 389 217 lignes de la table). Tous les jours-cluster touchés gardent
   de l'usage légitime ; il n'y a que des **corrections de valeur**. Seule
   `pipeline_cost_daily` a des orphelines (113 085). Traiter les deux tables symétriquement aurait
   armé une suppression inutile sur la plus grosse table du plugin.
7. **La grâce de 7 jours ne pouvait pas servir de levier de purge**, contrairement à ce que
   suggère la consigne de « conserver `SNAPSHOT_ABSENT_ROW_GRACE_DAYS = 7 <
   INCREMENTAL_LOOKBACK_DAYS = 10` » comme cadre de la purge. `pipeline_cost_daily` n'a **qu'une**
   valeur de `_generated_at` (2026-09-09) : ce garde-fou aurait supprimé **0 ligne** tout en
   rapportant un succès — le scénario de « purge partielle non signalée » que tu voulais éviter.
   D'où le seuil « début du run ». Les deux constantes, elles, sont bien celles que tu citais
   (lignes 267 et 242) : ce point-là est exact.

---

## 6. Tables aval : héritage vérifié (pas deviné) et ordre de relance

Vérifié dans `entrypoint.py` (registre des builders) et dans le SQL de chaque builder.

| Table gold aval | Lit | Impact | Se nettoie seule ? |
|---|---|---|---|
| `pipeline_cost_rolling` | `pipeline_cost_daily` | **13 983 lignes** orphelines sur 9 647 pipelines | **Oui, avec délai** : snapshot sans watermark + `SNAPSHOT_ABSENT_ROW_DELETE_GUARD`. `_generated_at` = 2026-09-09 (1 seule valeur) → supprimées au premier run où `current_date() - 7 > 2026-09-09`, soit **à partir du 2026-09-17** |
| `cluster_cost_rolling` | `cluster_cost_daily` | valeurs seulement (0 orpheline en amont), dont `sku_group` | Oui (aucune orpheline à supprimer) |
| `cluster_efficiency_daily` | `cluster_cost_daily` en **`LEFT JOIN cost cst`** | `estimated_savings_usd` seulement : sa population vient de `node_timeline`, pas du coût | Sans objet : pas d'orpheline, valeurs corrigées par un `full_refresh` |
| `cluster_efficiency_rolling` | `cluster_efficiency_daily` | valeurs héritées | Oui (snapshot + garde-fou) |
| `cluster_governance` | `cluster_efficiency_daily` | valeurs héritées | Oui (snapshot + garde-fou) |
| `recommendations` | `cluster_cost_rolling`, `cluster_efficiency_rolling`, `cluster_reliability_rolling`, `cluster_governance` | valeurs (`estimated_savings_usd`, seuils de coût) | Oui, garde-fou `last_seen_date < current_date() - 90` |
| `forecast_daily` | `cluster_cost_daily`, `pipeline_cost_daily`, `cluster_efficiency_daily`, `job_cluster_cost_daily`, `warehouse_*` | **7 800 lignes** `object_type = 'PIPELINE'` sur 497 ids retirés | **NON** : `watermark_column = None` **et** aucun garde-fou → upsert pur. Cf. décision en tête de rapport |
| `cluster_reliability_daily` / `_rolling` | `curated_dbx_compute_clusters`, `curated_dbx_access_audit` | **aucun** (ne lit aucune table de coût) | — |
| `job_*`, `warehouse_*` | `job_id` / `warehouse_id` | **aucun** (autres grains) | — |

`pipeline_efficiency_daily` mérite une mention : il passe par
`grain_resolution.pipeline_clusters_cte_sql`, dont le `WHERE` (ligne 103) est
`u.usage_metadata.dlt_pipeline_id IS NOT NULL` **sans prédicat produit** — troisième occurrence du
même défaut, hors du périmètre que tu as fixé (voir §7). Chiffrée : sur 179 043 couples
`(cluster_id, dlt_pipeline_id)` distincts, **1 seul** provient exclusivement d'un produit non-DLT
(la CTE exige les **deux** ids, et les porteurs non-DLT — des requêtes SQL — n'ont presque jamais
de `cluster_id`). Le risque est donc latent, pas actif ; mais après T001c les deux tables peuvent
en principe diverger sur ce qu'est un pipeline.

### Ordre de relance (après ton déploiement)

1. `pipeline_cost_daily` — `one_off_purge=true` + `full_refresh=true` (run soumis à la main).
   Contrôle : `numTargetRowsDeleted` ≈ **113 085**.
2. `cluster_cost_daily` — `full_refresh=true` **sans** `one_off_purge` (0 orpheline ; le mécanisme
   l'accepterait mais supprimerait 0 ligne — inutile).
3. `pipeline_cost_rolling`, puis `cluster_cost_rolling` (recalcul complet, aucun paramètre).
4. `cluster_efficiency_daily` — `full_refresh=true` (recalcule `estimated_savings_usd`).
5. `cluster_efficiency_rolling`, puis `cluster_governance`, puis `recommendations` (dans cet
   ordre : chacun lit le précédent).
6. `forecast_daily` (dernier ; résidu de 7 800 lignes à arbitrer).
7. Repasser sur `pipeline_cost_rolling` **le 2026-09-17 ou après** pour purger ses 13 983
   orphelines, ou attendre le run planifié de ce jour-là.

Entre les étapes 1 et 7, la page affiche des fenêtres glissantes pipeline encore surévaluées.
C'est borné (≤ 7 jours) et réversible, contrairement au résidu `forecast_daily`.

---

## 7. Ce qui n'est pas fait, et pourquoi

- **Validation sur donnée réelle** : aucune. Aucun `bundle deploy`, aucun `jobs run-now`, aucun
  DDL/DML — conformément à tes contraintes. Toutes les mesures de ce rapport sont des `SELECT`
  émis via l'API `/api/2.0/sql/statements` avec le profil OAuth `dcm-dev` et le warehouse
  `DCM-metrics`. Les 113 085 lignes annoncées sont une **prédiction mesurée**, pas un résultat de
  purge.
- **Renommage `sku_group` → `sku_family`** : hors périmètre (ton point 4). Rien fait. Note : le
  commentaire de colonne que je viens de réécrire devra être repris par ce renommage.
- **`job_cluster_cost_daily`** (T001b, commit `639ac8e`) : non modifié. **Mais sa docstring devient
  fausse par mon fait** — lignes 129-137, elle annonce « le correctif est le même que côté pipeline
  (T001c) : porter `billing_origin_product` dans le grain, pas ajouter un filtre ». T001c a fait
  l'inverse : un filtre, pas une colonne de grain. Correction d'une phrase, non appliquée parce que
  tu as explicitement mis ce fichier hors périmètre. À faire dans la foulée.
- **§10.2 `product_features.is_serverless`** = T001g : rien fait.
- **Troisième occurrence du défaut** (`grain_resolution.pipeline_clusters_cte_sql`, ligne 103) :
  signalée et chiffrée (§6, 1 couple sur 179 043), non corrigée — ton brief nommait les deux
  tables de coût.
- **`resources/job_dcm_gold_dbx_compute.yml`** : non modifié (lu seulement, et restauré à
  l'identique après le sabotage S12). Le paramètre de job éventuel reste ton arbitrage (§2).
- **Aucun commit, aucune branche créée ou changée.** Le stamp de review pré-commit
  (`/speckit.dcm.review --commit`) reste à ta charge.
