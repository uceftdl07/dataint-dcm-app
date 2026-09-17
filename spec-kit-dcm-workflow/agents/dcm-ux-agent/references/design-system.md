# DCM Mockup Design-System Reference

The canonical design-system file is `references/Design_system_pour_les_maquettes.html`. Its `<style>` block is the sole CSS source for generated HTML.

## Canonical sources

- Canonical literal CSS and master page: `references/Design_system_pour_les_maquettes.html`
- Existing frontend tokens: `packages/dcm-frontend/src/styles/tokens.css` (context only)
- Shared UI components: `packages/dcm-frontend/src/components/ui/` (context only)
- Existing HTML examples: `maquette/compute-metrics-exposition/` (context only)

The canonical tooltip component is used for both KPI cards and metric-bearing table headers. If the supplied design-system CSS lacks a tooltip component, stop and report the missing component; do not invent a replacement.

## Stable mockup rules

- Use OKLCH color tokens and Inter typography.
- Use pill-shaped controls with `border-radius: 999px`.
- Use DCM card radius from `--card-radius`.
- Use colored KPI-card headers.
- Use uppercase small-caps table headers.
- Use two-column app shell: sidebar plus main content.
- Preserve readable responsive behavior and interactive demonstration controls.

The agent must copy the canonical `<style>` block literally. Frontend tokens/components and existing mockups must not be used to reconstruct or approximate missing CSS.
