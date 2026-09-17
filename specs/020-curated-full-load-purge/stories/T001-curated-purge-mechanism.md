# T001 — Mécanisme de purge générique des tables curated full-load

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/020-purge-curated-full-load-registre-opt-in
**Jira**: [DCINT-298](https://tdf.atlassian.net/browse/DCINT-298)
**Depends on**: none
**Work type**: technique

> **Branch** = git **branch name** only (e.g. `frontend/011-carousel-ui`). Never a commit SHA.

## Description

Ajoute un mécanisme de purge générique et opt-in par table pour les tables curated
full-load (`curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`,
`curated_dbx_compute_node_types`, `curated_dbx_billing_list_prices`), qui ne reçoivent
aujourd'hui que des upserts (`MERGE ... WHEN MATCHED/NOT MATCHED`, jamais de `DELETE`) et
dérivent donc silencieusement de la source qu'elles reflètent. Le mécanisme relit la
source, détecte les lignes absentes par clé de merge et par cloud, applique un garde-fou
volumétrique (seuil absolu **et** pourcentage, le plus restrictif), trace chaque run
(réel ou dry-run) dans une table d'audit Delta dédiée, et supprime via
`MERGE INTO ... WHEN NOT MATCHED BY SOURCE AND t.cloud_provider = '<cloud>' THEN DELETE`.
Le tout tourne sur un job Databricks Asset Bundle **séparé** de l'ingestion (`job_dcm_curated_purge.yml`,
cron hebdomadaire décalé), jamais une tâche du job `dcm_system_tables` existant.

Voir [plan.md](../plan.md), [research.md](../research.md), [data-model.md](../data-model.md)
et [contracts/purge-registry.md](../contracts/purge-registry.md) pour le détail des
décisions techniques (déjà tranchées, pas à rediscuter ici).

## Files to create/modify

- CREATE `packages/dcm-databricks-pipeline/pipelines/common/purge.py` — `purge_absent_rows()` : relit la source (native AWS / lots Azure via readers.py existant), calcule les lignes absentes (anti-join sur `merge_keys`), applique le garde-fou, retourne un `PurgeAuditRecord`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/common/writers.py` — ajoute `purge_rows_not_in_source()` : `MERGE INTO ... WHEN NOT MATCHED BY SOURCE AND t.cloud_provider = '<cloud>' THEN DELETE`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/common/models.py` — ajoute `IngestionSpec.purge_eligible: bool = False` (post-review refinement, voir section dédiée plus bas) — champ additif, aucun champ existant modifié
- CREATE `packages/dcm-databricks-pipeline/pipelines/system_tables/purge_specs.py` — `PURGE_ENABLED_KEYS` dérivé de `specs.SPECS` (filtré sur `purge_eligible`), seuils par table (défauts `threshold_absolute=1000`, `threshold_percentage=0.20`)
- UPDATE `packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py` — `purge_eligible=True` posé sur les 4 specs full-load (`UC_TABLES_SPEC`, `UC_TABLE_TAGS_SPEC`, `NODE_TYPES_SPEC`, `BILLING_LIST_PRICES_SPEC`), post-review refinement — additif (1 kwarg par spec ciblé), aucune des 12 autres specs ni la logique d'ingestion touchées
- CREATE `packages/dcm-databricks-pipeline/pipelines/system_tables/purge_entrypoint.py` — point d'entrée wheel task (`main(spark, secrets, params)`), même pattern que `entrypoint.py`, paramètre `dry_run`
- CREATE `packages/dcm-databricks-pipeline/resources/job_dcm_curated_purge.yml` — job dédié, cron hebdomadaire décalé après `dcm_system_tables` (03:00), `for_each` sur `PURGE_ENABLED_KEYS`, aucun `depends_on` vers l'ingestion
- UPDATE `packages/dcm-databricks-pipeline/pyproject.toml` — `[project.scripts]` : `dcm-curated-purge = "pipelines.system_tables.purge_entrypoint:run"`
- CREATE `packages/dcm-databricks-pipeline/tests/common/test_purge.py`
- CREATE `packages/dcm-databricks-pipeline/tests/common/test_models.py` — invariants de `IngestionSpec.purge_eligible` (post-review refinement)
- UPDATE `packages/dcm-databricks-pipeline/tests/common/test_writers.py` — cas `purge_rows_not_in_source`
- CREATE `packages/dcm-databricks-pipeline/tests/system_tables/test_purge_specs.py`
- CREATE `packages/dcm-databricks-pipeline/tests/system_tables/test_purge_entrypoint.py`

## Acceptance Criteria

- [x] Table activée pour la purge : les lignes curated absentes de la dernière lecture source complète (par clé de merge, par cloud) sont supprimées, les autres conservées (spec AC1)
- [x] Table **non** activée (`purge_eligible=False`, défaut) : aucune suppression possible, elle n'apparaît jamais dans `PURGE_ENABLED_KEYS` (spec AC2)
- [x] Job de purge sur chemin d'exécution et cron séparés de l'ingestion, aucun appel/dépendance technique vers/depuis `dcm_system_tables` (spec AC3)
- [x] Dépassement du seuil absolu **ou** pourcentage (le plus restrictif) → arrêt sans suppression, anomalie tracée en audit (spec AC4)
- [x] Mode `dry_run=true` : calcul et trace en audit sans `DELETE` réel (spec AC5)
- [x] Chaque run (réel ou dry-run) insère une ligne dans `curated_dbx_purge_audit_log` (table, cloud, mode, compteurs) (spec AC6)
- [x] Les 4 tables full-load du socle sont activées dans `PURGE_ENABLED_KEYS` dès la livraison (spec AC7)
- [x] Rejouer un run réel sur un état déjà purgé est un no-op (idempotence P6) : `rows_to_delete = 0`, `rows_deleted = 0`
- [x] Gates du package verts (ruff → mypy → pytest → build) (spec AC8)

## Tests

- `cd packages/dcm-databricks-pipeline && PYENV_VERSION=3.12.11 uv run pytest tests/common/test_purge.py tests/common/test_writers.py tests/system_tables/test_purge_specs.py tests/system_tables/test_purge_entrypoint.py -q`
- `PYENV_VERSION=3.12.11 uv run mypy -p pipelines.common` et `-p pipelines.system_tables`
- `PYENV_VERSION=3.12.11 uv run ruff check pipelines/common/purge.py pipelines/system_tables/purge_specs.py pipelines/system_tables/purge_entrypoint.py`
- Validation manuelle dry-run/réel/garde-fou : [quickstart.md](../quickstart.md)

## Out of scope

- Toute modification du COMPORTEMENT du socle d'ingestion existant (`ingest.py`, `entrypoint.py`, `job_dcm_system_tables.yml`) — additif uniquement. `specs.py`/`models.py` ONT été touchés (post-review refinement, `purge_eligible`) mais uniquement pour ajouter un champ opt-in par table, sans changer la lecture/écriture d'aucune des 16 tables existantes
- Activation de la purge sur une table incrémentale sans revue humaine explicite (`purge_eligible=True` reste une décision posée à la main, jamais déduite automatiquement)
- Consommation de `curated_dbx_purge_audit_log` par un dashboard ou une couche gold (hors scope de ce ticket)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [x] Tests pass
- [x] No files outside package scope (tout reste dans `packages/dcm-databricks-pipeline` ; `specs.py`/`models.py` touchés additivement, voir Out of scope)
- [x] Diff stays reviewable (prefer fewer changed files / one concern)
- [x] Sub-spec checkboxes reviewed
- [x] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

- Réutilise `pipelines.common.readers` (`read_native_source`, `read_azure_batches`) et
  `pipelines.common.azure_auth`/`AzureConnectionConfig` tels quels — pas de nouveau
  mécanisme de lecture.
- `PurgeAuditRecord` (schéma complet) : voir [data-model.md](../data-model.md).
- Seuils par défaut modifiables sans changement de code (`purge_specs.py`), cf.
  [research.md](../research.md) R3 pour la justification des valeurs 1000 / 20%.

## Implementation report (subagent dp-data-databricks-engineer)

- Gates ré-exécutés indépendamment par l'agent principal (ruff, mypy -p pipelines.common, pytest scoped) : tous verts (42 passed).
- 1 erreur mypy pré-existante hors périmètre dans `pipelines/system_tables/entrypoint.py:143` (fichier non touché par T001, confirmée pré-existante via `git stash` par le subagent) — non corrigée, hors scope.
- 2 déviations documentées par le subagent, dans le même package :
  1. `databricks.yml` : ajout `pause_status: PAUSED` pour `dcm_curated_purge` sur les targets `dev_local`/`dev` (cohérence avec les 4 autres jobs, évite qu'un job hebdomadaire de DELETE tourne UNPAUSED par défaut en non-prod).
  2. `writers.py` : ajout `non_cloud_merge_keys` — `cloud_provider` n'existe pas dans une lecture source brute (ajouté seulement à l'enveloppe côté curated), donc exclu de la condition de jointure côté source, filtré explicitement côté cible.
- Garde-fou "seuil le plus restrictif" implémenté comme `effective_limit = min(threshold_absolute, rows_in_curated_before * threshold_percentage)`.
- Garde-fou supplémentaire (non demandé explicitement, choix conservateur) : si la lecture Azure est activée mais ne retourne aucun lot, le garde-fou est forcé à `True` (aucune suppression) plutôt que calculé normalement — évite qu'un échec de lecture transitoire ne vide un cloud entier.
- `databricks bundle validate --strict -t dev` : "Validation OK!".
- Artefacts d'installation `apm`/`databricks aitools` détectés en untracked sous `packages/dcm-databricks-pipeline/.agents/`, `.github/agents/`, `.github/hooks/` (installés par erreur dans ce sous-dossier au lieu de la racine repo) — à nettoyer/gitignorer avant commit, hors scope de ce sub-spec.

## Post-review refinement (garde-fou d'éligibilité à la purge)

Suite à une revue de conception après le checkpoint initial : le garde-fou "table incrémentale jamais purgeable" reposait sur une inférence (`watermark_column is not None ⇒ jamais purgeable`) qui n'est qu'un proxy imparfait — rien n'empêche en théorie une table incrémentale de type 1 (upsert sur clé métier seule, sans composant version). Remplacé par un flag explicite :

- `pipelines/common/models.py::IngestionSpec` : nouveau champ `purge_eligible: bool = False`.
- `pipelines/system_tables/specs.py` : `purge_eligible=True` posé explicitement sur les 4 specs full-load (`UC_TABLES_SPEC`, `UC_TABLE_TAGS_SPEC`, `NODE_TYPES_SPEC`, `BILLING_LIST_PRICES_SPEC`), juste à côté du commentaire qui explique déjà pourquoi (miroir d'état courant vs log/SCD) — plus de duplication de la décision dans un second fichier.
- `pipelines/system_tables/purge_specs.py` : `PURGE_ENABLED_KEYS` devient **dérivé** de `SPECS` (filtré sur `purge_eligible`) au lieu d'une liste manuelle.
- Tests : nouveau `tests/common/test_models.py` ; `tests/system_tables/test_purge_specs.py` simplifié.

**Correction ultérieure (2ᵉ passe de revue)** : la première version de ce refinement ajoutait un `IngestionSpec.__post_init__` qui levait `ValueError` si `purge_eligible=True` avec `watermark_column is not None` — recréant exactement l'heuristique imparfaite que ce refinement visait à éliminer (et contredisant l'exemple `ACTIVE_USERS_SPEC` discuté en conception : une table incrémentale de type 1 doit pouvoir être `purge_eligible=True`). Vérifié que `pipelines.common.purge._read_full_source` ignore déjà `watermark_column` (relit toujours la source intégralement) : les deux champs sont fonctionnellement orthogonaux. `__post_init__` **retiré** ; `purge_eligible` reste une décision humaine pure, non vérifiable automatiquement, documentée par le commentaire à côté de chaque `purge_eligible=True` dans `specs.py`. Test `test_purge_eligible_true_with_watermark_raises` remplacé par `test_purge_eligible_and_watermark_column_are_orthogonal`.

Gates re-vérifiés après les deux passes : ruff ✅, mypy ✅ (même finding pré-existant hors périmètre dans `entrypoint.py`), pytest 315/315.
