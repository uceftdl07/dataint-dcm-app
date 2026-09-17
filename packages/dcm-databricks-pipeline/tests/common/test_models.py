"""Tests de `pipelines.common.models.IngestionSpec` (020-curated-full-load-purge).

Couvre uniquement le champ ajoute par ce ticket (`purge_eligible`) : le reste
du dataclass est un simple porteur de donnees, sans comportement a tester.
"""

from __future__ import annotations

from pipelines.common.models import IngestionSpec


def test_purge_eligible_true_without_watermark_is_allowed() -> None:
    spec = IngestionSpec(
        source_table="system.some.reference_table",
        curated_table="curated_dbx_reference_table",
        merge_keys=("cloud_provider", "id"),
        purge_eligible=True,
    )
    assert spec.purge_eligible is True


def test_purge_eligible_and_watermark_column_are_orthogonal() -> None:
    # watermark_column ne borne que la lecture d'INGESTION incrementale ; le
    # mecanisme de purge relit toujours la source integralement, quel que soit
    # watermark_column (cf. pipelines.common.purge._read_full_source). Rien
    # n'empeche donc, en theorie, une table incrementale de type 1 (cle de
    # merge purement metier, sans composant evenement/version) d'etre a la
    # fois watermarkee ET purge_eligible : aucune verification automatique
    # n'est possible ici, seule une revue humaine du merge_keys en decide
    # (documentee a cote de purge_eligible=True dans specs.py).
    spec = IngestionSpec(
        source_table="system.access.users",
        curated_table="curated_dbx_active_users",
        merge_keys=("cloud_provider", "user_id"),
        watermark_column="last_seen_at",
        purge_eligible=True,
    )
    assert spec.purge_eligible is True
    assert spec.watermark_column == "last_seen_at"


def test_purge_eligible_defaults_to_false() -> None:
    spec = IngestionSpec(
        source_table="system.some.table",
        curated_table="curated_dbx_table",
        merge_keys=("cloud_provider", "id"),
    )
    assert spec.purge_eligible is False


def test_incremental_spec_without_purge_eligible_is_allowed() -> None:
    spec = IngestionSpec(
        source_table="system.some.event_log",
        curated_table="curated_dbx_event_log",
        merge_keys=("cloud_provider", "event_id"),
        watermark_column="event_time",
    )
    assert spec.watermark_column == "event_time"
    assert spec.purge_eligible is False
