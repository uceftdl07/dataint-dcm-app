# T001 — Create DCM UX Mockup Agent Bundle

**Domain**: misc
**Package**: `spec-kit-dcm-workflow/agents/dcm-ux-agent`
**Branch**: `misc/014-dcm-ux-mockup-agent`
**Jira**: pending
**Depends on**: none
**Work type**: technique

## Description

Create the repository-local DCM UX mockup agent bundle. The primary artifact is a GitHub Copilot `.agent.md` custom agent with a plain Markdown workflow that remains usable manually or from Claude Code as a secondary path.

The agent must resolve spike inputs, read confirmed Gold metadata and the existing frontend design system, inventory calculable KPIs, require persona/objective/value for proposed KPIs, iterate with the PO without an artificial limit, and refuse all deliverable generation until explicit final approval.

## Files to create/modify

- CREATE `spec-kit-dcm-workflow/agents/dcm-ux-agent/dcm-ux-agent.agent.md`
- CREATE `spec-kit-dcm-workflow/agents/dcm-ux-agent/README.md`
- CREATE `spec-kit-dcm-workflow/agents/dcm-ux-agent/references/design-system.md`
- CREATE `spec-kit-dcm-workflow/agents/dcm-ux-agent/references/output-contract.md`
- CREATE `spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh`
- UPDATE `specs/014-dcm-ux-mockup-agent/quickstart.md` only if implementation details change the validation command or manual scenarios

## Sub-tasks

1. Create minimal Copilot-compatible frontmatter and portable Markdown workflow.
2. Encode mandatory input resolution and read order for spike inputs, Gold reference, and frontend design-system paths.
3. Encode exhaustive KPI inventory fields: source table/columns, formula, calculability, persona, objective, value, selection status, and exclusion reason.
4. Encode challenge loop for redundant, non-actionable, or persona-less KPIs and page decomposition.
5. Encode unlimited PO iteration and separate explicit final generation confirmation.
6. Encode fail-closed behavior for missing/ambiguous spike inputs and absent/incomplete `reference/gold-tables-confirmed.md`.
7. Encode output naming precedence and required HTML/spec/report files.
8. Reference existing frontend tokens/components without duplicating token values.
9. Add README usage paths for Copilot and secondary Claude/manual execution.
10. Add offline shell smoke validation for file structure, frontmatter, required markers, and forbidden credential/fake-fixture content.

## Acceptance Criteria

- [x] `spec-kit-dcm-workflow/agents/dcm-ux-agent/dcm-ux-agent.agent.md` uses valid repository-compatible frontmatter and contains a plain Markdown workflow usable without proprietary tool syntax.
- [x] Agent reads explicit spike input first, otherwise lists ambiguous candidates and asks the PO; it never guesses.
- [x] Agent requires `reference/gold-tables-confirmed.md` or an explicitly PO-confirmed fallback, and blocks unsupported generation.
- [x] Every proposed KPI requires confirmed Gold source, formula, calculability, persona, objective, and business value.
- [x] Agent records complete Gold KPI inventory and unused calculable KPIs, not only retained items.
- [x] Agent challenges KPI redundancy/actionability and page structure before proposal approval.
- [x] Agent supports unlimited feedback cycles and separates proposal feedback from explicit final generation approval.
- [x] Approved output contains one `<page-name>.html` plus one `<page-name>-spec.md` per page, `gap-analysis.md`, and `unused-gold-kpis.md`.
- [x] Generated HTML instructions reference current frontend tokens/components and require DCM mockup visual conventions.
- [x] `spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh` exits zero for a valid bundle and non-zero for missing required markers/files.
- [x] No secret, cloud credential, fabricated Gold reference, or fake production evidence is bundled.

## Tests

- `spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh`
- Manual scenarios: `specs/014-dcm-ux-mockup-agent/quickstart.md`
- No LLM, browser, cloud, or network dependency for smoke validation.

## Out of scope

- Implementing a React frontend feature or modifying `packages/dcm-frontend`.
- Creating or maintaining `reference/gold-tables-confirmed.md`.
- Validating Gold tables with the data team.
- Calling an LLM, cloud API, backend API, or database.
- Generating a real feature mockup before a PO invokes the agent and approves the proposal.
- Confluence publication or Jira automation implementation.

## Before PR

- [ ] Rebased/merged latest develop before PR
- [x] `spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh` passes
- [x] No files outside package scope and explicitly listed spec/quickstart updates
- [x] Diff stays reviewable: one agent bundle, one concern
- [x] Sub-spec checkboxes reviewed
- [x] Jira Story lists Git branch `misc/014-dcm-ux-mockup-agent`, not a commit SHA

## Notes

- Design decisions: [research.md](../research.md)
- File entities and state: [data-model.md](../data-model.md)
- Agent contract: [../contracts/agent-contract.md](../contracts/agent-contract.md)
- Output contract: [../contracts/output-contract.md](../contracts/output-contract.md)
- Manual validation: [quickstart.md](../quickstart.md)
- `reference/gold-tables-confirmed.md` is intentionally absent from this change until maintained by the PO/data team.

## Correction Validation — 2026-08-20

- [x] Blocked or partially covered Gold sources remove dependent KPIs and subviews from generated navigation.
- [x] Canonical `Design_system_pour_les_maquettes.html` is stored in the agent bundle and must be copied literally.
- [x] KPI tooltips use the approved persona/objective/value text.
- [x] Object-table drawers and functional filter/empty-state behavior are mandatory generation requirements.
- [x] Page specs require navigation, subviews, KPI/persona/objective/value, recommendations, exclusions, drawer, Gold grain, filter contract, and technical correction sections.
- [x] Output directory uses mandatory `ux-` prefix under `maquette/ux-<resolved-name>/`; Compute uses `maquette/ux-compute-metrics-definition/`.

## Round 4 Validation — 2026-08-20

- [x] Exact `.th-tip-bubble` CSS/HTML contract is required for metric table headers.
- [x] Categorical fields with more than two values require functional `<select>` controls.
- [x] Shared `.id-card`/`.drawer-kpis`/`.mini-kpi`/`.mini-reco` drawer structure is required on every object-table page.
- [x] Domain toggles use `.subtabs`/`.subtab`/`.tab-panel`, distinct from panel filters.
- [x] `validate-generated-output.sh` blocks delivery when structural checks fail.
## Round 3 Validation — 2026-08-20

- [x] One metric-definition dictionary drives KPI-card and metric-header tooltips.
- [x] Confirmed coherent data domains remain separate subviews after exclusions.
- [x] Filter candidates are proposed per subview from field types and validated with PO.
- [x] One shared drawer structure/class set is applied across all object-table pages in a run.
- [x] Final run-level regression review covers tabs, filters, tooltips and drawers together.

## Round 4 Validation — 2026-08-20

- [x] Exact `.th-tip-bubble` CSS/HTML contract required for metric table headers.
- [x] Functional `<select>` required for categorical fields with more than two values.
- [x] Shared structured drawer required on every object-table page.
- [x] Domain toggles use `.subtabs`/`.subtab`/`.tab-panel`, distinct from filters.
- [x] `validate-generated-output.sh` blocks delivery when structural checks fail.
Validation command:

```bash
spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh
```
