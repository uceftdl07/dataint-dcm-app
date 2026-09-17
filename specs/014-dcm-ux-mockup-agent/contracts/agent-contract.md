# Agent Contract

## Artifact

`spec-kit-dcm-workflow/agents/dcm-ux-agent/dcm-ux-agent.agent.md`

## Invocation inputs

The agent accepts:

- an optional explicit spike directory path;
- an optional explicit feature/output name;
- otherwise, the feature inputs as raw Markdown/text supplied by the Product Owner.

## Mandatory read order

1. Resolve and validate spike inputs.
2. Read `reference/gold-tables-confirmed.md` when present, or use an explicitly PO-confirmed feature data model as the documented fallback source for the current execution.
3. Read the selected frontend design-system paths.
4. Build the complete Gold KPI inventory.
5. Present KPI and page proposals for PO review.
6. Wait for explicit final approval.

## Prohibited behavior

- Never choose an ambiguous spike directory automatically.
- Never invent a Gold table, column, formula input, cloud value, or data coverage.
- Never generate HTML or Markdown deliverables before final PO approval.
- Never use versioned-scope terminology for non-selected KPIs.
- Never treat a missing Gold reference as permission to continue without explicit PO confirmation of the fallback source.

## Required proposal fields

Every proposed KPI must include:

- name;
- confirmed Gold source table and columns;
- formula and calculability status;
- persona(s);
- objective/question per persona;
- business value;
- page placement;
- selection rationale.

## Required approval protocol

The agent must separate:

- iterative proposal feedback, which can repeat without a fixed limit;
- final approval, which explicitly authorizes file generation.

A non-affirmative or ambiguous response keeps the agent in proposal mode.
