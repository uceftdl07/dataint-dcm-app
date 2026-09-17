import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  parseClusterStateFromUrl,
  parseDatabricksFocusView,
  type DatabricksFocusView,
} from '../lib/databricks/focus-view';
import type { ComputeState } from '../types/api';

export interface OpenDatabricksViewOptions {
  state?: ComputeState;
  jobStatus?: string;
  clearFilters?: boolean;
  toggle?: boolean;
}

function deleteViewParams(params: URLSearchParams) {
  params.delete('view');
  params.delete('state');
  params.delete('jobStatus');
}

export function useDatabricksFocusView() {
  const [searchParams, setSearchParams] = useSearchParams();

  const view = useMemo(
    () => parseDatabricksFocusView(searchParams.get('view')),
    [searchParams],
  );

  const clusterState = useMemo(
    () => parseClusterStateFromUrl(searchParams.get('state')),
    [searchParams],
  );

  const jobStatus = useMemo(() => searchParams.get('jobStatus') ?? '', [searchParams]);

  const patchParams = useCallback(
    (patch: { view?: string | null; state?: string | null; jobStatus?: string | null }) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          Object.entries(patch).forEach(([key, value]) => {
            if (value === null || value === undefined || value === '') {
              next.delete(key);
            } else {
              next.set(key, value);
            }
          });
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const clearView = useCallback(() => {
    patchParams({ view: null, state: null, jobStatus: null });
  }, [patchParams]);

  const openView = useCallback(
    (target: DatabricksFocusView, options: OpenDatabricksViewOptions = {}) => {
      const { toggle = true, clearFilters = false, state, jobStatus: nextJobStatus } = options;

      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          const currentView = parseDatabricksFocusView(next.get('view'));
          const currentState = parseClusterStateFromUrl(next.get('state'));
          const currentJobStatus = next.get('jobStatus') ?? '';

          const resolvedState = clearFilters
            ? ''
            : state !== undefined
              ? state
              : currentState;
          const resolvedJobStatus =
            nextJobStatus !== undefined ? nextJobStatus : currentJobStatus;

          const isSameView =
            currentView === target &&
            (target !== 'clusters' || currentState === resolvedState) &&
            (target !== 'jobs' || currentJobStatus === resolvedJobStatus);

          if (toggle && isSameView) {
            deleteViewParams(next);
            return next;
          }

          next.set('view', target);

          if (target === 'clusters') {
            if (resolvedState) {
              next.set('state', resolvedState);
            } else {
              next.delete('state');
            }
            next.delete('jobStatus');
          } else if (target === 'jobs') {
            next.delete('state');
            if (resolvedJobStatus) {
              next.set('jobStatus', resolvedJobStatus);
            } else {
              next.delete('jobStatus');
            }
          } else {
            next.delete('state');
            next.delete('jobStatus');
          }

          return next;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );

  const setClusterStateParam = useCallback(
    (state: ComputeState | '') => {
      if (view !== 'clusters') {
        return;
      }
      patchParams({ state: state || null });
    },
    [patchParams, view],
  );

  const setJobStatusParam = useCallback(
    (status: string) => {
      if (view !== 'jobs') {
        return;
      }
      patchParams({ jobStatus: status || null });
    },
    [patchParams, view],
  );

  return {
    clearView,
    clusterState,
    jobStatus,
    openView,
    patchParams,
    setClusterStateParam,
    setJobStatusParam,
    view,
  };
}
