import { ArrowLeft, Copy, RefreshCw, Search } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import {
  FilterField,
  FilterPanel,
  FilterSelect,
  PageError,
  PageNotice,
} from '../components/domain';
import { ClustersFocusView } from '../components/domain/databricks/views/clusters-focus-view';
import { CostsFocusView } from '../components/domain/databricks/views/costs-focus-view';
import { GovernanceFocusView } from '../components/domain/databricks/views/governance-focus-view';
import { JobsFocusView } from '../components/domain/databricks/views/jobs-focus-view';
import { SecurityAlertsFocusView } from '../components/domain/databricks/views/security-alerts-focus-view';
import { WorkspacesFocusView } from '../components/domain/databricks/views/workspaces-focus-view';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useDatabricksPageData } from '../hooks/useDatabricksPageData';
import { DATABRICKS_MODULE_FOCUS_PATHS } from '../lib/databricks/focus-routes';
import {
  DATABRICKS_FOCUS_VIEW_DESCRIPTIONS,
  DATABRICKS_FOCUS_VIEW_LABELS,
  parseClusterStateFromUrl,
  parseDatabricksFocusView,
  type DatabricksFocusView,
} from '../lib/databricks/focus-view';
import type { ComputeState } from '../types/api';

const states: Array<ComputeState | ''> = ['', 'running', 'terminated', 'error', 'unknown'];
const jobStatuses = ['', 'succeeded', 'failed', 'running', 'cancelled', 'skipped'];

function formatState(state: ComputeState | '') {
  if (!state) return 'All states';
  return state.charAt(0).toUpperCase() + state.slice(1);
}

function formatJobStatus(status: string) {
  if (!status) return 'All statuses';
  return status.charAt(0).toUpperCase() + status.slice(1);
}

const DatabricksFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parseDatabricksFocusView(viewParam ?? null);

  const urlState = parseClusterStateFromUrl(searchParams.get('state'));
  const urlJobStatus = searchParams.get('jobStatus') ?? '';

  const {
    error,
    focusViewData,
    jobStatusFilter,
    load,
    loading,
    notice,
    resetFilters,
    search,
    setJobStatusFilter,
    setSearch,
    setStateFilter,
    stateFilter,
  } = useDatabricksPageData({
    initialJobStatusFilter: urlJobStatus,
    initialStateFilter: urlState,
  });

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setStateFilter(urlState);
  }, [urlState, setStateFilter]);

  useEffect(() => {
    setJobStatusFilter(urlJobStatus);
  }, [urlJobStatus, setJobStatusFilter]);

  const syncUrlFilters = useCallback(
    (patch: { state?: ComputeState | ''; jobStatus?: string }) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (patch.state !== undefined) {
            if (patch.state) next.set('state', patch.state);
            else next.delete('state');
          }
          if (patch.jobStatus !== undefined) {
            if (patch.jobStatus) next.set('jobStatus', patch.jobStatus);
            else next.delete('jobStatus');
          }
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const copyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, []);

  if (!view) {
    return <Navigate to="/databricks" replace />;
  }

  if (view === 'costs') {
    return <Navigate to={DATABRICKS_MODULE_FOCUS_PATHS.costs} replace />;
  }
  if (view === 'security-alerts') {
    return <Navigate to={DATABRICKS_MODULE_FOCUS_PATHS.alerts} replace />;
  }
  if (view === 'governance') {
    return <Navigate to={DATABRICKS_MODULE_FOCUS_PATHS.governance} replace />;
  }

  const showFilters = view === 'clusters' || view === 'jobs';
  const activeFilterCount = [stateFilter, jobStatusFilter, search].filter(Boolean).length;

  const renderView = (focusView: DatabricksFocusView) => {
    switch (focusView) {
      case 'clusters':
        return <ClustersFocusView data={focusViewData} />;
      case 'jobs':
        return <JobsFocusView data={focusViewData} />;
      case 'costs':
        return <CostsFocusView data={focusViewData} />;
      case 'workspaces':
        return <WorkspacesFocusView data={focusViewData} />;
      case 'security-alerts':
        return <SecurityAlertsFocusView data={focusViewData} />;
      case 'governance':
        return <GovernanceFocusView data={focusViewData} />;
      default:
        return null;
    }
  };

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/databricks">
              <ArrowLeft size={16} />
              Back to Databricks overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{DATABRICKS_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{DATABRICKS_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
          </div>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void copyLink()}>
            <Copy size={14} />
            {copied ? 'Link copied' : 'Copy link'}
          </Button>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {notice && <PageNotice title="DCM data unavailable" message={notice} />}
      {error && <PageError message={error} />}

      <ContentMain className="space-y-6">
        {showFilters && (
          <FilterPanel
            title="Filters"
            description="Refine the list below. Scope and period come from the header."
            resultCount={
              view === 'jobs'
                ? focusViewData.filteredWorkloadRows.length
                : focusViewData.filteredClusters.length
            }
            activeFilterCount={activeFilterCount}
            emptyLabel="Full view"
            onReset={() => {
              resetFilters();
              syncUrlFilters({ state: '', jobStatus: '' });
            }}
            className="grid grid-cols-1 items-end gap-4 pt-0 md:grid-cols-2 xl:grid-cols-4"
          >
            {view === 'clusters' && (
              <FilterField label="State" htmlFor="databricks-focus-state">
                <FilterSelect
                  id="databricks-focus-state"
                  value={stateFilter}
                  onChange={(event) => {
                    const next = event.target.value as ComputeState | '';
                    setStateFilter(next);
                    syncUrlFilters({ state: next });
                  }}
                >
                  {states.map((state) => (
                    <option key={state || 'all'} value={state}>
                      {formatState(state)}
                    </option>
                  ))}
                </FilterSelect>
              </FilterField>
            )}
            {view === 'jobs' && (
              <FilterField label="Job status" htmlFor="databricks-focus-job-status">
                <FilterSelect
                  id="databricks-focus-job-status"
                  value={jobStatusFilter}
                  onChange={(event) => {
                    const next = event.target.value;
                    setJobStatusFilter(next);
                    syncUrlFilters({ jobStatus: next });
                  }}
                >
                  {jobStatuses.map((status) => (
                    <option key={status || 'all'} value={status}>
                      {formatJobStatus(status)}
                    </option>
                  ))}
                </FilterSelect>
              </FilterField>
            )}
            <FilterField label="Search" htmlFor="databricks-focus-search">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
                <Input
                  id="databricks-focus-search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={
                    view === 'jobs' ? 'Job name, ID, error…' : 'Cluster, workspace, tag…'
                  }
                  className="pl-9"
                />
              </div>
            </FilterField>
          </FilterPanel>
        )}

        {renderView(view)}
      </ContentMain>
    </Content>
  );
};

export default DatabricksFocusPage;
