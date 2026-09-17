# Technical Specification: DCM UX Mockup Agent

**Feature Branch**: `feat/sdd_agent_ux`
**Work Type**: technique
**Priority**: P2
**Created**: 2026-08-20

## Domain Scope

| Domaine | In scope | Packages |
|---------|----------|----------|
| Misc / UX tooling | Yes | `spec-kit-dcm-workflow/agents/dcm-ux-agent` |
| Frontend application | No | — |
| Backend | No | — |
| DataEng | No | — |
| DevOps / CI | No | — |
| QA | No | — |

`misc` is used only because the workflow registry has no UX tooling domain. The agent itself is a reusable design and specification tool, not an application feature.

## Clarifications

### Session 2026-08-20

- Q: Quelle doit être la source canonique du design system utilisé par l’agent ? → A: Frontend existant (`packages/dcm-frontend/src/styles/tokens.css` et `src/components/ui`)
- Q: Quel format de distribution doit être planifié pour l’agent portable ? → A: Format `.agent.md` GitHub Copilot prioritaire, avec compatibilité Claude secondaire
- Q: Quelle stratégie de test veux-tu pour valider l’agent sans dépendance à un LLM ou au cloud ? → A: Smoke minimal : vérifier structure, frontmatter et fichiers attendus

## Context

DCM mockups have already been produced manually for Compute and Anomaly Detection & Alerting. The method requires reading spike results, checking confirmed Gold tables, challenging KPI proposals with the Product Owner, choosing a readable page structure, and producing validated HTML mockups with associated specifications.

The method must become repeatable without allowing unsupported KPIs, fictitious data, premature file generation, or ambiguous source selection.

## Objective

Create a reusable portable agent definition in `spec-kit-dcm-workflow/agents/dcm-ux-agent/` that guides Claude Code and GitHub Copilot through the complete DCM mockup workflow. The agent must challenge KPI and page-design decisions with the PO, iterate without an artificial iteration limit, and generate final deliverables only after explicit approval.

## Approach

The agent definition will:

1. Resolve spike inputs according to an explicit priority order and stop when the source is missing or ambiguous.
2. Read mapping, data model, feature description, and `reference/gold-tables-confirmed.md` before proposing KPIs.
3. Build an exhaustive inventory of mathematically calculable KPIs from confirmed Gold columns, separating calculable, non-calculable, retained, and non-selected items.
4. Require persona, objective, and business value for every proposed KPI, covering DataOps, Data Engineer, SysOps, and Data Product Owner as applicable.
5. Challenge redundancy, weak actionability, and overloaded single-page designs before presenting a proposal.
6. Iterate with the PO until explicit satisfaction, then require a second explicit final confirmation gate.
7. Generate one HTML mockup and one page specification per validated page, plus `gap-analysis.md` and `unused-gold-kpis.md`.
8. Apply the DCM mockup visual contract from the existing frontend tokens and UI components: OKLCH tokens, Inter typography, pill controls, rounded cards, colored KPI headers, uppercase small-caps table headers, and two-column application shell.

Validation scope is a minimal smoke check for agent structure, frontmatter, and expected files; the plan must verify how this satisfies DCM test requirements without introducing an LLM or cloud dependency.

The primary artifact will use the GitHub Copilot custom-agent `.agent.md` format. Its instruction body must remain readable and executable manually, with Claude Code compatibility documented as a secondary path. Platform-specific frontmatter or tool declarations must be isolated and optional.

## Prerequisites

- **Small branches / small PRs**: this Story is limited to the reusable agent definition and its supporting reference/instruction files under `spec-kit-dcm-workflow/agents/dcm-ux-agent/`.
- Spec intake + domain scope confirmed in `intake.json` and `domain-scope.json`.
- `reference/gold-tables-confirmed.md` exists and covers the requested feature domain before KPI proposal.
- The DCM mockup design-system reference is available in `packages/dcm-frontend/src/styles/tokens.css` and `packages/dcm-frontend/src/components/ui` before HTML generation.
- No production cloud data, secrets, or fictitious KPI values are introduced.
- The PO has an explicit confirmation path available for the final generation gate.

## Impact

- Performance: agent interaction time may vary with the number of Gold tables and PO iterations; no artificial iteration cap is introduced.
- Breaking changes: none to application runtime, APIs, databases, or existing frontend packages.
- Operational impact: adds a reusable repository-local agent asset and a consistent mockup artifact structure.
- Data integrity: unsupported or partially covered KPIs are blocked from mockups and reported for data-team validation.

## Functional Requirements

- **FR-001**: Agent MUST read spike mapping, data model, and feature description before proposing any KPI or page.
- **FR-002**: Agent MUST locate spike inputs by explicit path first, otherwise list available `spike/` directories and ask the PO to choose; it MUST never select an ambiguous directory automatically.
- **FR-003**: Agent MUST read `reference/gold-tables-confirmed.md` when present. If absent, it MAY use a feature data model only after explicit PO confirmation that the named file is authoritative for the current execution; otherwise it MUST stop the gap analysis.
- **FR-004**: Agent MUST produce an exhaustive inventory of KPIs mathematically calculable from confirmed Gold columns, not only the KPIs ultimately selected.
- **FR-005**: Agent MUST mark a KPI as non-calculable when required Gold data is absent or partial and MUST exclude it from mockups.
- **FR-006**: Every proposed KPI MUST include at least one persona, that persona's question or decision objective, and the business value provided.
- **FR-007**: Agent MUST challenge redundant, weakly actionable, or persona-less KPIs and record the reason for exclusion.
- **FR-008**: Agent MUST propose and justify one or more pages based on KPI volume, domain separation, readability, cognitive load, and persona needs.
- **FR-009**: Agent MUST support unlimited PO feedback iterations and must re-present the updated KPI and page proposal after each requested adjustment.
- **FR-010**: Agent MUST NOT generate HTML, page specs, `gap-analysis.md`, or `unused-gold-kpis.md` before explicit PO confirmation at the final validation gate.
- **FR-011**: Agent MUST avoid versioned-scope terminology in reasoning and generated deliverables; non-selected KPIs are simply non-selected.
- **FR-012**: For every validated page, agent MUST generate one interactive HTML mockup and one associated spec file with User Scenarios, Functional Requirements, Key Entities, API Endpoints, and checklist sections.
- **FR-013**: Agent MUST generate `gap-analysis.md` containing the complete calculable KPI inventory and selection status.
- **FR-014**: Agent MUST generate `unused-gold-kpis.md` containing every calculable but unused KPI, with the known non-selection reason or `non sélectionné à ce jour`.
- **FR-015**: Agent MUST name the output directory `maquette/ux-<resolved-name>/`, with mandatory `ux-` prefix; Compute uses `maquette/ux-compute-metrics-definition/`. Resolution order remains source spike directory name first, explicit feature name second, and PO-provided name last.
- **FR-016**: Generated mockups MUST follow the DCM mockup design-system contract and MUST not use fictitious cloud values as evidence.
- **FR-017**: Agent MUST list generated files and summarize unused Gold KPIs after generation.
- **FR-018**: Agent MUST be distributed primarily as a GitHub Copilot `.agent.md` custom agent, while remaining usable with Claude Code through documented secondary compatibility and a readable instruction body.
- **FR-019**: The feature MUST include a minimal smoke validation covering agent structure, frontmatter, and expected artifact files without requiring an LLM invocation or cloud access.

## Acceptance Criteria

1. **Given** a valid spike directory and a covered Gold-table reference, **when** the agent is invoked, **then** it reads all required inputs and presents a traceable KPI inventory before proposing mockups.
2. **Given** an absent or incomplete Gold-table reference, **when** the agent starts gap analysis, **then** it stops the affected analysis and requests the reference to be completed; no unsupported KPI is mocked.
3. **Given** a candidate KPI, **when** the agent proposes it, **then** persona, objective, value, Gold source, and calculability are explicit.
4. **Given** redundant or weakly actionable KPIs, **when** the proposal is prepared, **then** the agent challenges and records their exclusion reasons.
5. **Given** a multi-domain KPI set, **when** page structure is proposed, **then** the agent compares a single-page layout with a separated layout and justifies the selected structure.
6. **Given** PO feedback, **when** the PO requests changes, **then** the agent updates the proposal and repeats the review without a fixed iteration limit.
7. **Given** no explicit final PO confirmation, **when** the agent is asked to generate files, **then** it refuses generation and keeps the deliverable set absent.
8. **Given** explicit final PO confirmation, **when** generation starts, **then** each validated page receives HTML plus a matching page spec and the root receives gap-analysis and unused-gold-kpis reports.
9. **Given** final generation, **when** files are listed, **then** every mockup uses the DCM tokens and layout conventions and no versioned-scope wording appears in deliverables.
10. **Given** either supported agent environment, **when** the agent definition is loaded, **then** its workflow remains understandable and executable without relying on proprietary syntax.
11. **Given** the repository checkout, **when** the smoke validation runs, **then** it checks the agent structure, frontmatter, and expected files without calling an LLM or cloud service.

## Work Breakdown (preview)

| ID | Domain | Summary |
|----|--------|---------|
| T001 | Misc / UX tooling | Create portable DCM UX mockup agent definition, references, generation gate, and acceptance tests |

## Rollback

Remove the `spec-kit-dcm-workflow/agents/dcm-ux-agent/` directory and its associated documentation/tests. No runtime application rollback is required because this feature does not modify deployed services.
