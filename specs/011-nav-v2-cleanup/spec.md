# Feature Specification: DCM Navigation v2 — Sidebar Cleanup & Restructure

**Feature Branch**: `011-nav-v2-cleanup`

**Created**: 2026-07-28

**Status**: Draft

**Input**: User description: "Cleaner la version 1 fonctionnelle de DCM — garder uniquement les menus Home, Databricks, Talk to your Data ; spliter le menu vertical avec une section Settings contenant Administration et My Landing Zones ; hider le reste sans supprimer ; créer les sous-sections Databricks (Lakeflow/Pipelines, Lakeflow/Workflows, Compute/Cluster, Compute/SQL Warehouse, FinOps, Usage Data Product) en pages vides."

---

## Clarifications

### Session 2026-07-28

- Q: Pour un utilisateur non-admin, que voit-il pour "Administration" dans la section Settings ? → A: Hidden — l'item n'apparaît pas du tout
- Q: Dans le menu Databricks, comment Lakeflow et Compute s'affichent-ils ? → A: Labels/headers statiques non-cliquables — séparateurs visuels uniquement
- Q: Pour les 6 nouvelles routes Databricks, quel pattern d'URL utiliser ? → A: Plat, préfixe `/databricks/` seul (`/databricks/pipelines`, `/databricks/cluster`…)
- Q: Route pour “Usage Data Product” — nouvelle ou réutiliser `/data-product-usage` ? → A: Nouvelle route `/databricks/data-product-usage` (spécifique, évite collision)- Q: "Talk to your Data" — nav principale ou section Settings ? → A: Nav principale (fonctionnalité métier, pas un paramètre)
---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Simplified Main Navigation (Priority: P1)

A user opens DCM and sees only three items in the main navigation: **Home**, **Databricks**, and **Talk to your Data**. All other previously visible menu items (Data Factory, Databases, Clusters, Global FinOps, Global Alerts, Cloud Security, Standard Checks, Users, Collection Status, Settings) are no longer visible in the sidebar but their underlying pages remain accessible via direct URL.

**Why this priority**: Reduces visual noise immediately. First thing every user sees on login. Establishes the v2 navigation contract for future sprints.

**Independent Test**: Log in and verify the sidebar shows exactly 3 items in its main section. Confirm `/datafactory`, `/clusters`, `/costs` etc. still load correctly when accessed by URL.

**Acceptance Scenarios**:

1. **Given** a logged-in user, **When** they look at the sidebar, **Then** they see exactly: Home, Databricks (collapsed/expandable), Talk to your Data — and nothing else in the main nav section.
2. **Given** a hidden page route (e.g., `/costs`), **When** the user navigates directly via URL, **Then** the page loads correctly (no 404, no redirect).
3. **Given** the sidebar is collapsed, **When** the user hovers over the icons, **Then** tooltips correctly identify the three visible items.

---

### User Story 2 — Settings Section in Sidebar (Priority: P1)

The sidebar has a visually distinct **Settings** section below the main navigation. It contains two items: **Administration** and **My Landing Zones**. The section is always visible but visually separated from the main navigation area (e.g., divider, different label, or positioned at the bottom of the sidebar above the user menu).

**Why this priority**: Administration and My Landing Zones are operational pages — they belong in a distinct, intentional zone rather than buried in a long flat list.

**Independent Test**: Verify the sidebar renders two distinct visual zones. Confirm "Administration" and "My Landing Zones" links navigate to `/admin` and `/my-access` respectively.

**Acceptance Scenarios**:

1. **Given** a logged-in user, **When** they look at the sidebar, **Then** they see a "Settings" section header below the main nav items, containing Administration and My Landing Zones.
2. **Given** a non-admin user, **When** they view the Settings section, **Then** Administration is completely hidden — only My Landing Zones is visible.
3. **Given** a user clicks "My Landing Zones" in Settings, **When** the page loads, **Then** they land on `/my-access`.
4. **Given** the sidebar is in collapsed state, **When** the Settings section items are shown, **Then** they display as icon-only with tooltip, consistent with main nav items.

---

### User Story 3 — Restructured Databricks Sub-Navigation (Priority: P2)

The Databricks menu in the main nav is replaced with a new hierarchical structure:

```
Databricks
├── Lakeflow
│   ├── Pipelines
│   └── Workflows
├── Compute
│   ├── Cluster
│   └── SQL Warehouse
├── FinOps
└── Usage Data Product
```

Each leaf item navigates to a dedicated placeholder page that displays a "coming soon" or empty state. The existing Databricks sub-pages (Dashboard, Alerts, Governance, Insights, Unity Catalog, Monitoring Reports) are **hidden from the nav** but their routes remain active.

**Why this priority**: Establishes the Databricks v2 navigation contract. Empty pages are required as scaffolding for future sprints.

**Independent Test**: Expand the Databricks menu and verify the new sub-sections render. Click each leaf item and confirm a placeholder page loads (no error).

**Acceptance Scenarios**:

1. **Given** a user expands Databricks, **When** they view the submenu, **Then** they see: Lakeflow (with Pipelines/Workflows sub-items), Compute (with Cluster/SQL Warehouse sub-items), FinOps, Usage Data Product.
2. **Given** a user clicks any Databricks sub-item (e.g., Lakeflow > Pipelines), **When** the page loads, **Then** a placeholder/empty-state page renders — no crash, no 404.
3. **Given** old Databricks routes like `/databricks/alerts`, **When** accessed by URL, **Then** the existing page still loads (not deleted, just hidden from nav).
4. **Given** the sidebar is collapsed, **When** the user hovers over the Databricks icon, **Then** a tooltip shows "Databricks".

---

### Edge Cases

- What happens when a user with a bookmarked hidden route (e.g., `/security`) visits it after the nav change? → Page must still load; only the nav link is hidden.
- What happens when an admin vs non-admin views the Settings section? → Administration item must respect existing role guard.
- Databricks sub-groups (Lakeflow, Compute) are static non-clickable section headers — visual separators only. Only leaf items (Pipelines, Workflows, Cluster, SQL Warehouse, FinOps, Usage Data Product) are navigable links.
- What if the sidebar is collapsed and Databricks has nested groups? → Collapsed sidebar shows only the Databricks icon; hover tooltip shows "Databricks".

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The main sidebar navigation section MUST display exactly three items: Home, Databricks, and Talk to your Data.
- **FR-002**: All previously visible menu items not in FR-001 (Data Factory, Databases, Clusters, Global FinOps, Global Alerts, Cloud Security, Standard Checks, Users, Collection Status, top-level Settings page) MUST be removed from the sidebar navigation array without deleting their route definitions or page components.
- **FR-003**: The sidebar MUST render a visually distinct "Settings" section (separated from the main nav) containing two items: Administration (`/admin`) and My Landing Zones (`/my-access`).
- **FR-004**: The Administration item in the Settings section MUST be completely hidden for non-admin users (not visible, not grayed out). Only users with the `requiresAdmin` permission see it.
- **FR-005**: The Databricks submenu MUST be restructured to contain: two static group headers (Lakeflow and Compute), each followed by two leaf items, plus two direct leaf items (FinOps and Usage Data Product).
  - Lakeflow > Pipelines → `/databricks/pipelines`
  - Lakeflow > Workflows → `/databricks/workflows`
  - Compute > Cluster → `/databricks/cluster`
  - Compute > SQL Warehouse → `/databricks/sql-warehouse`
  - FinOps → `/databricks/finops-v2`
  - Usage Data Product → `/databricks/data-product-usage`
- **FR-006**: Each new Databricks leaf route MUST render a placeholder page showing an empty state (e.g., "Coming soon" or section name with a brief description). No functional data is required.
- **FR-007**: All existing Databricks sub-routes (`/databricks`, `/databricks/alerts`, `/databricks/finops`, `/databricks/governance`, `/databricks/insights`, `/unitycatalogexplorer`, `/data-product-usage`, `/monitoringreports`) MUST remain registered in the router and render their existing pages when accessed directly.
- **FR-008**: The sidebar collapsed state MUST continue to work correctly: icon-only display with tooltips for all visible items in both sections.

### Non-Functional Requirements

- **NFR-001**: No existing page component or route file is deleted — only nav config entries are removed/hidden.
- **NFR-002**: The sidebar visual split between main nav and Settings section must be clear without additional color coding — a label and/or divider is sufficient.
- **NFR-003**: The new placeholder pages must be lightweight (no API calls, no data fetching).

---

## Key Entities

- **`MODULE_MENU`** (`packages/dcm-frontend/src/config/navigation.ts`): Central array defining all sidebar items. This is the primary config to modify.
- **`Sidebar.tsx`** (`packages/dcm-frontend/src/components/Sidebar.tsx`): Renders the sidebar from `MODULE_MENU`. Needs to support two nav sections (main + settings).
- **`app-routes.ts`** (`packages/dcm-frontend/src/app-routes.ts`): Route definitions. New Databricks placeholder routes added here; no existing routes removed.
- **Placeholder page component**: A new shared `ComingSoonPage` or per-section stub pages for the 6 new Databricks routes.
- **Admin permission guard**: Existing `requiresAdmin` flag on Administration menu item in `navigation.ts` — must be preserved in the new Settings section config.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the change, the sidebar main section contains exactly 3 top-level items (Home, Databricks, Talk to your Data) — verifiable by counting rendered nav items in a Vitest component test.
- **SC-002**: The Settings section renders 2 items (Administration, My Landing Zones) — verifiable by Vitest snapshot or DOM query.
- **SC-003**: All 6 new Databricks placeholder routes return HTTP 200 and render without console errors.
- **SC-004**: All previously visible hidden routes (≥ 8 routes: `/costs`, `/clusters`, `/security`, `/governance`, `/users`, `/datafactory`, `/databases`, `/status`) still load without 404 when accessed directly.
- **SC-005**: Zero TypeScript compilation errors introduced by this change (`tsc --noEmit` exits 0).
- **SC-006**: Existing Vitest tests for Sidebar and navigation pass without modification (no regressions).

---

## Assumptions

- Databricks group headers (Lakeflow, Compute) are **static non-clickable labels** (visual separators). Only leaf items are navigable. This requires a new `group` concept in `ModuleMenuItem` or inline rendering in `Sidebar.tsx`.
- The "Settings" section header in the sidebar is a static label/divider, not a route link.
- The top-level `/settings` route (existing `Settings` page) is removed from the nav but its route remains registered.
- Route paths for new Databricks sub-sections use a flat single-prefix pattern under `/databricks/`: `/databricks/pipelines`, `/databricks/workflows`, `/databricks/cluster`, `/databricks/sql-warehouse`, `/databricks/finops-v2`, `/databricks/data-product-usage`. Note: `/databricks/finops` is already taken by the hidden legacy route, so the new FinOps placeholder uses `/databricks/finops-v2`. Note: `/data-product-usage` is the hidden legacy route; the new Databricks-scoped route uses `/databricks/data-product-usage` to avoid collision.
- "Usage Data Product" in the new Databricks nav is a new placeholder route (not reusing the existing `/data-product-usage` route, to avoid confusion with the hidden old page). This assumption should be confirmed during implementation.
- No new API endpoints are needed — placeholder pages are purely frontend, no data fetching.
- Mobile/responsive behavior is out of scope for this spec; sidebar behavior follows existing collapsed/expanded logic.
- The `Talk to your Data` menu label is the user-facing label for the existing `Talk to Data` item (`/talk-to-data`).
