# T005 — Frontend Lakeflow/Jobs NULL-safe + bandeau fraîcheur

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/013-frontend-null-safe-freshness
**Jira**: [DCINT-240](https://tdf.atlassian.net/browse/DCINT-240)
**Depends on**: T004
**Work type**: technique

## Description

Rendre la page **Lakeflow/Jobs** (N1/N2/N3) NULL-safe : colonne « Attente » (queue | lag) **masquée par défaut** (clarif. Q3), tooltip cron du Trigger retiré, durées/attente NULL affichées « n/d » (jamais 0), fallback `workspace_id`/`creator_id` quand le nom est absent, et bandeau de fraîcheur « données à ~X h » calculé depuis le champ `as_of` de l'API (clarif. Q5). Aucune route front retirée (`app-routes.ts` inchangé).

## Files to create/modify

- UPDATE packages/dcm-frontend — page Lakeflow/Jobs (N1/N2/N3) : colonnes NULL-safe, « Attente » masquée, tooltip cron supprimé, drill N3 sans ventilation queue/exec, `error_message` = code + message court, bandeau `as_of`
- UPDATE packages/dcm-frontend — hook/data-layer consommant `as_of` (TanStack Query) si nécessaire
- UPDATE packages/dcm-frontend — *.test.tsx (Vitest) : fixtures NULL, rendu « n/d », bandeau fraîcheur, colonne « Attente » absente

## Acceptance Criteria

- [ ] Colonne « Attente » (queue | lag) **masquée par défaut** (retirée du jeu visible).
- [ ] Durées/attente `null` → « n/d » / tiret, **jamais `0`** (P9/P16).
- [ ] Tooltip cron du Trigger supprimé ; `trigger_type` conservé.
- [ ] Colonnes Workspace / Propriétaire : fallback `workspace_id` / `creator_id` si nom absent.
- [ ] Drill N3 : ventilation durée (queue/exec) retirée ; total `duration_seconds` affiché ; `error_message` libellé « code de terminaison ».
- [ ] Bandeau « données à ~X h » dérivé de `as_of` (âge = `now - as_of`), pas un texte statique.
- [ ] Lien `run_page_url` reconstruit fonctionne.
- [ ] `app-routes.ts` inchangé ; lint + Vitest verts.

## Tests

- `npm run lint && npm run test` (dans `packages/dcm-frontend`)

## Out of scope

- Backend/API (T004).
- Pipeline (T001-T003).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Vitest + lint pass (fixtures NULL, rendu « n/d », bandeau `as_of`)
- [ ] No files outside `packages/dcm-frontend`
- [ ] Diff reviewable
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name

## Notes

- Dépend de `as_of` livré par T004.
- Réf. : [impact_back_front.md §2](../../../docs/spike/migration_from_collector_to_sys_table/impact_back_front.md), [contracts/api-freshness-contract.md §5](../contracts/api-freshness-contract.md).
