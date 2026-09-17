# Implementation Plan: DCM UX Mockup Agent

**Branch**: `feat/sdd_agent_ux` | **Date**: 2026-08-20 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from [spec.md](spec.md)

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Create one reusable GitHub Copilot custom agent under `spec-kit-dcm-workflow/agents/dcm-ux-agent/` for DCM HTML mockup discovery, KPI challenge, PO iteration, and gated artifact generation. Keep the instruction body plain Markdown so Claude Code can use it as a secondary manual/portable path. Validate the static agent bundle with an offline shell smoke test; fail closed when confirmed Gold-table reference is absent or incomplete.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Markdown agent instructions, POSIX shell smoke test

**Primary Dependencies**: Existing Copilot `.agent.md` convention; frontend design tokens/components as runtime references; no new runtime dependency

**Storage**: Repository files only; generated mockups under `maquette/ux-<resolved-name>/`; Compute destination is `maquette/ux-compute-metrics-definition/`

**Testing**: `spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh`; manual PO acceptance scenarios in [quickstart.md](quickstart.md)

**Target Platform**: GitHub Copilot custom agents primarily; Claude Code/manual Markdown workflow secondarily; POSIX shell for smoke test

**Project Type**: Repository-local agent/tooling bundle

**Performance Goals**: No fixed latency target; no artificial cap on PO iterations; smoke test completes quickly without network

**Constraints**: No LLM/cloud dependency for smoke test; no fictitious Gold data; no output generation before explicit PO approval; no duplicated design-token source

**Scale/Scope**: One agent definition, one README, two reference contracts, one smoke script; no application runtime changes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle / constraint | Status | Evidence / plan |
|---|---|---|
| P1 Test-first & code quality | PASS with scoped interpretation | Add offline smoke validation for static agent assets; manual behavior scenarios cover PO gates. No Python/React runtime code is introduced. |
| P2 Simplicity & explicitness | PASS | One primary agent file; no duplicated Claude agent or token copy. |
| P3 Self-documenting artifacts | PASS | README, contracts, and plain Markdown workflow explain public behavior. |
| P4 Fail fast, fail loud | PASS | Missing/ambiguous inputs and Gold coverage stop workflow and report blocker. |
| P5 Modularity | PASS | Agent, references, and smoke validation separated under one focused bundle. |
| P7/P8 Secrets | PASS | No credentials; smoke test rejects credential-like bundled content. |
| P9 No fake data | PASS | No Gold placeholder or cloud fixture; mockup content must be clearly non-production evidence. |
| P10 Traceability | PASS | KPI inventory, gap analysis, unused KPI report, and output listing required. |
| P11-P13 Medallion | N/A | Agent reads confirmed Gold metadata; it does not transform or persist medallion data. |
| P14-P15 API/schema stability | N/A | No API or shared model change. |
| P16 Frontend quality | PASS by reference | Generated HTML must follow existing frontend tokens/components; no React code changes. |
| CI zero-warning constraints | PASS | Shell smoke test is dependency-free; no new package lock or lint surface. |

No constitution violation requires complexity tracking.

## Project Structure

### Documentation (this feature)

```text
specs/014-dcm-ux-mockup-agent/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
spec-kit-dcm-workflow/agents/dcm-ux-agent/
├── dcm-ux-agent.agent.md       # Primary Copilot custom agent; plain Markdown body
├── README.md                   # Installation, invocation, Claude secondary usage
├── references/
│   ├── design-system.md        # Canonical frontend paths and stable visual rules
│   └── output-contract.md      # Generated artifact contract
└── smoke-test.sh               # Offline structural validation

reference/
└── gold-tables-confirmed.md    # Maintained by PO/data team; required input, not created here
```

**Structure Decision**: Use one focused repository-local agent bundle. Keep confirmed Gold reference ownership outside the bundle. Point to the PO-provided design-system CSS rather than reconstructing it. Keep generated feature outputs under `maquette/ux-<resolved-name>/` only after final PO approval.

## Phase 0: Research Summary

Research decisions are recorded in [research.md](research.md): Copilot `.agent.md` primary format, plain Markdown portability, shell smoke test, referenced design system, fail-closed Gold gate, and conversational approval boundary.

## Phase 1: Design Summary

- [data-model.md](data-model.md) defines file-based input, KPI inventory, proposal, state, and output entities.
- [contracts/agent-contract.md](contracts/agent-contract.md) defines invocation, read gates, proposal fields, and prohibited behavior.
- [contracts/output-contract.md](contracts/output-contract.md) defines output paths, page spec sections, HTML visual contract, and failure behavior.
- [quickstart.md](quickstart.md) defines offline smoke validation and manual PO scenarios.

## Implementation Notes

1. Create the `.agent.md` with minimal repository-compatible frontmatter and portable Markdown instructions.
2. Add references that point to frontend tokens/components and define generated-output expectations without copying token values.
3. Add shell smoke test with strict non-zero failures for missing files, malformed frontmatter, missing safety markers, and credential-like content.
4. Add README documenting Copilot invocation, Claude secondary usage, required Gold reference, and the explicit generation gate.
5. Keep `reference/gold-tables-confirmed.md` a PO/data-team prerequisite; never add a fabricated sample.
6. After implementation, run smoke test and execute manual acceptance scenarios with a real confirmed Gold reference.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | No constitution violation. |
