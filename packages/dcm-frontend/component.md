# DCM Guardian Component Reference

## Objective

The DCM frontend aligns with the Guardian/TotalEnergies design language while keeping its current stack: React 18, Vite, React Router, Tailwind CSS 3, and the DCM backend API.

## Tokens

Tokens are centralized in `src/index.css` and exposed through `tailwind.config.js`.

- Surfaces: `bg-background`, `bg-card`, `bg-popover`
- Text: `text-foreground`, `text-card-foreground`, `text-muted-foreground`
- Actions: `bg-primary`, `text-primary`, `text-primary-foreground`
- States: `bg-destructive`, `text-destructive`, `bg-tdf-green`, `bg-tdf-blue`
- Layout: `bg-sidebar`, `text-sidebar-foreground`, `border-sidebar-border`

Dark mode relies on the `.dark` class carried by `document.documentElement`.

## UI Components

Shared components live in `src/components/ui`.

- `Button` : variants `default`, `secondary`, `outline`, `ghost`, `destructive`, `link`
- `Card` : `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`
- `Badge` : variants `default`, `secondary`, `outline`, `success`, `warning`, `info`, `destructive`
- `Table` : `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell`
- `Alert` : `Alert`, `AlertTitle`, `AlertDescription`
- `Input` and `Select`: accessible native fields compatible with the theme
- `Skeleton`: loading state
- `StatusBadge`: standard mapping for backend statuses

## Page Layout

Use the `src/components/layout/content.tsx` helpers for every page:

```tsx
<Content>
  <ContentHeader>
    <div>
      <ContentTitle>Title</ContentTitle>
      <ContentDescription>Business description</ContentDescription>
    </div>
    <ContentActions>Actions</ContentActions>
  </ContentHeader>
  <ContentMain>Content</ContentMain>
</Content>
```

## Backend Data

Pages must use `src/api/dcmApiClient.ts`. Mocks should only be used for explicitly isolated prototypes.

Endpoints already used in the migration:

- `getDashboardOverview`
- `getGovernanceScore`
- `getCostSummary`
- `listPipelines`
- `listComputes`
- `listDatabases`
- `listSecurityAlerts`
- `getHealth`

## Accessibility Rules

- All interactive buttons must have a `focus-visible` state.
- Icon-only actions must declare an `aria-label`.
- `loading`, `error`, and `empty` states must be visible.
- Tables must use the `Table*` components to keep semantic structure.

## Page-By-Page Migration Rules

1. Keep the existing business logic if it already calls the backend.
2. Remove POC types when a backend type exists in `src/types/api.ts`.
3. Replace ad hoc classes with `Card`, `Table`, `Badge`, `Button`, `Alert`, `Input`, `Select`.
4. Verify light/dark mode after migration.
5. Run `npm run build` before considering a page complete.

## Pages Already Updated

- `Dashboard`: real dashboard aggregation for costs, governance, pipelines, clusters, databases, and alerts.
- `Databricks`: real clusters through `/api/v1/clusters`.
- `DatabricksAlerts`: real Azure alerts through `/api/v1/security/alerts`.
- `DataFactory`: real Azure pipelines through `/api/v1/pipelines`.
- `Alerts`: real global alerts through `/api/v1/security/alerts`.
- `Settings`: real backend health check and theme toggle.
