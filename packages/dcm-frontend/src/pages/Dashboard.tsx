import {
  AlertTriangle,
  ArrowRight,
  BellRing,
  Boxes,
  CalendarDays,
  Cloud,
  DatabaseZap,
  Lock,
  RefreshCw,
  Server,
  Workflow,
} from 'lucide-react';
import React, { useMemo } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis } from 'recharts';
import { Link } from 'react-router-dom';
import { AccessGate } from '../components/AccessGate';
import { Content, ContentMain, ContentTitle } from '../components/layout/content';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { DASHBOARD_WIDGET_PERMISSIONS } from '../config/role-permissions';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';
import { useDashboardQueries } from '../hooks/useDashboardQueries';
import { useRolePermissions } from '../hooks/useRolePermissions';
import { getSelectedLzIds } from '../lib/monitoring-scope-filter';
import { cn, formatCompactCurrency, formatCurrency } from '../lib/utils';
import type { HomeAlertBreakdown, HomeFinOpsTrendPoint } from '../types/api';

interface ModuleCardProps {
  title: string;
  description: string;
  source: string;
  to: string;
  icon: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

function ModuleCard({
  title,
  description,
  source,
  to,
  icon,
  children,
  className,
}: ModuleCardProps) {
  return (
    <Link
      to={to}
      aria-label={`Open ${title}`}
      className={cn(
        'block h-full rounded-[var(--card-radius)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        className
      )}
    >
      <Card interactive className="h-full min-h-56 p-5">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-sm font-bold tracking-tight text-foreground">{title}</h2>
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            {icon}
          </span>
        </div>
        <div className="mt-4 flex-1">
          {children}
          <p className="mt-2 text-sm leading-5 text-muted-foreground">{description}</p>
        </div>
        <div className="mt-5 flex items-center gap-1 text-sm font-semibold text-primary">
          Open {title} <ArrowRight size={15} aria-hidden />
        </div>
        <p className="mt-3 border-t border-border/70 pt-3 text-[11px] text-muted-foreground">
          Source: {source}
        </p>
      </Card>
    </Link>
  );
}

function RoadmapCard({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
}) {
  return (
    <Card
      aria-disabled="true"
      className="min-h-28 border-dashed bg-muted/55 p-5 opacity-75 shadow-none"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-border bg-background text-muted-foreground">
          {icon}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-bold">{title}</h2>
            <Badge variant="secondary">Coming soon</Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
    </Card>
  );
}

function formatMonthLabel(month: string) {
  const date = new Date(`${month}-01T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return month;
  return new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: 'UTC' }).format(date);
}

function formatAsOf(value: string | null | undefined) {
  if (!value) return 'Unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unavailable';
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

function FinOpsChart({ points }: { points: HomeFinOpsTrendPoint[] }) {
  const chartData = useMemo(
    () =>
      points.map((point) => ({
        month: formatMonthLabel(point.month),
        current: point.current_year_usd,
        previous: point.previous_year_usd,
      })),
    [points]
  );
  const hasPreviousYear = points.some((point) => point.previous_year_usd !== null);

  if (points.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-lg bg-muted/50 text-xs text-muted-foreground">
        Monthly trend unavailable
      </div>
    );
  }

  return (
    <figure aria-label="Monthly YTD cost trend" className="mt-4">
      <div className="h-28 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id="home-finops-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--primary)" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              fontSize={11}
              stroke="var(--muted-foreground)"
            />
            <Tooltip
              formatter={(value: number) => formatCurrency(value)}
              contentStyle={{ borderRadius: 8, fontSize: 12, borderColor: 'var(--border)' }}
            />
            {hasPreviousYear ? (
              <Area
                type="monotone"
                dataKey="previous"
                stroke="var(--muted-foreground)"
                strokeDasharray="3 2"
                strokeWidth={1.25}
                fill="none"
                connectNulls
                dot={false}
                isAnimationActive={false}
                name="Previous year"
              />
            ) : null}
            <Area
              type="monotone"
              dataKey="current"
              stroke="var(--primary)"
              strokeWidth={2}
              fill="url(#home-finops-area)"
              dot={false}
              isAnimationActive={false}
              name="Current year"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {points.map((point) => (
          <li key={point.month}>
            {point.month}: {formatCurrency(point.current_year_usd)} current year
            {point.previous_year_usd === null
              ? ''
              : `, ${formatCurrency(point.previous_year_usd)} previous year`}
          </li>
        ))}
      </ul>
    </figure>
  );
}

function AlertBreakdown({ breakdown }: { breakdown: HomeAlertBreakdown }) {
  const items = [
    { label: 'Critical', value: breakdown.critical, className: 'bg-danger-subtle text-danger' },
    { label: 'High', value: breakdown.high, className: 'bg-warning-subtle text-warning' },
    { label: 'Medium', value: breakdown.medium, className: 'bg-info-subtle text-info' },
    { label: 'Low', value: breakdown.low, className: 'bg-success-subtle text-success' },
  ].filter((item) => item.value !== undefined);

  return (
    <div className="mt-3 flex flex-wrap gap-2" aria-label="Active alerts by severity">
      {items.length ? (
        items.map((item) => (
          <span
            key={item.label}
            className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', item.className)}
          >
            {item.value} {item.label}
          </span>
        ))
      ) : (
        <span className="text-xs text-muted-foreground">Severity breakdown unavailable</span>
      )}
    </div>
  );
}

const Dashboard: React.FC = () => {
  const { getApiParams } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const { start_date, end_date } = getApiParams();
  const scopedParams = getScopedParams({
    cloudProvider: true,
    sourceLzId: true,
    workspaceId: true,
  });
  const dashboardQuery = useDashboardQueries({
    start_date,
    end_date,
    cloud_provider: scopedParams.cloud_provider,
    source_lz_id: scopedParams.source_lz_id,
    source_lz_ids: getSelectedLzIds(scope),
    workspace_id: scopedParams.workspace_id,
    workspace_ids: scopedParams.workspace_ids,
  });
  const { user } = useCurrentDcmUser();
  const { canAccess } = useRolePermissions();
  const data = dashboardQuery.data;
  const displayName = user?.display_name?.trim();
  const firstName = displayName?.split(/\s+/)[0];
  const error = dashboardQuery.error instanceof Error ? dashboardQuery.error.message : null;

  const alertBreakdown = useMemo<HomeAlertBreakdown>(() => {
    if (data?.overview.alert_breakdown) return data.overview.alert_breakdown;
    if (!data) return {};
    return data.alerts
      .filter((alert) => alert.status === 'active')
      .reduce<HomeAlertBreakdown>((counts, alert) => {
        counts[alert.severity] = (counts[alert.severity] ?? 0) + 1;
        return counts;
      }, {});
  }, [data]);

  return (
    <div className="mx-auto max-w-[1320px] px-3 pb-16 pt-4 sm:px-5">
      <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-border pb-3.5">
        <div className="text-[15px] font-bold tracking-tight">
          DCM <span className="font-medium text-muted-foreground">· Data Connect Monitoring</span>
        </div>
        <div className="flex-1" />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => dashboardQuery.refetch()}
          disabled={dashboardQuery.isFetching}
        >
          <RefreshCw />
          Refresh
        </Button>
      </div>

      <Content className="gap-6 p-0">
        <div className="sr-only">
          <ContentTitle>Home</ContentTitle>
        </div>

        <section className="rounded-[var(--card-radius)] border border-border bg-[linear-gradient(120deg,oklch(97.5%_.015_265)_0%,oklch(98.5%_.012_176)_100%)] px-5 py-5 sm:px-7">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">
                {firstName ? `Welcome, ${firstName}` : 'Welcome'} <span aria-hidden>👋</span>
              </h1>
              <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                Here is the current health of your connected data environments.
              </p>
            </div>
            <div className="space-y-1 text-sm text-muted-foreground">
              <p className="flex items-center gap-2">
                <CalendarDays size={15} aria-hidden />
                Last synchronization:{' '}
                <strong className="text-foreground">
                  {formatAsOf(data?.overview.as_of ?? data?.overview.period.end)}
                </strong>
              </p>
              <p className="flex items-center gap-2">
                <Cloud size={15} aria-hidden />
                Monitoring scope: <strong className="text-foreground">{scope.label}</strong>
              </p>
            </div>
          </div>
        </section>

        {error ? (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>Dashboard unavailable</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
              <span>
                {error}. No metric values are shown until the dashboard data can be loaded.
              </span>
              <Button variant="outline" size="sm" onClick={() => dashboardQuery.refetch()}>
                Try again
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        <ContentMain className="gap-7">
          {dashboardQuery.isLoading ? (
            <div
              aria-label="Loading dashboard"
              className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
            >
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-60" />
              ))}
            </div>
          ) : data ? (
            <>
              <section aria-labelledby="databricks-modules">
                <h2
                  id="databricks-modules"
                  className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  Databricks
                </h2>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <AccessGate
                    allowed={canAccess(DASHBOARD_WIDGET_PERMISSIONS.failures)}
                    resourceLabel="Jobs & Pipelines metrics"
                    compact
                  >
                    <ModuleCard
                      title="Jobs & Pipelines"
                      description="Failed jobs during the last rolling 24 hours"
                      source="gold_dbx_workflow_runs"
                      to="/databricks/workflows"
                      icon={<Workflow size={21} aria-hidden />}
                    >
                      <p
                        className={cn(
                          'text-4xl font-extrabold',
                          (data.overview.failed_databricks_jobs_24h ?? 0) > 0
                            ? 'text-destructive'
                            : 'text-success'
                        )}
                      >
                        {data.overview.failed_databricks_jobs_24h ?? 'Unavailable'}
                      </p>
                    </ModuleCard>
                  </AccessGate>

                  <AccessGate
                    allowed={canAccess(DASHBOARD_WIDGET_PERMISSIONS.clusters)}
                    resourceLabel="compute metrics"
                    compact
                  >
                    <ModuleCard
                      title="Compute"
                      description="Resources active in your authorized monitoring scope"
                      source="compute_clusters, compute_warehouses"
                      to="/databricks/cluster"
                      icon={<Server size={21} aria-hidden />}
                    >
                      <dl className="grid grid-cols-2 gap-4">
                        <div>
                          <dt className="text-xs text-muted-foreground">Active clusters</dt>
                          <dd className="mt-1 text-3xl font-extrabold">
                            {data.overview.active_clusters}
                          </dd>
                        </div>
                        <div className="border-l border-border pl-4">
                          <dt className="text-xs text-muted-foreground">Active SQL Warehouses</dt>
                          <dd className="mt-1 text-3xl font-extrabold">
                            {data.overview.active_sql_warehouses ?? 'Unavailable'}
                          </dd>
                        </div>
                      </dl>
                    </ModuleCard>
                  </AccessGate>

                  <AccessGate
                    allowed={canAccess(DASHBOARD_WIDGET_PERMISSIONS.databricksCard)}
                    resourceLabel="usage tracking"
                    compact
                  >
                    <ModuleCard
                      title="Usage tracking"
                      description="Track table queries, consumers, governance, and associated costs. Select tables in the module to view their indicators."
                      source="query_history, access_audit"
                      to="/databricks/data-product-usage"
                      icon={<DatabaseZap size={21} aria-hidden />}
                    />
                  </AccessGate>
                </div>
              </section>

              <section aria-labelledby="finops-module">
                <h2
                  id="finops-module"
                  className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  FinOps — Cost &amp; consumption
                </h2>
                <AccessGate
                  allowed={canAccess(DASHBOARD_WIDGET_PERMISSIONS.finopsCard)}
                  resourceLabel="FinOps metrics"
                  compact
                >
                  <Link
                    to="/databricks/finops-v2"
                    aria-label="Open FinOps"
                    className="block rounded-[var(--card-radius)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  >
                    <Card
                      interactive
                      className="grid grid-cols-1 gap-6 p-5 sm:grid-cols-[1fr_1.4fr] sm:items-center"
                    >
                      <div className="flex flex-col gap-1">
                        <span className="text-xs font-bold uppercase tracking-[0.04em] text-muted-foreground">
                          Databricks total cost
                        </span>
                        <span className="text-[2.1rem] font-extrabold leading-tight">
                          {data.overview.cost_ytd_usd == null
                            ? 'Unavailable'
                            : formatCompactCurrency(data.overview.cost_ytd_usd)}
                        </span>
                        {data.overview.cost_ytd_delta_pct != null ? (
                          <span
                            className={cn(
                              'text-sm font-semibold',
                              data.overview.cost_ytd_delta_pct > 0 ? 'text-warning' : 'text-success'
                            )}
                          >
                            {data.overview.cost_ytd_delta_pct > 0 ? '▲' : '▼'}{' '}
                            {Math.abs(data.overview.cost_ytd_delta_pct).toFixed(1)}% vs same period
                            last year
                          </span>
                        ) : null}
                        <span className="text-xs text-muted-foreground">
                          Since Jan 1, {new Date().getUTCFullYear()}
                        </span>
                        <span className="mt-1 flex items-center gap-1 text-sm font-semibold text-primary">
                          Open FinOps <ArrowRight size={15} aria-hidden />
                        </span>
                      </div>
                      <FinOpsChart points={data.overview.cost_ytd_monthly ?? []} />
                    </Card>
                  </Link>
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Source: system.billing.usage
                  </p>
                </AccessGate>
              </section>

              <section aria-labelledby="alerts-module">
                <h2
                  id="alerts-module"
                  className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  Anomalies &amp; Alerts
                </h2>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <AccessGate
                    allowed={canAccess(DASHBOARD_WIDGET_PERMISSIONS.alerts)}
                    resourceLabel="active alerts"
                    compact
                  >
                    <ModuleCard
                      title="Active alerts"
                      description="Open alerts requiring attention"
                      source="/security/alerts"
                      to="/databricks/alerts"
                      icon={<BellRing size={21} aria-hidden />}
                    >
                      <p
                        className={cn(
                          'text-4xl font-extrabold',
                          data.overview.open_alerts > 0 ? 'text-destructive' : 'text-success'
                        )}
                      >
                        {data.overview.open_alerts}
                      </p>
                      <AlertBreakdown breakdown={alertBreakdown} />
                    </ModuleCard>
                  </AccessGate>
                </div>
              </section>

              <section aria-labelledby="roadmap-modules">
                <h2
                  id="roadmap-modules"
                  className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground"
                >
                  Other sources · Roadmap
                </h2>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <RoadmapCard
                    title="Cognite"
                    description="Monitoring for Cognite Data Fusion environments"
                    icon={<Boxes size={20} aria-hidden />}
                  />
                  <RoadmapCard
                    title="Azure Data Factory"
                    description="ADF pipeline and consumption monitoring"
                    icon={<Workflow size={20} aria-hidden />}
                  />
                  <RoadmapCard
                    title="Consolidated anomalies"
                    description="Cross-module consolidated anomaly monitoring"
                    icon={<Lock size={20} aria-hidden />}
                  />
                </div>
              </section>
            </>
          ) : null}
        </ContentMain>
      </Content>
    </div>
  );
};

export default Dashboard;
