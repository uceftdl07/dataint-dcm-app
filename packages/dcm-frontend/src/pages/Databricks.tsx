import {
  Activity,
  CheckCircle2,
  Cloud,
  Database,
  DollarSign,
  Download,
  Layers,
  ListChecks,
  RefreshCw,
  Server,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import React from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import {
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
  PageError,
  PageNotice,
} from '../components/domain';
import { PipelineRunAccordion } from '../components/domain/pipeline-run-accordion';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { useDatabricksPageData } from '../hooks/useDatabricksPageData';
import { downloadCsv } from '../lib/databricks/databricks-utils';
import {
  assertDatabricksWidgetTarget,
  buildDatabricksFocusPath,
  DATABRICKS_WIDGET_TARGETS,
} from '../lib/databricks/focus-routes';
import { parseClusterStateFromUrl, parseDatabricksFocusView } from '../lib/databricks/focus-view';
import {
  formatCurrency,
  formatWorkers,
  getClusterCreator,
  getClusterHourlyCost,
  getClusterStartTime,
  getClusterTerminatedTime,
  normalizeTags,
  pct,
} from '../lib/databricks/view-data';

function getClusterHealthCopy(errorCount: number) {
  if (errorCount > 0) return `${errorCount} cluster${errorCount > 1 ? 's' : ''} to review first`;
  return 'Cluster estate stable';
}

function buildLegacyFocusRedirect(searchParams: URLSearchParams): string | null {
  const legacyView = parseDatabricksFocusView(searchParams.get('view'));
  if (!legacyView) {
    return null;
  }
  const state = parseClusterStateFromUrl(searchParams.get('state'));
  const jobStatus = searchParams.get('jobStatus') ?? '';
  return buildDatabricksFocusPath(legacyView, {
    state: state || undefined,
    jobStatus: jobStatus || undefined,
  });
}

const Databricks: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const legacyRedirect = buildLegacyFocusRedirect(searchParams);

  const {
    clusters,
    databricksAlerts,
    databricksCostUsd,
    databricksPipelines,
    error,
    errorClusters,
    estimatedHourlyCostUsd,
    failedJobs,
    filteredClusters,
    filteredWorkloadRows,
    governanceScore,
    landingZones,
    load,
    loading,
    loadingDetails,
    nonCompliantChecks,
    notice,
    runningClusters,
    runningJobs,
    scope,
    workspaces,
    avgCpu,
    avgMem,
  } = useDatabricksPageData();

  const goTo = (path: string) => {
    navigate(assertDatabricksWidgetTarget(path));
  };

  const exportClustersToCsv = () => {
    downloadCsv(
      `databricks-clusters-${new Date().toISOString().slice(0, 10)}.csv`,
      [
        'Cluster',
        'ID',
        'Workspace',
        'Landing zone',
        'Account',
        'State',
        'Workers',
        'Node',
        'Spark',
        'CPU %',
        'Memory %',
        'Hourly cost USD',
        'Creator',
        'Start time',
        'Terminated time',
        'Collected',
        'Tags',
      ],
      filteredClusters.map((cluster) => [
        cluster.resource_name,
        cluster.compute_resource_id,
        cluster.workspace_id ?? '',
        cluster.source_lz_id,
        cluster.subscription_or_account_id ?? '',
        cluster.state,
        formatWorkers(cluster),
        cluster.node_type ?? '',
        cluster.spark_version ?? '',
        cluster.avg_cpu_utilization_pct ?? '',
        cluster.avg_mem_utilization_pct ?? '',
        getClusterHourlyCost(cluster) ?? '',
        getClusterCreator(cluster) ?? '',
        getClusterStartTime(cluster) ?? '',
        getClusterTerminatedTime(cluster) ?? '',
        cluster.collected_at,
        Object.entries(normalizeTags(cluster.tags))
          .map(([key, value]) => `${key}:${String(value)}`)
          .join('; '),
      ])
    );
  };

  const exportWorkloadsToCsv = () => {
    downloadCsv(
      `databricks-workloads-${new Date().toISOString().slice(0, 10)}.csv`,
      [
        'Name',
        'ID',
        'Type',
        'Source',
        'Parent',
        'Status',
        'Duration seconds',
        'Start',
        'End',
        'Landing zone',
        'Account',
        'Rows read',
        'Rows written',
        'Data read',
        'Data written',
        'Error',
      ],
      filteredWorkloadRows.map((workload) => [
        workload.name,
        workload.id,
        workload.type,
        workload.source,
        workload.parentName ?? '',
        workload.status,
        workload.durationSeconds ?? '',
        workload.startTime ?? '',
        workload.endTime ?? '',
        workload.sourceLzId ?? '',
        workload.subscriptionOrAccountId ?? '',
        workload.rowsRead ?? '',
        workload.rowsWritten ?? '',
        workload.dataReadBytes ?? '',
        workload.dataWrittenBytes ?? '',
        workload.errorMessage ?? '',
      ])
    );
  };

  if (legacyRedirect) {
    return <Navigate to={legacyRedirect} replace />;
  }

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <ContentTitle>Databricks</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`${filteredClusters.length} Databricks cluster(s) monitored — ${runningClusters.length} running — ${scope.label}${errorClusters.length > 0 ? ` — ${errorClusters.length} in error` : ''}`}
              tags={[
                { value: 'Databricks', icon: <Server size={14} />, tone: 'primary' },
                { label: 'Clusters', value: filteredClusters.length },
                { label: 'Running', value: runningClusters.length },
                { label: 'Scope', value: scope.label },
                ...(errorClusters.length > 0
                  ? [{ label: 'Errors', value: errorClusters.length, tone: 'danger' as const }]
                  : []),
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={exportClustersToCsv}
            disabled={loading || filteredClusters.length === 0}
          >
            <Download />
            Export clusters
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={exportWorkloadsToCsv}
            disabled={loading || filteredWorkloadRows.length === 0}
          >
            <Download />
            Export jobs
          </Button>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {notice && <PageNotice title="DCM data unavailable" message={notice} />}
      {error && <PageError message={error} />}

      <ContentMain className="space-y-6">
        {loading ? (
          <Skeleton className="h-[180px]" />
        ) : (
          <Card
            className="relative overflow-hidden rounded-[2rem] border-border/70 shadow-[var(--card-shadow)]"
            style={{
              background:
                'linear-gradient(135deg, color-mix(in oklch, var(--tdf-blue) 10%, transparent), color-mix(in oklch, var(--tdf-teal) 7%, transparent) 52%, var(--card-background))',
            }}
          >
            <CardContent className="relative p-5 xl:p-6">
              <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                    Databricks overview
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-foreground">
                    Click a metric to open its detail page.
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                    Each card opens a dedicated view — clusters, jobs, costs, alerts — without
                    scrolling past this dashboard.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/60 bg-white/75 p-4 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/10">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        Running
                      </p>
                      <p className="mt-1 text-3xl font-semibold tracking-[-0.05em] text-tdf-green">
                        {runningClusters.length}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {filteredClusters.length} visible clusters
                      </p>
                    </div>
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-card/90 text-tdf-green shadow-sm ring-1 ring-success-border/70">
                      <CheckCircle2 size={18} />
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge
                  variant={errorClusters.length > 0 ? 'warning' : 'success'}
                  className="px-3 py-1"
                >
                  {getClusterHealthCopy(errorClusters.length)}
                </Badge>
                <Badge variant="outline" className="bg-card/70 px-3 py-1">
                  {filteredClusters.length} Databricks of {clusters.length} compute resources
                </Badge>
              </div>
            </CardContent>
          </Card>
        )}

        <MetricGrid
          loading={loading}
          skeletonCount={8}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        >
          <MetricCard
            label="Workspaces"
            value={workspaces.size}
            description="Workspace summary"
            icon={<Database />}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.workspaces)}
          />
          <MetricCard
            label="Landing zones"
            value={landingZones.size}
            description="Landing zone sources"
            icon={<Cloud />}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.landingZones)}
          />
          <MetricCard
            label="Clusters"
            value={filteredClusters.length}
            description="Full cluster list"
            icon={<Activity />}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.clusters)}
          />
          <MetricCard
            label="Running"
            value={runningClusters.length}
            description="Running clusters only"
            icon={<Server />}
            tone="success"
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.running)}
          />
          <MetricCard
            label="Errors"
            value={errorClusters.length}
            description="Clusters in error"
            icon={<XCircle />}
            tone={errorClusters.length > 0 ? 'danger' : 'success'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.errors)}
          />
          <MetricCard
            label="Job runs"
            value={databricksPipelines.length}
            description={`${failedJobs.length} failed · ${runningJobs.length} running`}
            icon={<Layers />}
            tone={failedJobs.length > 0 ? 'danger' : runningJobs.length > 0 ? 'warning' : 'default'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.jobs)}
          />
          <MetricCard
            label="Security alerts"
            value={databricksAlerts.length}
            description="Active security alerts"
            icon={<ShieldAlert />}
            tone={databricksAlerts.length > 0 ? 'danger' : 'success'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.securityAlerts)}
          />
          <MetricCard
            label="Governance score"
            value={
              governanceScore?.global_score_pct == null
                ? '—'
                : `${governanceScore.global_score_pct}%`
            }
            description="Compliance checks"
            icon={<ListChecks />}
            tone={nonCompliantChecks.length > 0 ? 'warning' : 'success'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.governance)}
          />
        </MetricGrid>

        <Card className="rounded-[1.75rem] border-border/70">
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                  Latest Databricks jobs
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Workflow runs only — notebooks and activities are under Jobs view.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.jobs)}
              >
                View all jobs
              </Button>
            </div>
            <PipelineRunAccordion
              runs={databricksPipelines.slice(0, 8)}
              loading={loading}
              emptyMessage="No Databricks job run in this scope. Enable databricks-jobs collector on the landing zone."
            />
          </CardContent>
        </Card>

        <MetricGrid
          loading={loadingDetails}
          skeletonCount={4}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        >
          <MetricCard
            label="Average CPU"
            value={pct(avgCpu)}
            description="Cluster utilization"
            icon={<Activity />}
            tone={avgCpu !== null && avgCpu > 80 ? 'warning' : 'default'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.averageCpu)}
          />
          <MetricCard
            label="Average memory"
            value={pct(avgMem)}
            description="Cluster utilization"
            icon={<Database />}
            tone={avgMem !== null && avgMem > 80 ? 'warning' : 'default'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.averageMemory)}
          />
          <MetricCard
            label="Databricks cost"
            value={formatCurrency(databricksCostUsd)}
            description="Cost breakdown"
            icon={<DollarSign />}
            tone={databricksCostUsd > 0 ? 'warning' : 'default'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.databricksCost)}
          />
          <MetricCard
            label="Cluster hourly"
            value={estimatedHourlyCostUsd > 0 ? `${formatCurrency(estimatedHourlyCostUsd)}/h` : '—'}
            description="Cluster costs"
            icon={<DollarSign />}
            tone={estimatedHourlyCostUsd > 0 ? 'warning' : 'default'}
            onClick={() => goTo(DATABRICKS_WIDGET_TARGETS.clusterHourly)}
          />
        </MetricGrid>

        {loadingDetails ? (
          <Skeleton className="h-40 rounded-[1.75rem]" />
        ) : (
          <Card className="rounded-[1.75rem]">
            <CardHeader>
              <CardTitle>Field coverage</CardTitle>
              <CardDescription>
                Snapshot of Databricks fields collected by DCM in this scope.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 pt-0 md:grid-cols-2 xl:grid-cols-4">
              <p className="text-sm">
                <span className="font-medium">Cluster creator:</span>{' '}
                {filteredClusters.filter((cluster) => getClusterCreator(cluster)).length}/
                {filteredClusters.length}
              </p>
              <p className="text-sm">
                <span className="font-medium">Start/created date:</span>{' '}
                {filteredClusters.filter((cluster) => getClusterStartTime(cluster)).length}/
                {filteredClusters.length}
              </p>
              <p className="text-sm">
                <span className="font-medium">Cluster hourly cost:</span>{' '}
                {estimatedHourlyCostUsd > 0
                  ? `${formatCurrency(estimatedHourlyCostUsd)}/h visible`
                  : 'Not collected'}
              </p>
              <p className="text-sm">
                <span className="font-medium">Per-job cost/creator:</span> Not collected by current
                APIs
              </p>
            </CardContent>
          </Card>
        )}
      </ContentMain>
    </Content>
  );
};

export default Databricks;
