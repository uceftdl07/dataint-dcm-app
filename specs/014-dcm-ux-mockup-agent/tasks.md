# Tasks: DCM UX Mockup Agent

**Input**: Design documents from `specs/014-dcm-ux-mockup-agent/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Dispatch**: one task for ticket domain `misc`; all implementation details are folded into T001 sub-tasks.

## Phase 1: Setup and Foundational Work

**Purpose**: Establish the repository-local agent bundle and its offline validation boundary.

No separate setup task is created: DCM dispatch mode is `one_per_domain` and this feature has one ticket domain.

## Phase 2: Misc / UX Tooling — T001

**Goal**: Create a portable DCM UX mockup agent that validates inputs, challenges KPI/page proposals with the PO, and generates approved HTML/spec artifacts only after explicit final confirmation.

**Independent Test**: Run `spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh`; it must validate agent structure, frontmatter, required safety/generation markers, expected reference files, and exit non-zero for malformed or incomplete bundles. Manual scenarios in `quickstart.md` cover missing Gold reference, ambiguous spike selection, PO iteration, final gate, and visual contract.

- [x] T001 [MISC] Correct agent contract for Gold truth, literal design system, tooltips, drawers, functional filters, enriched specs, and exact output naming in `spec-kit-dcm-workflow/agents/dcm-ux-agent/`

## Dependencies & Execution Order

- T001 has no implementation dependency and is the only ticket-domain task.
- `reference/gold-tables-confirmed.md` is a runtime prerequisite owned by the PO/data team; its absence blocks KPI analysis and artifact generation but does not block creating the agent bundle.
- Final HTML generation occurs only after explicit PO approval during agent execution.

## Parallel Opportunities

- No parallel task split: T001 owns one focused bundle and must keep its files internally consistent.
- Within T001, static reference documents may be drafted in parallel with README content, but the `.agent.md` and smoke test must be validated together.

## Implementation Strategy

### MVP

1. Implement T001 bundle structure and portable `.agent.md` workflow.
2. Add fail-closed Gold-reference rule and explicit PO final gate.
3. Add offline smoke validation.
4. Run smoke test and manual scenarios from `quickstart.md`.

### Incremental Delivery

- First deliver static agent instructions and references.
- Then validate smoke checks and refine wording against the acceptance scenarios.
- Do not add runtime integrations, LLM evaluation, cloud access, or application frontend changes in this task.
