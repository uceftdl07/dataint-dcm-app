# T001 — DataEng : histogramme de latence en gold et exclusion des tables éphémères

**Domain**: dataeng
**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/024-usage-tracking-governance` ⚠️ **branche unique partagée** avec
T002 et T003 — ne pas créer `dataeng/024-histogramme-…` que le parseur dérive du titre
**Jira**: `DCINT-334` (1 seule Story pour les 3 tasks)
**Depends on**: none pour l'étape 1 · étape 2 : spec 027 livrée (`is_deleted` sur
`gold_dbx_usage_table_catalog`) et T002 étape 6 (la jointure d'anti-appartenance)
**Work type**: feature

## Description

Deux changements de la couche gold usage, tous deux bornés à
`packages/dcm-databricks-pipeline` :

1. **Un histogramme de latence** (FR-020) sur `gold_dbx_usage_table_query_performance_daily`, pour
   que le P95 soit reconstituable sur une période arbitraire — sans rescanner
   `curated_dbx_query_history` et sans violer P12 (agrégations métier en Gold uniquement).
2. **L'exclusion des tables éphémères** (FR-024) des 5 tables gold porteuses de la clé de table :
   les tables de staging créées et droppées par un même run de job n'ont jamais été des
   objets gouvernés, et le registre en fabriquait une ligne marquée supprimée à chaque
   exécution.

Aucun grain, aucune clé de merge n'est modifié. `workspace_id` n'est **pas** ajouté
(arbitré et écarté — cf. Clarifications de la spec).

---

## Étape 1 — Histogramme de latence pour un P95 de période

`gold_dbx_usage_table_query_performance_daily` ne stockait qu'un `percentile_approx`
quotidien, dont **aucun P95 de période n'est recalculable**. Une colonne est ajoutée au
grain existant `(cloud_provider, catalog, schema, table_name, period_start)` :

| Colonne | Type | Sémantique |
|---|---|---|
| `latency_bucket_counts` | `MAP<STRING, BIGINT>` | clé = borne supérieure du bucket en ms, valeur = nombre de statements |

Les compteurs étant additionnables, l'API (T002) reconstitue le P95 par interpolation.
Bornes fixes, log-espacées (ms), déclarées en constante `LATENCY_BUCKET_UPPER_BOUNDS_MS`
dans `specs.py` au même titre que `USAGE_FAILURE_RATE_PCT_THRESHOLD` — aucun littéral
numérique dans le SQL :

```
10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 300000, +inf
```

Les durées viennent de la **même** CTE de statements que celle qui alimente déjà
`latency_p95_ms` : pas de second chemin de lecture vers `query_history`.

`LATENCY_BUCKET_UPPER_BOUNDS_MS` est un **contrat d'écriture** : le modifier rend
l'historique déjà écrit inadditionnable et impose un full-refresh. Le point est commenté
dans le code. La convention `MAP<STRING,BIGINT>` diffère de l'`array<bigint>` de
`gold_dbx_compute/sql_helpers.py` — duplication assumée entre domaines gold, et T002 doit
traiter une clé absente comme `0`.

`latency_p95_ms` est **conservée** : T002 peut basculer sans casser un lecteur éventuel.

---

## Étape 2 — Écarter les tables éphémères du catalogue et des faits

`gold_dbx_usage_table_catalog` fabrique une ligne pour toute table absente du référentiel
dont l'audit porte un `deleteTable`. Or les jobs Databricks créent et droppent des tables
de staging à chaque exécution : chacune produit un `createTable` puis un `deleteTable`,
donc une ligne de registre marquée supprimée pour un objet que personne n'a jamais
gouverné.

L'accumulation est irréversible en l'état : `merge_into_table` ne supprime **jamais** de
ligne cible, donc l'état `DELETED` une fois écrit y reste pour toujours. C'est un effet de
bord explicitement voulu par la spec 027 (survivre à la sortie de l'événement d'audit de la
fenêtre de rétention), correct pour une vraie suppression et ruineux pour un intermédiaire
d'exécution. Le registre grossit sans borne, et toute anti-appartenance calculée dessus se
dégrade avec lui (T002 étape 4).

Le discriminant retenu est la **durée de vie auditée**, pas le nom, pas le tag, pas
l'usage : un objet gouverné (déclaré, tagué, consommé, sauvegardé) ne vit pas moins d'une
heure, un intermédiaire d'exécution ne vit pas plus.
`EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS = 3600`, retenu après mesure de la distribution des
durées de vie sur la warehouse de dev, qui n'est pas un continuum mais deux paquets
séparés.

### Cinq tables, pas seulement le registre

La première version de cette étape ne traitait que `gold_dbx_usage_table_catalog`. La
review du subagent `dp-data-databricks-engineer` l'a bloquée sur un point vérifié depuis la
source : **l'exclusion en aval lit une PRÉSENCE, pas une absence.**

```python
f"{column} NOT IN (SELECT table_full_name FROM {GOLD_TABLE_CATALOG} "
"WHERE is_deleted AND table_full_name IS NOT NULL)"
```

Ce prédicat est appelé depuis **11 sites** de l'API, tous appliqués aux **tables de fait**.
Le seul signal qui cache aujourd'hui une éphémère est donc sa ligne `is_deleted = true` au
registre. Retirer cette ligne sans retirer les lignes de fait la ferait **réapparaître
comme une table vivante** — l'inverse exact de ce que T002/T003 ont livré pour FR-023.

Deux issues ont été écartées avant celle-ci, chacune par une mesure :

- **basculer l'exclusion sur l'appartenance au registre** (semi-jointure : est exclu ce qui
  n'est pas dans `curated_dbx_uc_tables`) cacherait **66 264 tables de production
  vivantes**, des catalogues entiers étant absents du référentiel faute de GRANT sur le
  principal d'ingestion — dont un à 35 M de requêtes ;
- **garder une ligne d'éphémère sous un `lifecycle_state` dédié** laisserait au registre le
  volume que l'étape veut couper, donc la jointure d'anti-appartenance coûteuse.

La purge porte donc sur **toutes les tables qui portent la clé de table** :

| Table gold | Filtre à l'écriture | Purge | Pourquoi |
|---|---|---|---|
| `table_catalog` | oui (`deleted_only`) | oui | le registre lui-même |
| `table_daily` | oui | oui | fait porteur de la clé, source des deux suivantes |
| `table_popularity_daily` | **hérité** | oui | prend ses clés de `table_daily` (`FROM daily_agg`), n'enrichit que par LEFT JOIN |
| `table_query_performance_daily` | oui, le sien | oui | lit lineage + `query_history`, n'hérite de rien |
| `table_governance` | hérité du registre | oui | écrite **sans** `absent_row_delete_predicate` : une clé que le registre ne produit plus y **gèle** |
| `consumer_daily` | hérité | **non** | grain CONSOMMATEUR : ne porte aucune colonne de la clé de table, rien à apparier |
| `recommendations` | — | **non** | s'auto-répare : `status = 'RESOLVED'` dès qu'un candidat n'est plus émis |
| `forecast_daily` | — | **non** | aucune colonne de clé de table ; `FORECAST_MIN_OBSERVED_DAYS = 8` rend une clé éphémère inéligible, et sa source `table_popularity_daily` est purgée |

La définition de « éphémère » est écrite **une seule fois**, dans
`pipelines/gold_dbx_usage/ephemeral_tables.py`. Une divergence entre deux de ces tables ne
se verrait pas : chacune resterait cohérente avec elle-même, seule la jointure entre elles
mentirait.

### Deux mécanismes, tous les deux nécessaires

**1. Ne pas écrire** — filtre dans la CTE `deleted_only` de `build_table_catalog`, et
`not_ephemeral_predicate` sur la projection publiée des faits :

```sql
last_operation AS (
    SELECT …,
        MAX(event_time) AS last_operation_at,
        MIN(CASE WHEN action_name = 'createTable' THEN event_time END) AS created_event_at
    …
),
deleted_only AS (
    SELECT lo.cloud_provider, lo.catalog, lo.schema, lo.table_name
    FROM last_operation lo
    LEFT ANTI JOIN base b ON …
    WHERE lo.last_operation = 'deleteTable'
      AND (
          lo.created_event_at IS NULL
          OR unix_timestamp(lo.last_operation_at) - unix_timestamp(lo.created_event_at)
             >= 3600
      )
)
```

**2. Retirer après coup** — `purge_ephemeral_rows`, appelée après l'écriture de chacune des
cinq tables. Le filtre ci-dessus n'écrit plus de ligne d'éphémère, mais il ne retire rien :

- les lignes écrites par les runs antérieurs restent, le registre étant un snapshot
  recalculé mais **écrit en MERGE** ;
- surtout, la ligne `ACTIVE` d'une table qu'un run a vue **vivante**, entre son
  `createTable` et son `deleteTable`, est entrée par le référentiel et non par
  `deleted_only` : aucun filtre de durée de vie ne peut la voir passer. Elle reste ensuite
  un fantôme `ACTIVE` pour une table qui n'existe plus.

```sql
MERGE INTO {table_cible} AS cible
USING (
    -- les 4 CTE rendues par `ephemeral_keys_cte`, seule définition de l'éphémère
    WITH cles_ephemeres_referentiel AS (…), …, cles_ephemeres AS (…)
    SELECT cloud_provider, catalog, schema, table_name FROM cles_ephemeres
) AS ephemere
  ON cible.cloud_provider = ephemere.cloud_provider AND …
WHEN MATCHED THEN DELETE
```

Le corps des CTE n'est **pas** recopié ici, volontairement : ce serait une seconde copie de
la définition que l'étape existe pour unifier, et c'est elle qui dériverait la première.

Trois conditions cumulatives, aucune redondante :

- **absente du référentiel maintenant** (`LEFT ANTI JOIN`) : une clé présente dans
  `curated_dbx_uc_tables` (full load purge) est vivante au moment du run, quelle que soit
  son histoire d'audit. C'est ce qui protège un nom réutilisé et une table recréée ;
- **`deleteTable` comme dernière opération** : l'absence du référentiel vient
  majoritairement d'un privilège manquant sur le principal d'ingestion (cf.
  `LIFECYCLE_STATE_UNKNOWN`), elle ne prouve rien ;
- **âge connu et sous le seuil** : une naissance sortie de la fenêtre de rétention d'audit
  ne permet pas de conclure.

**Appariement sur la clé de TABLE**, jamais sur la clé de merge de la cible : sur un fait,
une clé éphémère doit perdre **toutes** ses lignes datées, pas celles d'un jour. Plusieurs
lignes cible pour une ligne source est licite en MERGE ; c'est l'inverse qui lève
`DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`, et la source est ici un
`GROUP BY` sur ces 4 mêmes colonnes.

Le `ON` ne porte **aucun** prédicat d'état (`is_deleted`, `lifecycle_state`) : c'est
précisément ce qui permet de retirer la ligne `ACTIVE` d'une table vue vivante. En ajouter
un par réflexe défensif rendrait la purge aveugle à ce fantôme, qui est justement la ligne
qu'aucun filtre à l'écriture ne peut atteindre.

**Ordre imposé dans `entrypoint.py`** : écrire → purger → compter. La purge suit l'écriture
(c'est le MERGE du writer qui vient de reposer les lignes, et lui ne supprime jamais) et
précède le comptage de contrôle FR-018, sinon la mesure annonce des suppressions qui ne
sont plus dans la table. La position de la purge se lit par rapport au **MERGE d'écriture**
et non au nombre d'instructions émises : le writer intercale des dizaines de
`COMMENT`/`ALTER COLUMN`, si bien qu'un simple encadrement `0 < i < len - 1` resterait vrai
en déplaçant la purge avant l'écriture.

**Le registre est purgé en dernier dans le DAG du job.** `gold_usage_table_catalog` gagne
deux `depends_on` qui ne correspondent à aucune lecture : `table_popularity_daily` et
`table_query_performance_daily`. Sa ligne `is_deleted` est le seul signal par lequel l'API
cache une éphémère ; purger le registre avant les faits ouvrirait à chaque run une fenêtre
où l'éphémère est visible comme une table **vivante**, et avec `max_retries: 0` une tâche
de fait en échec laisserait cette fenêtre ouverte jusqu'au prochain run réussi. Reste une
fenêtre irréductible : `table_governance` **lit** le registre, elle ne peut donc pas être
purgée avant lui — sa durée est celle de sa propre tâche.

**Le nombre de lignes retirées est journalisé** (`num_deleted_rows` du MERGE, lu par nom de
colonne). C'est la seule opération destructrice de cette couche gold : sans trace, personne
ne verrait un pic. La métrique est lue mais jamais exigée — une session qui ne la publierait
pas ne doit pas faire échouer la tâche, le log dit alors « compte non rapporté » plutôt que
zéro, qui serait faux.

### Points de sémantique

- **La naissance vient de l'audit**, pas du référentiel : une table supprimée n'a plus de
  ligne dans `curated_dbx_uc_tables`, donc plus de `created` à comparer.
  `created_event_at` ne sert qu'à mesurer et **n'est jamais publiée** — `created_at` reste
  celui du référentiel.
- **`MIN(createTable)` et non `MAX`** : sur un nom réutilisé, la durée obtenue couvre toute
  l'activité auditée, donc la plus longue des lectures possibles. L'erreur va toujours dans
  le sens « garder ».
- **Les deux prédicats sont écrits en positif et strictement complémentaires** : réunion =
  toutes les lignes, intersection = vide. Un chevauchement ferait écrire puis supprimer la
  même ligne à chaque run ; un trou y laisserait un fantôme définitif. D'où l'`IS NULL` d'un
  côté et l'`IS NOT NULL` de l'autre, et non un `NOT (…)` : l'âge **inconnu** est gardé des
  deux côtés, jamais d'action sur un doute.
- **Une éphémère n'obtient aucune ligne** : ni `DELETED`, ni `UNKNOWN`, ni rien. Dit dans le
  commentaire de colonne de `lifecycle_state`, sinon quelqu'un la cherchera sous un autre
  état.
- **Le contrat des 5 tables purgées dit désormais qu'une ligne peut disparaître.** C'est le
  seul cas, et c'était impossible avant.
- **Ce qui est perdu en purgeant les faits est une ATTRIBUTION, pas une vérité de
  facturation.** `table_daily.estimated_cost_usd` est une répartition (`cost_basis`,
  `cost_attribution_method`) ; la dépense de référence vit dans `gold_dbx_compute`,
  alimentée par le billing. Les lignes retirées portent 0,89 % du coût attribué du périmètre
  mesuré.
- **Une clé dont `catalog`/`schema` est NULL** (nom malformé dans l'audit) n'est atteinte ni
  par le filtre ni par la purge, qui comparent colonne par colonne. Sa ligne de registre
  reste, avec `is_deleted = true` : l'exclusion en aval continue de la cacher. Comportement
  d'avant l'étape 2, préservé.

### Pourquoi pas `absent_row_delete_predicate`

`merge_into_table` accepte un `absent_row_delete_predicate` qui ajoute
`WHEN NOT MATCHED BY SOURCE AND <prédicat> THEN DELETE` — il retirerait en une ligne toute
clé absente de la source. Écarté : il retirerait **aussi** les vraies suppressions dès que
leur événement d'audit quitte la fenêtre de rétention, et rien dans la cible ne distingue
« sortie de rétention » de « éphémère ». Or la survie des lignes `DELETED` à cette sortie
est un choix explicite de la spec 027. La purge est donc ciblée sur une **preuve**, pas sur
une absence. `absent_row_delete_predicate` n'est d'ailleurs utilisé **nulle part** dans
`gold_dbx_usage` (vérifié depuis la source) : aucune table de ce plugin ne s'auto-répare par
suppression.

### Pas de nettoyage manuel

Aucun `TRUNCATE` ni `DELETE` à passer à la main : la purge traite l'existant au premier run,
exactement comme les lignes futures. Seules subsistent les lignes dont la naissance est
sortie de la fenêtre de rétention d'audit — gardées faute de preuve, ce qui est le
comportement voulu.

---

## Files to create/modify

Étape 1 :

- UPDATE `pipelines/gold_dbx_usage/specs.py` — `LATENCY_BUCKET_UPPER_BOUNDS_MS`,
  `LATENCY_BUCKET_OVERFLOW_KEY`, commentaire de colonne `latency_bucket_counts`
- UPDATE `pipelines/gold_dbx_usage/table_query_performance_daily.py` — compteurs par bucket
- UPDATE `tests/gold_dbx_usage/test_specs.py`,
  `tests/gold_dbx_usage/test_table_query_performance_daily.py`

Étape 2 :

- UPDATE `pipelines/gold_dbx_usage/sql_helpers.py` —
  `EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS`, en secondes (la durée de vie se mesure par
  différence de deux `unix_timestamp`)
- CREATE `pipelines/gold_dbx_usage/ephemeral_tables.py` — **définition unique** :
  `TABLE_KEY_COLUMNS`, les deux prédicats complémentaires (`LIVED_LONG_ENOUGH_PREDICATE`,
  `WAS_EPHEMERAL_PREDICATE`), `table_operations_cte`, `ephemeral_keys_cte`,
  `not_ephemeral_predicate`, `purge_ephemeral_rows`
- UPDATE `pipelines/gold_dbx_usage/table_catalog.py` — `created_event_at` dans
  `last_operation`, filtre dans `deleted_only`, bascule sur le module partagé (la fonction
  `purge_ephemeral_tables` locale disparaît), docstring de module
- UPDATE `pipelines/gold_dbx_usage/table_daily.py` — nouveau paramètre
  `table_operations_table`, CTE des clés éphémères, filtre sur la projection publiée (dont
  héritent `table_popularity_daily` et `consumer_daily`)
- UPDATE `pipelines/gold_dbx_usage/table_query_performance_daily.py` — même chose, son
  propre filtre : elle ne dérive d'aucune table gold
- UPDATE `pipelines/gold_dbx_usage/entrypoint.py` — `PURGED_OF_EPHEMERAL_TABLES` (les 5
  tables), nouveaux arguments des deux builders, purge après l'écriture
- UPDATE `pipelines/gold_dbx_usage/specs.py` — commentaire de colonne `lifecycle_state`, et
  `_EPHEMERAL_PURGE_CONTRACT` ajouté au commentaire des **5** tables purgées
- UPDATE `resources/job_dcm_gold_dbx_usage.yml` — le registre est purgé **en dernier** :
  deux dépendances qui ne correspondent à aucune lecture
- CREATE `tests/gold_dbx_usage/test_ephemeral_tables.py` — 15 cas, dont la complémentarité
  **évaluée** sur SQLite et l'absence de prédicat d'état dans le `ON`
- UPDATE `tests/gold_dbx_usage/test_specs.py` — le périmètre lu depuis
  `PURGED_OF_EPHEMERAL_TABLES` et non recopié
- UPDATE `tests/gold_dbx_usage/test_table_catalog.py` — les tests de purge partent dans le
  module ci-dessus ; restent ceux du filtre à l'écriture
- UPDATE `tests/gold_dbx_usage/test_table_daily.py` — filtre posé, hérité par les deux
  dérivées
- UPDATE `tests/gold_dbx_usage/test_table_query_performance_daily.py` — filtre propre, posé
  du côté lineage de la jointure
- UPDATE `tests/gold_dbx_usage/test_entrypoint.py` — ordre des étapes comparé au MERGE
  d'écriture, purge sur les 5 tables, absence de purge sur les 2 autres, périmètre de purge
  **dérivé** du critère

## Acceptance Criteria

### Étape 1 — histogramme de latence

Les 4 critères data sont **prouvés sur la vraie donnée** par l'audit `dbx-validate` (profil
rapide, 13 requêtes en lecture seule, `@v374`, 3 643 242 lignes / 66 jours). Plan, findings,
rapport et harnais SQL rejouable : `specs/024-usage-tracking-governance/validation/` —
**artefacts locaux, non versionnés** (`.gitignore` § databricks-data-validator).

- [x] **Conservation** : `SUM(map_values(latency_bucket_counts)) = query_count` sur
      **3 643 229 / 3 643 242** lignes ; les 13 restantes sous-comptent d'exactement 1,
      prouvé imputable à 13 statements sans `total_duration_ms` en amont (13/13,
      correspondance exacte). Aucune ligne ne sur-compte
- [x] **Additivité** : sur 30 j × top 5 tables, l'`AVG` des P95 quotidiens sort du bucket
      correct sur 2/5 et le `MAX` sur 5/5. P95 de période réel **1 236 ms** vs **5 163,8 ms**
      en `AVG` (+318 %) et **16 560 ms** en `MAX` (×13) — ce n'est donc pas un repli déguisé
- [x] **Fidélité** : le `percentile_approx` recalculé sur `curated_dbx_query_history` tombe
      dans le bucket interpolé pour **5/5** tables sur période, et le `latency_p95_ms`
      quotidien pour **3 643 229 / 3 643 229** lignes (l'unique cas limite vaut exactement
      la borne, écart 0 ms)
- [x] **Idempotence (P6)** : recalcul indépendant depuis curated — **22 grains, 22
      `query_count` identiques, 22 jeux de clés identiques, 22 maps identiques valeur par
      valeur**
- [x] **Pas de fabrication** : `map_filter(..., n > 0)` omet les buckets vides ; **0**
      compteur ≤ 0, **0** map `NULL`, 13 maps vides = exactement les 13 (table, jour) sans
      durée mesurée
- [x] `latency_p95_ms` **existant conservé**
- [x] Bornes déclarées en constante commentée, aucun littéral numérique dans le SQL ; test
      comparant les clés rendues à la constante, **0** clé hors bornes observée en base

### Étape 2 — tables éphémères

- [x] Une table dont la vie auditée fait moins de `EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS`
      n'obtient **aucune ligne**
- [x] Une ligne d'éphémère **déjà écrite** est retirée au run suivant, y compris la ligne
      `ACTIVE` d'une table vue vivante par un run
- [x] Une ligne dont la clé est **présente au référentiel** n'est jamais retirée
- [x] Une suppression sans `deleteTable` audité n'est jamais retirée
- [x] Une table supprimée d'âge **inconnu** est gardée — et n'est pas purgée non plus
- [x] Les deux prédicats sont complémentaires, et cette complémentarité est **évaluée**
      (SQLite, quatre cas) et non lue par sous-chaîne : aucune ligne écrite puis supprimée à
      chaque run, aucune ligne hors de portée des deux
- [x] Une clé éphémère ne laisse **aucune ligne** dans les tables de fait porteuses de la
      clé de table, ni dans `table_governance` — sinon l'exclusion en aval, qui lit la
      présence d'une ligne `is_deleted` au registre, la ferait réapparaître **vivante**
- [x] La purge apparie sur la clé de **table** et sur elle seule : toutes les lignes datées
      d'une clé éphémère partent, pas celles d'un jour ; le `ON` ne porte aucun prédicat
      d'état
- [x] La définition de « éphémère » n'existe qu'en **un seul endroit**
- [x] Le nombre de lignes retirées est journalisé, et son absence ne fait pas échouer la
      tâche
- [x] `created_event_at` ne sort pas dans les colonnes publiées ; `created_at` reste celui du
      référentiel
- [x] Le seuil est une constante nommée, unique, partagée par les deux prédicats
- [x] Le contrat des **5** tables purgées dit qu'une ligne peut disparaître, et un test lit
      ce périmètre depuis `PURGED_OF_EPHEMERAL_TABLES` au lieu de le recopier ; le contrat de
      colonne dit qu'une éphémère n'est ni `DELETED` ni `UNKNOWN` mais absente
- [x] Le registre est purgé **après** les faits dans le DAG du job
- [x] Tests falsifiés (4 falsifications, échecs constatés puis restauration)
- [ ] Effet vérifié sur la warehouse **après** déploiement du job — non vérifiable depuis ce
      poste, le pipeline ne tourne pas en local (voir Notes)

### Les deux étapes

- [x] Aucun fichier hors `packages/dcm-databricks-pipeline/` et
      `specs/024-usage-tracking-governance/`
- [x] `ruff` / `ruff format` / `mypy` n'ajoutent aucune erreur au périmètre

## Tests

```bash
cd packages/dcm-databricks-pipeline
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/ -q
```

Une suite verte sur des assertions portant sur le **texte du SQL généré** ne prouve rien sur
la donnée (cf. skill `dbx-validate-sql-render`) : les invariants de conservation et
d'idempotence de l'étape 1 sont prouvés par `dbx-validate` sur la warehouse, et la
complémentarité des prédicats de l'étape 2 est **exécutée** sur SQLite plutôt que lue par
sous-chaîne.

## Out of scope

Étape 1 :

- Toute autre table gold que `gold_dbx_usage_table_query_performance_daily`
- Ajout de `workspace_id` où que ce soit (arbitré et écarté — cf. Clarifications)
- Changement de grain, de clés de merge ou de fenêtre incrémentale
- Suppression ou renommage de `latency_p95_ms`
- Sketch t-digest / UDF de merge — écarté pour complexité non justifiée (P2)

Étape 2 :

- **Rétention sur les lignes DELETED.** Avec le filtre, la croissance du registre redevient
  de l'ordre des suppressions réelles : la rétention devient un confort. Et c'est un
  arbitrage de la spec 027, dont le comportement actuel est explicitement voulu.
- **Filtrer par pattern de nom.** Encode la convention de nommage d'une équipe : le jour où
  quelqu'un renomme, le filtre se tait sans bruit. Écarté comme règle ; utilisable en second
  rideau sous forme de liste de schémas scratch en config si le seuil ne suffit pas.
- **Filtrer par tag ou par usage.** Mesuré inutilisable : les tables de staging ne portent
  aucun tag, et `last_read_at` est renseigné sur la quasi-totalité d'entre elles — la table
  de staging est lue par le job qui la crée, avant d'être droppée.
- **La branche `UNKNOWN` de `lifecycle_state` est morte.** `socle` = `base` (toujours
  `present_in_referential`, donc `ACTIVE`) ∪ `deleted_only` (filtrée sur `deleteTable`, donc
  `DELETED`) : aucune ligne ne peut atteindre le `ELSE`. Ce n'est pas un défaut — un `ELSE`
  défensif est correct — mais le contrat de colonne décrit `UNKNOWN` comme un cas courant
  alors qu'il ne se produit jamais. Constaté en passant, pas corrigé : ça touche la
  sémantique de la spec 027.
- **Bascule de l'exclusion en aval sur une semi-jointure au référentiel.** Ce serait la
  forme naturelle une fois les éphémères hors registre — et elle cacherait 66 264 tables de
  production vivantes, faute de GRANT sur le principal d'ingestion. Aucun changement backend
  ici : la purge des faits obtient le même résultat sans y toucher.
- **Purge de `consumer_daily`.** Grain consommateur, aucune colonne de la clé de table :
  rien à apparier. Elle hérite du filtre de `table_daily` pour la fenêtre recalculée ; les
  jours plus anciens gardent une contribution d'éphémère jusqu'à un `--full-refresh`. Le
  corriger demanderait de lui ajouter une clé de table, donc de changer son grain.
- **Matérialisation des clés éphémères dans une table dédiée.** Les cinq tables sont cinq
  tâches, donc cinq sessions Spark : l'agrégat d'audit est reconstruit **8 fois par run**
  (5 purges + les 2 filtres de builder + celui du registre), soit +7 par rapport à avant.
  Ce scan-là reste peu coûteux — `curated_dbx_uc_table_operations` est
  `system.access.audit` restreint à 3 actions DDL, pas la plus grosse source curated. Ce qui
  domine est ailleurs et n'est pas non plus traité ici : **chaque purge est un MERGE qui
  scanne sa table cible en entier**, sur des tables écrites sans partitionnement ni liquid
  clustering. Coût assumé. Le borner dans le temps n'est **pas** l'issue — le stock antérieur
  ne serait alors jamais purgé. Matérialiser les clés une fois par run fermerait aussi la
  fenêtre où chaque purge recalcule l'ensemble à **son** instant, un `deleteTable` arrivé en
  cours de run étant sinon purgé de certaines tables et pas des autres.
- **Garde-fou volumétrique et trace persistée sur la purge.** `pipelines/common/purge.py`
  porte la convention du dépôt pour les opérations destructrices (seuil absolu + pourcentage,
  `PurgeAuditRecord` inconditionnel) ; ici il n'y a qu'un log. C'est la première opération
  destructrice de la couche gold : le sujet est réel, mais choisir les seuils est un
  arbitrage, pas un détail d'implémentation.

## Revues

| Étape | Rapport | Verdict | Reste ouvert |
|---|---|---|---|
| 1 — histogramme | review 2026-09-11 | **PASS** (0 🔴, 0 🟡 — 1 résolu par l'audit `dbx-validate`, 3 🟢) | rien |
| 2 — éphémères | review 2026-09-17, subagent `dp-data-databricks-engineer`, 2 passes (la 1<sup>re</sup> a rendu FAIL) | **WARN** (0 🔴, 7 🟡) | le garde-fou volumétrique et la trace persistée (voir Out of scope) |

Le FAIL de la première passe portait sur le périmètre : purger le seul registre détruisait
le signal que l'exclusion en aval consomme. Levé en élargissant aux 5 tables, table par
table depuis `GOLD_SPECS`, pas par affirmation. Six des sept 🟡 ont été corrigés dans la
même task (ordre du DAG, périmètre dérivé par test, contrat des 5 tables, chiffrage du coût
dans le docstring et dans Out of scope) ; le septième est l'absence de garde-fou
volumétrique, consignée en Out of scope parce que choisir un seuil est un arbitrage.

## Before PR

- [x] Tests pass
- [x] No files outside package scope
- [x] Diff stays reviewable
- [x] Sub-spec checkboxes reviewed
- [x] Jira Story lists **Git branch** name (not a commit SHA)
- [ ] `/speckit.dcm.review --commit` avant le `git commit` de l'étape 2

## Notes

- **Délégation obligatoire** : `dcm-config.yml` impose
  `domain_subagents.dataeng: "Databricks Data Engineer"` avec
  `domain_subagents_required: true`. Cette task se code via le subagent
  `dp-data-databricks-engineer`, pas par l'agent principal.
- **Exécution sur le workspace partagé** : charger `dbx-exec-safety` avant tout run ou
  deploy. Un full-refresh ou un `DROP` exige une confirmation explicite de l'utilisateur.
- Décision de conception de l'étape 1 : **D10** de [research.md](../research.md).
- Après l'étape 1, la table doit être **rafraîchie** avant de démarrer T002 — sinon l'API
  lira une colonne vide.
- Le dernier critère de l'étape 2 reste ouvert **par honnêteté** : les tests portent sur le
  SQL généré, la mesure d'avant portait sur la warehouse, mais l'effet réel ne se constatera
  qu'au prochain run du job. Requête de vérification :
  `SELECT COUNT(*) FROM {schema}.gold_dbx_usage_table_catalog WHERE is_deleted`.
- Le lien avec l'étape 4 de T002 est causal : la lenteur des recommandations venait d'une
  forme de prédicat **et** d'un volume qui n'aurait jamais dû exister. Corriger l'un sans
  l'autre laissait la moitié du problème.
