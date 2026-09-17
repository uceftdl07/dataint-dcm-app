# Requirements Checklist — 021-dim-landing-zone-view

Validation spec-kit standard. Cocher avant `plan`.

- [x] Work type et priorité définis (technique / P2)
- [x] Domain Scope renseigné (dataeng seul, ticket dataeng)
- [x] Contexte technique : objectif + approche décrits
- [x] Dependency Analysis : sources de la vue et FK identifiées avec preuves
- [x] Prerequisites non vide (bloque `plan` sinon)
- [x] Impact / breaking changes recensés
- [x] Rollback décrit
- [x] Colonnes exactes des tables sources vérifiées (BA: `subscription_or_account_id`/`business_application_id`/`business_application_name` confirmées ; BA multi-cloud AWS+Azure)
- [x] Consommateurs de `dim_landing_zone` recensés (backend `governance.py`, `lz_scope.py`, `access_requests.py`, `projects.py`, `admin_lz.py` — colonnes héritées préservées par clarif C2)
- [x] Ambiguïtés levées via `## Clarifications` (C1–C4)

Marqueurs `[NEEDS CLARIFICATION]` : 0.
