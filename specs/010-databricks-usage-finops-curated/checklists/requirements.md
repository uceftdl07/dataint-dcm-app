# Requirements Quality Checklist — 010-databricks-usage-finops-curated

- [x] Work type, domaines, packages définis (intake.json)
- [x] Ticket plan explicite (2 Stories DataEng : usage + finops)
- [x] Domaine hors ticket documenté (Backend/Frontend hors Epic)
- [x] FR numérotés et testables (FR-001 → FR-013)
- [x] Success Criteria mesurables (SC-001 → SC-006)
- [x] Médaillon respecté — curated fidèle source (FR-006, SC-003)
- [x] Naming `layer_source_domain_metric` (FR-005)
- [x] Cible `it.ba_data_connect_monitoring__d` (FR-004)
- [x] Accès source = Workflow + SP (pas Delta Sharing) (FR-003)
- [x] Multi-cloud Azure+AWS via `cloud_provider` (sans LZ) (FR-008)
- [x] Idempotence + traçabilité (FR-009, FR-010)
- [x] Pas de données fictives (FR-011)
- [x] Accès SP Azure accordé — résolu (A1)
- [x] Corrélation multi-cloud sans table mapping LZ — résolu (A2)
- [x] Workspaces cibles définis (AWS dev/prod, Azure dev+prod) (A6)
- [x] Valorisation coût `usage × list_prices` en curated — résolu (A3)

**Markers `[NEEDS CLARIFICATION]` = 0. Spec prête.**
