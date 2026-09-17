import { CheckCircle2, Filter, Info, RefreshCw, Search, ShieldCheck, XCircle } from 'lucide-react';
import * as React from 'react';
import { getDcmApiErrorMessage, isDcmDatabaseUnavailableError } from '../../api/dcmApiClient';
import { useGlobalTimeRange } from '../../contexts/time-range';
import { useGovernancePageQueries } from '../../hooks/useGovernancePageQueries';
import {
  filterStandardChecks,
  getStandardCheckCounts,
  standardCheckStateLabels,
  type CheckEffectFilter,
} from '../../lib/domain/governance';
import type { CloudProvider, StandardCheck, StandardCheckState } from '../../types/api';
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
import { FilterField, FilterPanel, FilterSelect } from './filter-panel';
import { HeaderTags } from './header-tags';
import { headerTagsDescriptionClass } from './header-tags.styles';
import { MetricCard, MetricGrid } from './metric-card';
import { PageError, PageNotice } from './states';
import { StandardChecksTable } from './standard-checks-table';

const databaseUnavailableMessage =
  'DCM API is running, but the Databricks warehouse connection is not initialized. Check backend Databricks credentials/warehouse configuration, then refresh this page.';

export function StandardChecksPage({
  title,
  description,
  icon,
  emptyTitle,
  resourceFallback,
  showSource = false,
  scopeChecks,
  cloudProvider = 'azure',
}: {
  title: string;
  description: (startDate: string, endDate: string) => string;
  icon: React.ReactNode;
  emptyTitle: string;
  resourceFallback: string;
  showSource?: boolean;
  scopeChecks?: (checks: StandardCheck[]) => StandardCheck[];
  cloudProvider?: CloudProvider | 'all';
}) {
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const [notice, setNotice] = React.useState<string | null>(null);
  const [selectedState, setSelectedState] = React.useState<StandardCheckState | ''>('');
  const [selectedResourceType, setSelectedResourceType] = React.useState('');
  const [selectedEffect, setSelectedEffect] = React.useState<CheckEffectFilter>('');
  const [selectedSource, setSelectedSource] = React.useState('');
  const [search, setSearch] = React.useState('');

  const { start_date, end_date } = getApiParams();
  const provider = cloudProvider === 'all' ? undefined : cloudProvider;

  const {
    checks,
    score,
    loading,
    loadingDetails,
    error: fetchError,
    reload: load,
  } = useGovernancePageQueries({
    start_date,
    end_date,
    cloud_provider: provider,
    limit: 100,
  });

  React.useEffect(() => {
    if (!fetchError) {
      setNotice(null);
      return;
    }
    if (isDcmDatabaseUnavailableError(fetchError)) {
      setNotice(databaseUnavailableMessage);
      return;
    }
    setNotice(null);
  }, [fetchError]);

  const error =
    fetchError && !notice
      ? getDcmApiErrorMessage(fetchError, `Error while loading ${resourceFallback} checks`)
      : null;

  const display = getDisplayRange();

  const scopedChecks = React.useMemo(() => {
    if (!scopeChecks) return checks;
    const selectedChecks = scopeChecks(checks);
    return selectedChecks.length > 0 ? selectedChecks : checks;
  }, [checks, scopeChecks]);

  const resourceTypes = React.useMemo(() => {
    return Array.from(
      new Set(
        scopedChecks
          .map((check) => check.resource_type)
          .filter((value): value is string => Boolean(value))
      )
    ).sort();
  }, [scopedChecks]);

  const sources = React.useMemo(() => {
    return Array.from(
      new Set(scopedChecks.map((check) => check.source_lz_id).filter(Boolean))
    ).sort();
  }, [scopedChecks]);

  const filteredChecks = React.useMemo(() => {
    return filterStandardChecks(scopedChecks, {
      state: selectedState,
      resourceType: selectedResourceType,
      effect: selectedEffect,
      source: selectedSource,
      search,
    });
  }, [scopedChecks, search, selectedEffect, selectedResourceType, selectedSource, selectedState]);

  const counts = React.useMemo(
    () => getStandardCheckCounts(scopedChecks, resourceTypes.length),
    [resourceTypes.length, scopedChecks]
  );

  const activeFilterCount = [
    search.trim(),
    selectedState,
    selectedResourceType,
    selectedEffect,
    selectedSource,
  ].filter(Boolean).length;
  const headerDescription = description(display.startDate, display.endDate);

  const resetFilters = () => {
    setSearch('');
    setSelectedState('');
    setSelectedResourceType('');
    setSelectedEffect('');
    setSelectedSource('');
  };

  const reload = React.useCallback(() => {
    void load();
  }, [load]);

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
                {
                  value: resourceFallback === 'multi-cloud' ? 'Multi-cloud' : resourceFallback,
                  icon,
                  tone: 'primary',
                },
                { label: 'Type', value: 'Compliance checks' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{filteredChecks.length} shown</Badge>
          <Badge variant="outline">{scopedChecks.length} total</Badge>
          {score && (
            <Badge variant="outline">{score.global_score_pct ?? 0}% global compliance</Badge>
          )}
          <Button variant="secondary" size="sm" onClick={reload} disabled={loading}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {notice && <PageNotice title="DCM data unavailable" message={notice} />}
      {error && <PageError message={error} />}

      <ContentMain>
        <MetricGrid loading={loading}>
          <MetricCard
            label="Compliant"
            value={counts.compliant}
            description="Validated checks"
            icon={<CheckCircle2 />}
            tone="success"
            active={selectedState === 'compliant'}
            onClick={() => setSelectedState((value) => (value === 'compliant' ? '' : 'compliant'))}
          />
          <MetricCard
            label="Non-compliant"
            value={counts.noCompliant}
            description="Fix first"
            icon={<XCircle />}
            tone="danger"
            active={selectedState === 'no_compliant'}
            onClick={() =>
              setSelectedState((value) => (value === 'no_compliant' ? '' : 'no_compliant'))
            }
          />
          <MetricCard
            label="Unknowns"
            value={counts.unknown}
            description="Checks to qualify"
            icon={<Info />}
            tone="warning"
            active={selectedState === 'unknown'}
            onClick={() => setSelectedState((value) => (value === 'unknown' ? '' : 'unknown'))}
          />
          <MetricCard
            label="Resources"
            value={counts.resources}
            description="Checked resource types"
            icon={<ShieldCheck />}
          />
        </MetricGrid>

        <FilterPanel
          title="Governance filters"
          description="Refine checks by state, resource, effect, or source."
          icon={<Filter size={16} />}
          resultCount={filteredChecks.length}
          activeFilterCount={activeFilterCount}
          emptyLabel="Governance view"
          tone="blue"
          onReset={resetFilters}
          className="grid grid-cols-1 items-end gap-4 pt-0 md:grid-cols-2 xl:grid-cols-3"
        >
          <FilterField label="Search" htmlFor={`${resourceFallback}-check-search`}>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
              <Input
                id={`${resourceFallback}-check-search`}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Check name, resource, type, source…"
                className="pl-9"
              />
            </div>
          </FilterField>
          <FilterField label="State" htmlFor={`${resourceFallback}-check-state`}>
            <FilterSelect
              id={`${resourceFallback}-check-state`}
              value={selectedState}
              onChange={(event) => setSelectedState(event.target.value as StandardCheckState | '')}
            >
              <option value="">All states</option>
              <option value="compliant">{standardCheckStateLabels.compliant}</option>
              <option value="no_compliant">{standardCheckStateLabels.no_compliant}</option>
              <option value="unknown">{standardCheckStateLabels.unknown}</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Type ressource" htmlFor={`${resourceFallback}-check-resource-type`}>
            <FilterSelect
              id={`${resourceFallback}-check-resource-type`}
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
          <FilterField label="Effet" htmlFor={`${resourceFallback}-check-effect`}>
            <FilterSelect
              id={`${resourceFallback}-check-effect`}
              value={selectedEffect}
              onChange={(event) => setSelectedEffect(event.target.value as CheckEffectFilter)}
            >
              <option value="">All effects</option>
              <option value="critical">Critical</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
              <option value="other">Autre</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Source" htmlFor={`${resourceFallback}-check-source`}>
            <FilterSelect
              id={`${resourceFallback}-check-source`}
              value={selectedSource}
              onChange={(event) => setSelectedSource(event.target.value)}
            >
              <option value="">All sources</option>
              {sources.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
        </FilterPanel>

        <StandardChecksTable
          checks={filteredChecks}
          allChecksCount={scopedChecks.length}
          loading={loading}
          title={`Compliance checks ${resourceFallback}`}
          emptyTitle={emptyTitle}
          emptyDescription="No check matches the selected filters."
          resourceFallback={resourceFallback}
          showSource={showSource}
        />
        {loadingDetails && !loading && (
          <p className="text-xs text-muted-foreground">Loading additional checks…</p>
        )}
      </ContentMain>
    </Content>
  );
}
