import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  DollarSign,
  Gauge,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import React from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import {
  FeatureCard,
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
  PageError,
} from '../components/domain';
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
import { useDatabasesPageData } from '../hooks/useDatabasesPageData';
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatStorage,
  getHealthCopy,
} from '../lib/databases/database-utils';
import { buildDatabaseFocusPath } from '../lib/databases/focus-routes';
import {
  parseAvailabilityFromUrl,
  parseDatabaseFocusView,
  parseDatabaseTypeFromUrl,
} from '../lib/databases/focus-view';

function buildLegacyFocusRedirect(searchParams: URLSearchParams): string | null {
  const legacyView = parseDatabaseFocusView(searchParams.get('view'));
  if (!legacyView) return null;
  const avail = parseAvailabilityFromUrl(searchParams.get('avail'));
  const type = parseDatabaseTypeFromUrl(searchParams.get('type'));
  return buildDatabaseFocusPath(legacyView, {
    avail: avail || undefined,
    type: type || undefined,
  });
}

const Databases: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const legacyRedirect = buildLegacyFocusRedirect(searchParams);

  const { dbs, error, filteredDbs, healthRate, load, loading, scope, stats } =
    useDatabasesPageData();

  const goTo = (path: string) => navigate(path);

  if (legacyRedirect) {
    return <Navigate to={legacyRedirect} replace />;
  }

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <ContentTitle>Database Dashboard</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`${filteredDbs.length} database(s) monitored — ${stats.availableCount} available — ${scope.label}${stats.unavailableCount > 0 ? ` — ${stats.unavailableCount} unavailable` : ''}`}
              tags={[
                { value: 'Databases', icon: <Database size={14} />, tone: 'primary' },
                { label: 'Monitored', value: filteredDbs.length },
                { label: 'Available', value: stats.availableCount },
                { label: 'Scope', value: scope.label },
                ...(stats.unavailableCount > 0
                  ? [
                      {
                        label: 'Unavailable',
                        value: stats.unavailableCount,
                        tone: 'danger' as const,
                      },
                    ]
                  : []),
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

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
                    Database overview
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-foreground">
                    Click a metric to open its detail page.
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                    Each card opens a dedicated view — inventory, pressure, capacity — without
                    scrolling past this dashboard.
                  </p>
                </div>
                <div className="rounded-2xl border border-white/60 bg-white/75 p-4 shadow-sm backdrop-blur dark:border-white/10 dark:bg-white/10">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        Availability
                      </p>
                      <p className="mt-1 text-3xl font-semibold tracking-[-0.05em] text-tdf-green">
                        {healthRate}%
                      </p>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {stats.availableCount} of {filteredDbs.length} visible
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
                  variant={stats.unavailableCount > 0 ? 'warning' : 'success'}
                  className="px-3 py-1"
                >
                  {getHealthCopy(stats.unavailableCount, healthRate)}
                </Badge>
                <Badge variant="outline" className="bg-card/70 px-3 py-1">
                  {filteredDbs.length} of {dbs.length} databases in scope
                </Badge>
              </div>
            </CardContent>
          </Card>
        )}

        <MetricGrid
          loading={loading}
          skeletonCount={6}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-6"
        >
          <MetricCard
            label="Databases"
            value={filteredDbs.length}
            description="Full inventory"
            icon={<Database />}
            onClick={() => goTo(buildDatabaseFocusPath('inventory'))}
          />
          <MetricCard
            label="Available"
            value={stats.availableCount}
            description="Healthy databases"
            icon={<CheckCircle2 />}
            tone="success"
            onClick={() => goTo(buildDatabaseFocusPath('inventory', { avail: 'true' }))}
          />
          <MetricCard
            label="Unavailable"
            value={stats.unavailableCount}
            description="Require investigation"
            icon={<XCircle />}
            tone={stats.unavailableCount > 0 ? 'danger' : 'success'}
            onClick={() => goTo(buildDatabaseFocusPath('inventory', { avail: 'false' }))}
          />
          <MetricCard
            label="Avg CPU"
            value={formatPercent(stats.avgCpu)}
            description="Pressure watchlist"
            icon={<Gauge />}
            tone={stats.avgCpu != null && stats.avgCpu > 80 ? 'warning' : 'default'}
            onClick={() => goTo(buildDatabaseFocusPath('pressure'))}
          />
          <MetricCard
            label="Storage used"
            value={formatStorage(stats.totalStorageUsed)}
            description="Capacity ranking"
            icon={<HardDrive />}
            onClick={() => goTo(buildDatabaseFocusPath('capacity'))}
          />
          <MetricCard
            label="Connections"
            value={formatNumber(stats.totalConnections)}
            description={`Storage impact ${formatCurrency(stats.totalStorageCost)}`}
            icon={<Activity />}
            tone="purple"
            onClick={() => goTo(buildDatabaseFocusPath('capacity', { sort: 'connections' }))}
          />
        </MetricGrid>

        <div className="grid gap-4 md:grid-cols-3">
          <Link to="/databasealerts">
            <FeatureCard
              title="Alerts"
              description="Security and availability alerts linked to database resources."
              icon={<AlertTriangle />}
              tone="red"
              badge="Operations"
              meta="Database"
            />
          </Link>
          <Link to="/databasefinops">
            <FeatureCard
              title="Costs & FinOps"
              description="Cost breakdown and optimization opportunities for database services."
              icon={<DollarSign />}
              tone="green"
              badge="FinOps"
              meta="Database"
            />
          </Link>
          <Link to="/databasegovernance">
            <FeatureCard
              title="Governance"
              description="Compliance checks, landing zones, and resource posture for databases."
              icon={<ShieldCheck />}
              tone="purple"
              badge="Checks"
              meta="Database"
            />
          </Link>
        </div>

        <Card className="rounded-[1.75rem]">
          <CardHeader>
            <CardTitle>Field coverage</CardTitle>
            <CardDescription>
              Snapshot of database fields collected by DCM in this scope.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 pt-0 md:grid-cols-2 xl:grid-cols-4">
            <p className="text-sm">
              <span className="font-medium">Average memory:</span> {formatPercent(stats.avgMemory)}
            </p>
            <p className="text-sm">
              <span className="font-medium">Average storage:</span>{' '}
              {formatPercent(stats.avgStorage)}
            </p>
            <p className="text-sm">
              <span className="font-medium">Total storage:</span>{' '}
              {formatStorage(stats.totalStorageUsed)}
            </p>
            <p className="text-sm">
              <span className="font-medium">Storage cost impact:</span>{' '}
              {formatCurrency(stats.totalStorageCost)}
            </p>
          </CardContent>
        </Card>
      </ContentMain>
    </Content>
  );
};

export default Databases;
