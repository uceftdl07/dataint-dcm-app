#!/usr/bin/env bash
# Cree/actualise le venv de debug isole (.venv-debug) pour Databricks Connect.
#
# Pourquoi un venv separe : databricks-connect embarque son propre pyspark et
# refuse de demarrer si `pyspark` (dep runtime du wheel, present dans .venv) est
# installe dans le meme environnement. On isole donc le debug ici, sans pyspark
# ni delta-spark ; databricks-connect fournit le namespace `pyspark.sql`.
#
# Usage :
#   cd packages/dcm-databricks-pipeline
#   ./scripts/setup_debug_env.sh
# Puis debug via VS Code (F5 "Debug System Tables local (Databricks Connect)") ou :
#   .venv-debug/bin/python -m pipelines.system_tables.entrypoint
set -euo pipefail

cd "$(dirname "$0")/.."

uv venv .venv-debug --python 3.12
# Deps de debug uniquement (databricks-connect apporte pyspark) — pas d'install
# du package pour eviter de tirer pyspark/delta-spark declares en runtime.
uv pip install --python .venv-debug \
  "databricks-connect>=16.4,<17" \
  "databricks-sql-connector==4.2.6" \
  "azure-identity==1.20.0" \
  "databricks-sdk>=0.30"

echo "[ok] .venv-debug pret. Interpreteur : $(pwd)/.venv-debug/bin/python"
