#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
AGENT="$ROOT/dcm-ux-agent.agent.md"
README="$ROOT/README.md"
DESIGN="$ROOT/references/design-system.md"
OUTPUT="$ROOT/references/output-contract.md"
DESIGN_SOURCE="$ROOT/references/Design_system_pour_les_maquettes.html"
VALIDATOR="$ROOT/validate-generated-output.sh"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

[ -f "$AGENT" ] || fail "missing agent file"
[ -f "$README" ] || fail "missing README"
[ -f "$DESIGN" ] || fail "missing design-system reference"
[ -f "$OUTPUT" ] || fail "missing output-contract reference"
[ -f "$DESIGN_SOURCE" ] || fail "missing canonical design-system file"
[ -f "$VALIDATOR" ] || fail "missing generated-output validator"

first_line=$(sed -n '1p' "$AGENT")
[ "$first_line" = "---" ] || fail "agent frontmatter must start with ---"
frontmatter_end=$(awk 'NR > 1 && $0 == "---" { print NR; exit }' "$AGENT")
[ -n "$frontmatter_end" ] || fail "agent frontmatter closing delimiter missing"

for marker in \
  'description:' \
  'name:' \
  'reference/gold-tables-confirmed.md' \
  'explicitly PO-confirmed feature data model' \
  'explicit final confirmation' \
  'gap-analysis.md' \
  'unused-gold-kpis.md' \
  'blocked' \
  'partially covered' \
  'Design_system_pour_les_maquettes' \
  'Design_system_pour_les_maquettes.html' \
  'literal' \
  'tooltip' \
  'Drawer détail' \
  'filter' \
  'Positionnement dans la navigation' \
  'KPI / Persona / Objectif / Valeur' \
  'maquette/ux-<resolved-name>/' \
  'non-selected'; do
  grep -Fq "$marker" "$AGENT" || fail "missing required marker: $marker"
done

for marker in \
  'metric-definition dictionary' \
  'metric-bearing `<th>`' \
  'coherent confirmed data domain' \
  'filter candidates' \
  'run-level drawer' \
  'run-level regression review'; do
  grep -Fq "$marker" "$AGENT" || fail "missing round-3 marker: $marker"
done

for marker in \
  'th-tip-icon' \
  'th-tip-bubble' \
  'subtabs' \
  'tab-panel' \
  'categorical field with more than two values' \
  'validate-generated-output.sh' \
  'atomic inventory' \
  '100%' \
  'distinct Gold tables' \
  'ux-` prefix' \
  'consecutive duplicate lines' \
  'date-range segmented control' \
  'sidebar-footer' \
  'user-chip' \
  'realistic, varied mock values' \
  'Reconciliation is exclusive' \
  'badge-success' \
  'human-readable labels' \
  'drawer is interactive' \
  'Selected primary KPIs' \
  'bidirectional' \
  'non-selected KPI must not occur' \
  'content-toolbar' \
  'filterRows' \
  'duplicate `(KPI, Gold table)`'; do
  grep -Fq "$marker" "$AGENT" || fail "missing round-4 marker: $marker"
done

for marker in \
  'one KPI per row' \
  'Domain toggles are table-driven' \
  'raw debug metadata' \
  'repeated conclusion phrases' \
  'Table des sous-vues' \
  'realistic varied mock values' \
  'Reconciliation is exclusive' \
  'badge-success' \
  'technical Gold names'; do
  grep -Fq "$marker" "$OUTPUT" || fail "missing output-contract marker: $marker"
done

if grep -Eiq '(api[_-]?key|client[_-]?secret|password[[:space:]]*:|BEGIN (RSA|OPENSSH) PRIVATE KEY)' "$ROOT"/*.md "$ROOT"/references/*.md; then
  fail "credential-like content found in agent bundle"
fi

if find "$ROOT" -type f \( -name '*.json' -o -name '*.csv' \) -print -quit | grep -q .; then
  fail "data fixture bundled in agent directory"
fi

printf 'PASS: DCM UX Mockup Agent smoke test\n'
