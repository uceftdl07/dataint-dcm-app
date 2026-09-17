<!--
Template de spec DCM, unique pour les 5 work types.

Le socle (en-tête → Work Breakdown) se remplit toujours. Les blocs marqués
`[work_type: …]` ne concernent qu'une partie des work types : garder ceux de ton
work type, **supprimer les autres, marqueur compris**. Une section laissée avec
son texte d'exemple vaut section absente pour un relecteur.

  feature   → Contexte · Users stories · Requirements · Success criteria
  technique → Contexte · Impact · Rollback
  dette     → Contexte · Périmètre borné · Validation Tech Lead
  hotfix    → Contexte · Rollback · Cherry-pick   (max 3 tasks)
  fixture   → Contexte · Périmètre borné · Patterns existants

`## Prerequisites` est la seule section dont l'absence bloque : le hook
`before_plan` (dcm-precheck.sh --gate plan) refuse une spec sans elle, ou dont le
contenu est resté `TODO`.
-->

# {feature | technique | dette | hotfix | fixture} : {TITRE}

**Feature Branch**: `{###-feature-name}` — branches filles `{domain}/{spec_num}-{slug}`
**Work Type**: {work_type}
**Priority**: {P0 | P1 | P2 | P3}
**Created**: {DATE}

**Input**: {description utilisateur, telle que donnée}

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅/❌ | ✅/❌ | packages/dcm-frontend ou — |
| Backend | ✅/❌ | ✅/❌ | packages/dcm-backend ou — |
| DataEng | ✅/❌ | ✅/❌ | packages/… ou — |
| DevOps | ✅/❌ | ✅/❌ | — |
| QA | ✅/❌ | ✅/❌ | — |

## Ticket Plan

| Stories Jira | {expected_story_count} |
|---|---|
| Mode | {single_domain \| one_per_domain \| custom} |
| Domaines avec ticket | {ticket_domains} |

## Contexte

**[work_type: feature]** Le besoin métier, et ce qui n'est pas encore possible aujourd'hui.
**[work_type: technique]** Le contexte technique, l'objectif (ce qui change, sans « As a user ») et l'approche retenue.
**[work_type: dette]** La dette : où, quoi, depuis quand · le risque si on ne la rembourse pas (incidents, vélocité, sécurité) · l'état cible.
**[work_type: hotfix]** Le symptôme observé en production · la cause racine (connue ou suspectée) · le périmètre minimal du correctif.
**[work_type: fixture]** Le manque de données de test / fixtures à combler.

## Dependency Analysis

Constats de la vérification code (Q6 de l'intake) et décision retenue — un besoin
identifié ici ne devient un ticket que s'il figure dans le Ticket Plan.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| {besoin} | backend | `path/to/file.py` — pas de filtre | `frontend_only_with_mock` |

## Prerequisites

- **Small branches / small PRs** : découper pour que chaque branche fille touche un
  ensemble **restreint** de fichiers (un package, une préoccupation) — moins de fichiers
  changés par PR, revue humaine plus simple.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Dépendances bloquantes de Dependency Analysis résolues, ou reportées avec une stratégie
  de mock explicite.
- **[work_type: feature, technique]** `[NEEDS CLARIFICATION]` levés (recommandé avant l'étape `plan` de spec-kit).
- **[work_type: dette]** Validation Tech Lead si > 5 tasks ou si `dcm-commons` est touché.
- **[work_type: hotfix]** Symptôme reproduit, et chemin de rollback connu **avant** le merge.
- **[work_type: fixture]** Patterns de fixtures existants identifiés (commons / frontend).

## User stories

**[work_type: feature]** Une story **uniquement** pour les domaines de `ticket_domains`,
jamais pour un domaine in-scope sans ticket.

### User Story 1 — {titre} (Priority: P1)

{parcours utilisateur}

**Why this priority** : {valeur}
**Independent Test** : {comment la tester seule}

**Acceptance Scenarios**

1. **Given** …, **When** …, **Then** …

## Acceptance Criteria

1. **Given** …, **When** …, **Then** …
2. Gates du package verts (lint → types → tests → build).

## Impact

**[work_type: technique]** Performance, compatibilité, breaking changes (aucun / liste).

## Périmètre borné

**[work_type: dette, fixture]**

**In scope** — {le correctif limité, les fichiers de fixture}
**Out of scope** — pas de feature creep : {ce qu'on ne touche pas}

## Patterns existants

**[work_type: fixture]** Suivre les patterns en place plutôt qu'en inventer un :
`packages/dcm-commons/fixtures/generate_fixtures.py`,
`packages/dcm-frontend/src/test/fixtures/dashboard.ts`.

## Out of scope (cet Epic)

Domaines in-scope **sans** ticket, avec la raison : ils sortent de la spec, des tasks et
du dispatch. Ex. « Backend : API de filtrage reportée, filtre côté UI pour cet Epic ».

## Work Breakdown (preview)

Une ligne par domaine **avec** ticket ; les autres en `❌ hors Epic`.

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | Frontend | {une ligne} | ✅ |
| — | Backend | {besoin reporté} | ❌ hors Epic |

**[work_type: hotfix]** Max **3** tasks — convention rappelée à l'agent, aucun script ne la vérifie.

## Requirements & Success Criteria

**[work_type: feature]**

- **FR-001** : {exigence fonctionnelle}
- **SC-001** : {critère de succès mesurable}

## Rollback

**[work_type: technique, hotfix]** Comment revenir en arrière si le changement échoue.
Pour un hotfix, à connaître avant le merge.

## Cherry-pick

**[work_type: hotfix]** Après le merge vers `main`, cherry-pick vers la branche
d'intégration ouverte si nécessaire.

## Validation Tech Lead

**[work_type: dette]** Requise si > 5 tasks ou si `dcm-commons` est touché.

## Assumptions

- {hypothèse tenue pour vraie, à démentir en revue si elle est fausse}
