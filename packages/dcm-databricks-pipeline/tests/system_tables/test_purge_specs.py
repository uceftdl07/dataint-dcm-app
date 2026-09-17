"""Tests de `pipelines.system_tables.purge_specs` (registre opt-in de purge, T001)."""

from __future__ import annotations

import pipelines.system_tables.purge_specs as purge_specs
import pipelines.system_tables.specs as specs


def test_purge_enabled_keys_are_currently_all_full_load_specs() -> None:
    # Vrai pour les 4 tables activees aujourd'hui, mais PAS un invariant du
    # design : purge_eligible et watermark_column sont orthogonaux (cf.
    # pipelines.common.models.IngestionSpec docstring) — une future table
    # incrementale de type 1 pourrait legitimement etre purge_eligible=True.
    for key in purge_specs.PURGE_ENABLED_KEYS:
        assert key in specs.SPECS
        assert specs.SPECS[key].watermark_column is None


def test_purge_enabled_keys_activates_the_four_socle_tables_on_delivery() -> None:
    assert set(purge_specs.PURGE_ENABLED_KEYS) == {
        "uc_tables",
        "uc_table_tags",
        "compute_node_types",
        "billing_list_prices",
    }


def test_purge_keys_matches_enabled_keys_order() -> None:
    assert tuple(purge_specs.PURGE_ENABLED_KEYS) == purge_specs.PURGE_KEYS


def test_default_thresholds_applied_to_every_registered_table() -> None:
    for guardrail in purge_specs.PURGE_ENABLED_KEYS.values():
        assert guardrail.threshold_absolute == purge_specs.DEFAULT_THRESHOLD_ABSOLUTE
        assert guardrail.threshold_percentage == purge_specs.DEFAULT_THRESHOLD_PERCENTAGE
    assert purge_specs.DEFAULT_THRESHOLD_ABSOLUTE == 1000
    assert purge_specs.DEFAULT_THRESHOLD_PERCENTAGE == 0.20


def test_audit_log_table_name_is_not_qualified() -> None:
    # Qualification catalog.schema a la charge de l'entrypoint (comme les
    # curated_table du registre d'ingestion), jamais codee en dur ici.
    assert purge_specs.CURATED_PURGE_AUDIT_LOG == "curated_dbx_purge_audit_log"
    assert "." not in purge_specs.CURATED_PURGE_AUDIT_LOG


def test_purge_enabled_keys_is_derived_from_purge_eligible_flag() -> None:
    # PURGE_ENABLED_KEYS n'est plus une liste manuelle : elle doit contenir
    # EXACTEMENT les cles dont le spec porte purge_eligible=True, ni plus ni
    # moins (garde-fou d'incremental deja garanti par
    # IngestionSpec.__post_init__, teste dans tests/common/test_models.py).
    expected = {key for key, spec in specs.SPECS.items() if spec.purge_eligible}
    assert set(purge_specs.PURGE_ENABLED_KEYS) == expected
