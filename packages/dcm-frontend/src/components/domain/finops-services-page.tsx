import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Database,
  DollarSign,
  Filter,
  RefreshCw,
  Settings,
  Target,
  Zap,
} from 'lucide-react';
import * as React from 'react';
import { useGlobalTimeRange } from '../../contexts/time-range';
import { useFinOpsPageQueries } from '../../hooks/useFinOpsPageQueries';
import {
  filterFinOpsServiceCosts,
  getBudgetLabel,
  getBudgetStatus,
  type BudgetFilter,
  type TrendDirection,
} from '../../lib/domain/finops';
import { formatCurrency, formatPercentage } from '../../lib/domain/formatters';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../layout/content';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { FilterField, FilterPanel, FilterSelect } from './filter-panel';
import { FinOpsServiceCostTable } from './finops-service-cost-table';
import { HeaderTags } from './header-tags';
import { headerTagsDescriptionClass } from './header-tags.styles';
import { MetricCard, MetricGrid, type MetricTone } from './metric-card';
import { MutedCardMessage, SummaryCard } from './summary-card';
import { PageError, PageVerdict } from './states';

export function FinOpsServicesPage({
  title,
  description,
  icon,
  serviceMetricLabel,
  serviceMetricDescription,
  contextHeader,
  contextLabel,
  emptyTitle,
  recommendationsDescription,
  synthesisDescription,
  isInScope,
  getContextValue,
}: {
  title: string;
  description: (startDate: string, endDate: string) => string;
  icon: React.ReactNode;
  serviceMetricLabel: string;
  serviceMetricDescription: string;
  contextHeader: string;
  contextLabel: string;
  emptyTitle: string;
  recommendationsDescription: string;
  synthesisDescription: string;
  isInScope: (serviceName: string) => boolean;
  getContextValue: (serviceName: string) => string;
}) {
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const [selectedService, setSelectedService] = React.useState('');
  const [selectedProvider, setSelectedProvider] = React.useState('');
  const [selectedBudgetStatus, setSelectedBudgetStatus] = React.useState<BudgetFilter>('');
  const [selectedTrend, setSelectedTrend] = React.useState<TrendDirection | ''>('');

  const { start_date, end_date } = getApiParams();
  const finOpsQuery = useFinOpsPageQueries({
    start_date,
    end_date,
    cloud_provider: 'azure',
  });

  const costSummary = finOpsQuery.summary;
  const servicesCosts = React.useMemo(() => {
    const items = finOpsQuery.byService.items ?? [];
    const scopedItems = items.filter((item) => isInScope(item.service_name));
    const visibleItems = scopedItems.length > 0 ? scopedItems : items;
    return visibleItems.map((item) => ({
      serviceName: item.service_name,
      cloudProvider: item.cloud_provider,
      monthlyCost: item.total_cost_usd,
      budgetPercentage: item.avg_budget_consumed_pct,
      contextLabel,
      contextValue: getContextValue(item.service_name),
      trend: { direction: 'stable' as const, percentageChange: 0 },
    }));
  }, [contextLabel, finOpsQuery.byService.items, getContextValue, isInScope]);

  const loading = finOpsQuery.loading;
  const loadingDetails = finOpsQuery.loadingDetails;
  const error = finOpsQuery.error
    ? finOpsQuery.error instanceof Error
      ? finOpsQuery.error.message
      : 'Error while loading FinOps data'
    : null;
  const load = React.useCallback(() => {
    void finOpsQuery.reload();
  }, [finOpsQuery]);

  const display = getDisplayRange();

  const services = React.useMemo(() => {
    return Array.from(
      new Set(servicesCosts.map((service) => service.serviceName).filter(Boolean))
    ).sort();
  }, [servicesCosts]);

  const providers = React.useMemo(() => {
    return Array.from(
      new Set(servicesCosts.map((service) => service.cloudProvider).filter(Boolean))
    ).sort();
  }, [servicesCosts]);

  const contexts = React.useMemo(() => {
    return Array.from(
      new Set(servicesCosts.map((service) => service.contextValue).filter(Boolean))
    ).sort();
  }, [servicesCosts]);

  const filteredServices = React.useMemo(() => {
    return filterFinOpsServiceCosts(servicesCosts, {
      service: selectedService,
      provider: selectedProvider,
      budgetStatus: selectedBudgetStatus,
      trend: selectedTrend,
    });
  }, [selectedBudgetStatus, selectedProvider, selectedService, selectedTrend, servicesCosts]);

  const totalFilteredCost = React.useMemo(() => {
    return filteredServices.reduce((sum, service) => sum + service.monthlyCost, 0);
  }, [filteredServices]);

  const totalScopedCost = React.useMemo(() => {
    return servicesCosts.reduce((sum, service) => sum + service.monthlyCost, 0);
  }, [servicesCosts]);

  const budgetedServices = servicesCosts.filter((service) => service.budgetPercentage !== null);
  const averageBudget =
    budgetedServices.length > 0
      ? budgetedServices.reduce((sum, service) => sum + (service.budgetPercentage ?? 0), 0) /
        budgetedServices.length
      : null;

  const activeFilterCount = [
    selectedService,
    selectedProvider,
    selectedBudgetStatus,
    selectedTrend,
  ].filter(Boolean).length;

  const resetFilters = () => {
    setSelectedService('');
    setSelectedProvider('');
    setSelectedBudgetStatus('');
    setSelectedTrend('');
  };

  const budgetTone: MetricTone =
    averageBudget === null
      ? 'default'
      : averageBudget >= 100
        ? 'danger'
        : averageBudget >= 80
          ? 'warning'
          : 'success';
  const hasCostData = servicesCosts.length > 0;
  const costVerdictTone = !hasCostData
    ? 'warning'
    : averageBudget === null
      ? 'warning'
      : averageBudget >= 100
        ? 'danger'
        : averageBudget >= 80
          ? 'warning'
          : 'success';
  const headerDescription = description(display.startDate, display.endDate);

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <div className="rounded-xl bg-primary p-2 text-primary-foreground">{icon}</div>
            <ContentTitle>{title}</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={headerDescription}
              tags={[
                { value: serviceMetricLabel, icon, tone: 'primary' },
                { label: 'Type', value: 'Costs' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{filteredServices.length} shown</Badge>
          <Badge variant="outline">{formatCurrency(totalFilteredCost)}</Badge>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {error && <PageError message={error} />}

      <ContentMain>
        {!loading && (
          <PageVerdict
            title={
              !hasCostData
                ? 'Cost data unavailable'
                : averageBudget === null
                  ? 'Budget data unavailable'
                  : averageBudget >= 100
                    ? 'Budget overrun'
                    : averageBudget >= 80
                      ? 'To monitor'
                      : 'Costs controlled'
            }
            description={
              !hasCostData
                ? 'No FinOps line is available for this scope and period. Check collection status or widen the period before treating this as zero spend.'
                : averageBudget === null
                  ? 'Costs are available but Azure/AWS budget fields were not collected for this period. Check collector permissions and budget configuration.'
                  : averageBudget >= 100
                    ? `${serviceMetricLabel} budget consumption is above target on average; review the highest cost services first.`
                    : averageBudget >= 80
                      ? `${serviceMetricLabel} costs are close to budget thresholds; keep monitoring this period.`
                      : `${serviceMetricLabel} costs are within the current budget thresholds for the selected period.`
            }
            tone={costVerdictTone}
            icon={
              costVerdictTone === 'success' ? (
                <CheckCircle2 size={18} />
              ) : (
                <AlertTriangle size={18} />
              )
            }
            badge={display.description}
          />
        )}

        <MetricGrid loading={loading}>
          <MetricCard
            label="Cost total"
            value={formatCurrency(totalScopedCost)}
            description="Azure spend over the period"
            icon={<DollarSign />}
            tone="cost"
          />
          <MetricCard
            label={serviceMetricLabel}
            value={servicesCosts.length}
            description={serviceMetricDescription}
            icon={<Database />}
            tone="default"
          />
          <MetricCard
            label={contextHeader}
            value={contexts.length}
            description="Tracked categories"
            icon={<BarChart3 />}
            tone="purple"
          />
          <MetricCard
            label="Average budget"
            value={averageBudget === null ? '—' : formatPercentage(averageBudget)}
            description={
              averageBudget === null ? 'No budget configured' : getBudgetLabel(averageBudget)
            }
            icon={<Target />}
            tone={budgetTone}
            active={selectedBudgetStatus === getBudgetStatus(averageBudget)}
            onClick={() =>
              setSelectedBudgetStatus((value) =>
                value === getBudgetStatus(averageBudget) ? '' : getBudgetStatus(averageBudget)
              )
            }
          />
        </MetricGrid>

        <FilterPanel
          title="FinOps filters"
          description="Refine costs by service, provider, budget, or trend."
          icon={<Filter size={16} />}
          resultCount={filteredServices.length}
          activeFilterCount={activeFilterCount}
          emptyLabel="Cost view"
          tone="blue"
          onReset={resetFilters}
        >
          <FilterField label="Service" htmlFor={`${title}-finops-service`}>
            <FilterSelect
              id={`${title}-finops-service`}
              value={selectedService}
              onChange={(event) => setSelectedService(event.target.value)}
            >
              <option value="">All services</option>
              {services.map((service) => (
                <option key={service} value={service}>
                  {service}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Provider" htmlFor={`${title}-finops-provider`}>
            <FilterSelect
              id={`${title}-finops-provider`}
              value={selectedProvider}
              onChange={(event) => setSelectedProvider(event.target.value)}
            >
              <option value="">All providers</option>
              {providers.map((provider) => (
                <option key={provider} value={provider}>
                  {provider}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Budget" htmlFor={`${title}-finops-budget`}>
            <FilterSelect
              id={`${title}-finops-budget`}
              value={selectedBudgetStatus}
              onChange={(event) => setSelectedBudgetStatus(event.target.value as BudgetFilter)}
            >
              <option value="">All budgets</option>
              <option value="controlled">Controlled</option>
              <option value="watch">To monitor</option>
              <option value="overBudget">Over budget</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Trend" htmlFor={`${title}-finops-trend`}>
            <FilterSelect
              id={`${title}-finops-trend`}
              value={selectedTrend}
              onChange={(event) => setSelectedTrend(event.target.value as TrendDirection | '')}
            >
              <option value="">All trends</option>
              <option value="stable">Stable</option>
              <option value="up">Increasing</option>
              <option value="down">Decreasing</option>
            </FilterSelect>
          </FilterField>
        </FilterPanel>

        <FinOpsServiceCostTable
          items={filteredServices}
          allItemsCount={servicesCosts.length}
          loading={loading || loadingDetails}
          title={`Costs by service ${serviceMetricLabel}`}
          emptyTitle={emptyTitle}
          emptyDescription="No service matches the selected filters."
          contextHeader={contextHeader}
        />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <SummaryCard
            title="Summary"
            description={synthesisDescription}
            icon={<BarChart3 className="size-5 text-emerald-600" />}
            badge={costSummary?.by_service.length ?? 0}
          >
            <MutedCardMessage
              icon={<Target size={30} />}
              title="Detailed summary to connect"
              description="Detailed costs can be isolated as soon as the API exposes them."
            />
          </SummaryCard>

          <SummaryCard
            title="Recommandations"
            description={recommendationsDescription}
            icon={<Zap className="size-5 text-orange-600" />}
            badge={0}
          >
            <MutedCardMessage
              icon={<Settings size={30} />}
              title="No recommendation available"
              description="Recommendations will appear when optimizations are exposed by the API."
            />
          </SummaryCard>
        </div>
      </ContentMain>
    </Content>
  );
}
