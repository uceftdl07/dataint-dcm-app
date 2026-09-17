# DCM Review Report — T001

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `feat/add-dim-reference-lz-workspace` (base: `develop`)
**Domain**: dataeng
**Stack**: backend (PySpark)
**Verdict**: **PASS**

> Note : le script `dcm-review.sh` reporte un FAIL trompeur — il invoque `ruff`/`pytest`
> directement (pas via `uv run`), donc absents du PATH. Les gates réels ont été exécutés
> manuellement via `uv run` (résultats ci-dessous).

## Changed files (scope = packages/dcm-databricks-pipeline ✅)

```
NEW  pipelines/reference_lz/__init__.py
NEW  pipelines/reference_lz/specs.py
NEW  pipelines/reference_lz/ingest.py
NEW  pipelines/reference_lz/entrypoint.py
NEW  resources/job_dcm_reference_lz.yml
NEW  tests/reference_lz/test_specs.py
NEW  tests/reference_lz/test_ingest.py
NEW  tests/reference_lz/test_entrypoint.py
MOD  pipelines/common/transforms.py   (+ dedupe_by_key, filter_null_or_empty_key)
MOD  tests/conftest.py                 (+ FakeColumn/FakeWindow/FakeWindowSpec + FakeDataFrame méthodes)
MOD  tests/common/test_transforms.py
MOD  pyproject.toml                    (+ script dcm-reference-lz)
MOD  uv.lock                           (bump lockfile auto)
```

Aucun fichier hors du package. Aucun refactor non lié.

## Gates (exécutés via `uv run`)

| Gate | Status | Detail |
|------|--------|--------|
| ruff (scoped) | PASS | `pipelines/reference_lz/ pipelines/common/transforms.py resources/ tests/reference_lz/ tests/common/test_transforms.py tests/conftest.py` → All checks passed |
| mypy | PASS | `mypy -p pipelines.common -p pipelines.reference_lz` → no issues (13 files) |
| pytest | PASS | 25/25 (`tests/reference_lz/` + `tests/common/test_transforms.py`) |

> Dette pré-existante hors scope : `tests/test_dlt_workflow.py` porte 266 erreurs ruff
> ANN001 (annotations de fixtures manquantes) — sans rapport avec T001, non introduite ici.

## Skill review (dcm-python / dcm-testing / dcm-verify)

- ✅ Python 3.12, imports absolus (`pipelines.common.*`), aucun import relatif.
- ✅ Aucun secret en dur — résolution via `secrets.get(scope=…, key=…)` (dbutils.secrets), scope paramétré.
- ✅ Aucun `print`, logging structuré via `logging.getLogger(__name__)`.
- ✅ Type hints complets (mypy strict OK).
- ✅ Idempotence (P6) : `dedupe_by_key` déterministe (row_number sur clé, tri sur toutes
  les autres colonnes ASC NULLS LAST) + `MERGE INTO` sur `merge_keys` — pas de
  `dropDuplicates()` non déterministe.
- ✅ Fail-loud (P4) : `filter_null_or_empty_key` logue le nombre de lignes exclues ;
  `entrypoint.main` lève `ValueError` explicite (business_application sans config Azure, FR-004 ;
  catalog/schema vides ; `--table` inconnu).
- ✅ Tests : fakes partagés (pas de JVM), couvrent câblage (renommage par cloud, staging,
  MERGE, cleanup) + sémantique des 2 primitives isolément.

### Finding (corrigé pendant la review)

- `tests/reference_lz/test_entrypoint.py:test_main_ingests_both_tables_when_table_param_empty`
  🟡 → **corrigé** : le test appelait `main()` avec Azure désactivé mais attendait les 2 tables
  ingérées, en contradiction avec le garde-fou FR-004 (business_application exige une config
  Azure). Passé sur `_azure_params()` + `_FakeSecrets()`. Pas de bug côté code prod.

## Acceptance Criteria

13/14 vérifiées par code + tests (voir `stories/T001-reference-lz-ingestion.md`).
SC-003 (présence lignes `aws` ET `azure`) non vérifiable en local — nécessite un run réel
cluster contre les sources ; à valider via `quickstart.md` §4 après déploiement dev.

## Next

- Verdict PASS → PR branche fille → `develop` via `/speckit.dcm.publish-pr --spec 014-reference-lz-tables --task T001`.
