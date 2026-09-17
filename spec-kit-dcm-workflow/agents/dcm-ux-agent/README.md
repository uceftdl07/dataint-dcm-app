# DCM UX Mockup Agent

Reusable GitHub Copilot custom agent for designing DCM HTML mockups from validated spike and Gold-table inputs.

## Copilot usage

Load `dcm-ux-agent.agent.md` as a workspace custom agent, then provide either:

- an explicit feature spike directory under `spike/`; or
- the mapping, data model, and feature description as Markdown/text.

The agent reads `reference/gold-tables-confirmed.md` on every execution when it exists. If it is absent, a feature data model may be used only after the PO explicitly names that file and confirms it as authoritative for the current execution. Missing confirmation or incomplete Gold coverage blocks KPI proposals and all artifact generation.

The canonical design system is stored at `references/Design_system_pour_les_maquettes.html`. The agent copies its `<style>` block literally and validates every generated class against it. It does not reconstruct CSS from frontend tokens or existing mockups.

## Claude Code or manual usage

Use the Markdown body of `dcm-ux-agent.agent.md` as the instruction contract. The workflow uses generic actions only: read files, list directories, ask the Product Owner questions, and write files after explicit approval.

Do not create a second divergent agent prompt. Keep platform-specific frontmatter limited to the Copilot file.

## Design system sources

Generated mockups use the canonical local design-system file and reference repository sources only as context:

- `references/Design_system_pour_les_maquettes.html`
- `packages/dcm-frontend/src/styles/tokens.css` (context only)
- `packages/dcm-frontend/src/components/ui` (context only)
- relevant existing mockups under `maquette/`

## Output gate

The agent must complete KPI inventory, persona/objective/value mapping, page-structure challenge, Gold truth gate, design-system class validation, and the Product Owner review loop first. It must receive explicit final confirmation before creating any HTML, page spec, or report.

## Validation

Run offline smoke validation from repository root:

```bash
spec-kit-dcm-workflow/agents/dcm-ux-agent/smoke-test.sh
```

No LLM, browser, cloud credential, or network access is required.

Validate a generated run before delivery:

```bash
spec-kit-dcm-workflow/agents/dcm-ux-agent/validate-generated-output.sh maquette/ux-<resolved-name>
```

This check blocks delivery when metric-header tooltips, categorical selects, shared drawers, or domain toggles are missing.
