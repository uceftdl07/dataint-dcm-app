"""Transformations pures d'enveloppe (fidele source) + primitives dedup/filtre.

Fonctions sans effet de bord, testables sans cluster : elles n'ajoutent que des
colonnes de tracabilite (enveloppe), sans jamais toucher aux colonnes source
(medaillon pur) -- ou bornent/dedupliquent le DataFrame source avant un MERGE
idempotent, sans logique metier specifique a un domaine.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyspark.sql import Window
from pyspark.sql import functions as F

if TYPE_CHECKING:
    from pyspark.sql import Column, DataFrame

logger = logging.getLogger(__name__)


# Colonnes d'enveloppe ajoutees a chaque ligne (jamais de transformation source).
ENVELOPE_COLUMNS = (
    "cloud_provider",
    "collected_at",
)

# Colonne technique ephemere portant le rang de deduplication (`dedupe_by_key`) ;
# toujours supprimee avant retour, jamais persistee en curated.
_DEDUPE_ROW_NUMBER_COLUMN = "_dcm_dedupe_row_number"


def enrich_with_envelope(
    df: DataFrame,
    *,
    cloud_provider: str,
    collected_at: str,
) -> DataFrame:
    """Ajoute les colonnes d'enveloppe sans toucher aux colonnes source.

    Medaillon pur : aucune colonne source n'est renommee, castee ou supprimee ;
    on se contente d'annexer les colonnes de tracabilite / provenance.
    """
    return df.withColumn("cloud_provider", F.lit(cloud_provider)).withColumn(
        "collected_at", F.to_timestamp(F.lit(collected_at))
    )


def filter_null_or_empty_key(df: DataFrame, *key_columns: str) -> DataFrame:
    """Exclut les lignes dont une colonne de la cle de fusion est NULL/vide (FR-011).

    Garde-fou avant `MERGE` : la `PRIMARY KEY` declaree sur une table curated
    n'est PAS enforced par Delta (contrainte informative) -- une ligne a cle
    invalide romprait silencieusement l'unicite attendue (SC-001/SC-002) et
    toute jointure aval. Le nombre de lignes exclues est loggue explicitement
    (jamais un rejet silencieux, P4 Fail Fast/Fail Loud).
    """
    before_count = df.count()
    condition: Column | None = None
    for key in key_columns:
        key_condition = F.col(key).isNotNull() & (F.trim(F.col(key)) != "")
        condition = key_condition if condition is None else condition & key_condition
    filtered = df.filter(condition) if condition is not None else df
    excluded = before_count - filtered.count()
    if excluded:
        logger.warning(
            "filter_null_or_empty_key excluded=%d key_columns=%s", excluded, key_columns
        )
    return filtered


def dedupe_by_key(df: DataFrame, key_columns: tuple[str, ...]) -> DataFrame:
    """Deduplique `df` sur `key_columns` avant `MERGE`, choix deterministe (FR-009).

    `dropDuplicates()` seul ne suffit pas : Spark ne garantit pas quelle ligne
    est conservee entre 2 runs (depend du plan physique / de l'ordre des
    tasks), ce qui violerait l'idempotence (P6). On trie donc explicitement sur
    TOUTES les colonnes restantes (ASC NULLS LAST) pour rendre le choix
    reproductible run apres run, independamment de l'ordre physique de
    lecture -- condition necessaire quand la source contient des doublons de
    cle dans un meme run (sinon `MERGE` echoue avec
    `DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW`).
    """
    order_columns = [c for c in df.columns if c not in key_columns]
    # Aucune colonne restante (cas degenere, cle = toutes les colonnes) : les
    # lignes candidates sont alors identiques pour l'usage MERGE, un ordre
    # arbitraire mais stable (constante) suffit.
    order_by: list[Column] = [F.col(c).asc_nulls_last() for c in order_columns] or [F.lit(1)]
    window = Window.partitionBy(*key_columns).orderBy(*order_by)
    return (
        df.withColumn(_DEDUPE_ROW_NUMBER_COLUMN, F.row_number().over(window))
        .filter(F.col(_DEDUPE_ROW_NUMBER_COLUMN) == 1)
        .drop(_DEDUPE_ROW_NUMBER_COLUMN)
    )
