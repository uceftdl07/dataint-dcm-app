import {
  AlertTriangle,
  CheckCircle2,
  DollarSign,
  Factory,
  RefreshCw,
  ShieldCheck,
  Workflow,
  XCircle,
} from 'lucide-react';
import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FeatureCard,
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
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
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useDataFactoryPageData } from '../hooks/useDataFactoryPageData';
import { buildDataFactoryFocusPath } from '../lib/datafactory/focus-routes';

const DataFactory: React.FC = () => {
  const navigate = useNavigate();
  const { getDisplayRange } = useGlobalTimeRange();
  const { error, load, loading, loadingDetails, runs, stats, total } = useDataFactoryPageData();
  const display = getDisplayRange();
  const goTo = (path: string) => navigate(path);

  return (
    <Content>
      <ContentHeader>
        <div>
          <div className="sr-only">
            <ContentTitle>Data Factory</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`Azure Data Factory — ${display.startDate} to ${display.endDate}`}
              tags={[
                { value: 'Azure Data Factory', icon: <Factory size={14} />, tone: 'primary' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading || loadingDetails}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Loading error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <ContentMain className="space-y-6">
        {loading ? (
          <Skeleton className="h-[140px]" />
        ) : (
          <Card className="rounded-[2rem] border-border/70">
            <CardContent className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                Data Factory overview
              </p>
              <h2 className="mt-2 text-2xl font-semibold">Click a metric to open pipeline runs.</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Dedicated page with accordion details and pagination — no scroll hunt.
              </p>
            </CardContent>
          </Card>
        )}

        <MetricGrid
          loading={loading}
          skeletonCount={4}
          className="grid grid-cols-1 gap-4 md:grid-cols-4"
        >
          <MetricCard
            label="Runs Azure"
            value={total}
            description="All runs"
            icon={<Workflow />}
            onClick={() => goTo(buildDataFactoryFocusPath('runs'))}
          />
          <MetricCard
            label="Success rate"
            value={`${stats.successRate}%`}
            description={`${stats.succeeded} successful`}
            icon={<CheckCircle2 />}
            tone="success"
            onClick={() => goTo(buildDataFactoryFocusPath('runs', { status: 'succeeded' }))}
          />
          <MetricCard
            label="Visible failures"
            value={stats.failed}
            description="Failed runs"
            icon={<XCircle />}
            tone={stats.failed > 0 ? 'danger' : 'success'}
            onClick={() => goTo(buildDataFactoryFocusPath('runs', { status: 'failed' }))}
          />
          <MetricCard
            label="Running"
            value={stats.running}
            description="Active pipelines"
            icon={<RefreshCw />}
            tone={stats.running > 0 ? 'warning' : 'default'}
            onClick={() => goTo(buildDataFactoryFocusPath('runs', { status: 'running' }))}
          />
        </MetricGrid>

        <Card className="rounded-[1.75rem] border-border/70">
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                  Latest ADF runs
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Filtered Azure Data Factory pipelines for the selected period.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => goTo(buildDataFactoryFocusPath('runs'))}
              >
                View all runs
              </Button>
            </div>
            <PipelineRunAccordion
              runs={runs.slice(0, 8)}
              loading={loading}
              emptyMessage="No ADF pipeline run in this scope. Check collector azure-adf and landing zone filter."
            />
          </CardContent>
        </Card>

        <div className="grid gap-4 md:grid-cols-3">
          <Link to="/datafactoryalerts">
            <FeatureCard
              title="Alerts"
              description="Security alerts for Data Factory resources."
              icon={<AlertTriangle />}
              tone="red"
              badge="Security"
              meta="Azure"
            />
          </Link>
          <Link to="/datafactoryfinops">
            <FeatureCard
              title="Costs & FinOps"
              description="Azure cost view and recommendations."
              icon={<DollarSign />}
              tone="green"
              badge="FinOps"
              meta="Azure"
            />
          </Link>
          <Link to="/datafactorygovernance">
            <FeatureCard
              title="Governance"
              description="Compliance checks for pipelines."
              icon={<ShieldCheck />}
              tone="purple"
              badge="Checks"
              meta="Azure"
            />
          </Link>
        </div>
      </ContentMain>
    </Content>
  );
};

export default DataFactory;
