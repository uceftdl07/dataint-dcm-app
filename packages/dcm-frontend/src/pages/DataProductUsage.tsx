import { Activity, Database, DollarSign, RefreshCw, Users } from 'lucide-react';
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
import { useDataProductUsagePageData } from '../hooks/useDataProductUsagePageData';
import { formatCurrency, formatDateTime } from '../lib/domain/formatters';
import { buildDataProductFocusPath } from '../lib/data-product-usage/focus-routes';

function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat('en-GB').format(value ?? 0);
}

function formatBytes(bytes: number | null | undefined) {
  const value = bytes ?? 0;
  if (value < 1024) return `${formatNumber(value)} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let amount = value / 1024;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

const DataProductUsage: React.FC = () => {
  const navigate = useNavigate();
  const { getDisplayRange } = useGlobalTimeRange();
  const { error, load, loading, loadingDetails, overview, scope } = useDataProductUsagePageData();
  const display = getDisplayRange();
  const goTo = (path: string) => navigate(path);

  return (
    <Content className="mx-auto max-w-[1700px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <ContentTitle>Data Product Usage</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`Unity Catalog usage — ${display.startDate} to ${display.endDate} — ${scope.label}`}
              tags={[
                { value: 'Unity Catalog usage', icon: <Database size={14} />, tone: 'primary' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
                { label: 'Scope', value: scope.label },
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(0)}
            disabled={loading || loadingDetails}
          >
            <RefreshCw size={14} />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {error && <PageError message={error} />}

      <ContentMain className="space-y-6">
        {loading ? (
          <Skeleton className="h-[140px]" />
        ) : (
          <Card className="rounded-[2rem] border-border/70">
            <CardContent className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                Data product overview
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                Click a metric to open usage or consumer details.
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Accordion rows with pagination on dedicated pages.
              </p>
            </CardContent>
          </Card>
        )}

        <MetricGrid
          loading={loading}
          skeletonCount={4}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        >
          <MetricCard
            label="Data products"
            value={formatNumber(overview?.total_data_products)}
            description="Consumed products"
            icon={<Database />}
            tone="purple"
            onClick={() => goTo(buildDataProductFocusPath('usage'))}
          />
          <MetricCard
            label="Active consumers"
            value={formatNumber(overview?.active_consumers)}
            description="Top consumers"
            icon={<Users />}
            tone="success"
            onClick={() => goTo(buildDataProductFocusPath('consumers'))}
          />
          <MetricCard
            label="Data read"
            value={formatBytes(overview?.data_read_bytes)}
            description={`${formatNumber(overview?.request_count)} requests`}
            icon={<Activity />}
            onClick={() => goTo(buildDataProductFocusPath('usage'))}
          />
          <MetricCard
            label="Estimated cost"
            value={formatCurrency(overview?.cost_usd)}
            description={`Last used: ${formatDateTime(overview?.last_used_at)}`}
            icon={<DollarSign />}
            tone="cost"
            onClick={() => goTo(buildDataProductFocusPath('consumers', { metric: 'cost_usd' }))}
          />
        </MetricGrid>
      </ContentMain>
    </Content>
  );
};

export default DataProductUsage;
