# Tasks: Inactive Cluster Widget on Dashboard

**Feature**: 009-widget-inactive-cluster  
**Spec**: [spec.md](spec.md)  
**Intake**: [intake.json](intake.json)  
**Domain scope**: Frontend only  
**Dispatch mode**: one_per_domain (1 Story Jira, 1 branch)  
**Branch**: `frontend/009-inactive-cluster-widget`

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (no dependency on incomplete tasks)
- **[Story]**: User story this task belongs to (US1, US2, US3)
- Each task links to its sub-spec in `stories/`

---

## Phase 1 — Frontend: Inactive Cluster Widget

**Domain**: Frontend  
**Package**: `packages/dcm-frontend`  
**Story goal**: Show count of terminated compute clusters on Dashboard with warning tone and drill-down navigation.  
**Independent test**: Navigate to Dashboard → verify "Inactive clusters" MetricCard is visible with correct count, tone, and click navigation.

- [x] T001 [P] [US1] Frontend inactive cluster widget on Dashboard → [stories/T001-frontend-inactive-cluster-widget.md](stories/T001-frontend-inactive-cluster-widget.md)

---

## Dependencies

```
T001 — no dependencies (standalone frontend change)
```

## Parallel execution

T001 is the only task. No parallelism needed.

## Implementation strategy

- MVP = T001 only (US1 + US2 + US3 all covered in T001 sub-spec checklist)
- All user stories are folded into a single MetricCard addition — minimal blast radius

## Task count summary

| Domain   | Tasks |
|----------|-------|
| Frontend | 1     |
| **Total**| **1** |

Stories Jira prévues (intake): **1**  
Sub-specs created: `stories/T001-frontend-inactive-cluster-widget.md`
