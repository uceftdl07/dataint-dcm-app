import { Info, Workflow } from 'lucide-react';
import React, { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getDcmApiErrorMessage, type EmbeddedDashboard } from '../api/dcmApiClient';
import { PageError } from '../components/domain';
import { DatabricksEmbeddedDashboard } from '../components/domain/databricks/databricks-embedded-dashboard';
import { Content, ContentDescription, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Card, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { FieldLabel, Select } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { useEmbeddedDashboards } from '../hooks/useEmbeddedDashboards';
import { useDatabricksWorkspacesList } from '../hooks/useDatabricksWorkspacesList';
import { formatWorkspaceLabel } from '../lib/databricks/workspace-label';
import RequireAdmin from '../components/RequireAdmin';

const ALL_WORKSPACES = '';

function workspaceLabel(
  workspaceId: string,
  workspacesById: Map<string, string>,
): string {
  const displayName = workspacesById.get(workspaceId);
  if (displayName && displayName !== workspaceId) {
    return `${displayName} (${formatWorkspaceLabel(workspaceId, 16)})`;
  }
  return formatWorkspaceLabel(workspaceId);
}

function dashboardMatchesWorkspace(dashboard: EmbeddedDashboard, workspaceId: string): boolean {
  if (!workspaceId) {
    return true;
  }
  if (dashboard.scope === 'global') {
    return true;
  }
  return dashboard.workspace_id === workspaceId;
}

function buildWorkspaceOptions(dashboards: EmbeddedDashboard[]) {
  const ids = new Set(dashboards.map((dashboard) => dashboard.workspace_id));
  return Array.from(ids).sort();
}

const DatabricksInsights: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedWorkspaceId = searchParams.get('workspace') ?? ALL_WORKSPACES;
  const selectedSlug = searchParams.get('dashboard') ?? '';

  const dashboardsQuery = useEmbeddedDashboards();
  const workspacesQuery = useDatabricksWorkspacesList(true);

  const dashboards = dashboardsQuery.data?.items ?? [];
  const workspacesById = useMemo(() => {
    const map = new Map<string, string>();
    for (const workspace of workspacesQuery.data?.items ?? []) {
      map.set(workspace.workspace_id, workspace.display_name);
    }
    return map;
  }, [workspacesQuery.data?.items]);

  const workspaceOptions = useMemo(() => buildWorkspaceOptions(dashboards), [dashboards]);

  const filteredDashboards = useMemo(
    () => dashboards.filter((dashboard) => dashboardMatchesWorkspace(dashboard, selectedWorkspaceId)),
    [dashboards, selectedWorkspaceId],
  );

  const selectedDashboard = useMemo(() => {
    if (!filteredDashboards.length) {
      return null;
    }
    return filteredDashboards.find((dashboard) => dashboard.dashboard_slug === selectedSlug)
      ?? filteredDashboards[0];
  }, [filteredDashboards, selectedSlug]);

  useEffect(() => {
    if (!filteredDashboards.length) {
      if (selectedSlug || selectedWorkspaceId) {
        setSearchParams({}, { replace: true });
      }
      return;
    }

    const slugStillValid = filteredDashboards.some((dashboard) => dashboard.dashboard_slug === selectedSlug);
    if (slugStillValid) {
      return;
    }

    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set('dashboard', filteredDashboards[0].dashboard_slug);
        if (selectedWorkspaceId) {
          next.set('workspace', selectedWorkspaceId);
        } else {
          next.delete('workspace');
        }
        return next;
      },
      { replace: true },
    );
  }, [filteredDashboards, selectedSlug, selectedWorkspaceId, setSearchParams]);

  const error = dashboardsQuery.error
    ? getDcmApiErrorMessage(dashboardsQuery.error, 'Error while loading embedded dashboards')
    : null;

  const updateWorkspace = (workspaceId: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (workspaceId) {
          next.set('workspace', workspaceId);
        } else {
          next.delete('workspace');
        }
        next.delete('dashboard');
        return next;
      },
      { replace: true },
    );
  };

  const updateDashboard = (slug: string) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set('dashboard', slug);
        return next;
      },
      { replace: true },
    );
  };

  return (
    <Content>
      <ContentHeader>
        <div>
          <ContentTitle>Databricks Insights</ContentTitle>
          <ContentDescription>
            Select a Databricks workspace and dashboard. Additional filters stay inside each embedded iframe.
          </ContentDescription>
        </div>
      </ContentHeader>

      <ContentMain className="flex min-h-0 flex-1 flex-col gap-4">
        {error ? <PageError message={error} /> : null}

        <Alert className="border-amber-200 bg-amber-50 text-amber-950">
          <Info className="text-amber-700" />
          <AlertTitle>Technical account required</AlertTitle>
          <AlertDescription className="text-amber-900">
            Embedded dashboards use your Databricks session in this browser. Use your{' '}
            <strong>Total technical account</strong> (not a personal <strong>@totalenergies.com</strong> account).
            With a personal account you may only see the Databricks login screen inside the iframe.
            Sign in once to Databricks with your technical account in this browser, or use{' '}
            <strong>Open in Databricks</strong> below.
          </AlertDescription>
        </Alert>

        {dashboardsQuery.isLoading ? (
          <Skeleton className="h-24 rounded-xl" />
        ) : null}

        {!dashboardsQuery.isLoading && !error && dashboards.length > 0 ? (
          <>
            <div className="grid gap-3 rounded-2xl border border-border/70 bg-card p-4 shadow-sm md:grid-cols-2">
              <label className="grid gap-1.5">
                <FieldLabel className="inline-flex items-center gap-1.5">
                  <Workflow className="h-3.5 w-3.5 text-primary" />
                  Databricks workspace
                </FieldLabel>
                <Select
                  value={selectedWorkspaceId}
                  onChange={(event) => updateWorkspace(event.target.value)}
                >
                  <option value={ALL_WORKSPACES}>All workspaces</option>
                  {workspaceOptions.map((workspaceId) => (
                    <option key={workspaceId} value={workspaceId}>
                      {workspaceLabel(workspaceId, workspacesById)}
                    </option>
                  ))}
                </Select>
              </label>

              <label className="grid gap-1.5">
                <FieldLabel>Embedded dashboard</FieldLabel>
                <Select
                  value={selectedDashboard?.dashboard_slug ?? ''}
                  onChange={(event) => updateDashboard(event.target.value)}
                  disabled={filteredDashboards.length === 0}
                >
                  {filteredDashboards.map((dashboard) => (
                    <option key={dashboard.dashboard_slug} value={dashboard.dashboard_slug}>
                      {dashboard.title}
                      {dashboard.scope === 'global' ? ' · global' : ''}
                    </option>
                  ))}
                </Select>
              </label>
            </div>

            {selectedDashboard ? (
              <DatabricksEmbeddedDashboard
                title={selectedDashboard.title}
                description={selectedDashboard.description}
                embedUrl={selectedDashboard.embed_url}
                directUrl={selectedDashboard.direct_url}
              />
            ) : (
              <Card>
                <CardHeader>
                  <CardTitle>No dashboard for this workspace</CardTitle>
                  <CardDescription>
                    Pick another workspace or register a dashboard for this workspace in Administration → DBX Embeds.
                  </CardDescription>
                </CardHeader>
              </Card>
            )}
          </>
        ) : null}

        {!dashboardsQuery.isLoading && !error && dashboards.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>No embedded dashboards configured</CardTitle>
              <CardDescription>
                Add dashboards in Administration → DBX Embeds, then refresh this page.
              </CardDescription>
            </CardHeader>
          </Card>
        ) : null}
      </ContentMain>
    </Content>
  );
};

const DatabricksInsightsPage: React.FC = () => (
  <RequireAdmin>
    <DatabricksInsights />
  </RequireAdmin>
);

export default DatabricksInsightsPage;
