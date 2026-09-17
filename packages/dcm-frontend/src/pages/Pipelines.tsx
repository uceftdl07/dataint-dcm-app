import { CheckCircle, Clock, Layers, RefreshCw, XCircle } from 'lucide-react';
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
} from '../components/domain';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { useGlobalTimeRange } from '../contexts/time-range';
import { usePipelinesPageData } from '../hooks/usePipelinesPageData';
import { buildPipelinesFocusPath } from '../lib/pipelines/focus-routes';

function formatDuration(seconds: number | null) {
  if (seconds === null) return '—';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${(seconds / 60).toFixed(1)} min`;
}

const Pipelines: React.FC = () => {
  const navigate = useNavigate();
  const { getDisplayRange } = useGlobalTimeRange();
  const { load, loading, loadingDetails, runs, scope, stats, total } = usePipelinesPageData();
  const display = getDisplayRange();
  const durations = runs
    .map((r) => r.duration_seconds)
    .filter((d): d is number => d != null)
    .sort((a, b) => a - b);
  const medianDuration = durations.length > 0 ? durations[Math.floor(durations.length / 2)] : null;
  const medianDurationLabel =
    loadingDetails && medianDuration === null
      ? '—'
      : medianDuration !== null
        ? formatDuration(medianDuration)
        : '—';

  return (
    <Content>
      <ContentHeader>
        <div>
          <ContentTitle>Pipelines</ContentTitle>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={
                loading
                  ? `${display.startDate} to ${display.endDate} — ${scope.label}`
                  : `${display.startDate} to ${display.endDate} — ${total.toLocaleString('en-GB')} runs — ${scope.label}`
              }
              tags={[
                { value: 'Pipelines', icon: <Layers size={14} />, tone: 'primary' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
                { label: 'Runs', value: loading ? '…' : total.toLocaleString('en-GB') },
                { label: 'Scope', value: scope.label },
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
      <ContentMain className="space-y-6">
        {loading ? (
          <Skeleton className="h-[140px]" />
        ) : (
          <Card>
            <CardContent className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                Pipelines overview
              </p>
              <h2 className="mt-2 text-2xl font-semibold">Click a metric to open pipeline runs.</h2>
            </CardContent>
          </Card>
        )}
        <MetricGrid
          loading={loading}
          skeletonCount={4}
          className="grid grid-cols-1 gap-4 md:grid-cols-4"
        >
          <MetricCard
            label="Total runs"
            value={total}
            description="All runs"
            icon={<Layers />}
            onClick={() => navigate(buildPipelinesFocusPath('runs'))}
          />
          <MetricCard
            label="Success rate"
            value={`${stats.successRate}%`}
            description={`${stats.succeeded} successful`}
            icon={<CheckCircle />}
            tone="success"
            onClick={() => navigate(buildPipelinesFocusPath('runs', { status: 'succeeded' }))}
          />
          <MetricCard
            label="Median duration"
            value={medianDurationLabel}
            description="Central run duration"
            icon={<Clock />}
            onClick={() => navigate(buildPipelinesFocusPath('runs'))}
          />
          <MetricCard
            label="Failures 24h"
            value={stats.failed24h}
            description="Failed runs"
            icon={<XCircle />}
            tone={stats.failed24h > 0 ? 'danger' : 'success'}
            onClick={() => navigate(buildPipelinesFocusPath('runs', { status: 'failed' }))}
          />
        </MetricGrid>
      </ContentMain>
    </Content>
  );
};

export default Pipelines;
