"""Registre opt-in des tables curated FULL-LOAD eligibles a la purge (T001, 020-...).

Derive de `pipelines.system_tables.specs.SPECS` : chaque `IngestionSpec` porte
son propre flag `purge_eligible` (cf. `pipelines.common.models.IngestionSpec`),
positionne explicitement au cas par cas dans `specs.py`, juste a cote du
commentaire qui explique deja pourquoi cette table est un miroir d'etat
courant (et pas un log d'evenements/historique SCD). Aucune deuxieme liste a
maintenir en synchronisation manuelle avec le socle d'ingestion : ajouter une
table au socle sans se prononcer sur `purge_eligible` la laisse par defaut
`False` (jamais purgeable).

`purge_eligible` est une decision HUMAINE pure, non verifiable
automatiquement (`watermark_column` est orthogonal : il ne borne que la
lecture d'ingestion, jamais celle de la purge, cf. docstring du champ dans
`pipelines.common.models.IngestionSpec`). Registre toujours OPT-IN au sens ou
aucune table n'est purgee sans qu'un humain ait explicitement pose
`purge_eligible=True` sur son spec — mais cette decision vit desormais dans
`specs.py` (source unique de verite du socle), pas ici.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipelines.system_tables.specs import SPECS

# Table d'audit Delta (append-only, 1 ligne par (table, cloud, run) — reel ou
# dry-run). Nom court (comme les autres `curated_dbx_*`) ; qualifiee
# `catalog.schema.` par l'entrypoint, jamais code en dur qualifie ici.
CURATED_PURGE_AUDIT_LOG = "curated_dbx_purge_audit_log"

# Seuils par defaut du garde-fou volumetrique (le plus restrictif des deux
# s'applique, cf. `pipelines.common.purge._guardrail_breached`) :
#   - `threshold_absolute` : nombre de lignes maximum supprimables en un run ;
#   - `threshold_percentage` : fraction maximale de `rows_in_curated_before`.
DEFAULT_THRESHOLD_ABSOLUTE = 1000
DEFAULT_THRESHOLD_PERCENTAGE = 0.20


@dataclass(frozen=True)
class PurgeGuardrail:
    """Seuils du garde-fou volumetrique, par table (surchargeables au besoin)."""

    threshold_absolute: int = DEFAULT_THRESHOLD_ABSOLUTE
    threshold_percentage: float = DEFAULT_THRESHOLD_PERCENTAGE


# Registre opt-in DERIVE : cle = meme identifiant que `system_tables.specs.SPECS`
# (valeur `{{input}}` du `for_each` du job `dcm_curated_purge`). Toute table
# dont le spec porte `purge_eligible=True` y apparait automatiquement, avec les
# seuils par defaut (a surcharger ici au besoin, ex.
# `"uc_tables": PurgeGuardrail(threshold_absolute=5000)`).
PURGE_ENABLED_KEYS: dict[str, PurgeGuardrail] = {
    key: PurgeGuardrail() for key, spec in SPECS.items() if spec.purge_eligible
}

PURGE_KEYS = tuple(PURGE_ENABLED_KEYS)

