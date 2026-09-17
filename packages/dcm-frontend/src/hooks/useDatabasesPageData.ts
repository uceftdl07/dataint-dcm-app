import { useCallback, useMemo, useState } from 'react';
import { listDatabases } from '../api/dcmApiClient';
import {
  computeDatabaseStats,
  sortDatabasesByCapacity,
  sortDatabasesByPressure,
} from '../lib/databases/database-utils';
import type { DatabaseCapacitySort } from '../lib/databases/focus-view';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { matchesSourceLzScope } from '../lib/monitoring-scope-filter';
import type { DatabaseMetric, DatabaseType } from '../types/api';
import { useStagedListFetch } from './useStagedQueries';

export interface UseDatabasesPageDataOptions {
  initialAvailFilter?: '' | 'true' | 'false';
  initialTypeFilter?: DatabaseType | '';
}

export function useDatabasesPageData(options: UseDatabasesPageDataOptions = {}) {
  const { scope, getScopedParams } = useMonitoringScope();
  const [typeFilter, setTypeFilter] = useState<DatabaseType | ''>(options.initialTypeFilter ?? '');
  const [availFilter, setAvailFilter] = useState<'' | 'true' | 'false'>(options.initialAvailFilter ?? '');
  const [search, setSearch] = useState('');
  const [capacitySort, setCapacitySort] = useState<DatabaseCapacitySort>('storage');
  const scopedParams = getScopedParams({ cloudProvider: true });

  const {
    items: dbs,
    loading,
    loadingDetails,
    error,
    reload: load,
  } = useStagedListFetch<DatabaseMetric, { items: DatabaseMetric[]; total: number }>(
    () => listDatabases({ cloud_provider: scopedParams.cloud_provider }).then((response) => ({
      items: response.items ?? [],
      total: response.items?.length ?? 0,
    })),
    [scopedParams.cloud_provider],
  );

  const filteredDbs = useMemo(() => {
    const subscriptionScopedParams = getScopedParams({ subscriptionOrAccountId: true });
    const effectiveSubscription = subscriptionScopedParams.subscription_or_account_id || '';
    const term = search.trim().toLowerCase();

    return dbs.filter((db) => {
      const matchesType = !typeFilter || db.db_type === typeFilter;
      const matchesAvail =
        !availFilter || (availFilter === 'true' ? db.is_available : !db.is_available);
      const matchesSource = matchesSourceLzScope(db.source_lz_id, scope);
      const matchesSubscription = !effectiveSubscription || db.subscription_or_account_id === effectiveSubscription;
      const matchesSearch =
        !term
        || [
          db.db_name,
          db.db_id,
          db.server_name,
          db.region,
          db.availability_zone,
          db.resource_group,
          db.subscription_or_account_id,
          db.source_lz_id,
          db.db_type,
          db.cloud_provider,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(term));

      return matchesType && matchesAvail && matchesSource && matchesSubscription && matchesSearch;
    });
  }, [availFilter, dbs, getScopedParams, scope, search, typeFilter]);

  const stats = useMemo(() => computeDatabaseStats(filteredDbs), [filteredDbs]);
  const healthRate = filteredDbs.length > 0 ? Math.round((stats.availableCount / filteredDbs.length) * 100) : 0;
  const pressureDbs = useMemo(() => sortDatabasesByPressure(filteredDbs), [filteredDbs]);
  const capacityDbs = useMemo(
    () => sortDatabasesByCapacity(filteredDbs, capacitySort),
    [capacitySort, filteredDbs],
  );

  const resetFilters = useCallback(() => {
    setTypeFilter('');
    setAvailFilter('');
    setSearch('');
  }, []);

  return {
    availFilter,
    capacityDbs,
    capacitySort,
    dbs,
    error,
    filteredDbs,
    healthRate,
    load,
    loading,
    loadingDetails,
    pressureDbs,
    resetFilters,
    scope,
    search,
    setAvailFilter,
    setCapacitySort,
    setSearch,
    setTypeFilter,
    stats,
    typeFilter,
  };
}
