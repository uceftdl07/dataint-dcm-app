"""Socle reutilisable d'ingestion medaillon (readers / writers / transforms).

Regroupe les briques generiques, independantes de tout domaine metier
(billing, usage, audit...), qu'un plugin d'ingestion (`pipelines.<domaine>`)
assemble via une `IngestionSpec`. Aucun module ici ne connait la notion de
facturation : c'est ce decouplage qui rend le socle reutilisable pour tout
nouveau flux d'extraction Azure ⊎ AWS vers curated.
"""
