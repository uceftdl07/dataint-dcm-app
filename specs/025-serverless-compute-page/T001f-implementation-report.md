# Rapport d'implémentation — T001f (`curated_dbx_lakeflow_pipeline_update_timeline` + `gold_dbx_compute_pipeline_update_stats`)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` (aucune branche créée, aucun switch)
· **Base** : `develop`
**Task** : T001f (spec 025) — ingestion **fidèle source** de `system.lakeflow.pipeline_update_timeline`
au grain `(cloud_provider, workspace_id, pipeline_id, update_id, period_start_time)`, **plus** un
builder gold au grain **exécution** `(cloud_provider, update_id)` qui alimente les blocs 2 et 3 de la page.
**Diff** : 10 fichiers, **+1 206 / −4** — 2 fichiers créés (513 l.), 8 modifiés (+693 / −4)
**Rien n'est stagé, rien n'est committé, rien n'est déployé, aucun job lancé.** Mesures : SQL
**lecture seule** via le profil OAuth `dcm-dev`.

## Ce qu'il faut trancher avant déploiement

Trois points, dont **un seul est irréversible**, et il ne concerne pas le gold mais l'ingestion.

1. **`account_id` n'est pas dans les clés de merge de la curated, et ça diverge des deux tables
   sœurs.** `curated_dbx_lakeflow_job_run_timeline` et
   `curated_dbx_lakeflow_job_task_run_timeline` mettent `account_id` en tête de clé ; ma spec ne le
   fait pas. Ce n'est **pas** une contrainte de schéma — `DESCRIBE` confirme que la colonne existe
   dans la source et elle est bien ingérée, elle n'est simplement pas discriminante côté clé
   (`workspace_id` est déjà unique par compte). **Mais c'est irréversible en pratique** : après le
   premier déploiement, changer la clé de merge d'une table Delta déjà peuplée oblige à la
   reconstruire. Deux options, à trancher avant le run : garder `(cloud_provider, workspace_id,
   pipeline_id, update_id, period_start_time)` — cohérent avec le grain réel, 5 colonnes au lieu de
   6 — ou aligner sur les sœurs pour l'uniformité du package. J'ai retenu la première et je la
   signale ; le coût du changement est de deux lignes **maintenant**, d'un `CREATE OR REPLACE`
   **après**.
2. **Le suffixe `_stats` est nouveau dans le package gold.** Toutes les autres tables gold de
   `gold_dbx_compute` sont en `_daily`, `_efficiency_*` ou `_governance`. `pipeline_update_stats`
   est déjà publié dans `plan.md`, `spec.md`, `stories/T001.md` et `stories/T002.md` : je ne l'ai
   pas renommé, conformément à ta consigne. À valider une fois, puisque le nom d'une table gold est
   contractuel pour le backend.
3. **Aucun `depends_on` ne relie le job d'ingestion (03:00) au job gold (05:00).** La dépendance
   est **réelle** — le gold lit la curated que l'ingestion vient d'écrire — mais elle n'est pas
   exprimable dans un `depends_on`, qui est intra-job. Elle ne tient donc qu'à la marge de 2 h
   entre les deux `schedule`. Si l'ingestion des 19 tables dépasse 2 h, le gold recalcule sur une
   curated de la veille **sans lever d'erreur** : il produira des lignes correctes mais en retard
   d'un jour, et la fenêtre de 10 jours les corrigera au run suivant. C'est acceptable, ce n'est
   pas invisible : le YAML porte l'avertissement, et le vrai correctif (un seul job, ou un
   `run_job_task`) est hors périmètre T001f.

**Une valeur que j'avais moi-même publiée était fausse et je l'ai corrigée avant de te la
livrer** : le taux de vide du compute côté jobs est de **97,0 %**, pas 88,5 % (§7.6). Et **deux
assertions de la baseline sont à requalifier**, pas à jeter (§7.2, §7.3).

---

## 1. Ce qui change, fichier par fichier

| Fichier | Nature |
|---|---|
| `pipelines/system_tables/specs.py` | +70 l. — constantes source/cible, clés de merge, `LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC`, entrée du registre (19ᵉ) |
| `resources/job_dcm_system_tables.yml` | +9 / −3 — clé ajoutée aux `inputs` du `for_each_task`, compteurs 18 → 19, avertissement opérationnel |
| `pipelines/gold_dbx_compute/pipeline_update_stats.py` | **créé** (245 l.) — le builder |
| `pipelines/gold_dbx_compute/specs.py` | +266 l. — `GOLD_PIPELINE_UPDATE_STATS`, clés de merge, commentaire de table, 16 commentaires de colonnes, `PIPELINE_UPDATE_STATS_SPEC`, entrée du registre (27ᵉ) |
| `pipelines/gold_dbx_compute/entrypoint.py` | +13 l. — import + entrée de dispatch |
| `resources/job_dcm_gold_dbx_compute.yml` | +28 l. — tâche `gold_pipeline_update_stats` |
| `tests/system_tables/test_specs.py` | +83 / −1 — registre à 19, spec de la nouvelle table, **équivalence registre ↔ `inputs` du YAML** |
| `tests/gold_dbx_compute/test_pipeline_update_stats.py` | **créé** (268 l.) — 13 tests |
| `tests/gold_dbx_compute/test_specs.py` | +129 l. — 8 tests |
| `tests/gold_dbx_compute/test_entrypoint.py` | +95 l. — 5 tests |

Non touchés et pourtant modifiés dans l'arbre : `T001f-baseline-measures.md` et `stories/T001.md`
— ce sont **tes** mises à jour de spec, je ne les ai ni écrites ni réécrites.

## 2. Pourquoi deux artefacts et pas un

La story demandait une seule `IngestionSpec` agrégeant la source par `update_id`. Trois mesures
l'interdisent, et la troisième est celle qui tranche.

1. **`IngestionSpec` n'a pas de crochet d'agrégation.** C'est une dataclass figée
   (`source_table`, `merge_keys`, `watermark_column`, `select_columns`, `row_filter`…) consommée par
   un lecteur qui fait un `df.select(*colonnes)` côté AWS (`pipelines/common/readers.py:68`) et une
   liste de colonnes SQL côté Azure (l. 82). **Aucun alias possible dans un cas comme dans
   l'autre** : `compute.type → compute_type` est déjà impossible, un `GROUP BY` l'est a fortiori.
   Agréger à l'ingestion voudrait dire un lecteur spécial pour une table sur 19.
2. **Une agrégation à l'ingestion serait fausse par construction.** L'ingestion est incrémentale
   sur une fenêtre de **3 jours** (`DEFAULT_LOOKBACK_DAYS`). Or **427 updates** (0,104 %) terminent
   un autre jour calendaire que celui où ils commencent, **184** couvrent au moins 3 jours
   calendaires, **40** au moins 4, et **un** s'étale sur **19 jours / 448,1 h**. Agréger dans la
   fenêtre d'ingestion rendrait pour ces updates un `MIN(period_start_time)` tronqué à la borne de
   la fenêtre, donc une durée **plus courte que la réalité**, sans erreur ni alerte.
3. **La fidélité source est ce qui rend l'erreur rattrapable.** En gardant les tranches, une durée
   mal calculée se recalcule d'un `--full-refresh` du gold. En agrégeant à l'ingestion, la donnée
   fine est perdue : il faut re-télécharger la source, qui ne garde qu'**un an glissant**
   (367 jours au 2026-09-10).

D'où la répartition retenue :

- **curated** = copie fidèle, périodisée, une ligne par tranche d'état. **Aucune** agrégation,
  **aucun** `select_columns` (les 16 colonnes sources, structs et arrays compris), clé de merge au
  grain réel de la source.
- **gold** = une ligne par exécution, agrégation lisant **toute** la curated, fenêtre appliquée à
  la **sortie**.

### La fenêtre : sur la sortie, jamais sur l'entrée

C'est le seul point de conception non évident du builder, et il vaut son explication.

```
lecture curated : AUCUN filtre        → MIN/MAX exacts même pour un update de 19 jours
GROUP BY (cloud_provider, update_id)  → une ligne par clé de merge, structurellement
WHERE 1 = 1 {AND update_end_time >= DATE '...'}  → ce qui part au MERGE
```

Conséquences chiffrées : le MERGE traite **15 054** lignes au lieu de 412 350 (**×27** de moins) sur
une fenêtre de 10 jours, alors que le `GROUP BY` reste exact. Le filtre porte sur
`update_end_time`, qui est **exactement** le `watermark_column` de la spec : c'est ce qui garantit
que `compute_gap_aware_lower_bound` inspecte le même axe que celui que le builder réécrit. Et
`gap_scan_sql` encapsule déjà le watermark dans `to_date(...)`, donc un watermark TIMESTAMP
conserve la détection de trous au jour — vérifié dans le code, pas supposé.

Filtrer sur `update_start_time` aurait figé dans leur état partiel les updates commencés avant la
borne et terminés après (2 cas sur une fenêtre de 10 jours). Un test le verrouille.

## 3. Le gold, colonne par colonne

16 colonnes, 16 commentaires Unity Catalog. `merge_into_table` émet un `ALTER COLUMN … COMMENT`
par entrée de `column_comments` : une clé orpheline échoue **au runtime**, d'où le test
d'équivalence colonnes de sortie ↔ clés des commentaires.

| Colonne | Formule | Rôle / ce que le commentaire UC porte |
|---|---|---|
| `cloud_provider` | clé du `GROUP BY` | posée par la curated, pas par la system table ; **tous les repères chiffrés sont AWS** |
| `update_id` | clé du `GROUP BY` | grain + clé de merge ; une exécution ≠ une demande d'exécution |
| `workspace_id` | `MAX(workspace_id)` | **attribut**, 0 update ambigu mesuré |
| `pipeline_id` | `MAX(pipeline_id)` | **attribut** ; rapprochement `usage_metadata.dlt_pipeline_id` non vérifié à ce jour |
| `compute_type` | `MAX(compute.type)` | discriminant central ; 0 NULL ; aplatissement du struct fait ici, faute de pouvoir l'être à l'ingestion |
| `result_state` | `MAX(result_state)` | exact **par mesure** ; NULL délibérément non replié sur `'UNKNOWN'` ; limite `MAX()` = ordre alphabétique si deux états coexistaient |
| `duration_sec` | `unix_timestamp(MAX(period_end_time)) − unix_timestamp(MIN(period_start_time))` | durée **horloge** ; ne pas sommer avec les heures des tables `*_efficiency_*` |
| `update_start_time` | `MIN(period_start_time)` | borne externe de l'update entier |
| `update_end_time` | `MAX(period_end_time)` | borne externe + **axe du watermark** |
| `request_id` | `MAX(request_id)` | **clé de déduplication des retentatives**, porte la requête SQL de dédup |
| `trigger_type` | `MAX(trigger_type)` | mode de déclenchement |
| `update_type` | `MAX(update_type)` | type d'update (full refresh, etc.) |
| `run_as_user_name` | `MAX(run_as_user_name)` | identité d'exécution |
| `performance_target` | `MAX(trigger_details.job_task.performance_target)` | cible de perf serverless, NULL hors déclenchement par job |
| `period_count` | `COUNT(*)` | colonne d'**audit** : `SUM(period_count)` doit égaler le `COUNT(*)` curated |
| `_generated_at` | `current_timestamp()` | batch de calcul, toujours en dernier |

Volontairement **absentes** : `compute.cluster_id` (NULL sur 81,7 % des lignes, le serverless n'a
pas de cluster), `attempt_number` / `is_last_attempt` (un rang **matérialisé** devient faux en
silence : 6 requêtes étalent leurs tentatives sur 10 jours ou plus, jusqu'à 49 — la retentative qui
arrive après la sortie de fenêtre de la précédente ne peut plus la corriger), et les 3 colonnes
ARRAY de la source (vides sur > 99,8 % des lignes).

### Le piège des retries est dans le schéma, pas seulement dans ce rapport

C'était la demande explicite, et c'est le point le plus important de la table. Le
`table_comment` et le commentaire de `request_id` portent, en Unity Catalog :

- la définition du taux d'échec (`result_state = 'FAILED'` rapporté à **toutes** les exécutions de
  la fenêtre, `CANCELED` et lignes sans état terminal comprises au dénominateur) ;
- **les deux fenêtres**, chacune avec ses chiffres et la date de mesure ;
- le facteur de sur-estimation **1,49×** et son calcul ;
- la requête de déduplication, copiable telle quelle :

```sql
SELECT * FROM (
  SELECT *, row_number() OVER (
      PARTITION BY cloud_provider, request_id
      ORDER BY update_end_time DESC, update_id DESC) AS rn
  FROM gold_dbx_compute_pipeline_update_stats
) WHERE rn = 1
```

Un test (`test_pipeline_update_stats_figures_declare_their_measurement_date`) refuse tout
commentaire portant un nombre à 4 chiffres ou un `%` sans la date `2026-09-10`. Il a attrapé quatre
commentaires que j'avais écrits sans date.

## 4. Contrôles lecture seule exécutés

Tous en SQL via `/api/2.0/sql/statements`, profil OAuth `dcm-dev`, warehouse DCM-metrics. Aucune
écriture, aucun DDL, aucun run de job.

| # | Question | Résultat |
|---|---|---|
| 1 | Schéma réel de la source | 16 colonnes ; `compute` = `struct<type,cluster_id>` ; `account_id` **présent** ; toutes les colonnes lues par le builder existent |
| 2 | Un update porte-t-il deux `compute.type` ? deux `result_state` ? | **0** et **0** sur 412 362 updates (`max_states = 1`) — les deux `MAX` choisissent dans un singleton |
| 3 | `update_id` est-il globalement unique ? | oui : 412 350 ids pour autant de triplets `(workspace_id, pipeline_id, update_id)` |
| 4 | Combien d'updates à cheval sur plusieurs jours ? | **427** (0,104 %), dont 184 sur ≥ 3 jours, 40 sur ≥ 4, un sur **19 jours / 448,1 h**, cumul 3 065,2 h |
| 5 | Les deux définitions de durée concordent-elles ? | oui : écart médian **0,0 s**, p95 **0,0 s**, 0 update au-delà de 60 s sur 9 683 multi-tranches |
| 6 | Sur-comptage du `COUNT(*)` source | 422 167 lignes pour 412 350 updates → **+2,38 %** ; 9 817 lignes à `result_state IS NULL` |
| 7 | Taux d'échec par update vs par requête, historique complet | par update : serverless **23,16 %** / classique **11,52 %** (2,01×) ; par requête, **dernière tentative** : **7,03 %** / **5,19 %** (1,35×) → sur-estimation **1,49×** |
| 8 | Idem sur 30 jours (`update_end_time >= 2026-08-11`) | **inversion** : par update classique **27,76 %** / serverless **7,18 %** ; par requête **13,24 %** / **2,02 %** |
| 9 | Durées médianes des `COMPLETED` | serverless **82 s** / classique **694 s** (historique) ; **93 s** / **846 s** (30 j) — ce qui ne s'inverse pas |
| 10 | Retentatives | 412 350 updates pour **347 683** `request_id`, **14 056** requêtes retentées, jusqu'à **14** tentatives ; 1,21 update/requête en serverless contre 1,07 en classique |
| 11 | Qualité du compute côté jobs, pour comparaison | `job_run_timeline.compute_ids` vide ou NULL sur **97,0 %** (6 465 611 / 6 668 284) ; au grain tâche, `job_task_run_timeline.compute_ids` sur **16,2 %** de 23 360 279 lignes |
| 12 | Volumes attendus après un backfill de 30 jours | 44 016 lignes curated → **42 334** lignes gold ; `SUM(period_count) = 44 016` ; 1 660 multi-tranches ; 0 `result_state` NULL ; 35 929 serverless / 6 405 classiques ; 48 à cheval ; **2** tronqués par la borne de backfill |

Les SQL des contrôles 1 à 11 sont dans `T001f-baseline-measures.md` (§1 à §10 et addendum) ; le
contrôle 8 et le contrôle 12 ont été (re)mesurés pendant l'implémentation, voici le second, qui
sert directement de référence pour ta validation :

```sql
WITH w AS (SELECT date_trunc('DAY', current_timestamp() - INTERVAL 30 DAYS) AS cutoff),
     src AS (SELECT t.* FROM system.lakeflow.pipeline_update_timeline t, w
             WHERE t.period_start_time >= w.cutoff),
     per_update AS (
       SELECT update_id, COUNT(*) AS period_count,
              MAX(compute.type) AS compute_type, MAX(result_state) AS result_state,
              MIN(period_start_time) AS s, MAX(period_end_time) AS e
       FROM src GROUP BY update_id)
SELECT (SELECT COUNT(*) FROM src)                               AS curated_rows_30d,
       (SELECT COUNT(*) FROM per_update)                        AS gold_rows_30d,
       (SELECT SUM(period_count) FROM per_update)               AS sum_period_count,
       (SELECT COUNT(*) FROM per_update WHERE to_date(s) <> to_date(e)) AS straddling;
```

## 5. Campagne de mutation — 23 mutations, 23 tuées

Chaque mutation est une variante **voisine et crédible** : celle qu'une relecture rapide laisserait
passer, ou qu'une « optimisation évidente » introduirait. Protocole : mutation appliquée au fichier
réel, `pytest -x` sur `tests/gold_dbx_compute` + `tests/system_tables/test_specs.py`, fichier
restauré (script : `/tmp/mut_t001f.py`, hors dépôt).

| # | Mutation | Verdict |
|---|---|---|
| M01 | fenêtre posée sur la **lecture** curated au lieu de la sortie | tuée |
| M02 | fenêtre sur `update_start_time` au lieu de `update_end_time` | tuée |
| M03 | bornes de durée inversées (`MIN(fin) − MAX(début)`) | tuée |
| M04 | `update_start_time = MAX(...)` au lieu de `MIN(...)` | tuée |
| M05 | `GROUP BY` à 4 colonnes (parents promus clés de fait) | tuée |
| M06 | `result_state` NULL replié sur `'UNKNOWN'` | tuée |
| M07 | `compute_type` alimenté par `compute.cluster_id` | tuée |
| M08 | `request_id` retiré de la sortie | tuée |
| M09 | `period_count = COUNT(DISTINCT …)` | tuée |
| M10 | rang de tentative **matérialisé** (`row_number() OVER`) | tuée |
| M11 | lecture directe de `system.lakeflow` au lieu du paramètre curated | tuée |
| M12 | colonne ARRAY vide ajoutée à l'agrégation | tuée |
| M13 | `watermark_column` de la spec = `update_start_time` | tuée |
| M14 | clés de merge gold élargies aux deux parents | tuée |
| M15 | garde de suppression des lignes absentes activée (upsert non pur) | tuée |
| M16 | date de mesure retirée d'un commentaire chiffré | tuée |
| M17 | entrée de `column_comments` orpheline (colonne nue en catalogue) | tuée |
| M18 | `source_tables` de la spec = table `system.*` au lieu de la curated | tuée |
| M19 | clé de dispatch de l'entrypoint renommée (builder injoignable) | tuée |
| M20 | `period_start_time` retiré des clés de merge curated | tuée |
| M21 | clé retirée des `inputs` du job d'ingestion (**code jamais exécuté**) | tuée |
| M22 | `table:` du task gold renommée (registre non planifié) | tuée |
| M23 | `depends_on` inter-tâches ajouté au task gold | tuée |

M21 et M22 sont les deux qui m'intéressaient le plus : ce sont les deux façons d'écrire du code
correct qui **ne s'exécute jamais**. Elles sont désormais couvertes par deux tests d'équivalence
— `SPEC_KEYS` ↔ liste `inputs` du YAML d'ingestion, et `GOLD_SPEC_KEYS` ↔ union des tâches des
**deux** YAML gold. Le second a révélé au passage que `forecast_daily` est délibérément planifié
dans `job_dcm_gold_forecast.yml` (il lui faut un SQL warehouse pour `ai_forecast`) : le test le
formalise au lieu de le supposer.

## 6. Statut des gates

| Gate | Commande | Résultat |
|---|---|---|
| Tests | `.venv/bin/python -m pytest -q` | **874 passed** (846 de référence + 28 nouveaux) |
| Lint | `ruff check` sur les 10 fichiers du diff | **All checks passed!** |
| Types | `mypy` sur les 4 fichiers `pipelines/` du diff | **Success: no issues found in 4 source files** |
| Bundle | `databricks bundle validate -t dev_local -p dcm-dev` | **Validation OK!** (host `dbc-223d60ab-45bd`, user `aj1087147@tdf.hubtotal.net`) |
| Mutation | 23 mutations ciblées | **23 / 23 tuées** |

Répartition des 28 tests : 13 dans `test_pipeline_update_stats.py`, 8 dans
`tests/gold_dbx_compute/test_specs.py`, 5 dans `tests/gold_dbx_compute/test_entrypoint.py`, 2 dans
`tests/system_tables/test_specs.py`. Aucun test existant supprimé ni assoupli.

`ruff format --check` signale 4 des fichiers modifiés — **pré-existant, vérifié** : la même
commande sur les copies HEAD des mêmes fichiers échoue à l'identique. Ce n'est donc pas le gate
appliqué dans ce package et mon diff n'ajoute pas de dérive.

## 7. Tes assertions : confirmées / infirmées

### 7.1 Confirmées, avec la mesure

- **L'agrégation imposée est sûre.** Les deux `MAX` choisissent dans un singleton : 0 update à > 1
  `compute.type`, 0 à > 1 `result_state` non-NULL. Mieux, c'est démontré et pas seulement observé
  (§10.1 de la baseline) : chaque update a au moins une ligne non-NULL et le nombre de lignes
  non-NULL égale **exactement** le nombre d'updates.
- **Clé de merge gold `(cloud_provider, update_id)`** — `update_id` est globalement unique, les
  parents n'apportent aucun pouvoir discriminant, seulement un mode de panne (un `pipeline_id` qui
  changerait ferait **insérer un doublon** au lieu de mettre à jour).
- **`cloud_provider` dans le `GROUP BY`** — la curated est bi-cloud ; sans lui la colonne ne
  pourrait être portée que par un agrégat arbitraire.
- **`compute.type` et non `compute_type`** — vérifié dans `readers.py` : `select_columns` ne peut
  aliaser ni côté AWS (`df.select`) ni côté Azure (liste SQL). L'aplatissement appartient au gold.
- **Les deux définitions de durée concordent** → la définition horloge est retenue sans arbitrage.
- **`result_state` peut être NULL en gold sans anomalie** — 0 cas sur la fenêtre de 30 jours, mais
  rien ne l'interdit ; jamais replié sur `'UNKNOWN'`.
- **Les deux YAML sont la condition d'exécution** — les mutations M21/M22 le prouvent : sans eux le
  code est correct et mort.
- **Le fond du finding retries** : un taux d'échec par update sur-estime l'écart
  serverless/classique.

### 7.2 À requalifier — le taux par requête dépend de sa définition

La baseline §9 contrôle 11 publie « taux d'échec par `request_id` : serverless **7,37 %**,
classique **5,77 %** ». J'ai publié **7,03 %** et **5,19 %**. Les deux sont justes, ce sont **deux
définitions différentes**, mesurées le même jour :

| Définition d'une requête « en échec » | serverless | classique | rapport | sur-estimation du par-update |
|---|---|---|---|---|
| **au moins une** tentative `FAILED` | 7,37 % | 5,77 % | 1,28× | 1,57× |
| état de la **dernière** tentative | 7,03 % | 5,19 % | 1,35× | **1,49×** |

J'ai retenu la seconde et je l'ai **écrite dans le commentaire de table** : une requête qui échoue
puis réussit à la retentative n'est pas une requête en échec — la compter comme telle reproduit
exactement le double-comptage que le finding dénonce. La requête de déduplication publiée dans le
commentaire de `request_id` est celle qui rend ces 7,03 % / 5,19 %, donc le schéma est
auto-cohérent : le lecteur qui l'exécute retrouve les chiffres du commentaire.

### 7.3 À requalifier — les 30 jours dépendent de l'axe de la fenêtre

Le même taux sur 30 jours vaut **27,90 %** si la fenêtre est posée sur `period_start_time` et
**27,76 %** si elle est posée sur `update_end_time`. L'écart est petit — assez pour passer
inaperçu, assez pour être cité dans un comité. J'ai aligné les commentaires UC sur
`update_end_time`, parce que c'est **l'axe que filtrera un consommateur du gold** : les chiffres
publiés sont ainsi reproductibles depuis la table elle-même. Le commentaire nomme l'axe, et un test
verrouille les deux valeurs et leur raison.

### 7.4 Infirmée — `reset_checkpoint_selection` n'est pas un `array<struct>`

La story l'annonce `array<struct>`. `DESCRIBE TABLE system.lakeflow.pipeline_update_timeline` rend
`array<string>`. Ce sont `refresh_selection` et `full_refresh_selection` qui sont
`array<struct<table_catalog,table_schema,table_name>>`. Sans conséquence sur le code (les trois sont
ingérées telles quelles et aucune n'est agrégée), mais la story est à corriger si elle sert de
référence à T002.

### 7.5 Infirmée — « serverless échoue deux fois plus » n'est pas seulement un artefact de retries

La baseline attribue l'écart au comptage des retentatives. La déduplication ne fait que le
**réduire** (2,01× → 1,35×) ; ce qui le **renverse**, c'est la fenêtre : sur 30 jours c'est le
**classique** qui échoue le plus, par update (27,76 % contre 7,18 %) comme par requête (13,24 %
contre 2,02 %). Deux corrections indépendantes, donc, et c'est pour cela qu'aucun taux ne doit
sortir de cette table sans sa fenêtre **et** son grain.

### 7.6 Mon erreur, corrigée avant livraison

J'avais écrit deux fois — dans la docstring du builder et dans le commentaire UC de `compute_type`
— que « `job_run_timeline.compute[]` est vide sur **88,5 %** des lignes ». Remesure :

```sql
SELECT COUNT(*) AS rows_total,
       SUM(CASE WHEN compute_ids IS NULL OR size(compute_ids) = 0 THEN 1 ELSE 0 END) AS without
FROM system.lakeflow.job_run_timeline;
-- 6 668 284 lignes, 6 465 611 sans compute_ids  →  97,0 %
```

La colonne s'appelle `compute_ids` (un `array` d'identifiants, pas un struct de type), et le taux
est de **97,0 %**. Nuance à garder : au grain **tâche**,
`job_task_run_timeline.compute_ids` n'est vide que sur **16,2 %** de 23 360 279 lignes — donc « le
côté jobs n'a pas d'information de compute » serait faux : il a des **identifiants** au grain
tâche, jamais un **type** sans une jointure de plus. Les deux emplacements portent désormais la
mesure exacte, sa date et cette nuance.

### 7.7 La source est vivante — conséquence sur la validation

Trois mesures du même total à quelques minutes d'intervalle : 412 328, 412 350, 412 362 updates.
Ce n'est pas une incohérence, c'est une table qui grossit. **Conséquence directe pour tes
contrôles** : aucune comparaison `gold` ↔ `system.*` ne peut être exacte. Les contrôles du §8
comparent donc **gold ↔ curated**, sous forme d'**identités** et non de constantes.

## 8. Contrôles lecture seule après ton déploiement

Ordre : `bundle deploy -t dev_local -p dcm-dev`, puis la tâche d'ingestion
`lakeflow_pipeline_update_timeline` du job `dcm_system_tables`, **puis** la tâche
`gold_pipeline_update_stats` du job `dcm_gold_dbx_compute`. Le gold sur une curated absente
échouerait à la lecture — c'est le comportement voulu (fail-fast), pas un bug.

Tables, target `dev_local` : catalogue `it`, schéma `ba_data_connect_monitoring__d`.

**C1 — la curated est peuplée sur ~30 jours (backfill initial)**

```sql
SELECT COUNT(*) AS rows, COUNT(DISTINCT update_id) AS updates,
       MIN(period_start_time) AS min_start, MAX(period_end_time) AS max_end
FROM it.ba_data_connect_monitoring__d.curated_dbx_lakeflow_pipeline_update_timeline;
```

Attendu : `rows` ≈ **44 000**, `updates` ≈ **42 300** (ratio ≈ 1,040), `min_start` ≈ jour du run
− 30 j. **Pas 412 350** : `initial_lookback_days = INITIAL_BACKFILL_DAYS` (30 j) alors que la
source garde 367 jours. L'historique long s'accumule ensuite, run après run — c'est le
comportement des 18 tables sœurs.

**C2 — le gold a exactement une ligne par clé de la curated**

```sql
SELECT (SELECT COUNT(*) FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats) AS gold_rows,
       (SELECT COUNT(DISTINCT concat_ws('|', cloud_provider, update_id))
        FROM it.ba_data_connect_monitoring__d.curated_dbx_lakeflow_pipeline_update_timeline) AS curated_keys;
```

Attendu **au premier run** : les deux nombres **égaux** (≈ 42 300). Aux runs suivants
`gold_rows ≥ curated_keys` est normal : l'upsert est pur, le gold garde ce que la source a purgé.

**C3 — l'identité d'audit `period_count`**

```sql
SELECT (SELECT SUM(period_count) FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats) AS sum_period_count,
       (SELECT COUNT(*) FROM it.ba_data_connect_monitoring__d.curated_dbx_lakeflow_pipeline_update_timeline) AS curated_rows;
```

Attendu **au premier run** : **égalité stricte**. C'est le contrôle qui prouve que l'agrégation n'a
ni perdu ni dupliqué une tranche.

**C4 — le grain tient**

```sql
SELECT COUNT(*) - COUNT(DISTINCT concat_ws('|', cloud_provider, update_id)) AS doublons
FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats;
```

Attendu : **0**.

**C5 — les durées sont saines**

```sql
SELECT SUM(CASE WHEN duration_sec < 0 THEN 1 ELSE 0 END)  AS negatives,
       SUM(CASE WHEN duration_sec IS NULL THEN 1 ELSE 0 END) AS nulls,
       SUM(CASE WHEN duration_sec = 0 THEN 1 ELSE 0 END)  AS zeros,
       MAX(duration_sec) AS max_sec
FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats;
```

Attendu : `negatives = 0`, `nulls = 0`, `zeros` quelques dizaines, `max_sec` **> 86 400** — une
durée supérieure à 24 h est la **preuve** que la fenêtre ne borne pas la lecture.

**C6 — la fenêtre ne tronque pas les updates à cheval**

```sql
SELECT COUNT(*) AS straddling,
       SUM(CASE WHEN datediff(to_date(update_end_time), to_date(update_start_time)) >= 3 THEN 1 ELSE 0 END) AS over_3_days
FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats
WHERE to_date(update_start_time) <> to_date(update_end_time);
```

Attendu sur ~30 jours : `straddling` ≈ **48**. Si le résultat est **0**, la fenêtre a fui vers
l'entrée — c'est exactement la régression M01.

Caveat mesuré : **2** updates commencent avant la borne du backfill de 30 jours et finissent après.
Leur `duration_sec` et leur `update_start_time` sont sous-estimés **au premier run seulement** ; le
`--full-refresh` du gold après quelques jours d'ingestion les corrige.

**C7 — le compute et l'état terminal**

```sql
SELECT compute_type, result_state, COUNT(*) AS updates
FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats
GROUP BY compute_type, result_state ORDER BY 1, 2;
```

Attendu : `compute_type` ∈ {`SERVERLESS_COMPUTE`, `CLASSIC_COMPUTE`}, **aucun NULL** ; répartition
≈ 35 900 serverless / 6 400 classiques ; `result_state` ∈ {`COMPLETED`, `FAILED`, `CANCELED`} et
**pas** de `'UNKNOWN'`. Un `result_state` NULL n'est pas une anomalie mais il n'y en avait aucun sur
la fenêtre de 30 jours au 2026-09-10.

**C8 — les commentaires Unity Catalog sont bien arrivés**

```sql
SELECT column_name, comment IS NOT NULL AND length(comment) > 0 AS documented
FROM it.information_schema.columns
WHERE table_schema = 'ba_data_connect_monitoring__d'
  AND table_name  = 'gold_dbx_compute_pipeline_update_stats'
ORDER BY ordinal_position;
```

Attendu : **16 lignes, `documented = true` partout**. Et le commentaire de table :

```sql
SELECT comment FROM it.information_schema.tables
WHERE table_schema = 'ba_data_connect_monitoring__d'
  AND table_name  = 'gold_dbx_compute_pipeline_update_stats';
```

Attendu : le texte contient `PIEGE A CONNAITRE AVANT DE PUBLIER UN TAUX D'ECHEC`, les deux fenêtres
et `1,49x`. C'est le contrôle qui vérifie que le finding est **dans le produit**, pas seulement dans
ce rapport.

**C9 — le finding reproduit depuis le gold seul**

```sql
WITH g AS (SELECT * FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats),
     last_attempt AS (
       SELECT *, row_number() OVER (PARTITION BY cloud_provider, request_id
                                    ORDER BY update_end_time DESC, update_id DESC) AS rn
       FROM g)
SELECT 'par update' AS grain, compute_type, COUNT(*) AS n,
       ROUND(100.0 * SUM(CASE WHEN result_state = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_fail
FROM g GROUP BY compute_type
UNION ALL
SELECT 'par requete', compute_type, COUNT(*),
       ROUND(100.0 * SUM(CASE WHEN result_state = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 2)
FROM last_attempt WHERE rn = 1 GROUP BY compute_type
ORDER BY 1, 2;
```

Attendu, sur un gold couvrant ~30 jours : par update, classique ≈ **27,8 %** contre serverless
≈ **7,2 %** ; par requête, classique ≈ **13,2 %** contre serverless ≈ **2,0 %**. Ces quatre valeurs
sont celles du commentaire de table : si elles divergent de plus de ~0,5 pt, c'est le périmètre du
gold qui n'est pas celui que je supposais, pas le calcul.

**C10 — idempotence : relancer la tâche gold sans redéployer**

```sql
SELECT CASE WHEN update_end_time >= date_trunc('DAY', current_timestamp() - INTERVAL 10 DAYS)
            THEN 'dans la fenetre' ELSE 'hors fenetre' END AS zone,
       COUNT(*) AS rows, COUNT(DISTINCT _generated_at) AS batches, MAX(_generated_at) AS last_batch
FROM it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_update_stats
GROUP BY 1;
```

Attendu après un **second** run : `rows` total **inchangé** (aucune insertion, aucune suppression),
`last_batch` de la zone « dans la fenêtre » **postérieur** à celui de « hors fenêtre ». Si des
lignes hors fenêtre portent aussi le nouveau batch, c'est que `compute_gap_aware_lower_bound` a
remonté la borne — légitime s'il a détecté un trou ou un jour non stabilisé, à lire dans les logs
de la tâche avant de conclure à une anomalie.

## 9. Coût et fiabilité

**Coût.** Le task gold réutilise l'`environment_key: gold_compute_env` du job existant — aucun
compute supplémentaire, aucune ressource créée. La fenêtre de sortie divise le volume du MERGE par
**27** (15 054 lignes contre 412 350) tout en gardant l'agrégation exacte. Côté ingestion,
`azure_fetch_batch_size = AZURE_BATCH_NESTED` (15 000) est choisi pour une ligne portant un struct
et trois arrays : plus large ferait grossir les paquets JDBC pour rien, plus étroit multiplierait
les allers-retours cross-tenant. Aucun `select_columns` : les 16 colonnes sont ingérées, ce qui est
le coût assumé de la fidélité source (≈ 44 000 lignes par backfill initial, quelques milliers par
run incrémental — négligeable devant `billing_usage` ou `query_history`).

**Fiabilité.** `max_retries: 0` sur le task gold (le recalcul est déterministe, un échec est un
symptôme à lire, pas à masquer) ; upsert **pur**, aucune ligne jamais supprimée, parce que la
source ne garde qu'un an glissant et que cette table est la mémoire longue ; MERGE null-safe sur
`<=>` ; `dropDuplicates(merge_keys)` en amont du MERGE ; fenêtre alignée sur le watermark inspecté
par la détection de trous ; deux tests d'équivalence code ↔ YAML qui rendent impossible le scénario
« code correct, jamais exécuté ». Le point faible connu et documenté reste la dépendance
temporelle inter-jobs du §Ce qu'il faut trancher, point 3.

## 10. Vérification cyber

**Périmètre** : deux specs de données, un builder SQL, deux YAML de tâches, quatre fichiers de
tests, et des mesures SQL en lecture seule. Aucune authentification, aucun stockage, aucun
mouvement inter-environnements, aucun endpoint.

| Règle | Statut | Preuve | Remédiation |
|---|---|---|---|
| PAT / token en clair | **PASS** | aucun secret dans le diff ; toutes les mesures via `-p dcm-dev` (OAuth), jamais `[DEFAULT]` | — |
| Secret de service principal | **PASS** | aucun `client_secret` ni `azure_client_secret` introduit | — |
| DBFS | **PASS** | aucun `dbfs:/`, aucun `dbutils.fs` ; tables Unity Catalog uniquement | — |
| Secret en clair dans un YAML | **PASS** | les deux YAML ne portent que des clés de tâches et des paramètres non sensibles | — |
| Données personnelles PROD → NON-PROD | **PASS (avec une ligne à connaître)** | `run_as_user_name` est une identité utilisateur ; elle suit le pattern **déjà en place** (`access_audit.user_identity` en curated, `run_as`/`owned_by`/`created_by` dans 3 tables gold), même catalogue, même finalité de supervision, cible `dev_local` | rien à corriger dans T001f ; la question de fond — l'ingestion cross-tenant Azure d'identités vers un catalogue de dev — est pré-existante et transverse aux 19 tables |
| Moindre privilège UC | **N.A.** | aucun `GRANT` introduit ; le schéma cible est celui du bundle | — |
| `"Anyone in my organization can use"` | **N.A.** | aucun objet partageable créé | — |
| Modèle de fondation public | **N.A.** | aucun appel de modèle | — |
| Contournement de contrôle | **PASS** | aucun `--no-verify`, aucun test désactivé, aucun gate ignoré ; 874 tests verts sans suppression | — |

**Hors périmètre, groupé** : ML, Apps, Vector Search, MCP, Genie, Lakebase, model serving — ce
travail est de l'ingestion et de l'agrégation SQL.

**Constat hors périmètre, signalé une fois** : le job `dcm_gold_dbx_compute` n'a pas de `run_as` et
s'exécute donc sous l'identité de qui déploie. Pré-existant, transverse aux 8 jobs du bundle, déjà
signalé en T001d/T001e, non bloquant pour `dev_local` — **bloquant avant un déploiement `prod`**,
et seul toi peux fournir le nom du service principal. T001f n'introduit pas la violation et n'en
hérite pas.

**Conseil upstream écarté** : aucun. Les skills lues ne proposaient rien de contraire aux règles
TTE sur ce périmètre.

**Bloquants avant déploiement** : aucun d'ordre cyber sur `dev_local`. Les trois points à trancher
du haut de ce rapport sont de conception, pas de sécurité — dont un seul, `account_id`, coûte cher
après le premier run.

## 11. Skills consultées

- `dp-data-databricks-cyber` — `/Users/adrien.hereng/Documents/DCM/dataint-dcm-app/.agents/skills/dp-data-databricks-cyber/SKILL.md`
- `databricks-dabs` — `…/.agents/skills/databricks-dabs/SKILL.md`
- `databricks-jobs` — `…/.agents/skills/databricks-jobs/SKILL.md` (+ `references/task-types.md`)
- `databricks-unity-catalog` — `…/.agents/skills/databricks-unity-catalog/SKILL.md`

Gate step 0 : **satisfaite par le verdict transmis** (29 skills `databricks-*` dans
`.agents/skills`, overlay `dp-data-*` co-localisé) — non re-sondée.

---

## 12. Addendum de revue et de déploiement (2026-09-10, après le rapport ci-dessus)

Ce rapport a été écrit **avant** revue, déploiement et exécution. Les trois sont faits. Ce qui
suit corrige ce qui l'était devenu faux, et n'efface rien : le §9 disait « code correct, jamais
exécuté », ce n'est plus le cas.

### 12.1 Deux défauts corrigés dans le livrable

1. **Le commentaire de table contredisait le commentaire de colonne** sur le dénominateur du taux
   d'échec. `PIPELINE_UPDATE_STATS_TABLE_COMMENT` annonçait un dénominateur incluant « les 2,3 %
   encore sans état terminal », alors que le commentaire de `result_state` exclut les NULL. Pire,
   ce 2,3 % est un taux **ligne** de la curated (9 817 / 422 167) transposé à une table de grain
   **update**, où il vaut **0 %** : aucun update sur 412 350 n'a que des tranches sans état.
   Publier un taux de grain dans un commentaire de l'autre grain est exactement le piège que cette
   table existe pour supprimer. Les deux commentaires sont réécrits et disent maintenant la même
   chose. **La donnée déployée confirme la correction** : `result_state` NULL = **0** en gold.
2. **Une assertion vide dans `tests/system_tables/test_specs.py`** — un `!=` entre le tuple de
   clés (5 éléments) et un tuple de 4 éléments, censé « montrer » le mode de panne. La comparaison
   est vraie par construction (mypy la signale, `comparison-overlap`) et n'assure donc rien ;
   l'égalité juste au-dessus couvre déjà l'intention. Supprimée, et le commentaire dit pourquoi ne
   pas la remettre.

### 12.2 Le point 1 « à trancher » est désormais tranché par le run

Les clés de merge de la curated restent `(cloud_provider, workspace_id, pipeline_id, update_id,
period_start_time)`, **sans `account_id`**. La table est peuplée : revenir dessus coûte maintenant
un `CREATE OR REPLACE`, comme annoncé. La décision se défend sur le fond — `workspace_id` est
unique par compte, donc `account_id` n'est pas discriminant, et la clé colle au grain réel — mais
elle est prise, pas suspendue. Les points 2 (`_stats`) et 3 (dépendance 03:00 → 05:00) restent
tels quels : le premier est déjà contractuel côté specs, le second est documenté dans le YAML.

### 12.3 Déploiement, exécution, validation

| Étape | Résultat |
|---|---|
| `bundle validate -t dev_local -p dcm-dev` | **Validation OK!** |
| ruff check / ruff format sur les 8 fichiers du diff | check **clean** ; format : 6 fichiers à reformater, **tous les 6 déjà en échec sur HEAD**, les 2 fichiers créés sont clean |
| mypy sur les 8 fichiers | **1 erreur, pré-existante** (`test_entrypoint.py:452`, identique sur HEAD) |
| `pytest` | **874 passed** |
| ingestion, run `3083401854457` | **SUCCESS** — 19ᵉ table, les deux clouds |
| gold, run `105088015771793` | **SUCCESS** en 66 s |

Contrôles curated (fidélité) : 43 122 lignes attendues = 43 122 obtenues côté aws, **0 orphelin,
0 divergence, 0 doublon** sur la clé de merge, et 1,0399 ligne par update — la périodisation est
donc **conservée**, l'agrégation n'a pas fui dans l'ingestion.

Contrôles gold : grain exactement **1,0000** (127 640 updates pour 127 640 lignes, 0 doublon),
0 orphelin de réconciliation, les deux définitions de durée concordent, 0 divergence sur
`result_state` / `compute_type` / `request_id`, et l'auto-audit `SUM(period_count)` gold =
`COUNT(*)` curated est **exact par cloud** (43 122 et 86 591). Le contrôle anti-troncature — celui
qui a motivé le choix de mettre l'agrégation en gold plutôt qu'en ingestion — est **non vide** :
**48 updates** chevauchent la borne de fenêtre, étalement maximal **19,2 h**, **0 troncature**.

### 12.4 Ce que le run a appris et que personne ne pouvait mesurer avant

La partie azure est ingérée par JDBC cross-tenant : elle n'était pas interrogeable depuis les
system tables locales. Elle l'est maintenant, et elle **retire son objet au comparatif**
serverless / classique sur ce cloud — **86 174 updates azure sur 10 workspaces contre 41 466 aws
sur 42** (azure = 67,5 % du périmètre), dont **23** en compute classique, soit 0,027 %. Le taux
d'échec serverless y est **3× celui d'aws** (5,97 % contre 1,99 % par `request_id`). Détail,
mesures et conséquences en §10.8 de `T001f-baseline-measures.md` ; SC-008b de `spec.md` en tire le
**seuil de population minimale** de la tuile de comparaison, avec azure/classique comme
contre-exemple de test.

### 12.5 Réserves de revue, non bloquantes

- **La fenêtre de réécriture du gold porte sur `update_end_time`.** Une correction tardive qui ne
  toucherait que l'`update_start_time` d'un update terminé hors fenêtre ne serait pas réécrite.
  Le cas est théorique sur cette source (les tranches arrivent dans l'ordre), et le coût de la
  parade — élargir la fenêtre ou lire les deux bornes — n'est pas justifié sans un cas observé.
- Le commentaire de `GOLD_SPEC_KEYS` parle de la « liste `inputs` du `for_each` », alors que le job
  gold utilise des tâches explicites. Formulation pré-existante, sans effet, à corriger au passage
  d'une prochaine task sur ce fichier.
