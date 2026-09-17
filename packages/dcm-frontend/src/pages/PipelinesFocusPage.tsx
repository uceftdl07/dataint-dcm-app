import { ArrowLeft, Copy, RefreshCw, Search } from 'lucide-react';
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
import { usePipelinesPageData } from '../hooks/usePipelinesPageData';
import {
  PIPELINES_FOCUS_VIEW_DESCRIPTIONS,
  PIPELINES_FOCUS_VIEW_LABELS,
  parsePipelineStatusFromUrl,
  parsePipelinesFocusView,
} from '../lib/pipelines/focus-view';
import type { PipelineStatus } from '../types/api';

const PAGE_SIZE = 10;
const statuses: Array<PipelineStatus | ''> = ['', 'succeeded', 'failed', 'running', 'cancelled'];

const PipelinesFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parsePipelinesFocusView(viewParam ?? null);
  const urlStatus = parsePipelineStatusFromUrl(searchParams.get('status'));

  const {
    error,
    filteredRuns,
    load,
    loading,
    loadingDetails,
    resetFilters,
    search,
    setSearch,
    setStatusFilter,
    statusFilter,
  } = usePipelinesPageData({ initialStatusFilter: urlStatus });

  const pagination = useClientPagination(filteredRuns, PAGE_SIZE);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setStatusFilter(urlStatus);
  }, [urlStatus, setStatusFilter]);

  const syncUrl = useCallback(
    (status: PipelineStatus | '') => {
      setSearchParams(
        (c) => {
          const n = new URLSearchParams(c);
          if (status) n.set('status', status);
          else n.delete('status');
          return n;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  if (!view) return <Navigate to="/pipelines" replace />;

  return (
    <Content>
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/pipelines">
              <ArrowLeft size={16} />
              Back to Pipelines overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{PIPELINES_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{PIPELINES_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
          </div>
        </div>
        <ContentActions>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              void navigator.clipboard.writeText(window.location.href).then(() => setCopied(true))
            }
          >
            <Copy size={14} />
            {copied ? 'Copied' : 'Copy link'}
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
          resultCount={filteredRuns.length}
          activeFilterCount={[statusFilter, search].filter(Boolean).length}
          emptyLabel="Full view"
          onReset={() => {
            resetFilters();
            syncUrl('');
          }}
          className="grid grid-cols-1 gap-4 md:grid-cols-2"
        >
          <FilterField label="Status" htmlFor="pipelines-status">
            <FilterSelect
              id="pipelines-status"
              value={statusFilter}
              onChange={(e) => {
                const v = e.target.value as PipelineStatus | '';
                setStatusFilter(v);
                syncUrl(v);
              }}
            >
              {statuses.map((s) => (
                <option key={s || 'all'} value={s}>
                  {s || 'All statuses'}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Search" htmlFor="pipelines-search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
              <Input
                id="pipelines-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
                placeholder="Pipeline, error…"
              />
            </div>
          </FilterField>
        </FilterPanel>
        <PipelineRunAccordion
          runs={pagination.pageItems}
          loading={loading || loadingDetails}
          resetKey={`${pagination.currentPage}-${filteredRuns.length}`}
        />
        <ListPagination
          {...pagination}
          onNext={pagination.nextPage}
          onPrevious={pagination.previousPage}
        />
      </ContentMain>
    </Content>
  );
};

export default PipelinesFocusPage;
