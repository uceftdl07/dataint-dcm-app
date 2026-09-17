# T{ID} — {Title}

**Domain**: {frontend|backend|dataeng|qa|devops|misc}
**Package**: {packages/...}
**Branch**: {domain}/{spec_num}-{slug}
**Jira**: {DCINT-XXX or pending}
**Depends on**: {T00Y or none}
**Work type**: {from intake.json}

> **Branch** = git **branch name** only (e.g. `frontend/011-carousel-ui`). Never a commit SHA.

## Description

{What this task delivers — 2-4 sentences}

## Files to create/modify

- CREATE {path}
- UPDATE {path}

## Acceptance Criteria

- [ ] {testable criterion 1}
- [ ] {testable criterion 2}
- [ ] {testable criterion 3}

## Tests

- {test command or file}

## Out of scope

- {explicit exclusions}

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

{dependencies, API contracts, links to plan.md or contracts/}
