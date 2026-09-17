"""Extraction des Databricks system tables (billing + compute/access) vers curated.

Plugin unique mutualisant les anciens domaines `finops` et `usage` : un seul
socle de cablage (`ingest` + `entrypoint`) piloté par un registre de specs
(`specs.SPECS`). Chaque entrée du registre = une table système ingérée, exécutée
en parallèle par une itération de la tache `for_each` du job (une table = une
itération, sélectionnée par le paramètre `--table`).
"""
