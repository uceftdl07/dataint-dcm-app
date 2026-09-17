# Output Contract

## Directory

Create `maquette/ux-<resolved-name>/` only after explicit final PO approval. The `ux-` prefix is mandatory; Compute uses `maquette/ux-compute-metrics-definition/`.

## Required files

For each approved page:

- `<page-name>.html`
- `<page-name>-spec.md`

At feature root:

- `gap-analysis.md`
- `unused-gold-kpis.md`

## Page spec sections

Each page spec must contain:

1. User Scenarios
2. Functional Requirements
3. Key Entities
4. API Endpoints
5. checklist

## HTML contract

Generated HTML must:


The generated output must use `.th-tip-icon` and non-empty `.th-tip-bubble` markup for metric headers, real `<select>` controls when `requires-select: true`, and `.subtabs`/`.subtab`/`.tab-panel` when `calculable-domains` is greater than one.
## Traceability contract

Every KPI in `gap-analysis.md` must include source coverage, formula, calculability, personas, and selection status. Every calculable KPI absent from final pages must appear in `unused-gold-kpis.md`.

## Failure contract

When spike inputs are missing/ambiguous or Gold coverage is absent/incomplete, the agent must report the blocker and create none of the required output files.
