# DCM Mockup Output Contract

Create outputs only after explicit final Product Owner confirmation.

## Directory naming

Create `maquette/ux-<resolved-name>/` using this precedence. The `ux-` prefix is mandatory. Compute uses `maquette/ux-compute-metrics-definition/`:

1. source spike directory name;
2. explicit feature name;
3. Product Owner-provided name.

Never guess when the name remains ambiguous.

## Required files

For each approved page:

- `<page-name>.html`
- `<page-name>-spec.md`

At feature root:

- `gap-analysis.md`
- `unused-gold-kpis.md`

## Page specification sections

Each page spec contains:

1. Positionnement dans la navigation
2. Table des sous-vues
3. User Scenarios
4. Functional Requirements
5. Table KPI / Persona / Objectif / Valeur
6. Moteur de recommandations
7. Ce qui n'est pas sur cette page
8. Drawer détail
9. Key Entities
10. API Endpoints
11. Contrat de données et grain Gold
12. Contrat d'interaction des filtres
13. Corrections techniques
14. checklist

## Traceability

Every KPI in `gap-analysis.md` is an atomic named field: one KPI per row, never a comma-separated family list. Each row includes Gold table/columns, formula, calculability, personas, objectives, value, and selection status. Every individually named `calculable` KPI is found either in generated HTML as a KPI-card label/table column or in `unused-gold-kpis.md` with a non-empty reason. This reconciliation is mandatory and must reach 100% before delivery. Every calculable KPI absent from the final pages appears in `unused-gold-kpis.md` with a known reason or `non-selected to date`.

The `ux-` directory prefix is intentional: `maquette/ux-<resolved-name>/` must not be treated as a defect.

Every retained KPI and subview must reference only tables marked `calculable` in the same run's gap analysis. Blocked or partially covered sources are excluded from navigation and output. If a PO-approved exception exists, it must be explicit and traceable.

Object drawers are closed by default and interactive. Clicking any `.object-row` opens a fixed drawer populated from that row; `.close-btn` and `.drawer-overlay` close it. Static always-visible drawers or one hard-coded object detail fail the output contract.

Retained KPIs use realistic varied mock values and at least three rows per object table. The literal word `Illustrative` may appear only in the page-level warning, never in a KPI value or table cell. Visible KPI labels and metric headers are human-readable; technical Gold names remain in `data-field` or tooltip text.

Reconciliation is exclusive: a retained KPI must appear in generated HTML and nowhere in `unused-gold-kpis.md`; a non-selected KPI must appear in `unused-gold-kpis.md` with a reason and is not required in HTML. Retained KPIs absent from HTML and any KPI present in both categories block delivery.

Reconciliation is symmetric: a non-selected KPI must not appear anywhere in generated HTML, including technical attributes, tooltips or drawer content. Every `(KPI, Gold table)` pair appears at most once in `unused-gold-kpis.md`.

Each spec filter declaration maps one-to-one to controls in the matching HTML subview toolbar, and every control changes visibility of that subview's rows.

Every HTML file copies the canonical design-system `<style>` block byte-for-byte, including identical OKLCH `:root` tokens and `.badge-success`, `.badge-warning`, and `.badge-danger` usage for status/severity fields.

Domain toggles are table-driven. A page gets `.subtabs` only when it uses at least two distinct calculable Gold tables. One calculable Gold table means one view and no toggle. The count of `.subtab` elements, page-spec `Table des sous-vues` rows, and distinct calculable Gold tables used by the page must be identical.

Every generated `.kpi-card` has a non-empty tooltip whose text exactly matches the approved KPI objective/value justification. Every object table row opens a provided design-system drawer. Every visible filter is functional and has a documented empty state.

Every metric-bearing table header has the same tooltip component and metric-definition text as its matching KPI card. Each coherent confirmed data domain has its own subview with its own KPI cards and table unless a PO-approved merge is documented. Filter controls are derived per subview from displayed data types. Drawer structure and class set are identical across all object-table pages in a run. A final regression review checks all of these properties together.

Run `validate-generated-output.sh <directory>` before delivery. It must pass for every generated object-table page. It must reconcile atomic calculable KPIs, reject raw debug metadata (`key: value`) in report prose, reject consecutive duplicate lines and repeated conclusion phrases, and reject empty sections announced by the report table of contents. It must compare topbar/sidebar structure across all HTML files, including the date-range segmented control (`30j`, `90j`, `6m`), `.sidebar-footer`, and `.user-chip`, while ignoring only active navigation state. `gap-analysis.md` may carry machine-readable counts only in a dedicated clearly labelled metadata block consumed by the validator; debug lines must never appear as report content.

## Failure behavior

Missing or ambiguous spike inputs, absent Gold reference without explicit PO-confirmed fallback, incomplete Gold coverage, or absent `references/Design_system_pour_les_maquettes.html` blocks output creation. Do not create placeholder reports, mock Gold metadata, or invented CSS. When a fallback is explicitly confirmed, record its path and confirmation in `gap-analysis.md`.
