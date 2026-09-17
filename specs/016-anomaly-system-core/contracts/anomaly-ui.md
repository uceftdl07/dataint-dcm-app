# Anomaly UI Contract

## Anomaly Rules page

- Paginated table showing human-readable name, domain, severity, rule type, trigger mode, active state, and LZ scope.
- Create/edit dialog for custom rules.
- Company rules are visible but read-only.
- Activation toggle is shown only to authorized users.
- Loading, empty, validation, and authorization-error states are required.

## Anomaly Reports page

- Paginated incident table with rule, LZ, severity, start/end, duration, and status.
- Filters: LZ, status, rule, and period.
- Detail view shows metric value, threshold snapshot, formatted logs, and lifecycle timestamps.
- `unknown` reports are visually distinct from active and finalized incidents.
- Data access uses the central API client and TanStack Query hooks; network calls are mocked in Vitest.
