#!/bin/sh
set -eu

TARGET=${1:?Usage: validate-generated-output.sh <mockup-directory>}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
[ -d "$TARGET" ] || fail "missing output directory: $TARGET"
[ -f "$TARGET/gap-analysis.md" ] || fail "missing gap-analysis.md"
[ -f "$TARGET/unused-gold-kpis.md" ] || fail "missing unused-gold-kpis.md"

CANONICAL_STYLE="$ROOT/references/Design_system_pour_les_maquettes.html"
[ -f "$CANONICAL_STYLE" ] || fail "missing canonical design-system source"

if grep -Eq '^(requires-select|calculable-domains):[[:space:]]' "$TARGET/gap-analysis.md"; then
  fail "raw debug metadata found in gap-analysis.md"
fi

if awk 'length($0) > 0 && $0 !~ /^\|[-:|[:space:]]+\|[[:space:]]*$/ { if (++seen[$0] > 1) found = 1 } END { exit found ? 0 : 1 }' "$TARGET/gap-analysis.md"; then
  fail "repeated lines or conclusion phrases found in gap-analysis.md"
fi

grep -q '^## Selected primary KPIs' "$TARGET/gap-analysis.md" || fail "Selected primary KPIs section missing"
awk '
  /^## Selected primary KPIs/ { in_section = 1; next }
  in_section && /^## / { exit }
  in_section && /^\|/ && $0 !~ /KPI/ && $0 !~ /^\|[[:space:]-|]+\|[[:space:]]*$/ { found = 1 }
  END { exit found ? 0 : 1 }
' "$TARGET/gap-analysis.md" || fail "Selected primary KPIs section is empty"

awk '
  /^## / { if (heading != "" && !has_content) { exit 1 }; heading = $0; has_content = 0; next }
  heading != "" && $0 !~ /^[[:space:]]*$/ { has_content = 1 }
  END { if (heading != "" && !has_content) exit 1; exit 0 }
' "$TARGET/gap-analysis.md" || fail "announced gap-analysis section is empty"

grep -Eq '^\|[[:space:]]*KPI[[:space:]]*\|[[:space:]]*Table gold[[:space:]]*\|' "$TARGET/gap-analysis.md" \
  || fail "gap-analysis.md lacks atomic KPI inventory"

while IFS='|' read -r _ raw_kpi raw_table raw_status _; do
  kpi=$(printf '%s' "$raw_kpi" | tr -d ' `')
  table=$(printf '%s' "$raw_table" | tr -d ' `')
  status=$(printf '%s' "$raw_status" | tr -d ' `')
  [ -n "$kpi" ] || continue
  case "$table" in
    *cluster*) html_scope="$TARGET/clusters.html" ;;
    *warehouse*) html_scope="$TARGET/warehouses.html" ;;
    *recommendations*) html_scope="$TARGET/recommendations.html" ;;
    *) html_scope="$TARGET"/*.html ;;
  esac
  in_html=$(sed 's#<title>[^<]*</title>##g; s/page-title//g; s/Recommendation detail//g' $html_scope | grep -Fq "$kpi" && printf '1' || printf '0')
  in_unused=$(awk -F'|' -v wanted="$kpi" -v source="$table" '
    /^\| `/ {
      field=$2; gold=$3
      gsub(/[ `]/, "", field); gsub(/[ `]/, "", gold)
      if (field == wanted && gold == source) found=1
    }
    END { exit found ? 0 : 1 }
  ' "$TARGET/unused-gold-kpis.md" && printf '1' || printf '0')
  if printf '%s' "$status" | grep -q retained && [ "$in_html" -eq 0 ]; then
    fail "retained KPI reconciliation contradiction: $kpi"
  fi
  if printf '%s' "$status" | grep -q retained && awk -F'|' -v wanted="$kpi" -v source="$table" '/^\| `/ {field=$2; gold=$3; gsub(/[ `]/, "", field); gsub(/[ `]/, "", gold); if (field == wanted && gold == source) found=1} END {exit found ? 0 : 1}' "$TARGET/unused-gold-kpis.md"; then
    fail "retained KPI also listed as unused: $kpi"
  fi
  if [ "$status" = non-selected ] && [ "$in_unused" -eq 0 ]; then
    fail "non-selected KPI lacks unused report reason: $kpi"
  fi
  if [ "$status" = non-selected ] && [ "$in_html" -eq 1 ]; then
    fail "non-selected KPI appears in generated HTML: $kpi"
  fi
done <<EOF
$(awk -F'|' '/^## Atomic calculable KPI inventory/{inside=1; next} /^## Selected primary KPIs/{inside=0} inside && /^\| `/{print}' "$TARGET/gap-analysis.md")
EOF

while IFS='|' read -r _ raw_kpi _ raw_status _; do
  kpi=$(printf '%s' "$raw_kpi" | tr -d ' `')
  status=$(printf '%s' "$raw_status" | tr -d ' `')
  printf '%s' "$status" | grep -q 'retainedindrawer' || continue
  grep -q "class=\"mini-kpi\" data-field=\"$kpi\"" "$TARGET"/*.html \
    || fail "retained drawer KPI missing explicit drawer entry: $kpi"
done <<EOF
$(awk -F'|' '/^## Atomic calculable KPI inventory/{inside=1; next} /^## Selected primary KPIs/{inside=0} inside && /^\| `/{print}' "$TARGET/gap-analysis.md")
EOF

if awk -F'|' '/^\| `/{key=$2 "|" $3; gsub(/[ `]/, "", key); if (++seen[key] > 1) found=1} END {exit found ? 0 : 1}' "$TARGET/unused-gold-kpis.md"; then
  fail "duplicate KPI/Gold-table pair in unused-gold-kpis.md"
fi

while IFS='|' read -r _ selected_kpi _ _ _; do
  kpi=$(printf '%s' "$selected_kpi" | tr -d ' `')
  [ -n "$kpi" ] || continue
  awk -F'|' -v wanted="$kpi" '
    /^## Atomic calculable KPI inventory/ { inside=1; next }
    /^## Selected primary KPIs/ { inside=0 }
    inside && /^\| `/ {
      field=$2; state=$4
      gsub(/[ `]/, "", field); gsub(/[ `]/, "", state)
      if (field == wanted && state ~ /^retained/) { found=1 }
    }
    END { exit found ? 0 : 1 }
  ' "$TARGET/gap-analysis.md" || fail "Selected primary KPI is not retained in atomic inventory: $kpi"
done <<EOF
$(awk -F'|' '/^## Selected primary KPIs/{inside=1; next} inside && /^\| `/ {print}' "$TARGET/gap-analysis.md")
EOF

for spec in "$TARGET"/*-spec.md; do
  while IFS= read -r kpi; do
    [ -n "$kpi" ] || continue
    awk -F'|' -v wanted="$kpi" '
      /^## Atomic calculable KPI inventory/ { inside=1; next }
      /^## Selected primary KPIs/ { inside=0 }
      inside && /^\| `/ {
        field=$2; state=$4
        gsub(/[ `]/, "", field); gsub(/[ `]/, "", state)
        if (field == wanted && state ~ /^retained/) { found=1 }
      }
      END { exit found ? 0 : 1 }
    ' "$TARGET/gap-analysis.md" || fail "spec KPI is not retained in atomic inventory: $kpi ($spec)"
  done <<EOF
$(awk -F'|' '
  /^## Table des sous-vues/ { in_subviews=1; next }
  in_subviews && /^## / { in_subviews=0 }
  in_subviews && /^\| [^ -][^|]* \|/ { print $4 }
  /^## Table KPI \/ Persona \/ Objectif \/ Valeur/ { in_kpis=1; next }
  in_kpis && /^## / { in_kpis=0 }
  in_kpis && /^\| `/ { print $2 }
' "$spec" | grep -oE '`[a-z][a-z0-9_]+`' | tr -d '`' | sort -u)
EOF
done

html_files=$(find "$TARGET" -maxdepth 1 -type f -name '*.html' -print)
[ -n "$html_files" ] || fail "no generated HTML files"

first_sidebar_signature=
first_topbar_signature=
for file in $html_files; do
  case "$file" in
    */index.html) continue ;;
  esac
  grep -q 'class="segmented"' "$file" || fail "date-range segmented control missing: $file"
  for range in 30j 90j 6m; do
    grep -q "$range" "$file" || fail "date-range option missing ($range): $file"
  done
  grep -q 'class="sidebar-footer"' "$file" || fail "sidebar footer missing: $file"
  grep -q 'class="user-chip"' "$file" || fail "user chip missing: $file"
  for token in '--primary:[[:space:]]*oklch\(60% \.25 264\.376\)' '--success:[[:space:]]*oklch\(52% \.1483 133\.57\)' '--warning:[[:space:]]*oklch\(46% \.13 70\)' '--danger:[[:space:]]*oklch\(57\.7% \.245 27\.325\)' '--muted-foreground:[[:space:]]*oklch\(55\.2% \.016 285\.938\)' '--card-radius:[[:space:]]*1\.375rem'; do
    grep -Eq -- "$token" "$file" || fail "canonical design token missing ($token): $file"
  done
  grep -q 'badge-success\|badge-warning\|badge-danger' "$file" || fail "status badge class missing: $file"
  if grep -Eq 'class="kpi-card-header[^"]*"[^>]*>[^<]*[a-z][a-z0-9]*_[a-z0-9_]+|<th[^>]*>[^<]*[a-z][a-z0-9]*_[a-z0-9_]+' "$file"; then
    fail "technical snake_case label is visible: $file"
  fi
  if grep -Eq '<(td|div class="kpi-value")[^>]*>[^<]*Illustrative|<td[^>]*>Illustrative|<div class="kpi-value">Illustrative' "$file"; then
    fail "literal Illustrative used as mock value: $file"
  fi
  [ "$(grep -o 'class="object-row"' "$file" | wc -l | tr -d ' ')" -ge 3 ] || fail "fewer than three object rows: $file"

  sidebar_signature=$(grep -oE 'class="(app-sidebar|sidebar-footer|user-chip|nav-group|nav-sub)"' "$file" | sort)
  topbar_signature=$(grep -oE 'class="(app-topbar|topbar-right|btn-guide|dropdown-btn|date-field|segmented)"|>30j<|>90j<|>6m<' "$file" | sort)
  if [ -z "$first_sidebar_signature" ]; then
    first_sidebar_signature=$sidebar_signature
    first_topbar_signature=$topbar_signature
  else
    [ "$sidebar_signature" = "$first_sidebar_signature" ] || fail "sidebar structure differs: $file"
    [ "$topbar_signature" = "$first_topbar_signature" ] || fail "topbar structure differs: $file"
  fi
done

for file in $html_files; do
  case "$file" in
    */index.html) continue ;;
  esac
  grep -q 'class="th-tip-bubble">[^<][^<]*</span>' "$file" || grep -q 'data-field="' "$file" || fail "metric definition metadata missing: $file"
  grep -q 'class="kpi-tooltip"' "$file" || fail "KPI tooltip missing: $file"
  metric_headers=$(grep -o '<th[^>]*data-field="' "$file" | wc -l | tr -d ' ')
  metric_bubbles=$(grep -o 'class="th-tip-bubble"' "$file" | wc -l | tr -d ' ')
  [ "$metric_headers" -eq "$metric_bubbles" ] || fail "metric header tooltip count differs: $file"
  if grep -q 'class="object-row"' "$file"; then
    for drawer_class in id-card drawer-kpis mini-kpi mini-reco; do
      grep -q "class=\"$drawer_class\"" "$file" || fail "$drawer_class missing: $file"
    done
    grep -q 'position:fixed' "$file" || fail "drawer fixed positioning missing: $file"
    grep -q 'drawer-overlay.open' "$file" || fail "drawer overlay open state missing: $file"
    grep -q 'drawer.classList.add.*open\|drawer.classList.remove.*open' "$file" || fail "drawer open/close handlers missing: $file"
    grep -q 'object-row.*addEventListener.*click\|querySelectorAll('\''\.object-row'\'')' "$file" || fail "drawer row click handler missing: $file"
    grep -q 'close-btn.*addEventListener.*click' "$file" || fail "drawer close handler missing: $file"
  fi
  if grep -q '<select' "$file"; then
    grep -q '<select' "$file" || fail "categorical select missing: $file"
    grep -Eq 'onchange=|addEventListener\([^)]*change' "$file" || fail "select is not wired: $file"
  fi
  grep -q 'function filterRows' "$file" || fail "shared filterRows function missing: $file"
  grep -q 'content-toolbar' "$file" || fail "content toolbar missing: $file"
  case "$file" in
    */clusters.html|*/warehouses.html)
    grep -q 'class="subtabs"' "$file" || fail "domain toggle missing: $file"
    grep -q 'class="tab-panel' "$file" || fail "domain panel missing: $file"
    grep -q 'data-tab=' "$file" || fail "domain toggle behavior missing: $file"
    ;;
    */recommendations.html)
    if grep -q 'class="subtabs"' "$file"; then
      fail "single-table page must not have domain toggle: $file"
    fi
    ;;
  esac
done

[ "$(grep -c '^| Cost |' "$TARGET/clusters-spec.md")" -eq 1 ] || fail "clusters Cost subview missing from spec"
[ "$(grep -c '^| Efficiency |' "$TARGET/clusters-spec.md")" -eq 1 ] || fail "clusters Efficiency subview missing from spec"
[ "$(grep -c '^| Cost |' "$TARGET/warehouses-spec.md")" -eq 1 ] || fail "warehouses Cost subview missing from spec"
[ "$(grep -c '^| Utilization |' "$TARGET/warehouses-spec.md")" -eq 1 ] || fail "warehouses Utilization subview missing from spec"
[ "$(grep -o 'data-tab=' "$TARGET/clusters.html" | wc -l | tr -d ' ')" -eq 2 ] || fail "clusters tab count differs from spec"
[ "$(grep -o 'data-tab=' "$TARGET/warehouses.html" | wc -l | tr -d ' ')" -eq 2 ] || fail "warehouses tab count differs from spec"
[ "$(grep -o 'class=\"subtab' "$TARGET/recommendations.html" | wc -l | tr -d ' ')" -eq 0 ] || fail "recommendations has an unapproved subview"

[ "$(grep -o 'class=\"content-toolbar\"' "$TARGET/clusters.html" | wc -l | tr -d ' ')" -eq 2 ] || fail "clusters toolbar count differs from spec"
[ "$(grep -oE 'class="[^"]*filter-(search|select|pill)' "$TARGET/clusters.html" | wc -l | tr -d ' ')" -eq 6 ] || fail "clusters filter count differs from spec"
[ "$(grep -o 'class=\"content-toolbar\"' "$TARGET/warehouses.html" | wc -l | tr -d ' ')" -eq 2 ] || fail "warehouses toolbar count differs from spec"
[ "$(grep -oE 'class="[^"]*filter-(search|select|pill)' "$TARGET/warehouses.html" | wc -l | tr -d ' ')" -eq 5 ] || fail "warehouses filter count differs from spec"
[ "$(grep -o 'class=\"content-toolbar\"' "$TARGET/recommendations.html" | wc -l | tr -d ' ')" -eq 1 ] || fail "recommendations toolbar count differs from spec"
[ "$(grep -oE 'class="[^"]*filter-(search|select|pill)' "$TARGET/recommendations.html" | wc -l | tr -d ' ')" -eq 5 ] || fail "recommendations filter count differs from spec"

printf 'PASS: generated output contract (%s)\n' "$TARGET"
