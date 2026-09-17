# Merge Strategy: {FEATURE NAME}

**Spec**: `{###-feature-name}` (logical — dossier `specs/`, pas de branche git mère)
**Spec num**: `{###}`
**PR target**: `develop`
**Child branch base**: `develop`
**Branch pattern**: `{domain}/{spec_num}-{slug}`
**Work type**: {work_type}

## Merge Order

Implement and merge PRs in this order (earliest first):

1. T{NNN} {Domain} — {title} — blocks: {list or none}
2. T{NNN} {Domain} — {title}
3. ...

## Shared Files (conflict risk — within this Epic)

| File | Owner task | Other tasks must NOT touch |
|------|------------|----------------------------|
| packages/dcm-commons/... | T002 | T001, T003 |

## Cross-Epic Shared Files (MANDATORY if overlap)

Fill when `dcm-conflict-check.sh` reports domain/package overlap with another active Epic.

| File / area | Owner Epic (this spec) | Other active Epic | Rule until merge |
|-------------|------------------------|-------------------|------------------|
| packages/dcm-frontend/src/pages/Dashboard* | {###-this-spec} | {###-other-spec} | Other Epic read-only or coordinate daily |
| | | | |

**Recommended merge order across Epics** (earliest PR to develop first):

1. `{###-earlier-spec}` — {domain} — reason: {blocks other / smaller diff}
2. `{###-this-spec}` — {domain}
3. ...

Registry: `specs/active-epics.json` — update at dispatch, mark `--complete` when Epic Done.

## Sync Rule (before each PR)

Branches filles créées depuis `develop` — resync avant PR :

```bash
git fetch origin
git checkout {your-child-branch}
git merge origin/develop
# resolve conflicts locally, then push
```

PR target : **`develop`** (pas branche mère intermédiaire).

Rebase or merge daily if epic is active — **mandatory** when 2+ Epics share same domain.

## Domain isolation

| Domain | Package | Parallel safe with |
|--------|---------|-------------------|
| Frontend | packages/dcm-frontend | Backend (usually) — NOT another frontend Epic on same files |
| Backend | packages/dcm-backend | Frontend (usually) |
| DataEng | packages/dcm-*-collector | Often isolated |

## Hotfix cherry-pick

If hotfix merged to `main`/`develop` while this epic is open:

```bash
git checkout {your-child-branch}
git cherry-pick <hotfix-commit>
```

## Legacy (integration_branch strategy only)

If `branch_strategy: integration_branch` in dcm-config, PR target = branche mère `{###-feature-name}` instead of develop.
