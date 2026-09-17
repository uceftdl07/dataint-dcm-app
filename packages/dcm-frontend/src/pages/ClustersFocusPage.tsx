import { ArrowLeft, Copy, RefreshCw, Search } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { FilterField, FilterPanel, FilterSelect, PageError } from '../components/domain';
import { ComputeAccordion } from '../components/domain/compute-accordion';
import { ListPagination } from '../components/domain/list-pagination';
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
import { useClustersPageData } from '../hooks/useClustersPageData';
import {
  CLUSTERS_FOCUS_VIEW_DESCRIPTIONS,
  CLUSTERS_FOCUS_VIEW_LABELS,
  parseClustersFocusView,
  parseComputeStateFromUrl,
} from '../lib/clusters/focus-view';
import type { ComputeState } from '../types/api';

const PAGE_SIZE = 10;
const states: Array<ComputeState | ''> = ['', 'running', 'error', 'terminated', 'unknown'];

const ClustersFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parseClustersFocusView(viewParam ?? null);
  const urlState = parseComputeStateFromUrl(searchParams.get('state'));

  const {
    error,
    filteredComputes,
    load,
    loading,
    loadingDetails,
    resetFilters,
    search,
    setSearch,
    setStateFilter,
    setWorkspaceFilter,
    stateFilter,
    workspaceFilter,
  } = useClustersPageData({ initialStateFilter: urlState });

  const pagination = useClientPagination(filteredComputes, PAGE_SIZE);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setStateFilter(urlState);
  }, [urlState, setStateFilter]);

  const syncUrl = useCallback(
    (state: ComputeState | '') => {
      setSearchParams(
        (c) => {
          const n = new URLSearchParams(c);
          if (state) n.set('state', state);
          else n.delete('state');
          return n;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  if (!view) return <Navigate to="/clusters" replace />;

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/clusters">
              <ArrowLeft size={16} />
              Back to Compute overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{CLUSTERS_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{CLUSTERS_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
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
          resultCount={filteredComputes.length}
          activeFilterCount={[stateFilter, workspaceFilter, search].filter(Boolean).length}
          emptyLabel="Full view"
          onReset={() => {
            resetFilters();
            syncUrl('');
          }}
          className="grid grid-cols-1 gap-4 md:grid-cols-3"
        >
          <FilterField label="State" htmlFor="clusters-state">
            <FilterSelect
              id="clusters-state"
              value={stateFilter}
              onChange={(e) => {
                const v = e.target.value as ComputeState | '';
                setStateFilter(v);
                syncUrl(v);
              }}
            >
              {states.map((s) => (
                <option key={s || 'all'} value={s}>
                  {s || 'All states'}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Workspace" htmlFor="clusters-workspace">
            <Input
              id="clusters-workspace"
              value={workspaceFilter}
              onChange={(e) => setWorkspaceFilter(e.target.value)}
              placeholder="Workspace ID"
            />
          </FilterField>
          <FilterField label="Search" htmlFor="clusters-search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
              <Input
                id="clusters-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
          </FilterField>
        </FilterPanel>
        <ComputeAccordion
          computes={pagination.pageItems}
          loading={loading || loadingDetails}
          resetKey={`${pagination.currentPage}-${filteredComputes.length}`}
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

export default ClustersFocusPage;
