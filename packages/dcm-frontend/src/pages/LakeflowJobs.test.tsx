import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LakeflowJobListItem, LakeflowJobsListResponse } from '../types/api';
import { renderWithProviders, screen } from '../test/render';

const refetch = vi.fn();
const hookState: { data: LakeflowJobsListResponse | null } = { data: null };

vi.mock('../hooks/useLakeflowJobsData', () => ({
  // Les combos de filtre d'en-tête interrogent le scope de la table via
  // `useColumnFilterOptions` : mocker le module sans cet export casse le rendu
  // de la page entière, pas seulement le popover.
  useJobsScopeParams: () => ({ start_date: '2026-08-01', end_date: '2026-08-31' }),
  useLakeflowJobsList: () => ({
    data: hookState.data,
    loading: false,
    fetching: false,
    error: null,
    refetch,
  }),
}));

import LakeflowJobs from './LakeflowJobs';

function makeItem(overrides: Partial<LakeflowJobListItem> = {}): LakeflowJobListItem {
  return {
    workflow_id: 'wf-123',
    workflow_name: '',
    source_lz_id: null,
    workspace_id: 'ws-42',
    workspace_name: null,
    last_status: 'succeeded',
    last_start_time: null,
    last_end_time: null,
    last_trigger_type: null,
    last_run_type: null,
    last_duration_seconds: null,
    owner: null,
    last_run_page_url: null,
    terminal_runs: 3,
    succeeded_runs: 3,
    failed_runs: 0,
    timed_out_runs: 0,
    cancelled_runs: 0,
    success_rate_pct: null,
    success_rate_24h_pct: null,
    success_rate_24h_n: 0,
    success_rate_7d_pct: null,
    success_rate_7d_n: 0,
    avg_duration_seconds: null,
    duration_drift_pct: null,
    baseline_avg_14d: null,
    p50: null,
    p95: null,
    p99: null,
    avg_queued_duration_seconds: null,
    avg_schedule_lag_seconds: null,
    avg_retry_count: null,
    task_failure_rate_pct: null,
    execution_cost_usd: null,
    history: [],
    has_runs: true,
    ...overrides,
  };
}

describe('LakeflowJobs — NULL-safe + freshness banner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hookState.data = {
      items: [makeItem()],
      total: 1,
      page: 1,
      page_size: 25,
      total_cost_usd: null,
      jobs_with_cost: 0,
      window: { key: 'custom', from: '2026-08-01', to: '2026-08-31' },
      as_of: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    };
  });

  it('hides the "Attente" (queue | lag) column', () => {
    renderWithProviders(<LakeflowJobs />, { route: '/databricks/workflows' });
    expect(screen.queryByText('Attente')).not.toBeInTheDocument();
  });

  it('renders the freshness banner derived from as_of', () => {
    renderWithProviders(<LakeflowJobs />, { route: '/databricks/workflows' });
    expect(screen.getByText('données à ~2 h')).toBeInTheDocument();
  });

  it('falls back to workflow_id when the name is absent', () => {
    renderWithProviders(<LakeflowJobs />, { route: '/databricks/workflows' });
    expect(screen.getAllByText('wf-123').length).toBeGreaterThan(0);
  });

  it('renders a dash for NULL durations, never 0', () => {
    renderWithProviders(<LakeflowJobs />, { route: '/databricks/workflows' });
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.queryByText('0 s')).not.toBeInTheDocument();
  });
});
