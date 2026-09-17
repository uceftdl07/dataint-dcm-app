# Feature Specification: Inactive Cluster Widget on Dashboard

**Feature Branch**: `009-widget-inactive-cluster`

**Created**: 2026-07-01

**Status**: Draft

**Input**: User description: "add widget inactive cluster"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Dashboard Shows Inactive Cluster Count (Priority: P1)

As a platform operator, I want to see a widget on the main dashboard showing the number of inactive (terminated) compute clusters across all monitored Landing Zones, so I can immediately assess resource waste and idle infrastructure.

**Why this priority**: This is the core deliverable. A single visible count on the dashboard surfaces a signal that was previously invisible without manual investigation. It delivers value as a standalone MetricCard.

**Independent Test**: Navigate to the Dashboard → verify that the "Inactive clusters" MetricCard is visible in the metrics row and shows a numeric value.

**Acceptance Scenarios**:

1. **Given** the Dashboard is loaded, **When** there are terminated clusters in the data, **Then** the "Inactive clusters" MetricCard displays the correct count.
2. **Given** the Dashboard is loaded, **When** there are no terminated clusters, **Then** the MetricCard displays `0` with a success tone.
3. **Given** the Dashboard is loading, **When** the compute data is being fetched, **Then** the card renders in a skeleton/loading state consistent with other cards.

---

### User Story 2 — Inactive Cluster Count Uses Warning Tone (Priority: P2)

As a platform operator, I want the inactive cluster widget to be visually distinct (warning color) when the count is greater than zero, so I immediately know whether action is required without reading the number carefully.

**Why this priority**: Complements US1 with actionability signal. Standard DCM pattern (same as "Open alerts" card). Delivers higher value with minimal effort.

**Independent Test**: Simulate a scenario with > 0 terminated clusters → verify the MetricCard renders in warning tone. Simulate 0 → verify success tone.

**Acceptance Scenarios**:

1. **Given** the inactive cluster count is `> 0`, **When** the MetricCard renders, **Then** it uses the warning tone.
2. **Given** the inactive cluster count is `0`, **When** the MetricCard renders, **Then** it uses the success tone.

---

### User Story 3 — Click Navigates to Filtered Cluster List (Priority: P3)

As a platform operator, I want to click the inactive cluster widget to navigate directly to the cluster list filtered on terminated state, so I can investigate which clusters are inactive and take remediation action.

**Why this priority**: Nice-to-have drill-down. Depends on US1. Consistent with all other MetricCards on the dashboard.

**Independent Test**: Click the "Inactive clusters" card → verify navigation to `/clusters` page with `state=terminated` filter pre-applied.

**Acceptance Scenarios**:

1. **Given** the MetricCard is displayed, **When** the user clicks it, **Then** the browser navigates to the Clusters page filtered to show only terminated clusters.

---

### Edge Cases

- What happens when the compute API is unavailable or returns an error? → Widget shows a neutral state (no crash, graceful degradation consistent with other cards).
- What happens when no LZ has been onboarded yet? → Count is `0`, success tone displayed.
- What happens when workspace filter is active in the header? → The inactive cluster count respects the active workspace scope filter.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Dashboard MUST display a MetricCard labeled "Inactive clusters" showing the count of compute resources with `state = terminated`.
- **FR-002**: The MetricCard MUST use a warning tone when the inactive count is `> 0`, and a success tone when it is `0`.
- **FR-003**: The MetricCard MUST be consistent in layout, loading state, and visual style with the existing MetricCards on the Dashboard.
- **FR-004**: Users MUST be able to click the MetricCard to navigate to the Clusters page pre-filtered on terminated state.
- **FR-005**: The inactive cluster count MUST respect the active workspace scope filter applied via the header workspace selector.
- **FR-006**: The widget MUST be gated behind the existing cluster access permission (`DASHBOARD_WIDGET_PERMISSIONS.clusters`).
- **FR-007**: The inactive cluster count MUST be fetched via a separate query (not the existing active-count query) using the existing `GET /api/v1/clusters?state=terminated` endpoint.

## Key Entities

- **InactiveClusterCount**: A derived count — number of compute resources whose latest observed state is `terminated`. Not persisted; computed on read from `curated_compute_metrics` via the existing clusters API.
- **ComputeMetric**: Existing entity. Key field: `state: 'running' | 'terminated' | 'error' | 'unknown'`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The "Inactive clusters" MetricCard is visible on the Dashboard for any authenticated user with cluster access permissions.
- **SC-002**: The count is accurate — matches the result of `GET /api/v1/clusters?state=terminated` for the current scope.
- **SC-003**: The warning/success tone changes correctly based on count (0 → success, > 0 → warning).
- **SC-004**: Clicking the widget navigates to the Clusters page in ≤ 1 user interaction.
- **SC-005**: The widget does not degrade performance of the Dashboard — it reuses existing data fetched by the dashboard or adds a single lightweight additional query.

## Assumptions

- "Inactive cluster" is defined as a compute resource whose most recent observed state is `terminated`. This maps directly to the existing `state = 'terminated'` filter on `GET /api/v1/clusters`.
- The Backend API `GET /api/v1/clusters?state=terminated` already exists and is stable — no backend change is required.
- The existing `DASHBOARD_WIDGET_PERMISSIONS.clusters` permission gate also covers the new inactive cluster widget.
- The widget fetches its count via TanStack Query as a separate lightweight request (not via the main dashboard bundle), to avoid adding latency to the critical path.
- Mobile/responsive layout inherits from the existing MetricCard grid — no additional responsive work needed.
- The Clusters page (`/clusters`) already accepts a `state` query param or can be linked with a filter pre-applied.
