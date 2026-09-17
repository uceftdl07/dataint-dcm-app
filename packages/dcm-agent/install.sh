#!/usr/bin/env bash
# Install DCM agent @dp-dcm-lz-client for GitHub Copilot.
#
# From dataint-dcm-app repo root:
#   cd dataint-dcm-app
#   chmod +x packages/dcm-agent/install.sh
#   ./packages/dcm-agent/install.sh --global    # all projects (recommended)
#   ./packages/dcm-agent/install.sh             # this repo only
#
# Then: Reload VS Code → @dp-dcm-lz-client
# Docs: packages/dcm-agent/README.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENT_SRC="$SCRIPT_DIR/agents/dp-dcm-lz-client.agent.md"
GLOBAL=false

if [[ "${1:-}" == "--global" ]]; then
  GLOBAL=true
fi

link_or_copy() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" || -L "$dest" ]]; then
    rm -rf "$dest"
  fi
  local dest_dir rel
  dest_dir="$(cd "$(dirname "$dest")" && pwd)"
  rel="$(python3 -c "import os.path; print(os.path.relpath('${src}', '${dest_dir}'))")"
  ln -sf "$rel" "$dest"
  echo "  -> $dest"
}

install_skills() {
  local skills_root="$1"
  mkdir -p "$skills_root"
  for skill_dir in "$SCRIPT_DIR"/skills/dp-dcm-*/; do
    [[ -d "$skill_dir" ]] || continue
    name="$(basename "$skill_dir")"
    link_or_copy "$skill_dir" "$skills_root/$name"
  done
}

if $GLOBAL; then
  AGENTS_DIR="${HOME}/.github/agents"
  SKILLS_DIR="${HOME}/.agents/skills"
  echo "Installing DCM agent globally..."
  link_or_copy "$AGENT_SRC" "$AGENTS_DIR/dp-dcm-lz-client.agent.md"
  install_skills "$SKILLS_DIR"
else
  echo "Installing DCM agent in $REPO_ROOT ..."
  link_or_copy "$AGENT_SRC" "$REPO_ROOT/.github/agents/dp-dcm-lz-client.agent.md"
  install_skills "$REPO_ROOT/.agents/skills"
fi

echo ""
echo "Next steps:"
echo "  1. Reload VS Code window"
echo "  2. Invoke: @dp-dcm-lz-client Onboarder une nouvelle LZ dans DCM"
