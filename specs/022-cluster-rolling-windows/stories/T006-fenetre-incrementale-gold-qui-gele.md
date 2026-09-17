# T006 — La fenêtre incrémentale gold gèle le jour de queue de chaque run

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: (aucune — correctif demandé sur la branche courante)
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T001
**Work type**: bugfix

## Description

Découvert en vérifiant les volumes des trois tables `gold_dbx_compute_cluster_*_daily` :
`cluster_cost_daily` ne comptait que **2 242** cluster-jours le 2026-08-27 contre ~8 900 les
jours voisins, et **651,86 $** de coût contre ~3 800 $. Le trou n'était pas isolé.

La mesure décisive : le nombre de dates d'écriture distinctes par jour de `period_start`.

```
day        rows  first_written last_written n_write_dates  cost_usd
2026-08-26 8877  2026-08-30    2026-08-30   1              3566.75
2026-08-27 2242  2026-08-30    2026-08-30   1               651.86  <- queue du run du 08-30
2026-08-28 9024  2026-09-04    2026-09-04   1              4050.20
...
2026-09-02 6458  2026-09-04    2026-09-04   1              3930.38
2026-09-03 6338  2026-09-04    2026-09-04   1              3684.97
2026-09-04 3749  2026-09-04    2026-09-04   1              2170.90  <- queue du run du 09-04
```

`n_write_dates = 1` sur **tous** les jours : aucun jour n'est jamais recalculé. La fenêtre
incrémentale n'avance, elle ne revisite rien. Le jour de queue de chaque run est donc écrit
une seule fois, au moment où la source curated est la moins complète, puis figé
définitivement. 4 des 8 derniers jours étaient faux (08-27, 09-02, 09-03, 09-04), soit
≈15 600 cluster-jours manquants pour une médiane de ≈8 600/jour.

Trois causes se couvraient mutuellement :

1. **`compute_gap_aware_lower_bound`, candidat 4 = `last_day + 1`.** Le dernier jour écrit
   est par construction le MOINS stabilisé de tous ; repartir du lendemain le condamne. Le
   run du 09-04 a démarré au 08-28 = `last_day + 1` du run du 08-30, et n'a donc jamais revu
   le 08-27.
2. **`gap_scan_sql`, test de stabilisation strict.** `first_unsettled_day` ne signalait un
   jour que si sa dernière écriture était **strictement** antérieure à `jour + lookback`.
   Pour le 08-27 écrit le 08-30 avec `lookback_days = 3` : `08-30 < 08-30` = faux ⇒ déclaré
   stabilisé. Un jour écrit pile à la fermeture de sa fenêtre n'a par définition reçu aucune
   écriture *après* elle : il ne peut pas être final.
3. **`INCREMENTAL_LOOKBACK_DAYS = 3`, au plancher du retard réel des sources.** Mesuré en dev
   par `datediff(to_date(collected_at), jour)` sur `curated_dbx_billing_usage`,
   `curated_dbx_access_audit` et `curated_dbx_compute_node_timeline` : une journée n'arrive
   en curated que **3 à 8 jours** après le jour concerné (mode 3-4). Une fenêtre de 3 jours
   agrège donc systématiquement une source incomplète.

Impact utilisateur : les tables `*_rolling` étant des rollups de `*_daily`, les fenêtres 7 j,
30 j et 90 j sous-comptaient — la page Cluster affichait un coût trop bas
(`window_days = 30` à 99 342 $ avant correctif).

Le commentaire de `job_dcm_gold_dbx_compute.yml` affirmait par ailleurs que le décalage de
2 h après le job system tables « laisse le temps aux tables curated de finir de s'écrire » :
la mesure le contredit (3 à 8 jours, pas 2 heures). Ce qui fait converger l'agrégation est la
largeur de la fenêtre de rafraîchissement, pas l'heure de déclenchement.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/common/incremental.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py`
  (`INCREMENTAL_LOOKBACK_DAYS`)
- UPDATE `packages/dcm-databricks-pipeline/tests/common/test_incremental.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py`
- UPDATE `packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml`
  (commentaires + `timeout_seconds`)
- UPDATE `packages/dcm-databricks-pipeline/databricks.yml` (description de `lookback_days`)

## Sub-tasks

- [x] Candidat 4 de `compute_gap_aware_lower_bound` : `last_day + 1` → `last_day`.
- [x] Test de stabilisation de `gap_scan_sql` : `<` → `<=` (comparaison inclusive).
- [x] `INCREMENTAL_LOOKBACK_DAYS` : 3 → 10, avec le retard d'arrivée mesuré en commentaire.
- [x] Tests adaptés + test de régression nommé d'après le cas réel du 2026-08-27, couvrant
      `gap_scan_sql` **et** `compute_gap_aware_lower_bound`.
- [x] Commentaires du job corrigés : le décalage de 2 h ne garantit rien, et la fenêtre
      nominale est élargie automatiquement.
- [x] `timeout_seconds` du job : 7 200 → 14 400 s. Trouvé en mesurant la largeur du premier
      run : à 2 h, le levier de réparation que le job documente lui-même (`full_refresh`,
      ~167 min mesurées) ne pouvait pas aboutir — le run `563218448954827` du 2026-09-05 est
      d'ailleurs mort en `TIMEDOUT` à 120,2 min. Un timeout censé couper un run bloqué ne doit
      pas être calé sous la durée d'un run légitime.
- [x] Déploiement dev + run de réparation `360068623859212` (incrémental, **sans**
      `full_refresh` : c'est le chemin corrigé qu'il fallait prouver).

## Acceptance Criteria

- [x] Le run corrigé résout une borne basse **antérieure** au 08-27. Prédiction mesurée avant
      déploiement en rejouant le `gap_scan` corrigé en SQL : **2026-08-20** sur 6 tables,
      2026-08-26 sur `cluster_efficiency_daily` — soit 17 jours, **pas** les 90 jours du
      plancher d'inspection. Vérifié après le run : `last_written` est passé à 2026-09-06 sur
      08-20 → 09-04, et est resté au 2026-08-30 sur 08-18 et 08-19.
- [x] `cluster_cost_daily` le 2026-08-27 : **9 107 lignes et 3 752,28 $** au lieu de
      2 242 / 651,86 $.
- [x] `cluster_reliability_daily`, `job_cluster_cost_daily`, `warehouse_cost_daily` réparés
      par le même run (le 08-27 disparaît des jours sous-peuplés des trois tables).
- [x] `cluster_cost_rolling` : 30 j 99 342 → **102 443 $**, 90 j 291 946 → **295 047 $**,
      soit les ≈3 100 $ récupérés sur le 08-27. Ces tables étant des snapshots complets
      (`watermark_column = None`), la réparation est mécanique.
- [x] 09-02, 09-03 et 09-04 ont bien été **recalculés** (`last_written` = 09-06) mais leurs
      volumes n'ont pas bougé : curated n'a pas encore reçu ces journées (retard mesuré 3 à
      8 jours). C'est le comportement voulu — ils restent dans la fenêtre de 10 jours et
      seront recalculés à chaque run jusqu'à être complets. C'est exactement ce que
      l'ancienne fenêtre de 3 jours rendait impossible.

Critère abandonné, parce que mal posé : « `n_write_dates > 1` sur les jours de la fenêtre ».
Le MERGE réécrit `_generated_at` sur **toutes** les lignes du jour, donc un jour entièrement
recalculé repasse à une seule date d'écriture distincte. Il n'existe aucune trace de la
première écriture. L'observable correct est la valeur de `last_written` : 2026-09-06 sur les
jours de la fenêtre contre 2026-08-30 sur les jours restés hors d'elle.

## Tests

```bash
cd packages/dcm-databricks-pipeline
uv run pytest -q tests/common/test_incremental.py tests/gold_dbx_compute/
uv run ruff check . && uv run ruff format --check . && uv run pytest -q
```

Vérification en dev (lecture seule, OAuth) : `python3 /tmp/vol_verify_fix.py`.

## Out of scope

- **Le `lookback_days` de la couche curated reste à 3.** Vérifié : curated contient toutes
  les lignes de `system.billing.usage` sur 2026-08-24 → 08-30 **sauf 2** sur le 08-27, où
  l'`ingestion_date` de Databricks accusait 6 jours de retard. La variable s'appliquant à
  *toutes* les tables du `for_each` de `dcm_system_tables`, l'élargir multiplierait par ~3 le
  volume relu chaque jour sur `access.audit` (~4,5 M lignes/jour) pour récupérer 2 lignes. Un
  rattrapage par table demanderait un `lookback_days` dans `IngestionSpec` — non fait,
  arbitrage documenté dans `databricks.yml`.
- Un trou plus ancien que `DEFAULT_GAP_DETECTION_WINDOW_DAYS` (90 j) reste réparable
  uniquement par `full_refresh` : inchangé, c'est le prix d'un coût de scan borné.
- Vérification de l'ampleur du trou en **prod** : le workspace prod est distinct
  (`dbc-af3acef9-c998`), non interrogé ici.

## Notes

- **Le correctif converge, il ne s'emballe pas.** Avec `lookback_days = 10` et la comparaison
  inclusive, `first_unsettled_day` ne remonte pas jusqu'au plancher d'inspection : un jour de
  juin écrit le 08-30 donne `08-30 <= 06-18` = faux, donc stabilisé. Le premier jour signalé
  est celui où `last_written <= jour + 10` (08-20 pour un backfill du 08-30) ; une fois les
  jours réécrits à la date du run, la borne se stabilise sur `today - 10`. Régime permanent :
  chaque jour est recalculé pendant 10 jours puis figé, ce qui couvre le retard curated mesuré
  (3 à 8 jours).
- **La réparation est sûre sans `full_refresh`.** `merge_into_table` écrit en `WHEN MATCHED
  THEN UPDATE SET *` / `WHEN NOT MATCHED THEN INSERT *` et `absent_row_delete_predicate` est
  `None` pour ces specs : recalculer une fenêtre insère et met à jour, ne supprime jamais.
- **En dev, les schedules sont volontairement `PAUSED`** (`databricks.yml`, target `dev`) :
  aucun run automatique n'a lieu, ce qui explique que le trou du 08-27 ait survécu 9 jours
  sans être même tenté. En prod, la cible n'a pas cette surcharge — le job tourne chaque jour
  à 05:00 et les trois défauts y produisent donc un trou **permanent** à chaque run.
- Les baisses de 08-22, 08-23, 08-29 et 08-15 sont des week-ends (≈-15 %), pas des trous : le
  contrôle de volume doit les distinguer d'un effondrement à -75 % comme celui du 08-27.
  Confirmé par le run de réparation : 08-22 et 08-29 ont été recalculés et n'ont pas bougé.
- **Coût réel du run élargi** : 25,4 min pour les 16 tâches sur une fenêtre de 17 jours,
  contre 6 à 23 min sur une fenêtre de 3 à 8 jours. `cluster_efficiency_daily` concentre
  ≈20 des 25 min (node_timeline à granularité minute/nœud). Loin des 4 h de timeout.
- **Piste laissée ouverte, non traitée** : `GOVERNANCE_RECENT_DAYS = 3` fait lire à
  `cluster_governance` les 3 derniers jours gold de `cluster_efficiency_daily` pour
  `node_oversized` — donc les jours les moins stabilisés, sur la même hypothèse erronée que
  l'ancien lookback. Le snapshot étant recalculé en entier à chaque run il suit le gold
  corrigé, mais la constante mérite d'être remesurée.
