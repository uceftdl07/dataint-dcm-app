# Requirements Quality Checklist — 024-job-dlt-cluster-split

Validation de la spec avant `plan`. Cocher au fur et à mesure.

## Complétude

- [x] Work type, priorité, domaines et Ticket Plan renseignés
- [x] `## Prerequisites` présente et non-`TODO` (bloquant `before_plan`)
- [x] Une User Story par domaine avec ticket (frontend, backend, dataeng)
- [x] Work Breakdown : une ligne par ticket (T001–T003)
- [x] Out of scope explicite (efficience/reliability par famille, serverless, DevOps/QA)

## Testabilité

- [x] Chaque FR est vérifiable (table / endpoint / vue nommés)
- [x] SC mesurables sur données réelles (SC-001 count=0, SC-002 unicité, SC-003 égalité de sommes)
- [x] Independent Test défini par story

## Cohérence

- [x] Anti-double-comptage rollup DLT ↔ cluster_cost_daily explicité (FR-002, SC-003)
- [x] Ordre de livraison inter-domaines posé (DataEng → Backend → Frontend)
- [x] Grain DLT clarifié (`dlt_pipeline_id`, pas `dlt_update_id`) — Assumptions

## Clarifications

- [x] `[NEEDS CLARIFICATION]` : 0 en attente (max 3 autorisés)
- [x] 4 décisions de design verrouillées — section Clarifications (session 2026-09-09) :
  périmètre front 3 onglets, gouvernance éphémère abandonnée, maintenance DLT incluse,
  forecast PIPELINE coût/DBU only
