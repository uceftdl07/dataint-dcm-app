"""Agregations gold `gold_dbx_usage_*` — fait de consommation Usage Data Product.

Symetrique a `pipelines.gold_dbx_compute` (meme pattern : registre `GOLD_SPECS`,
entrypoint wheel unique parametre par `--table`) mais pour le domaine usage/
adoption/FinOps des data products (tables Unity Catalog), pas compute clusters/
warehouses (cf. `specs/019-usage-data-product-gold/research.md` R1).
"""

from __future__ import annotations
