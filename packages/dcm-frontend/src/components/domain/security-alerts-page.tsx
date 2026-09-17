import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Filter,
  Layers,
  RefreshCw,
  Search,
} from 'lucide-react';
import * as React from 'react';
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
import { Input } from '../ui/input';
import type { AlertSeverity, CloudProvider, SecurityAlert } from '../../types/api';
import {
  alertSeverityLabels,
  alertSeverityOrder,
  alertStatusLabels,
  alertStatusOrder,
  filterSecurityAlerts,
  getSecurityAlertCounts,
  type AlertStatusFilter,
} from '../../lib/domain/alerts';
import { getFilterControlClass } from '../../lib/domain/filter-styles';
import { useGlobalTimeRange } from '../../contexts/time-range';
import { useAlertsPageQueries } from '../../hooks/useAlertsPageQueries';
import { FilterField, FilterPanel, FilterSelect } from './filter-panel';
import { HeaderTags, type HeaderTag } from './header-tags';
import { headerTagsDescriptionClass } from './header-tags.styles';
import { ListPagination } from './list-pagination';
import { MetricCard, MetricGrid } from './metric-card';
import { PageError, PageVerdict } from './states';
import { SecurityAlertAccordion } from './security-alert-accordion';
import { useClientPagination } from '../../hooks/useClientPagination';

export function SecurityAlertsPage({
  title,
  description,
  headerTags,
  icon,
  emptyTitle,
  resourceFallback,
  resourceFilterLabel = 'Resource',
  cloudProvider = 'azure',
  scopeAlerts,
}: {
  title: string;
  description: (startDate: string, endDate: string) => string;
  headerTags?: (startDate: string, endDate: string) => HeaderTag[];
  icon: React.ReactNode;
  emptyTitle: string;
  resourceFallback: string;
  resourceFilterLabel?: string;
  cloudProvider?: CloudProvider | 'all';
  scopeAlerts?: (alerts: SecurityAlert[]) => SecurityAlert[];
}) {
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const [error, setError] = React.useState<string | null>(null);
  const [selectedSeverity, setSelectedSeverity] = React.useState<AlertSeverity | ''>('');
  const [selectedResourceType, setSelectedResourceType] = React.useState('');
  const [selectedResourceId, setSelectedResourceId] = React.useState('');
  const [selectedStatus, setSelectedStatus] = React.useState<AlertStatusFilter>('open');
  const [search, setSearch] = React.useState('');

  const { start_date, end_date } = getApiParams();
  const provider = cloudProvider === 'all' ? undefined : cloudProvider;
  const {
    items: alerts,
    loading,
    error: fetchError,
    reload: load,
  } = useAlertsPageQueries({
    start_date,
    end_date,
    cloud_provider: provider,
    limit: 200,
  });

  React.useEffect(() => {
    if (!fetchError) {
      setError(null);
      return;
    }
    setError(fetchError instanceof Error ? fetchError.message : 'Error while loading alerts');
  }, [fetchError]);

  const display = getDisplayRange();

  const scopedAlerts = React.useMemo(() => {
    if (!scopeAlerts) return alerts;
    const selectedAlerts = scopeAlerts(alerts);
    return selectedAlerts.length > 0 ? selectedAlerts : alerts;
  }, [alerts, scopeAlerts]);

  const resourceTypes = React.useMemo(() => {
    return Array.from(
      new Set(
        scopedAlerts
          .map((alert) => alert.resource_type)
          .filter((value): value is string => Boolean(value))
      )
    ).sort();
  }, [scopedAlerts]);

  const resourceIds = React.useMemo(() => {
    return Array.from(
      new Set(
        scopedAlerts
          .map((alert) => alert.resource_id)
          .filter((value): value is string => Boolean(value))
      )
    ).sort();
  }, [scopedAlerts]);

  const filteredAlerts = React.useMemo(() => {
    return filterSecurityAlerts(scopedAlerts, {
      severity: selectedSeverity,
      status: selectedStatus,
      resourceType: selectedResourceType,
      resourceId: selectedResourceId,
      search,
    });
  }, [
    scopedAlerts,
    search,
    selectedResourceId,
    selectedResourceType,
    selectedSeverity,
    selectedStatus,
  ]);

  const counts = React.useMemo(
    () => getSecurityAlertCounts(scopedAlerts, resourceTypes.length),
    [scopedAlerts, resourceTypes.length]
  );
  const alertPagination = useClientPagination(filteredAlerts, 10);
  const hasAlertsToReview = counts.critical > 0 || counts.high > 0 || counts.active > 0;
  const headerDescription = description(display.startDate, display.endDate);
  const visibleHeaderTags = headerTags?.(display.startDate, display.endDate) ?? [
    {
      value: resourceFallback === 'Cloud' ? 'Multi-cloud' : `Azure ${resourceFallback}`,
      icon,
      tone: 'danger' as const,
    },
    { label: 'Type', value: 'Alerts' },
    { label: 'From', value: display.startDate },
    { label: 'To', value: display.endDate },
  ];

  const activeFilterCount = [
    search.trim(),
    selectedSeverity,
    selectedResourceType,
    selectedResourceId,
    selectedStatus !== 'open' ? selectedStatus : '',
  ].filter(Boolean).length;

  const resetFilters = () => {
    setSearch('');
    setSelectedSeverity('');
    setSelectedResourceType('');
    setSelectedResourceId('');
    setSelectedStatus('open');
  };

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <div className="rounded-xl bg-primary p-2 text-primary-foreground">{icon}</div>
            <ContentTitle>{title}</ContentTitle>
          </div>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags description={headerDescription} tags={visibleHeaderTags} />
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{filteredAlerts.length} shown</Badge>
          <Badge variant="outline">{alerts.length} total</Badge>
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
            title={hasAlertsToReview ? 'Needs attention' : 'No open alerts in scope'}
            description={
              hasAlertsToReview
                ? `${counts.active} active alert(s), including ${counts.critical} critical and ${counts.high} high severity item(s), are visible for this scope.`
                : 'No open alerts are visible for this scope and period. If collection is active, this scope can be treated as clear.'
            }
            tone={hasAlertsToReview ? 'danger' : 'success'}
            icon={hasAlertsToReview ? <AlertTriangle size={18} /> : <CheckCircle size={18} />}
            badge={display.description}
          />
        )}

        <MetricGrid
          loading={loading}
          skeletonCount={5}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
        >
          <MetricCard
            label="Critical"
            value={counts.critical}
            description="Highest priority alerts"
            icon={<AlertCircle />}
            tone="danger"
            active={selectedSeverity === 'critical'}
            onClick={() => setSelectedSeverity((value) => (value === 'critical' ? '' : 'critical'))}
          />
          <MetricCard
            label="High"
            value={counts.high}
            description="Alerts needing quick review"
            icon={<AlertTriangle />}
            tone="warning"
            active={selectedSeverity === 'high'}
            onClick={() => setSelectedSeverity((value) => (value === 'high' ? '' : 'high'))}
          />
          <MetricCard
            label="Active"
            value={counts.active}
            description="Still open"
            icon={<Activity />}
            tone="danger"
            active={selectedStatus === 'active'}
            onClick={() => setSelectedStatus((value) => (value === 'active' ? 'open' : 'active'))}
          />
          <MetricCard
            label="Resources"
            value={counts.resourceTypes}
            description="Impacted resource types"
            icon={<Layers />}
          />
          <MetricCard
            label="Resolved"
            value={counts.resolved}
            description="Closed alerts"
            icon={<CheckCircle />}
            tone="success"
            active={selectedStatus === 'resolved'}
            onClick={() =>
              setSelectedStatus((value) => (value === 'resolved' ? 'open' : 'resolved'))
            }
          />
        </MetricGrid>

        <FilterPanel
          title="Alert filters"
          description="Refine alerts by search, severity, resource, and status."
          icon={<Filter size={16} />}
          resultCount={filteredAlerts.length}
          activeFilterCount={activeFilterCount}
          emptyLabel="Needs attention view"
          tone="red"
          resetDisabled={activeFilterCount === 0 && selectedStatus === 'open'}
          onReset={resetFilters}
          className="grid grid-cols-1 items-end gap-4 pt-0 md:grid-cols-2 lg:grid-cols-[minmax(220px,1.35fr)_repeat(4,minmax(150px,1fr))]"
        >
          <FilterField label="Search" htmlFor={`${resourceFallback}-alert-search`}>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-muted-foreground" />
              <Input
                id={`${resourceFallback}-alert-search`}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search"
                className={`${getFilterControlClass('red')} pl-9`}
              />
            </div>
          </FilterField>
          <FilterField label="Severity" htmlFor={`${resourceFallback}-alert-severity`}>
            <FilterSelect
              id={`${resourceFallback}-alert-severity`}
              tone="red"
              value={selectedSeverity}
              onChange={(event) => setSelectedSeverity(event.target.value as AlertSeverity | '')}
            >
              <option value="">All severities</option>
              {alertSeverityOrder.map((severity) => (
                <option key={severity} value={severity}>
                  {alertSeverityLabels[severity]}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Type" htmlFor={`${resourceFallback}-alert-type`}>
            <FilterSelect
              id={`${resourceFallback}-alert-type`}
              tone="red"
              value={selectedResourceType}
              onChange={(event) => setSelectedResourceType(event.target.value)}
            >
              <option value="">All types</option>
              {resourceTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label={resourceFilterLabel} htmlFor={`${resourceFallback}-alert-resource`}>
            <FilterSelect
              id={`${resourceFallback}-alert-resource`}
              tone="red"
              value={selectedResourceId}
              onChange={(event) => setSelectedResourceId(event.target.value)}
            >
              <option value="">All resources</option>
              {resourceIds.map((resource) => (
                <option key={resource} value={resource}>
                  {resource}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Status" htmlFor={`${resourceFallback}-alert-status`}>
            <FilterSelect
              id={`${resourceFallback}-alert-status`}
              tone="red"
              value={selectedStatus}
              onChange={(event) => setSelectedStatus(event.target.value as AlertStatusFilter)}
            >
              <option value="open">Needs attention</option>
              <option value="">All statuses</option>
              {alertStatusOrder.map((status) => (
                <option key={status} value={status}>
                  {alertStatusLabels[status]}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
        </FilterPanel>

        <SecurityAlertAccordion
          alerts={alertPagination.pageItems}
          loading={loading}
          emptyMessage={emptyTitle}
          resetKey={`${alertPagination.currentPage}-${filteredAlerts.length}`}
        />
        <ListPagination
          currentPage={alertPagination.currentPage}
          endIndex={alertPagination.endIndex}
          hasNextPage={alertPagination.hasNextPage}
          hasPreviousPage={alertPagination.hasPreviousPage}
          onNext={alertPagination.nextPage}
          onPrevious={alertPagination.previousPage}
          startIndex={alertPagination.startIndex}
          totalItems={alertPagination.totalItems}
          totalPages={alertPagination.totalPages}
        />
      </ContentMain>
    </Content>
  );
}
