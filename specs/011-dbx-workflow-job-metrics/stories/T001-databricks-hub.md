# T001 — Databricks hub, nav & workspaces

**Domain**: Fullstack  
**Packages**: `packages/dcm-frontend`, `packages/dcm-backend`  
**Branch**: `feature/DCINT-211-databricks-hub`  
**Jira**: [DCINT-211](https://tdf.atlassian.net/browse/DCINT-211)  
**Parent**: [DCINT-173](https://tdf.atlassian.net/browse/DCINT-173)  
**Depends on**: none  
**Work type**: feature  

## Description

Socle Databricks (départ à zéro) :

1. **Backend workspaces** — endpoint `/api/v1/databricks/workspaces` correct (noms ARM, soft-fail, pas de colonne inexistante).
2. **Navigation** — Overview au-dessus de Lakeflow ; groupes **Lakeflow** / **Compute** dépliables ; labels Title Case ; tabs enfants pour montrer l’appartenance.

**Aucune DEMO/maquette.**

## Backend workspaces (doit figurer dans cette Sub-task)

- Ne pas SELECT `workspace_name` sur `curated_compute_metrics`
- Sources de nom : gold/curated workflow si dispo ; sinon tags (`dcm_workspace_name`, `Project` like `dbw-%`)
- Normaliser `adb-<id>` / `<id>`
- Soft-fail tables absentes/stale
- Payload : `workspace_id`, `display_name`, `source_lz_id`, `cluster_count`
- Collector (optionnel même PR ou follow-up documenté) : stamp `dcm_workspace_name` dans tags

## Navigation (doit figurer dans cette Sub-task)

Sidebar sous Databricks :

```
Overview                    → /databricks/overview
▸ Lakeflow (collapsible)
    Workflows               → /databricks/workflows (alias jobs OK)
    Pipelines               → /databricks/pipelines
▸ Compute (collapsible)
    Cluster                 → /databricks/cluster
    SQL Warehouse           → /databricks/sql-warehouse
```

- **Pas** de page `/Lakeflow/Overview` — Overview = Databricks Overview uniquement
- Labels : `Lakeflow`, `Compute` — **pas** `LAKEFLOW` / `COMPUTE`
- Sur pages enfants : tab / secondary nav indiquant le parent (Lakeflow ou Compute)

## Files (indicatif)

- `packages/dcm-backend/app/api/routes/databricks.py`
- `packages/dcm-frontend/src/config/navigation.ts`
- `packages/dcm-frontend/src/components/Sidebar.tsx` (collapse groups)
- Header workspace filter / `workspace-label`
- Secondary nav / tabs enfants (composant à définir)

## Acceptance Criteria

- [ ] `/workspaces` retourne des `display_name` ARM quand possible ; pas de 500 si gold absente
- [ ] Header affiche le nom, pas l’id nu si nom dispo
- [ ] Overview est **au-dessus** de Lakeflow dans la sidebar
- [ ] Lakeflow et Compute sont dépliables ; enfants visibles seulement si déplié
- [ ] Labels Title Case (`Lakeflow`, `Compute`)
- [ ] Sur Pipeline / Workflows (et Compute enfants) : tab/indicateur « dans Lakeflow / Compute »
- [ ] Pas de DEMO
- [ ] PR → `develop` liée DCINT-211 (cette sub-spec + spec parent)

## Tests (implémentation ultérieure)

```bash
cd packages/dcm-backend && python -m pytest tests/test_databricks_workspaces.py -q
cd packages/dcm-frontend && npm run test -- --run Sidebar Header
```
