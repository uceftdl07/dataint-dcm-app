# Implementation Plan: Tracking d'usage — Usage des tables UC & Gouvernance

**Branch**: `024-usage-tracking-governance` | **Date**: 2026-09-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/024-usage-tracking-governance/spec.md`

## Summary

Exposer les 8 tables gold `gold_dbx_usage_*` (livrées par la feature 019) via un nouveau
routeur FastAPI `/api/v1/uc-usage`, puis construire 2 pages React qui les consomment :
**Usage des tables UC** (vue d'ensemble + 3 vues) et **Gouvernance & Recommandations**
(2 onglets). Une Story DataEng préalable, strictement bornée, ajoute un histogramme de
latence en gold pour rendre le P95 calculable sur une période arbitraire.

Approche technique : lecture directe du SQL Warehouse Databricks via le pool existant,
SQL isolé dans une couche `app/api/services/`, pagination serveur `page`/`page_size`, et
réutilisation des composants du domaine compute côté frontend. Trois tasks
séquentielles — T001 DataEng → T002 Backend → T003 Frontend — portées par **une seule
Story Jira et une seule branche** `dataeng/024-usage-tracking-governance` (écart assumé à
la convention 1-domaine-1-ticket, décidé pour la vélocité ; cf. Complexity Tracking).

Trois arbitrages structurants, rendus après vérification dans le code et documentés dans
[research.md](research.md) :

- **D3** — aucune des 8 tables gold ne porte `workspace_id` ni `source_lz_id`, et une
  table Unity Catalog n'appartient pas à un workspace. `workspace_id` n'est **pas**
  ajouté : les 2 pages sont réservées au scope non restreint.
- **D4** — aucun calcul par défaut : le bandeau de période global reste affiché, mais
  aucune requête datée ne part avant un clic sur **Appliquer**.
- **D10** — le P95 de période est reconstitué par interpolation sur un histogramme de
  latence stocké en gold, plutôt que par un `MAX` du pire jour ou un rescan du curated.

## Technical Context

**Language/Version**: Python 3.12 (pipeline PySpark + backend), TypeScript 5 / React 18 (frontend)

**Primary Dependencies**: PySpark (Databricks, DABs) ; FastAPI, `databricks-sql-connector` (via `DatabricksWarehousePool`), Pydantic ; TanStack Query, React Router, recharts, Tailwind

**Storage**: Databricks SQL Warehouse (Unity Catalog). Lecture seule côté API. La Story DataEng ajoute une colonne à une table gold existante — aucune table créée, pas de Lakebase.

**Testing**: pytest (pipeline et backend ; fixture `mock_db` de `tests/conftest.py` côté API) ; Vitest + Testing Library (`renderWithProviders`, `vi.mock` du client API)

**Target Platform**: API sur ECS Fargate ; SPA React servie par S3 + CloudFront

**Project Type**: Web application — backend API + frontend SPA, dans un monorepo de packages

**Performance Goals**: pagination serveur systématique sur les listes (défaut 25) ; agrégations poussées dans le warehouse, jamais côté client

**Constraints**: `NULL` jamais converti en `0` de bout en bout (SC-005) ; aucun paramètre de scope accepté (les colonnes n'existent pas) ; routeur réservé au scope non restreint ; aucune requête datée au chargement des pages

**Scale/Scope**: périmètre = toutes les tables Unity Catalog visibles (techniques, curated, staging incluses — aucun filtre `is_data_product`), d'où un volume de registre potentiellement élevé qui motive la pagination

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Référence : [spec-kit-dcm-workflow/memory/constitution.md](../../spec-kit-dcm-workflow/memory/constitution.md) v1.4.0

| Principe | Statut | Justification |
|---|---|---|
| **P1** Test-First (NON-NEG.) | ✅ | pytest par endpoint et Vitest par page, exigés avant merge ; gates listés dans [quickstart.md](quickstart.md) |
| **P2** Simplicité / YAGNI | ✅ | aucun endpoint hors des FR ; les points reportés (Genie, acquittement, persistance de filtres) ne sont pas construits |
| **P3** Code auto-documenté | ✅ | docstrings limitées aux `summary`/`description` FastAPI et aux `Field(description=…)` — surface publique OpenAPI, explicitement autorisée |
| **P4** Fail fast, fail loud | ✅ | table gold absente ⇒ 503 avec code explicite (D6), jamais un 200 vide ni un `except: pass` |
| **P5** Architecture & modularité | ✅ | routes minces / services porteurs du SQL, aucun appel cross-LZ, aucun nouveau canal de données |
| **P6** Idempotence | ✅ | Story DataEng : le MERGE des compteurs de buckets doit être rejouable sans dérive (invariant testé). API en lecture seule |
| **P7** Sécurité & moindre privilège | ⚠️ **arbitrage** | voir Complexity Tracking — les tables sont non scopables, le routeur est donc réservé au scope non restreint (précédent `unity_catalog.py`) |
| **P8** Aucun secret en dur (NON-NEG.) | ✅ | connexion warehouse via la configuration existante, aucun nouveau credential |
| **P9** Aucune donnée fictive en prod (NON-NEG.) | ✅ | fixtures confinées aux tests (D9) ; aucun chemin de rendu ne lit de mock |
| **P10** Observabilité | ✅ | structlog déjà en place sur les routes ; le 503 porte la table concernée |
| **P11**–**P13** Medallion | ✅ | l'histogramme de latence est calculé **en Gold** (P12), pas par le backend sur du curated ; nommage `gold_*` conservé (P11) ; raw non touché (P13) |
| **P14** Versionnement de schéma | N/A | pas de `MetricPayload` ni de modèle de domaine partagé modifié |
| **P15** Stabilité du contrat API | ✅ | nouveau préfixe `/api/v1/uc-usage`, aucun endpoint existant modifié ni cassé |
| **P16** Qualité frontend | ✅ | client API central, hooks TanStack Query, route dans `app-routes.ts`, Vitest réseau mocké, libellés lisibles (`consumer_name`, `table_full_name`), aucun `any` |

**Verdict Phase 0** : passe, avec un arbitrage documenté sur P7.
**Re-check post-Phase 1** : passe — la conception (contrats, data-model) n'introduit
aucune violation supplémentaire ; l'arbitrage P7 reste le seul point, inchangé.

## Project Structure

### Documentation (this feature)

```text
specs/024-usage-tracking-governance/
├── plan.md              # Ce fichier
├── spec.md
├── research.md          # Phase 0 — D1 à D9
├── data-model.md        # Phase 1 — entités exposées + règles de validation
├── quickstart.md        # Phase 1 — guide de validation exécutable
├── contracts/
│   └── uc-usage-api.md  # Phase 1 — contrat des endpoints
├── checklists/
│   └── requirements.md
├── intake.json / domain-scope.json
└── tasks.md             # Phase 2 — produit par /speckit.dcm.tasks, PAS par ce plan
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/               # Task T001 (1re sur la branche)
└── pipelines/gold_dbx_usage/
    ├── specs.py                                # + bornes de buckets + commentaires de colonne
    └── table_query_performance_daily.py        # + compteurs par bucket de latence
# Portée stricte : aucune autre table gold touchée, grain et clés de merge inchangés

packages/dcm-backend/                          # Task T002 (2e sur la branche)
├── app/
│   ├── main.py                                # + include_router(uc_usage.router, prefix="/api/v1/uc-usage")
│   └── api/
│       ├── routes/
│       │   ├── __init__.py                    # + export uc_usage
│       │   └── uc_usage.py                    # routes minces, require_unrestricted_scope
│       └── services/
│           ├── uc_usage_common.py             # période, filtres, pagination, erreur table absente
│           ├── uc_usage_latency.py            # interpolation du P95 sur buckets additionnés
│           ├── uc_usage_tables.py             # /overview, /tables, /tables/{…}/top-consumers
│           ├── uc_usage_consumers.py          # /consumers
│           ├── uc_usage_finops.py             # /finops/kpis, /cost-by-table, /trends
│           └── uc_usage_governance.py         # /governance/*, /recommendations, /attention
└── tests/
    └── test_uc_usage_routes.py

packages/dcm-frontend/                         # Task T003 (3e sur la branche)
└── src/
    ├── api/dcmApiClient.ts                    # + fonctions GET du contrat
    ├── types/api.ts                           # + types miroir des réponses
    ├── app-routes.ts                          # + 2 routes
    ├── config/navigation.ts                   # + 2 entrées sous Databricks
    ├── config/role-permissions.ts             # + 2 mappings page:unity-catalog
    ├── hooks/
    │   ├── query-keys.ts                      # + ucUsageQueryKeys
    │   └── useUcUsageQueries.ts               # hooks TanStack Query, enabled sur appliedPeriod
    ├── lib/uc-usage/severity.ts               # normalisation de casse (FR-015)
    ├── components/domain/uc-usage/            # composants propres à ces 2 pages
    ├── pages/UsageTablesUc.tsx
    ├── pages/UsageGovernance.tsx
    └── pages/…test.tsx + test/fixtures/uc-usage.ts
```

**Structure Decision** : trois packages du monorepo, alignés sur le Domain Scope
(DataEng ✅, Backend ✅, Frontend ✅), portés par **une branche unique**
`dataeng/024-usage-tracking-governance`. La task DataEng reste étroite — une colonne
sur une table gold, puis une purge de lignes sur cinq (FR-024) — pour ne pas rouvrir le
chantier de la feature 019 : aucune table n'est renommée, re-grainée ni enrichie d'une
colonne pour la purge.
Puisque la PR ne peut plus être petite, la lisibilité de la revue repose sur deux leviers :
les **trois sub-specs**, qui racontent la livraison étape par étape (le squash-and-merge
efface les commits, voir Complexity Tracking), et un découpage fin en modules de service
côté backend et en composants dédiés côté frontend, pour qu'aucun fichier ne devienne
monolithique.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| **P7** — routes réservées au scope non restreint plutôt qu'un filtrage par lignes | Aucune des 8 tables gold ne projette `source_lz_id` ni `workspace_id` (vérifié : clés de merge de `gold_dbx_usage/specs.py`, `SELECT` final de `table_daily.py`). Le modèle RBAC ne connaît que `lz_id` et `workspace_id` (`lz_scope.py`), or une table UC appartient à `catalog.schema`, pas à un workspace. Aucune dimension de scope n'est exprimable : soit tout est exposé, soit `1 = 0`. Précédent identique dans `unity_catalog.py`, motivé en commentaire dans `role-permissions.ts`. | **Exposer sous `page:databricks` sans filtre** : ferait fuiter l'usage de tout le parc UC — viole P7 frontalement. **Ajouter `workspace_id` au grain gold** : arbitré et écarté — changement de grain, full refresh de 4 tables, et la page Gouvernance (métadonnées UC) resterait non scopable de toute façon. **Scope par catalogue** : axe sémantiquement correct, mais aucun mapping projet → catalogue n'existe — Epic distinct. |
| **Convention DCM** — 3 tasks sur 1 seule Story Jira et 1 seule branche, au lieu de 1 domaine = 1 Story = 1 branche = 1 PR | Décision d'équipe pour la vélocité : éviter deux cycles de merge intermédiaires et pouvoir tester la chaîne gold → API → UI d'un seul tenant. | **Trois branches séquentielles** (convention) : plus sûr pour la revue, mais impose d'attendre deux merges avant de voir la chaîne complète. Compensation retenue : commits séparés par task dans l'ordre T001 → T002 → T003, une seule task ouverte à la fois. **Risque assumé** : PR large, revue humaine plus lourde, et un rollback ne peut plus cibler un seul domaine. |

⚠️ *Mise à jour du 2026-09-17* — la compensation retenue ci-dessus, « commits séparés par
task », est **annulée par le mode de merge** : la branche est livrée en
**squash-and-merge**, donc aucun commit individuel ne survit et l'historique ne portera plus
le découpage par task. Ce sont les **trois sub-specs** qui portent désormais le record : ils
décrivent étape par étape ce qui a été livré, y compris les 8 étapes parties hors task, avec
le verdict de revue de chacune. Le risque assumé est inchangé (revue humaine plus lourde,
rollback impossible à cibler par domaine) — seule sa compensation change de support, du
`git log` vers `stories/`.

Un seul arbitrage **de conception** subsiste (P7) ; le second est un écart **de process**
assumé. Les deux points ouverts à la première itération du plan ont été tranchés et ne
sont plus des écarts :

- la période par défaut disparaît au profit d'un déclenchement explicite (D4) ;
- le P95 de période devient exact à la largeur de bucket près, calculé **en Gold**, donc
  conforme à P12 (D10).
