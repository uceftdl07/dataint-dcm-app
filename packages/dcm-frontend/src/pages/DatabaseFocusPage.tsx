import { ArrowLeft, Copy, Filter, RefreshCw, Search } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { FilterField, FilterPanel, FilterSelect, PageError } from '../components/domain';
import {
  CapacityFocusView,
  InventoryFocusView,
  PressureFocusView,
} from '../components/domain/databases/views/database-focus-views';
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
import { useDatabasesPageData } from '../hooks/useDatabasesPageData';
import { DATABASE_TYPES, formatDatabaseType } from '../lib/databases/database-utils';
import {
  DATABASE_FOCUS_VIEW_DESCRIPTIONS,
  DATABASE_FOCUS_VIEW_LABELS,
  parseAvailabilityFromUrl,
  parseCapacitySortFromUrl,
  parseDatabaseFocusView,
  parseDatabaseTypeFromUrl,
  type DatabaseFocusView,
} from '../lib/databases/focus-view';
import type { DatabaseType } from '../types/api';

const DatabaseFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parseDatabaseFocusView(viewParam ?? null);

  const urlAvail = parseAvailabilityFromUrl(searchParams.get('avail'));
  const urlType = parseDatabaseTypeFromUrl(searchParams.get('type'));
  const urlSort = parseCapacitySortFromUrl(searchParams.get('sort'));

  const {
    availFilter,
    capacityDbs,
    capacitySort,
    error,
    filteredDbs,
    load,
    loading,
    loadingDetails,
    pressureDbs,
    resetFilters,
    search,
    setAvailFilter,
    setCapacitySort,
    setSearch,
    setTypeFilter,
    typeFilter,
  } = useDatabasesPageData({
    initialAvailFilter: urlAvail,
    initialTypeFilter: urlType,
  });

  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setAvailFilter(urlAvail);
  }, [urlAvail, setAvailFilter]);

  useEffect(() => {
    setTypeFilter(urlType);
  }, [urlType, setTypeFilter]);

  useEffect(() => {
    setCapacitySort(urlSort);
  }, [urlSort, setCapacitySort]);

  const syncUrlFilters = useCallback(
    (patch: { avail?: '' | 'true' | 'false'; type?: DatabaseType | '' }) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (patch.avail !== undefined) {
            if (patch.avail) next.set('avail', patch.avail);
            else next.delete('avail');
          }
          if (patch.type !== undefined) {
            if (patch.type) next.set('type', patch.type);
            else next.delete('type');
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
    return <Navigate to="/databases" replace />;
  }

  const activeFilterCount = [typeFilter, availFilter, search].filter(Boolean).length;
  const listCount =
    view === 'pressure'
      ? pressureDbs.length
      : view === 'capacity'
        ? capacityDbs.length
        : filteredDbs.length;

  const renderView = (focusView: DatabaseFocusView) => {
    switch (focusView) {
      case 'inventory':
        return <InventoryFocusView databases={filteredDbs} loading={loading || loadingDetails} />;
      case 'pressure':
        return <PressureFocusView databases={pressureDbs} loading={loading || loadingDetails} />;
      case 'capacity':
        return (
          <CapacityFocusView
            databases={capacityDbs}
            loading={loading || loadingDetails}
            sort={capacitySort}
          />
        );
      default:
        return null;
    }
  };

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/databases">
              <ArrowLeft size={16} />
              Back to Database overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{DATABASE_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{DATABASE_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
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
          description="Refine the list below. Scope comes from the header."
          icon={<Filter size={16} />}
          resultCount={listCount}
          activeFilterCount={activeFilterCount}
          emptyLabel="Full view"
          onReset={() => {
            resetFilters();
            syncUrlFilters({ avail: '', type: '' });
          }}
          className="grid grid-cols-1 items-end gap-4 pt-0 md:grid-cols-3"
        >
          <FilterField label="Engine" htmlFor="database-focus-type">
            <FilterSelect
              id="database-focus-type"
              value={typeFilter}
              onChange={(event) => {
                const next = event.target.value as DatabaseType | '';
                setTypeFilter(next);
                syncUrlFilters({ type: next });
              }}
            >
              <option value="">All engines</option>
              {DATABASE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {formatDatabaseType(type)}
                </option>
              ))}
            </FilterSelect>
          </FilterField>
          <FilterField label="Availability" htmlFor="database-focus-avail">
            <FilterSelect
              id="database-focus-avail"
              value={availFilter}
              onChange={(event) => {
                const next = event.target.value as '' | 'true' | 'false';
                setAvailFilter(next);
                syncUrlFilters({ avail: next });
              }}
            >
              <option value="">All statuses</option>
              <option value="true">Available</option>
              <option value="false">Unavailable</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Search" htmlFor="database-focus-search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
              <Input
                id="database-focus-search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name, server, region, engine…"
                className="pl-9"
              />
            </div>
          </FilterField>
        </FilterPanel>

        {renderView(view)}
      </ContentMain>
    </Content>
  );
};

export default DatabaseFocusPage;
