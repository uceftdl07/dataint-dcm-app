"""Lecture des sources (UC natif / Azure cross-tenant via Entra + SQL connector).

Fournit les readers generiques piloté par une `IngestionSpec` :
  - `read_native_source` : lecture Spark native (workspace local, distribuee) ;
  - `read_azure_batches` : lecture Azure cross-tenant en lots bornes (memoire
    driver plafonnee), via un jeton Entra M2M et le `databricks-sql-connector`.
Aucune notion metier : la table et le filtre incremental viennent de la spec.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyspark.sql import functions as F

from pipelines.common.azure_auth import make_credentials_provider
from pipelines.common.azure_decode import reference_schema, rows_to_dataframe

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from pyspark.sql import DataFrame, SparkSession

    from pipelines.common.models import AzureConnectionConfig, IngestionSpec


# Taille des lots de lecture Azure (nb de lignes par `fetchmany`). Borne la
# memoire du driver : les resultats du SQL connector transitent inline (cloud
# fetch desactive, cf. `read_azure_batches`), donc un `fetchall()` chargerait tout
# l'historique sur le driver ⇒ OOM. Ajustable selon la RAM du driver.
# 10 000 : seuil conservateur pour les tables larges (access.audit, ~50 colonnes)
# qui saturaient la JVM serverless à 50 000 (Java heap space).
DEFAULT_AZURE_FETCH_BATCH_SIZE = 10_000


def read_native_source(
    spark: SparkSession,
    spec: IngestionSpec,
    lower_bound: datetime | None = None,
) -> DataFrame:
    """Lecture native UC de la table source (workspace local, ex. AWS).

    Distribuee et lazy ; filtree par watermark en incremental (borne le volume
    lu a chaque run). Ajoute un filtre explicite sur la 1re colonne de partition
    quand elle existe : Delta peut pruner les partitions entieres (pas seulement
    les fichiers via stats min/max), ce qui evite d'ouvrir N annees de partitions
    quotidiennes pour ne lire que les 3 derniers jours.

    `row_filter` (optionnel) ecarte en plus les evenements hors perimetre (ex.
    `action_name` non pertinents pour `system.access.audit`) et `select_columns`
    projette un sous-ensemble de colonnes : les deux bornent le VOLUME et la
    LARGEUR des lignes materialisees, avant meme l'enveloppe / le MERGE.

    """
    df = spark.read.table(spec.source_table)
    if lower_bound is not None and spec.watermark_column is not None:
        df = df.filter(F.col(spec.watermark_column) >= F.lit(lower_bound))
        # Partition pruning explicite : saute les partitions anterieures a la borne.
        if spec.partition_columns:
            df = df.filter(F.col(spec.partition_columns[0]) >= F.lit(lower_bound.date()))
    if spec.row_filter is not None:
        df = df.filter(F.expr(spec.row_filter))
    if spec.select_columns is not None:
        df = df.select(*spec.select_columns)
    return df


def build_azure_query(spec: IngestionSpec, lower_bound: datetime | None) -> str:
    """Requete de lecture Azure, filtree par watermark en incremental.

    Le filtre est pousse cote SQL Warehouse Azure ⇒ seules les lignes recentes
    transitent vers le workspace local (evite de rapatrier tout l'historique et
    le `fetchall()` associe sur le driver). `select_columns` restreint la liste
    projetee (au lieu de `*`) et `row_filter` ajoute un predicat supplementaire
    (ex. `action_name IN (...)`) : les deux sont pousses cote source, donc ne
    transitent jamais vers le driver du workspace local.
    """
    columns = ", ".join(spec.select_columns) if spec.select_columns else "*"
    query = f"SELECT {columns} FROM {spec.source_table}"
    conditions: list[str] = []
    if lower_bound is not None and spec.watermark_column is not None:
        conditions.append(f"{spec.watermark_column} >= '{lower_bound.isoformat(sep=' ')}'")
    if spec.row_filter is not None:
        conditions.append(f"({spec.row_filter})")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    return query


def read_azure_batches(
    spark: SparkSession,
    spec: IngestionSpec,
    config: AzureConnectionConfig,
    lower_bound: datetime | None = None,
    batch_size: int = DEFAULT_AZURE_FETCH_BATCH_SIZE,
) -> Iterator[DataFrame]:
    """Lecture Azure cross-tenant, en lots bornes (memoire driver plafonnee).

    Le jeton AAD est obtenu depuis le SP Entra (client-credentials), puis passe
    au SQL Warehouse Azure. La lecture reste 100 % intra-Azure ; le workspace
    local ne recoit que les lignes resultats, bornees par watermark (spike E3).
    Import paresseux : `databricks-sql-connector` n'est requis qu'a l'execution,
    jamais pour les tests unitaires.

    `use_cloud_fetch=False` (CRITIQUE cross-cloud) : par defaut le connecteur
    rapatrie les gros resultats via "cloud fetch" (le warehouse Azure ecrit dans
    Azure Blob Storage et renvoie des liens presignes SAS que le client telecharge
    directement). Depuis le cluster serverless AWS, ce blob Azure
    (`*.blob.core.windows.net`) est injoignable — meme firewall ADLS que celui qui
    bloque Delta Sharing UC->UC (spike E3) ⇒ `ConnectionReset`. En desactivant le
    cloud fetch, les resultats transitent inline via Thrift a travers le warehouse
    lui-meme (endpoint deja joignable), sans passer par le blob presigne.

    Consequence du inline fetch : un `fetchall()` chargerait tout le resultat sur
    le driver (⇒ OOM / exit 137 sur l'historique complet). On streame donc le
    curseur par lots de `batch_size` lignes (`fetchmany`) et on yield un DataFrame
    Spark par lot ; le driver ne detient jamais plus d'un lot a la fois. Les lots
    vides sont ignores ; aucun yield si la source est vide.
    """
    from databricks import sql

    with (
        sql.connect(
            server_hostname=config.host,
            http_path=config.http_path,
            credentials_provider=make_credentials_provider(config),
            use_cloud_fetch=False,
        ) as connection,
        connection.cursor() as cursor,
    ):
        query = build_azure_query(spec, lower_bound)
        logger.info("azure.query.start table=%s lower_bound=%s", spec.source_table, lower_bound)
        cursor.execute(query)
        columns = [c[0] for c in cursor.description or []]
        schema = reference_schema(spark, spec.source_table, columns)
        batch_num = 0
        total_rows = 0
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            batch_num += 1
            total_rows += len(rows)
            logger.info(
                "azure.batch table=%s batch=%d rows=%d cumulative=%d",
                spec.source_table, batch_num, len(rows), total_rows,
            )
            batch = rows_to_dataframe(spark, columns, rows, schema)
            if batch is not None:
                yield batch
        logger.info(
            "azure.query.done table=%s total_batches=%d total_rows=%d",
            spec.source_table, batch_num, total_rows,
        )
