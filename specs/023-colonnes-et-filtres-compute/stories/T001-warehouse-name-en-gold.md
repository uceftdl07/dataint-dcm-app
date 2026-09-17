# T001 — `warehouse_name` en gold sur utilisation et performance des requêtes

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: `dataeng/023-warehouse-name-en-gold`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: rien
**Work type**: feature

## Description

Les 4 tables gold `gold_dbx_compute_warehouse_utilization_daily`/`_rolling` et
`gold_dbx_compute_warehouse_query_performance_daily`/`_rolling` n'exposent que
`warehouse_id`. Cette task y ajoute `warehouse_name`, résolu depuis
`curated_dbx_compute_warehouses` selon la règle **déjà** appliquée par
`warehouse_cost_daily.py` : dernier état connu à `period_start`, propagé au grain fenêtre
par `latest_attrs`.

Ce qui bloque réellement T002 est le seul couple `query_performance_daily`/`_rolling` —
`rg "warehouse_utilization" packages/dcm-backend/app/` ne renvoie rien, aucun endpoint ne
lit les tables d'utilisation. Elles sont incluses parce que le coût y est de 3 lignes
chacune (la jointure curated est déjà en place dans la quotidienne) et que les 4 familles de
tables warehouse portent alors le même attribut identifiant.

Deux options ont été rejetées, avec mesure : joindre la table de coût gold laisserait ~80 %
des lignes anonymes (`warehouse_cost_rolling` se termine par
`WHERE cost_usd <> 0 OR cost_usd_prev_window <> 0`, donc un warehouse non facturé n'y a
aucune ligne) ; joindre le curated côté API ferait franchir la frontière médaillon à un
service qui ne lit aujourd'hui que du gold. Détail en [research.md](../research.md) R1.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_utilization_daily.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_utilization_rolling.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_query_performance_daily.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_query_performance_rolling.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_warehouse_utilization.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_warehouse_query_performance.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py`

## Sub-tasks

- [x] **Tests d'abord**, sur le SQL généré (`FakeSpark`, aucune JVM) :
      `warehouse_name` présent dans le `SELECT` final des 4 builders ; la jointure de
      `query_performance_daily` est un `LEFT JOIN` borné par `change_time <= period_start`
      (**borne remplacée** par `< period_start + INTERVAL 1 DAY` — voir l'extension ci-dessous ;
      les assertions de test ont suivi) et un `QUALIFY ROW_NUMBER()` partitionné sur les 3 clés
      + `period_start` ;
      `latest_attrs` des 2 rolling porte `warehouse_name` et ordonne par `period_start DESC`.
- [x] `warehouse_utilization_daily.py` : ajouter `w.warehouse_name` à la CTE
      `warehouses_as_of` existante (l. 439-457), le propager dans `enriched` (à côté de
      `wa.auto_stop_minutes`, `wa.max_clusters`) puis dans le `SELECT` final.
- [x] `warehouse_utilization_rolling.py` : ajouter `warehouse_name` à la CTE `daily`, à
      `latest_attrs` (l. 94) et le rendre en `la.warehouse_name` dans le `SELECT`.
- [x] `warehouse_query_performance_daily.py` : nouveau paramètre **keyword-only**
      `warehouses_table: str`, nouvelle CTE `warehouses_as_of` **copiée sur celle de
      `warehouse_cost_daily.py`** (même prédicat, même `QUALIFY`), `LEFT JOIN` sur les
      3 clés + `period_start`, puis `warehouse_name` dans le `SELECT` final.
- [x] `warehouse_query_performance_rolling.py` : ajouter `warehouse_name` à la CTE `daily`,
      à `latest_attrs` (l. 100-111, à côté de `top_slow_statement_id`) et rendre
      `la.warehouse_name`.
- [x] `entrypoint.py` (l. ~316) : passer `warehouses_table=` à
      `build_warehouse_query_performance_daily`, en réutilisant la constante déjà résolue
      pour les autres builders — **pas** un littéral.
- [x] `specs.py` :
      `WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC.source_tables` passe de
      `(CURATED_QUERY_HISTORY,)` à `(CURATED_QUERY_HISTORY, CURATED_COMPUTE_WAREHOUSES)` ;
      `warehouse_name` ajouté aux 4 dicts `*_COLUMN_COMMENTS` avec la **règle de
      résolution** dans le texte (c'est la seule doc visible dans Catalog Explorer).
- [x] Vérifier qu'aucune `merge_keys` ne change : `warehouse_name` est un attribut, jamais
      une clé — un renommage ne doit pas créer une seconde ligne.
- [x] Gates : `pytest` (suite complète), `ruff check pipelines tests`,
      `mypy pipelines --explicit-package-bases`.
- [x] Déploiement dev + les 5 contrôles de [quickstart.md](../quickstart.md) §4.

### Extension arbitrée le 2026-09-07 — la borne `change_time <= period_start`

Après T007 et un `full_refresh`, SC-001 mesure **97,1 à 100 %** sur `query_performance_rolling`
mais **90,3 % (w90) et 93,2 % (w30)** sur `utilization_rolling` : sous le seuil. La cause n'est
plus l'ingestion, c'est la borne de résolution du nom.

> **Mon constat #2 en [T007](T007-curated-warehouses-en-full-load.md) était faux sur sa
> conclusion.** J'y écrivais que la conséquence de la borne warehouse ne touchait que les tables
> **quotidiennes** et que « les `*_rolling` passent par `latest_attrs` et n'ont pas cette borne,
> donc **SC-001 n'est pas exposé** ». `latest_attrs` n'applique effectivement pas la borne — mais
> il **lit une valeur produite sous elle** : le nom de la ligne quotidienne au `period_start` le
> plus récent. Si ce jour-là le nom est `NULL`, la ligne fenêtre hérite du `NULL`. C'est
> exactement le mécanisme d'héritage décrit en [research.md](../research.md) R9b, avec une autre
> cause en amont.

Les 3 builders quotidiens warehouse bornent la résolution à `change_time <= period_start`, où
`period_start` est une `DATE` — donc **minuit** du jour agrégé. Un warehouse créé *dans* la
journée n'a aucune version satisfaisant ce prédicat : il sort `NULL` ce jour-là. Quand ce jour
est aussi son **dernier** jour d'activité — cas de tous les warehouses éphémères, créés et
utilisés le même jour, jamais retouchés — `latest_attrs` n'a que ce `NULL` à propager, sur les
4 fenêtres.

Mesuré en dev sur le snapshot courant : **100 % des lignes non nommées se résolvent** avec la
borne « journée entière » `change_time < period_start + INTERVAL 1 DAY`, celle de la famille
cluster/job. Aucune n'est absente du curated.

| Table `*_rolling` | w1 | w7 | w30 | w90 |
|---|---|---|---|---|
| `utilization` — non nommées | 5 | 15 | 45 | 71 |
| `query_performance` — non nommées | 0 | 4 | 17 | 20 |
| dont résolues par la borne journée entière | **tout** | **tout** | **tout** | **tout** |
| dont absentes du curated | 0 | 0 | 0 | 0 |

Les warehouses concernés sont sans ambiguïté des éphémères de bundle : `[dev al1128729]
…-serverless-dev-warehouse`, `test sql warehouse`, `DCM-metrics-2`, avec 1 ou 2 versions et un
premier `change_time` à 08:41 / 11:42 / 13:44 le jour même.

- [x] Aligner les **3** builders quotidiens warehouse sur `change_time < period_start +
      INTERVAL 1 DAY` : `warehouse_utilization_daily.py:460`,
      `warehouse_query_performance_daily.py:179`, `warehouse_cost_daily.py:151`.
      `warehouse_cost_daily.py` est inclus **bien qu'il soit hors SC-001** : le laisser créerait
      une **troisième** convention dans le dépôt, pire que la divergence à deux que le constat #1
      de T007 signalait. L'`ORDER BY change_time DESC` du `QUALIFY` est déjà le bon et ne change
      pas.
- [x] Mettre à jour les docstrings et commentaires qui **énoncent** l'ancienne borne :
      `warehouse_cost_daily.py:61`, `warehouse_query_performance_daily.py:65` et `:162`,
      `warehouse_utilization_daily.py:94` et `:152`, et le commentaire de colonne
      `specs.py:1268` (« ou egale au jour agrege (change_time <= period_start) »), qui est la
      seule documentation visible dans Catalog Explorer.
- [x] Test dédié par builder, dont le nom énonce le cas : un warehouse dont l'unique
      `change_time` tombe **dans** la journée doit être nommé ce jour-là. Sans ce test, le
      prédicat peut être « resserré » par mimétisme sur les warehouses et le défaut revient.
- [x] Rejouer les tâches gold en dev **avec** `full_refresh`, puis SC-001 sur le snapshot courant.
      → **fait, et ma consigne initiale était fausse.** Elle disait « **sans** `full_refresh` : la
      borne élargit une jointure, elle ne change pas les données lues ». Vrai sur la lecture, faux
      sur l'écriture : les quotidiennes sont incrémentales (`period_start >= 2026-08-27`), donc un
      run incrémental ne **réécrit** que 10 jours et laisse les lignes antérieures avec le nom
      résolu par l'ancienne borne. Mesuré en incrémental seul : `utilization` w90 plafonne à
      **92,1 %**. Le `full_refresh` rejoué **après** le correctif donne 97,7 / 99,1 / 99,1 /
      99,2 % — SC-001 atteint. L'ordre des deux opérations est donc contraignant.

## Acceptance Criteria

- [x] `warehouse_name` existe en `string` sur les 4 tables, avec son commentaire de colonne
      (quickstart §4.1).
- [x] **SC-001** : `warehouse_name` renseigné sur > 95 % des lignes des 2 tables
      `*_rolling`, sur les 4 valeurs de `window_days` (quickstart §4.2).
- [x] Un warehouse absent de `curated_dbx_compute_warehouses` **garde sa ligne**, avec
      `warehouse_name = NULL` : le `LEFT JOIN` enrichit, il ne filtre pas.
- [x] Aucune ligne perdue ni dupliquée par la nouvelle jointure : le compte de
      `query_performance_rolling` pour `window_days = 1` égale le nombre de warehouses
      distincts du dernier jour de la quotidienne (quickstart §4.4).
- [x] Un warehouse renommé pendant la fenêtre porte son **dernier** nom connu
      (quickstart §4.5) — ou le contrôle est déclaré **non joué** si aucun renommage n'existe
      en dev, pas déclaré vert par défaut.
- [x] Les 3 builders quotidiens warehouse bornent la résolution du nom à `change_time <
      period_start + INTERVAL 1 DAY`, **une seule convention** partagée avec la famille
      cluster/job. Un warehouse créé dans la journée est nommé dès ce jour-là, prouvé par un test
      par builder. Conséquence sémantique assumée : un warehouse renommé à 15:00 le jour J porte,
      pour J, le nom qu'il avait à 23:59 et non à 00:00 — « l'état à cette date » se lit désormais
      **fin de journée**, comme sur les clusters et comme `latest_attrs` le fait déjà côté fenêtre.
- [x] Aucun `DROP TABLE`, aucun `full_refresh` requis : `MERGE WITH SCHEMA EVOLUTION` seul.
- [x] Aucune valeur de repli fabriquée en gold (P9) : `NULL` quand le curated ne sait pas.
      Le repli sur l'id est une décision d'affichage, prise dans `WarehouseCell`.
- [x] Gates verts, suite pipeline complète.

## Notes cyber

- Déploiement par `databricks bundle deploy -t dev` sous **OAuth** (`databricks auth login`).
  Aucun PAT, aucun `DATABRICKS_TOKEN`, aucun `token=`.
- Aucun secret, aucun chemin DBFS : les tables sont dans Unity Catalog, le wheel dans
  `/Workspace/...`.
- La divergence PAT en lecture seule héritée de 022 est consignée en
  [quickstart.md](../quickstart.md) §6.1 — elle ne couvre **pas** le déploiement.
