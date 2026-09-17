# Tasks: Remplacer `dim_landing_zone` par une vue union

**Input**: Design documents from `/specs/021-dim-landing-zone-view/` (plan.md, spec.md, research.md, data-model.md, quickstart.md)

**Tests**: Pytest requis (P1 constitution) — builder SQL pur unit-testé, + mise à jour des tests DLT existants.

**Organization**: DCM dispatch mode = **single_domain (DataEng)**, conforme à `intake.json.ticket_plan` (1 Story Jira = 1 task = 1 branche = 1 sub-spec). La tâche unique correspond 1:1 à la User Story de [spec.md](./spec.md).

## Format: `[ID] [P?] DataEng Description → sub-spec`

- **[P]**: parallélisable — sans objet (une seule tâche).
- Tâche **DataEng**, package `packages/dcm-databricks-pipeline`.

## Tasks

- [x] T001 DataEng Rename collector + vue union `dim_landing_zone` + drop FK gold → [stories/T001-dim-landing-zone-view.md](stories/T001-dim-landing-zone-view.md) · [DCINT-302](https://tdf.atlassian.net/browse/DCINT-302)

## Dependencies & Execution Order

- **T001** — pas de dépendance interne. Dépend d'objets UC **déjà produits** par d'autres jobs (hors scope) : `dim_dbx_workspace` (feature 020), `dim_reference_landing_zone_business_application` (job `reference_lz`), pipeline gold DLT (produit `dim_landing_zone_collector` après rename).

## Implementation Strategy

Tâche unique, cohésive, un seul package, une seule PR vers `develop`. Trois changements groupés (rename table DLT + suppression FK + nouveau module vue) car indissociables : la vue ne peut prendre le nom `dim_landing_zone` qu'une fois la table DLT renommée et les FK retirées.

**Ordre interne d'implémentation** (dans le même ticket) :
1. Renommer la table DLT + rediriger les 3 `dlt.read` internes + supprimer les 7 FK dans `dlt_03_gold_layer.py`.
2. Créer le module `pipelines/gold_landing_zone/` (builder SQL pur + entrypoint wheel).
3. Câbler le job DAB + console script + overrides pause dev.
4. Tests (builder SQL + mise à jour tests DLT).
5. Validation dev (`quickstart.md`).

**STOP et VALIDER** après T001 : exécuter `quickstart.md`, confirmer les 6 critères d'acceptation de [spec.md](./spec.md).
