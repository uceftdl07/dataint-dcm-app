# DCM Review Report

**Package**: `packages/dcm-frontend`
**Branch**: `frontend/025-page-databricks-serverless-en-5-blocs` (base: `develop`)
**Stack**: frontend
**Verdict**: **FAIL** (fail=3 warn=0 skip=0)

## Changed files

```
packages/dcm-frontend/src/api/dcmApiClient.ts
packages/dcm-frontend/src/app-routes.ts
packages/dcm-frontend/src/components/domain/compute/compute-cluster-drawer.tsx
packages/dcm-frontend/src/components/domain/compute/compute-cost-tabs.tsx
packages/dcm-frontend/src/components/domain/compute/compute-drawer-sections.tsx
packages/dcm-frontend/src/components/domain/compute/compute-job-drawer.tsx
packages/dcm-frontend/src/components/domain/compute/compute-pipeline-drawer.tsx
packages/dcm-frontend/src/config/navigation.ts
packages/dcm-frontend/src/config/role-permissions.ts
packages/dcm-frontend/src/hooks/query-keys.ts
packages/dcm-frontend/src/hooks/useComputeJobsQueries.ts
packages/dcm-frontend/src/hooks/useComputePipelinesQueries.ts
packages/dcm-frontend/src/lib/compute/recommendations.ts
packages/dcm-frontend/src/lib/databricks/routes.ts
packages/dcm-frontend/src/lib/navigation-access.test.ts
packages/dcm-frontend/src/pages/ComputeClusters.test.tsx
packages/dcm-frontend/src/pages/ComputeClusters.tsx
packages/dcm-frontend/src/pages/ComputeJobs.test.tsx
packages/dcm-frontend/src/pages/ComputeJobs.tsx
packages/dcm-frontend/src/pages/ComputePipelines.test.tsx
packages/dcm-frontend/src/pages/ComputePipelines.tsx
packages/dcm-frontend/src/pages/ComputeRecommendationsForecast.tsx
packages/dcm-frontend/src/test/fixtures/compute-jobs.ts
packages/dcm-frontend/src/test/fixtures/compute-pipelines.ts
packages/dcm-frontend/src/types/api.ts
```

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| eslint | FAIL |   53:9  warning  The 'dashboards' logical expression could make the dependencies of useMemo Hook (at line 66) change on  |
| typescript | FAIL | src/pages/DatabricksFocusPage.tsx(74,5): error TS6133: 'workspaces' is declared but its value is never read. src/pages/D |
| vitest | FAIL |  ❯ Databricks src/pages/Databricks.tsx:237:67   ❯ renderWithHooks node_modules/react-dom/cjs/react-dom.development.js:15 |

## Next

- Agent: cross-check diff vs `dcm-python` / `dcm-react` skills + sub-spec acceptance criteria
- If PASS: open PR to integration branch
- If FAIL: fix and re-run `/speckit.dcm.review`

---

## Agent skill review — T003 (2026-09-10)

Skills chargées : `dcm-react`, `dcm-testing`, `dcm-verify`. Mode : `--task T003` (pas
`--commit`) → **aucun stamp écrit**.

### Ce que les gates ci-dessus mesurent — et ne mesurent pas

`dcm-review.sh` diffe `origin/develop...HEAD`. Les 25 fichiers listés sont ceux des commits
**déjà présents** sur la branche parente `spike/serverless_cluster` (frontend de la spec 024,
backend de la 025) : **aucun fichier de T003 n'y figure**, son travail étant staged ou untracked
et non commité. Les 3 gates FAIL portent donc sur du code antérieur à T003.

La revue de skills ci-dessous porte, elle, sur l'arbre de travail réel : 7 fichiers staged
(commit 1 — les 3 composants de dataviz + leurs tests + la palette) et 15 fichiers modifiés ou
untracked (commit 2 — page, hook, drawer, nav, routes, types, fixtures, tests), soit 22 fichiers
du seul package `dcm-frontend`.

### Findings

```
specs/025-serverless-compute-page/review-report-T003.md:6: 🟡 risk: verdict FAIL non imputable à T003 — 61 problèmes eslint / 101 erreurs tsc / 4 tests rouges sont l'état de develop, à l'identique avec et sans les fichiers de T003 → traité par T004
packages/dcm-frontend: 🟡 risk: branche fille coupée sur spike/serverless_cluster, pas sur origin/develop — une PR vers develop embarquerait T001/T002 ; arbitrer la base avant de publier
packages/dcm-frontend/src/pages/ComputeServerless.tsx:1: 🟡 risk: 1 929 lignes pour la page, 6 292 lignes ajoutées et 2 supprimées sur 22 fichiers (1 099 staged, 760 modifiés, 4 433 untracked) — le sub-spec autorise la scission en 2 PR (composants / page), recommandée pour rester relisible
specs/025-serverless-compute-page/tasks.md:10: 🟡 risk: aucune Story Jira ne porte le nom de branche — le dispatch n'a jamais tourné sur cette spec, l'item « Before PR » correspondant n'est pas cochable en l'état
packages/dcm-frontend/src/hooks/query-keys.ts:401: 🟢 note: les 8 clés serverless héritent la normalisation de column_filter du scope partagé ; governance sans window_days et cost-trend sans window_days sont cohérents entre client API et clé — pas d'anti-pattern « clé sans dimension de filtre »
packages/dcm-frontend/src/pages/ComputeServerless.tsx:783: 🟢 note: label workspace résolu par useWorkspaceLabelResolver, id brut réservé au title — conforme à la règle d'affichage dcm-react
packages/dcm-frontend/src/components/domain/compute/compute-stacked-bar.tsx:138: 🟢 note: 2 styles inline, couleur pilotée par la donnée (pastilles de légende), aucune mise en page — conforme
packages/dcm-frontend/src/pages/ComputeServerless.test.tsx:1: 🟢 note: 46 tests neufs verts, mock de dcmApiClient (jamais fetch global), renderWithProviders ; 1 régression détectée et corrigée dans lib/navigation-access.test.ts
```

Aucun 🔴 blocker.

### Checklist de l'étape 3

| # | Point | Résultat |
|---|-------|----------|
| 1 | Secret / `.env` / credential dans le diff | ✅ aucun (`token`, `password`, `secret`, `apikey` : 0 occurrence dans les 10 fichiers neufs) |
| 2 | Anti-patterns `dcm-react` | ✅ aucun `any`, `@ts-ignore`, `eslint-disable`, `fetch()` direct, `console.*` |
| 3 | Critères d'acceptation couverts | ✅ 17 sur 19 par un test ; les 2 restants sont les gates (→ T004) et la vérification navigateur (SC-012, humaine) |
| 4 | Fichiers ⊆ périmètre de l'intake | ✅ tout sous `packages/dcm-frontend/`, hors artefacts de spec |
| 5 | Tests pour tout changement de comportement | ✅ 4 fichiers de test neufs, 46 tests |
| 6 | Small PR | 🟡 gros diff — scission en 2 PR recommandée |
| 7 | Story Jira porte un nom de branche | 🟡 aucune Story (dispatch jamais exécuté) |

### Verdict de la revue

**FAIL** — imposé par les 3 gates de package, **aucun blocker** dans le diff de T003. Le stamp
de commit n'a pas été écrit et ne peut pas l'être (`review.before_commit_require_pass: true`)
tant que T004 n'a pas ramené les gates à zéro.
