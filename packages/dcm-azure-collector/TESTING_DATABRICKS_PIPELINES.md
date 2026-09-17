# Testing DatabricksPipelineCollector

Guide complet pour tester le nouveau collecteur Databricks Pipelines.

## Sommaire

1. [Tests unitaires (pytest)](#tests-unitaires)
2. [Test local avec mock (développement)](#test-local)
3. [Test d'intégration (données réelles)](#test-intégration)

---

## Tests unitaires

Rapides, sans dépendances externes, avec mocking complet.

### Exécuter tous les tests Azure Collector

```bash
cd packages/dcm-azure-collector
uv run pytest -q tests/
```

### Exécuter uniquement les tests DatabricksPipelineCollector

```bash
cd packages/dcm-azure-collector
uv run pytest -q tests/test_databricks_pipelines_collector.py -v
```

### Exécuter un test spécifique

```bash
uv run pytest -q tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_success -v
```

### Résultat attendu

```
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_init_default_parameters PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_init_custom_lookback PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_domain_property PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_success PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_failed PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_running PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_skipped PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_error_message_truncation PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_missing_run_id PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_missing_job_id PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_with_tags PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_cancelled PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_map_run_to_metric_queued PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_collect_metrics_no_workspaces PASSED
tests/test_databricks_pipelines_collector.py::TestDatabricksPipelineCollector::test_collect_metrics_with_job_runs PASSED
======================== 15 passed in 0.45s =========================
```

---

## Test local

Simule une collecte complète avec des données fictives (sans appels réels à Azure/Databricks).

### Exécuter le test local

```bash
cd packages/dcm-azure-collector
uv run python test_local_databricks_pipelines.py
```

### Output attendu

```
================================================================================
Testing DatabricksPipelineCollector with mock data
================================================================================

Collector domain: pipeline

Collection result:
  - Status event count: 1
  - Payload metric count: 3
  - Payload domain: pipeline

Collected metrics:

  Metric 1:
    - run_id: 1
    - pipeline_name: etl_daily_sync
    - status: succeeded
    - start_time: 2024-06-06T10:00:00+00:00
    - end_time: 2024-06-06T10:10:00+00:00
    - databricks_workspace_id: 1234567890

  Metric 2:
    - run_id: 2
    - pipeline_name: data_quality_checks
    - status: running
    - start_time: 2024-06-06T11:30:00+00:00
    - end_time: None
    - databricks_workspace_id: 1234567890

  Metric 3:
    - run_id: 3
    - pipeline_name: failed_job
    - status: failed
    - start_time: 2024-06-06T08:00:00+00:00
    - end_time: 2024-06-06T09:00:00+00:00
    - error_message: Task failed: schema validation error in step 2
    - databricks_workspace_id: 1234567890

================================================================================
✅ Test completed successfully!
================================================================================
```

---

## Test d'intégration

Teste le collecteur avec **vraies données** (Azure + Databricks réels).

### Prérequis

- Variables d'environnement définies :
  ```bash
  export AZURE_SUBSCRIPTION_ID="your-subscription-id"
  export DCM_SOURCE_LZ_ID="azure-sub-xxxx"
  export DCM_KEY_VAULT_URL="https://kv-dcm-prod.vault.azure.net/"
  ```

- Databricks Workspaces accessibles dans votre abonnement
- Identité Azure authentifiée (via `DefaultAzureCredential`)

### Exécuter une collecte réelle

```bash
cd packages/dcm-azure-collector

# Une seule collecte, mode verbeux
export DCM_LOG_LEVEL=DEBUG
export DCM_ENABLED_COLLECTORS="databricks_pipelines"
uv run python -m azure_collector.main --once
```

### Vérifier les résultats

Regardez dans le dossier courant pour :
- `payloads_local_test.json` — si `DCM_LOCAL_DEV=1` est défini
- Logs structurés (JSON) sur stdout/stderr

---

## Cas d'usage des tests

| Cas | Test | Quand utiliser |
|---|---|---|
| Vérifier que le collecteur démarre | `test_init_*` | Avant chaque déploiement |
| Vérifier le mapping des runs → metrics | `test_map_run_to_metric_*` | Code review |
| Vérifier la collection complète | `test_collect_metrics_*` | Avant merge sur main |
| Tester avec vraies données | `test_local_...py` | Développement local |
| Tester avec API réelle | `main --once` | Avant déploiement en staging |

---

## Dépannage

### ❌ ModuleNotFoundError: No module named 'httpx'

**Solution** :
```bash
uv sync --extra dev --python 3.12
```

### ❌ Tests async passent mais collecte échoue

**Vérifier** :
- Les tokens Databricks/Azure sont valides (`get_databricks_token`, `get_mgmt_token`)
- L'URL workspace contient `https://` (voir `_list_job_runs`)
- Les filtres de job runs sont corrects (voir `start_time_ms` en millisecondes)

### ❌ Erreur "Databricks jobs/runs/list returned HTTP 429"

**Solution** : Rate-limited. Réduisez la fréquence ou augmentez `lookback_hours`.

---

## Intégration CI/CD

Pour ajouter à GitHub Actions, voir `.github/workflows/ci-azure-collector.yml` :

```yaml
- name: Run DatabricksPipelineCollector tests
  run: |
    cd packages/dcm-azure-collector
    uv run pytest -q tests/test_databricks_pipelines_collector.py
```

