/**
 * Values offered by one filterable column's combo (023 T006).
 *
 * Fetches **only while the popover is open**: the eleven tables carry 88 filterable
 * columns, and prefetching them all would issue 88 `GROUP BY` on the warehouse to
 * populate lists nobody opened.
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getComputeFilterOptions,
  getLakeflowFilterOptions,
  type ComputeFilterOptionsParams,
  type LakeflowFilterOptionsParams,
} from '../api/dcmApiClient';
import type { ComputeColumnFilterOptions, ComputeFilterView } from '../types/api';
import { computeFilterOptionsQueryKeys } from './query-keys';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { useComputeScopeParams } from './useComputeRecommendations';
import { useJobsScopeParams } from './useLakeflowJobsData';

const LAKEFLOW_VIEWS = new Set<ComputeFilterView>(['lakeflow-jobs', 'lakeflow-job-runs']);

/** Same delay as the toolbar search inputs of the pages, for one felt behaviour. */
const SEARCH_DEBOUNCE_MS = 300;

export interface UseColumnFilterOptionsArgs {
  view: ComputeFilterView;
  column: string;
  /** The popover's state. `false` = no request at all. */
  open: boolean;
  /** Raw input of the combo's search field; debounced here, not by the caller. */
  search?: string;
  /**
   * The rolling window the table is showing. Without it the combo would list the
   * values of `window_days=1` next to a table showing 90 days.
   */
  windowDays?: number;
  /** Narrows `lakeflow-job-runs` to the workflow the detail page is showing. */
  workflowId?: string;
}

export interface ColumnFilterOptionsResult {
  data: ComputeColumnFilterOptions | null;
  loading: boolean;
  fetching: boolean;
  error: unknown;
  /** `true` once the debounce has caught up with what the user typed. */
  searchSettled: boolean;
}

export function useColumnFilterOptions(
  args: UseColumnFilterOptionsArgs
): ColumnFilterOptionsResult {
  const { view, column, open, search = '', windowDays, workflowId } = args;
  const isLakeflow = LAKEFLOW_VIEWS.has(view);

  // Both are plain `useMemo` over contexts, so calling both is not a conditional
  // hook — only the result of one of them is used.
  const computeScope = useComputeScopeParams();
  const jobsScope = useJobsScopeParams();

  const [debouncedSearch, setDebouncedSearch] = useState(search.trim());
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Closing the popover forgets what was typed: reopening on a stale `q` would
  // show a narrowed list next to an empty search field.
  useEffect(() => {
    if (!open) setDebouncedSearch('');
  }, [open]);

  const params = useMemo(() => {
    if (isLakeflow) {
      return {
        ...jobsScope,
        view: view as LakeflowFilterOptionsParams['view'],
        column,
        workflow_id: workflowId || undefined,
        q: debouncedSearch || undefined,
      } satisfies LakeflowFilterOptionsParams;
    }
    return {
      ...computeScope,
      view,
      column,
      window_days: windowDays,
      q: debouncedSearch || undefined,
    } satisfies ComputeFilterOptionsParams;
  }, [isLakeflow, jobsScope, computeScope, view, column, windowDays, workflowId, debouncedSearch]);

  const scopeReady = isLakeflow
    ? Boolean(jobsScope.start_date && jobsScope.end_date)
    : Boolean(computeScope.period_start && computeScope.period_end);

  const query = useQuery({
    queryKey: computeFilterOptionsQueryKeys.options(view, column, params, debouncedSearch),
    queryFn: () =>
      isLakeflow
        ? getLakeflowFilterOptions(params as LakeflowFilterOptionsParams)
        : getComputeFilterOptions(params as ComputeFilterOptionsParams),
    enabled: open && Boolean(column) && scopeReady,
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    // Keeps the previous list on screen while a new `q` is in flight, so the
    // popover does not collapse to a spinner on every keystroke.
    placeholderData: (previous) => previous,
  });

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    fetching: query.isFetching,
    error: query.error,
    searchSettled: debouncedSearch === search.trim(),
  };
}
