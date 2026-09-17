#!/usr/bin/env bash
# Shared resolver for the multi-epic team registry. Sourced by
# dcm-active-epics-update.sh and dcm-conflict-check.sh so both agree on the path.
#
# It lives under specs/ because it is TEAM state that must survive a clone: at the
# old path (.specify/, gitignored) each contributor saw only their own epics, so
# cross-epic detection was blind. A file left there is migrated on first use.

DCM_REGISTRY_DEFAULT="specs/active-epics.json"
DCM_REGISTRY_LEGACY=".specify/active-epics.json"

dcm_resolve_registry() {
  repo_root="$1"
  cfg="$repo_root/.specify/extensions/dcm/dcm-config.yml"
  rel=""
  if [ -f "$cfg" ]; then
    rel="$(grep -E '^[[:space:]]*registry_path:' "$cfg" 2>/dev/null | head -1 \
      | sed -E 's/^[^:]*:[[:space:]]*//; s/[[:space:]]*#.*$//; s/^"//; s/"$//; s/^'\''//; s/'\''$//')" || rel=""
  fi
  [ -n "$rel" ] || rel="$DCM_REGISTRY_DEFAULT"

  resolved="$repo_root/$rel"
  legacy="$repo_root/$DCM_REGISTRY_LEGACY"

  if [ ! -f "$resolved" ] && [ -f "$legacy" ] && [ "$resolved" != "$legacy" ]; then
    mkdir -p "$(dirname "$resolved")"
    cp "$legacy" "$resolved"
    # Retire the source: two registries drift apart and nobody knows which one won.
    mv "$legacy" "$legacy.migrated"
    echo "Migrated team registry: $DCM_REGISTRY_LEGACY -> $rel (commit it so the squad shares it)" >&2
    echo "  old copy kept as $DCM_REGISTRY_LEGACY.migrated — delete it once you have committed the new one" >&2
  fi

  printf '%s\n' "$resolved"
}
