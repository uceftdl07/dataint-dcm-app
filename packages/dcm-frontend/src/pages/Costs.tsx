import { Cloud, DollarSign, RefreshCw, Server } from 'lucide-react';
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
import { useCostsPageData } from '../hooks/useCostsPageData';
import { formatCurrency } from '../lib/domain/formatters';
import { buildCostsFocusPath } from '../lib/costs/focus-view';

const Costs: React.FC = () => {
  const navigate = useNavigate();
  const { byService, cloudCount, display, error, load, loading, loadingDetails, scope, summary } =
    useCostsPageData();

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <ContentTitle>Costs</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`Costs from ${display.startDate} to ${display.endDate} — ${scope.label}`}
              tags={[
                { value: 'Costs', icon: <DollarSign size={14} />, tone: 'primary' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
                { label: 'Scope', value: scope.label },
              ]}
            />
          </ContentDescription>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void load()}
          disabled={loading || loadingDetails}
        >
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
                Costs overview
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                Click a metric to open service breakdown.
              </h2>
            </CardContent>
          </Card>
        )}
        <MetricGrid
          loading={loading}
          skeletonCount={2}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        >
          <MetricCard
            label="Total period"
            value={formatCurrency(summary?.total_usd)}
            description="Selected period"
            icon={<DollarSign />}
            tone="cost"
            onClick={() => navigate(buildCostsFocusPath('services'))}
          />
          <MetricCard
            label="Clouds"
            value={cloudCount}
            description="Providers with spending"
            icon={<Cloud />}
            onClick={() => navigate(buildCostsFocusPath('services'))}
          />
        </MetricGrid>
        <MetricGrid
          loading={loadingDetails}
          skeletonCount={1}
          className="grid grid-cols-1 gap-4 sm:grid-cols-3"
        >
          <MetricCard
            label="Services"
            value={byService.length}
            description="Billed services"
            icon={<Server />}
            tone="purple"
            onClick={() => navigate(buildCostsFocusPath('services'))}
          />
        </MetricGrid>
      </ContentMain>
    </Content>
  );
};

export default Costs;
