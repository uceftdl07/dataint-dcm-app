"""Strategie d'ingestion incrementale (watermark, lookback, pruning).

Calcule la borne basse de lecture (`MAX(watermark) - lookback`) et le predicat
de pruning de partition. Generique : pilote uniquement par l'`IngestionSpec`
fournie (colonne watermark, colonnes de partition), sans notion metier.

Deux strategies coexistent, selon ce que l'appelant peut interroger :

- `compute_lower_bound` (couche curated) : ancre la fenetre sur le contenu de
  la table CIBLE (`MAX(watermark) - lookback`), donc auto-cicatrisante — un run
  manque, le suivant repart de la derniere donnee reellement ecrite.
- `compute_gap_aware_lower_bound` (couche gold) : inspecte la couverture jour
  par jour de la table cible (un `MAX(watermark)` ne dirait pas si les jours
  precedents sont complets).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

    from pipelines.common.models import IngestionSpec


# Lookback par defaut (jours) pour rattraper les arrivees tardives en incremental.
DEFAULT_LOOKBACK_DAYS = 3

# Profondeur (jours) inspectee dans la table cible par
# `compute_gap_aware_lower_bound` pour y detecter des trous de couverture.
# Bornee (et non "tout l'historique") pour que le cout du scan de detection
# reste stable dans le temps ; un trou plus ancien que cette fenetre ne se
# repare que par un `--full-refresh` explicite.
DEFAULT_GAP_DETECTION_WINDOW_DAYS = 90


def compute_lower_bound(
    spark: SparkSession,
    spec: IngestionSpec,
    cloud_provider: str,
    lookback_days: int,
) -> datetime | None:
    """Calcule la borne basse d'ingestion incrementale pour un cloud donne.

    Retourne `MAX(watermark) - lookback` deja present en curated pour ce
    `cloud_provider`. Le lookback rattrape les enregistrements arrives en retard
    cote source.

    Sans watermark configure ⇒ None (full load, ex. table de reference stable).

    Au TOUT PREMIER run (table curated absente ou aucune ligne pour ce cloud) :
    retourne la borne de backfill initiale `now - initial_lookback_days` si la
    spec en definit une, sinon None (backfill complet). Borner le premier run est
    indispensable pour les grosses tables d'evenements : un `SELECT *` sur tout
    l'historique via le SQL connector Azure (inline fetch) materialise le resultat
    sur le driver du warehouse et depasse `spark.driver.maxResultSize`.
    """
    if spec.watermark_column is None:
        return None
    if not spark.catalog.tableExists(spec.curated_table):
        return _initial_backfill_floor(spec)
    row = spark.sql(
        f"SELECT MAX({spec.watermark_column}) AS wm "
        f"FROM {spec.curated_table} WHERE cloud_provider = '{cloud_provider}'"
    ).collect()[0]
    watermark = row["wm"]
    if watermark is None:
        return _initial_backfill_floor(spec)
    # DATE columns (datetime.date) lack .date(); promote to datetime for uniformity.
    if type(watermark) is date:
        watermark = datetime(watermark.year, watermark.month, watermark.day)
    return cast("datetime", watermark) - timedelta(days=lookback_days)


def _initial_backfill_floor(spec: IngestionSpec) -> datetime | None:
    """Borne basse du premier backfill : `now - initial_lookback_days` ou None.

    None quand la spec ne borne pas le premier run (backfill complet assume, ex.
    historique de couts FinOps). Datetime naif (UTC) pour rester coherent avec le
    filtre SQL Azure `WHERE col >= 'YYYY-MM-DD HH:MM:SS'` (pas de suffixe fuseau).
    """
    if spec.initial_lookback_days is None:
        return None
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=spec.initial_lookback_days)


def gap_scan_sql(
    target_table: str,
    watermark_column: str,
    *,
    inspection_floor: date,
    lookback_days: int,
    generated_at_column: str | None = None,
) -> str:
    """Requete de diagnostic de couverture de la table CIBLE (3 scalaires).

    Agrege la table cible par jour de watermark sur `[inspection_floor, ...]` et
    renvoie une seule ligne :
      - `last_day` : dernier jour ecrit (borne haute de la couverture connue) ;
      - `first_missing_day` : premier jour ABSENT entre deux jours presents
        (trou interieur ; un jour anterieur au premier jour present n'est pas
        signale) ;
      - `first_unsettled_day` : premier jour dont la derniere ecriture est
        anterieure OU EGALE a `jour + lookback_days`, c'est-a-dire ecrit AVANT
        la fermeture de sa propre fenetre de rafraichissement — la source
        curated pouvait encore recevoir des arrivees tardives pour ce jour.
        Comparaison INCLUSIVE et non stricte : un jour ecrit pile a
        `jour + lookback_days` n'a recu aucune ecriture APRES la fermeture de sa
        fenetre, il ne peut donc pas etre considere comme final. Cas mesure : le
        2026-08-27 ecrit le 2026-08-30 avec `lookback_days=3`
        (`08-30 < date_add('08-27', 3)` = faux) etait declare stabilise alors
        qu'il sous-comptait d'un facteur 4 — et le candidat `last_day + 1` de
        `compute_gap_aware_lower_bound` l'avait par ailleurs saute : les deux
        defauts se couvraient l'un l'autre.
        `NULL` si `generated_at_column` n'est pas fourni.

    Fonction pure (chaine SQL) : testable sans Spark, comme les helpers de
    `pipelines.gold_dbx_compute.sql_helpers`.
    """
    day_expr = f"to_date({watermark_column})"
    if generated_at_column is None:
        unsettled_expr = "CAST(NULL AS DATE)"
        last_written_expr = "CAST(NULL AS TIMESTAMP)"
    else:
        unsettled_expr = (
            "MIN(CASE WHEN to_date(last_written_at) <= "
            f"date_add(day, {lookback_days}) THEN day END)"
        )
        last_written_expr = f"MAX({generated_at_column})"
    return f"""
    WITH written_days AS (
        SELECT {day_expr} AS day, {last_written_expr} AS last_written_at
        FROM {target_table}
        WHERE {day_expr} >= DATE '{inspection_floor.isoformat()}'
        GROUP BY {day_expr}
    ),
    scanned AS (
        SELECT day, last_written_at, LEAD(day) OVER (ORDER BY day) AS next_day
        FROM written_days
    )
    SELECT
        MAX(day) AS last_day,
        MIN(CASE WHEN next_day > date_add(day, 1) THEN date_add(day, 1) END)
            AS first_missing_day,
        {unsettled_expr} AS first_unsettled_day
    FROM scanned
    """


def compute_gap_aware_lower_bound(
    spark: SparkSession,
    *,
    target_table: str,
    watermark_column: str,
    lookback_days: int,
    today: date,
    generated_at_column: str | None = None,
    gap_detection_window_days: int = DEFAULT_GAP_DETECTION_WINDOW_DAYS,
) -> date:
    """Borne basse de recalcul ancree sur la COUVERTURE REELLE de `target_table`.

    Une fenetre calee sur le seul `today - lookback_days` perd definitivement
    tout jour qu'aucun run n'a couvert pendant sa fenetre (run non declenche/en
    echec, source curated en retard) : le trou devient permanent et les
    agregations glissantes sous-comptent silencieusement.

    Retient le MINIMUM de quatre bornes candidates :
      1. `today - lookback_days` : la fenetre nominale (arrivees tardives) ;
      2. le premier jour manquant a l'interieur de la couverture (trou) ;
      3. le premier jour ecrit trop tot pour etre stabilise (cf. `gap_scan_sql`) ;
      4. `last_day` : le dernier jour ecrit LUI-MEME (trou de queue).

    Recalculer depuis le trou (et non le seul jour manquant) est volontaire : les
    jours qui SUIVENT un trou ont ete calcules sur une source incomplete.

    Le candidat 4 est bien `last_day` et non `last_day + 1` : le dernier jour
    ecrit est par construction le MOINS stabilise de tous (la source curated
    etait encore en train d'arriver quand il a ete ecrit), repartir du lendemain
    le condamne definitivement. Signature mesuree en dev sur
    `gold_dbx_compute_cluster_cost_daily` avec `last_day + 1` :
    `COUNT(DISTINCT to_date(_generated_at)) = 1` sur TOUS les jours, autrement
    dit aucun jour n'etait jamais recalcule — la fenetre ne faisait qu'avancer,
    et le jour de queue de CHAQUE run restait fige avec son compte partiel (4
    des 8 derniers jours faux, ~15 600 cluster-jours manquants pour une mediane
    de ~8 600/jour).

    Convergence (verifiee sur les memes donnees) : la combinaison
    `lookback_days` > retard de collecte + comparaison inclusive ne fait PAS
    remonter la borne jusqu'au plancher d'inspection. Un jour ancien ecrit
    tardivement reste stabilise (`2026-08-30 <= 2026-06-18` est faux) ; seuls les
    jours dont la derniere ecriture est encore dans leur propre fenetre sont
    signales. En regime permanent chaque jour est donc recalcule pendant
    `lookback_days` jours puis fige.

    Limite residuelle : un jour present mais faux pour une autre raison (source
    revisee en profondeur), sans trou ni jour non stabilise autour, n'est
    detectable que par `--full-refresh`.
    """
    row = spark.sql(
        gap_scan_sql(
            target_table,
            watermark_column,
            inspection_floor=today - timedelta(days=gap_detection_window_days),
            lookback_days=lookback_days,
            generated_at_column=generated_at_column,
        )
    ).collect()[0]
    candidates = [today - timedelta(days=lookback_days)]
    candidates.extend(
        day
        for day in (_as_date(row["first_missing_day"]), _as_date(row["first_unsettled_day"]))
        if day is not None
    )
    last_day = _as_date(row["last_day"])
    if last_day is not None:
        candidates.append(last_day)
    return min(candidates)


def _as_date(value: object) -> date | None:
    """Normalise une valeur de ligne Spark (DATE ou TIMESTAMP) en `date`."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return cast("date", value)


def partition_predicate(spec: IngestionSpec, *bounds: datetime | None) -> str | None:
    """Predicat de pruning sur la 1re colonne de partition (borne la plus basse).

    Accepte un nombre variable de bornes (une par cloud) et retient la plus
    basse pour delimiter le scan. None si la table n'est pas partitionnee ou si
    aucune borne n'est fournie (full load ⇒ scan complet legitime).
    """
    if not spec.partition_columns:
        return None
    present = [bound for bound in bounds if bound is not None]
    if not present:
        return None
    floor = min(present).date()
    return f"t.{spec.partition_columns[0]} >= DATE '{floor.isoformat()}'"
