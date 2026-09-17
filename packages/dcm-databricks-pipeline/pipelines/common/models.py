"""Contrats generiques du socle d'ingestion (specs + config source Azure).

`IngestionSpec` decrit *quoi* ingerer (table source -> table curated) sans rien
supposer du domaine : n'importe quel plugin (`pipelines.<domaine>`) instancie
cette spec pour ses propres tables. `AzureConnectionConfig` porte les parametres
de connexion au SQL Warehouse Azure cross-tenant (lecture Entra M2M).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionSpec:
    """Decrit l'ingestion fidele d'une table source vers une table curated.

    Generique (aucune notion metier) : un plugin fournit les noms de tables, la
    cle metier du MERGE et, optionnellement, la strategie incrementale.

    - `watermark_column` : colonne temporelle pour l'ingestion incrementale
      (None ⇒ full load, ex. une table de reference petite et stable).
    - `partition_columns` : colonnes de partitionnement Delta de la table curated
      (pruning du MERGE + des lectures ; vide ⇒ table non partitionnee).
    - `initial_lookback_days` : fenetre de backfill du TOUT PREMIER run d'une
      table watermarkee (aucun watermark encore present en curated). None ⇒
      backfill de tout l'historique ; une valeur borne le premier scan a
      `now - N jours`. INDISPENSABLE pour les tables d'evenements volumineuses
      (ex. `system.access.audit`, `system.compute.node_timeline`) lues via le SQL
      connector Azure en inline fetch : un `SELECT *` sur l'historique complet
      materialise tout le resultat sur le driver du warehouse Azure et depasse
      `spark.driver.maxResultSize` (que l'on ne controle pas cross-tenant).
    """

    source_table: str
    curated_table: str
    merge_keys: tuple[str, ...]
    watermark_column: str | None = None
    partition_columns: tuple[str, ...] = ()
    initial_lookback_days: int | None = None
    azure_fetch_batch_size: int | None = None
    """Taille de lot Azure (`fetchmany`) specifique a cette table ; None ⇒ valeur
    globale du job. A baisser pour les tables LARGES (bcp de colonnes, ex.
    `system.access.audit` ~50 col.) : un lot global trop grand sature la JVM
    serverless (OOM) sur ces tables, alors qu'il passe pour les tables etroites."""
    select_columns: tuple[str, ...] | None = None
    """Sous-ensemble de colonnes source a projeter ; None ⇒ toutes (`SELECT *`).
    Reduit la LARGEUR de ligne (memoire driver cote lot Azure inline fetch, et
    volume ecrit en curated) pour les tables tres larges dont seul un sous-
    ensemble sert au cas d'usage cible (ex. `system.access.audit` : ~50 colonnes,
    dont certaines volumineuses/variables, alors que le tracking d'usage d'un
    data product n'en necessite qu'une poignee). DOIT inclure les colonnes de
    `merge_keys`, `watermark_column` et `partition_columns`."""
    row_filter: str | None = None
    """Predicat SQL pousse a la source (clause `WHERE` Azure, `.filter` AWS) pour
    ne retenir que les evenements pertinents (ex. `action_name IN (...)`). Reduit
    le VOLUME de lignes en amont, complementaire a `select_columns` (largeur) :
    les deux bornent la memoire driver et le temps de lecture Azure (inline
    fetch) sur les tables d'evenements volumineuses."""
    purge_eligible: bool = False
    """True ⇒ cette table peut etre activee dans le registre de purge
    (`pipelines.system_tables.purge_specs.PURGE_ENABLED_KEYS`, story T001,
    020-curated-full-load-purge). Reserve aux tables qui sont des MIROIRS
    D'ETAT COURANT de la source (une ligne absente de la derniere lecture
    signifie que l'objet n'existe plus) — jamais un LOG D'EVENEMENTS ou un
    HISTORIQUE VERSIONNE (SCD), ou une ligne "absente" d'une lecture bornee ne
    veut dire que "hors fenetre", pas "supprimee a la source" : purger la
    supprimerait a tort de l'historique legitime.

    ORTHOGONAL a `watermark_column` : ce dernier ne borne QUE la lecture
    d'ingestion (incrementale) ; le mecanisme de purge (`pipelines.common.purge`)
    relit TOUJOURS la source integralement, quel que soit `watermark_column`.
    Une table incrementale peut donc, en theorie, etre un simple miroir d'etat
    courant (cle de merge purement metier, sans composant evenement/version) et
    etre eligible a la purge. Ce que `merge_keys` represente (version/evenement
    vs entite stable) ne se deduit PAS mecaniquement de `watermark_column` ni
    du nom des colonnes : c'est une revue humaine, documentee par le
    commentaire pose a cote de `purge_eligible=True` dans `specs.py`. Aucune
    verification automatique n'est possible ici (cf. story 020-curated-full-
    load-purge, discussion de conception)."""


@dataclass(frozen=True)
class AzureConnectionConfig:
    """Parametres de connexion Azure Databricks SQL Warehouse (Entra M2M)."""

    host: str
    http_path: str
    tenant_id: str
    client_id: str
    client_secret: str
