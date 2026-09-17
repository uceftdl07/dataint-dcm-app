import { AlertCircle, CheckCircle2, PowerOff, RefreshCw, Server } from 'lucide-react';
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
  PageError,
} from '../components/domain';
import {
  Content,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { useClustersPageData } from '../hooks/useClustersPageData';
import { buildClustersFocusPath } from '../lib/clusters/focus-view';

const Computes: React.FC = () => {
  const navigate = useNavigate();
  const { computes, error, errorCount, load, loading, runningCount, scope, terminatedCount } =
    useClustersPageData();

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <ContentTitle>Compute</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`${computes.length} compute — ${runningCount} active — ${scope.label}${errorCount > 0 ? ` — ${errorCount} in error` : ''}`}
              tags={[
                { value: 'Compute', icon: <Server size={14} />, tone: 'primary' },
                { label: 'Total', value: computes.length },
                { label: 'Active', value: runningCount },
                { label: 'Scope', value: scope.label },
                ...(errorCount > 0
                  ? [{ label: 'Errors', value: errorCount, tone: 'danger' as const }]
                  : []),
              ]}
            />
          </ContentDescription>
        </div>
        <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
          <RefreshCw />
          Refresh
        </Button>
      </ContentHeader>
      {error && <PageError message={error} />}
      <ContentMain className="space-y-6">
        {loading ? (
          <Skeleton className="h-[140px]" />
        ) : (
          <Card>
            <CardContent className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                Compute overview
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                Click a metric to open cluster inventory.
              </h2>
            </CardContent>
          </Card>
        )}
        <MetricGrid
          loading={loading}
          skeletonCount={3}
          className="grid grid-cols-1 gap-4 sm:grid-cols-3"
        >
          <MetricCard
            label="Active"
            value={runningCount}
            description="Running clusters"
            icon={<CheckCircle2 />}
            tone="success"
            onClick={() => navigate(buildClustersFocusPath('inventory', { state: 'running' }))}
          />
          <MetricCard
            label="In error"
            value={errorCount}
            description="Clusters in error"
            icon={<AlertCircle />}
            tone={errorCount > 0 ? 'danger' : 'success'}
            onClick={() => navigate(buildClustersFocusPath('inventory', { state: 'error' }))}
          />
          <MetricCard
            label="Terminated"
            value={terminatedCount}
            description="Stopped clusters"
            icon={<PowerOff />}
            onClick={() => navigate(buildClustersFocusPath('inventory', { state: 'terminated' }))}
          />
        </MetricGrid>
      </ContentMain>
    </Content>
  );
};

export default Computes;
