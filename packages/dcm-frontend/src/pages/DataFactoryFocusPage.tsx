import { ArrowLeft, Copy, Filter, RefreshCw, Search } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { FilterField, FilterPanel, FilterSelect, PageError } from '../components/domain';
import { ListPagination } from '../components/domain/list-pagination';
import { PipelineRunAccordion } from '../components/domain/pipeline-run-accordion';
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
import { useClientPagination } from '../hooks/useClientPagination';
import { useDataFactoryPageData } from '../hooks/useDataFactoryPageData';
import {
  DATA_FACTORY_FOCUS_VIEW_DESCRIPTIONS,
  DATA_FACTORY_FOCUS_VIEW_LABELS,
  parseDataFactoryFocusView,
  parsePipelineStatusFromUrl,
} from '../lib/datafactory/focus-view';
import type { PipelineStatus } from '../types/api';

const RUN_PAGE_SIZE = 10;
const statuses: Array<PipelineStatus | ''> = ['', 'succeeded', 'failed', 'running', 'cancelled'];

function formatStatus(status: PipelineStatus | '') {
  if (!status) return 'All statuses';
  return status.charAt(0).toUpperCase() + status.slice(1);
}

const DataFactoryFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parseDataFactoryFocusView(viewParam ?? null);
  const urlStatus = parsePipelineStatusFromUrl(searchParams.get('status'));

  const {
    error,
    filteredRuns,
    load,
    loading,
    resetFilters,
    search,
    setSearch,
    setStatusFilter,
    statusFilter,
  } = useDataFactoryPageData({ initialStatusFilter: urlStatus });

  const pagination = useClientPagination(filteredRuns, RUN_PAGE_SIZE);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setStatusFilter(urlStatus);
  }, [urlStatus, setStatusFilter]);

  const syncUrlFilters = useCallback(
    (patch: { status?: PipelineStatus | '' }) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (patch.status !== undefined) {
            if (patch.status) next.set('status', patch.status);
            else next.delete('status');
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

  if (!view) return <Navigate to="/datafactory" replace />;

  return (
    <Content>
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/datafactory">
              <ArrowLeft size={16} />
              Back to Data Factory overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{DATA_FACTORY_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{DATA_FACTORY_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
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

      {error && <PageError message={error} />}

      <ContentMain className="space-y-6">
        <FilterPanel
          title="Filters"
          description="Refine Azure pipeline runs. Period comes from the header."
          icon={<Filter size={16} />}
          resultCount={filteredRuns.length}
          activeFilterCount={[statusFilter, search].filter(Boolean).length}
          emptyLabel="Full view"
          onReset={() => {
            resetFilters();
            syncUrlFilters({ status: '' });
          }}
          className="grid grid-cols-1 items-end gap-4 pt-0 md:grid-cols-2"
        >
          <FilterField label="Status" htmlFor="adf-focus-status">
            <FilterSelect
              id="adf-focus-status"
              value={statusFilter}
              onChange={(event) => {
                const next = event.target.value as PipelineStatus | '';
                setStatusFilter(next);
                syncUrlFilters({ status: next });
              }}
            >
              {statuses.map((status) => (
                <option key={status || 'all'} value={status}>
                  {formatStatus(status)}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Search" htmlFor="adf-focus-search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
              <Input
                id="adf-focus-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Pipeline, run ID, error…"
                className="pl-9"
              />
            </div>
          </FilterField>
        </FilterPanel>

        <PipelineRunAccordion
          runs={pagination.pageItems}
          loading={loading}
          resetKey={`${pagination.currentPage}-${filteredRuns.length}`}
        />
        <ListPagination
          currentPage={pagination.currentPage}
          endIndex={pagination.endIndex}
          hasNextPage={pagination.hasNextPage}
          hasPreviousPage={pagination.hasPreviousPage}
          onNext={pagination.nextPage}
          onPrevious={pagination.previousPage}
          startIndex={pagination.startIndex}
          totalItems={pagination.totalItems}
          totalPages={pagination.totalPages}
        />
      </ContentMain>
    </Content>
  );
};

export default DataFactoryFocusPage;
