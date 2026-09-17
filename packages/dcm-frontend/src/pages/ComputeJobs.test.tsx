import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  computeJobCostTrendFixture,
  computeJobDetailFixture,
  computeJobDetailWithoutEfficiencyFixture,
  computeJobUptimeTrendFixture,
  computeJobsCostFixture,
  computeJobsEfficiencyFixture,
  computeJobsOverviewFixture,
} from '../test/fixtures/compute-jobs';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import ComputeJobs from './ComputeJobs';

vi.mock('../api/dcmApiClient', () => ({
  getComputeJobsOverview: vi.fn(),
  listComputeJobsCost: vi.fn(),
  listComputeJobsEfficiency: vi.fn(),
  getComputeJobDetail: vi.fn(),
  getComputeJobCostTrend: vi.fn(),
  getComputeJobUptimeTrend: vi.fn(),
  listDatabricksWorkspaces: vi.fn(),
}));

import {
  getComputeJobCostTrend,
  getComputeJobDetail,
  getComputeJobUptimeTrend,
  getComputeJobsOverview,
  listComputeJobsCost,
  listComputeJobsEfficiency,
  listDatabricksWorkspaces,
} from '../api/dcmApiClient';

const apiMocks = {
  getComputeJobsOverview: vi.mocked(getComputeJobsOverview),
  listComputeJobsCost: vi.mocked(listComputeJobsCost),
  listComputeJobsEfficiency: vi.mocked(listComputeJobsEfficiency),
  getComputeJobDetail: vi.mocked(getComputeJobDetail),
  getComputeJobCostTrend: vi.mocked(getComputeJobCostTrend),
  getComputeJobUptimeTrend: vi.mocked(getComputeJobUptimeTrend),
  listDatabricksWorkspaces: vi.mocked(listDatabricksWorkspaces),
};

/**
 * Text of the given columns, read on the row carrying `label`, resolved by header rather
 * than by position — the two tabs do not put the uptime at the same index.
 */
async function cellsByHeader(label: string, headers: string[]) {
  const table = await screen.findByRole('table');
  const columns = within(table)
    .getAllByRole('columnheader')
    .map((cell) => cell.textContent?.trim());
  const row = (await within(table).findByText(label, { selector: 'div.font-semibold' })).closest(
    'tr'
  ) as HTMLElement;
  const cells = within(row).getAllByRole('cell');

  return headers.map((header) => cells[columns.indexOf(header)]?.textContent?.trim());
}

/** Opens the drawer from a row of the given tab, and returns the `user` session. */
async function openDrawerFrom(tab: 'Overview' | 'Cost' | 'Efficiency', label: string) {
  const user = userEvent.setup();
  renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

  if (tab !== 'Overview') await user.click(await screen.findByRole('tab', { name: tab }));

  // Scoped to the table: the "Top costly" KPI card names the same job.
  const table = await screen.findByRole('table');
  await user.click(await within(table).findByText(label, { selector: 'div.font-semibold' }));
  await screen.findByRole('dialog', { name: 'Job details' });

  return user;
}

describe('ComputeJobs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getComputeJobsOverview.mockResolvedValue(computeJobsOverviewFixture);
    apiMocks.listComputeJobsCost.mockResolvedValue(computeJobsCostFixture);
    apiMocks.listComputeJobsEfficiency.mockResolvedValue(computeJobsEfficiencyFixture);
    apiMocks.getComputeJobDetail.mockResolvedValue(computeJobDetailFixture);
    apiMocks.getComputeJobCostTrend.mockResolvedValue(computeJobCostTrendFixture);
    apiMocks.getComputeJobUptimeTrend.mockResolvedValue(computeJobUptimeTrendFixture);
    apiMocks.listDatabricksWorkspaces.mockResolvedValue({
      items: [
        {
          workspace_id: 'ws-1',
          display_name: 'dbw-analytics-prod',
          source_lz_id: 'lz-1',
          cluster_count: 0,
        },
      ],
    });
  });

  it('renders the job name, with the id below and as fallback when empty', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    // Named job: the human name is the visible label, the id sits below it.
    expect(await screen.findByText('nightly-ingest')).toBeInTheDocument();
    expect(screen.getByText('job-1042')).toBeInTheDocument();

    // The second job has no name in gold: the id is the visible fallback, so it
    // appears twice (main label + mono id line).
    expect(screen.getAllByText('job-2087')).toHaveLength(2);
  });

  it('grains on the job — the id is job_id, not a cluster id', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    const call = await waitFor(() => {
      const calls = apiMocks.getComputeJobsOverview.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last).toBeTruthy();
      return last!;
    });
    // The page reads the job grain: rolling window, default cost sort.
    expect(call.window_days).toBe(1);
    expect(call.sort).toBe('cost_desc');
  });

  it('switches the rolling window and refetches on that window', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    await screen.findByText('nightly-ingest');
    await user.click(screen.getByRole('button', { name: 'Last 30d' }));

    await waitFor(() => {
      const calls = apiMocks.getComputeJobsOverview.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last?.window_days).toBe(30);
    });
  });

  it('shows the utilization beside the cost on the Overview tab, and no DBU column', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    // Same reading as the all-purpose overview: cost, its predecessor, the cumulated
    // uptime and its predecessor, then the sizing verdict.
    expect(headers).toEqual([
      'Workspace',
      'Job',
      'Cost',
      'Prev cost',
      'Lifetime',
      'Prev lifetime',
      'Utilization',
      'Clusters',
    ]);
    // DBU is a billing unit, not a reading of the compute: it stays on the Cost tab.
    expect(headers).not.toContain('DBU');

    const measured = (
      await within(table).findByText('nightly-ingest', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;
    // 41.5 h cumulated over the window, 36 h over the previous one: +15.3 %.
    expect(within(measured).getByText('1d 17h 30m')).toBeInTheDocument();
    expect(within(measured).getByText('1d 12h')).toBeInTheDocument();
    expect(within(measured).getByText('+15.3%')).toBeInTheDocument();
    expect(within(measured).getByText('Overprovisioned')).toBeInTheDocument();
  });

  it('reads the same uptime under Lifetime on Overview and under Uptime on Efficiency', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    // Same column of the same snapshot: the Overview joins the very row the Efficiency
    // tab lists, so the two tabs cannot disagree on a measured job.
    const onOverview = await cellsByHeader('nightly-ingest', ['Lifetime', 'Prev lifetime']);
    await user.click(screen.getByRole('tab', { name: 'Efficiency' }));
    const onEfficiency = await cellsByHeader('nightly-ingest', ['Uptime', 'Uptime prev']);

    expect(onOverview).toEqual(onEfficiency);
    expect(onOverview[0]).toBe('1d 17h 30m');
  });

  it('reads "—" on the Overview tab when the job has neither predecessor nor metrics', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    // job-2087 has no predecessor window and no efficiency row: prev cost, lifetime,
    // prev lifetime and utilization all read the em dash. A `0` would claim the job
    // never ran, and `0 %` that it ran flat out.
    const row = (await screen.findByText('job-2087', { selector: 'div.font-semibold' })).closest(
      'tr'
    ) as HTMLElement;
    const cells = within(row)
      .getAllByRole('cell')
      .map((cell) => cell.textContent?.trim());

    expect(cells.slice(3, 7)).toEqual(['—', '—', '—', '—']);
    expect(cells.join(' ')).not.toMatch(/NaN/);
  });

  it('links the recommendations card to the JOB family', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    const link = await screen.findByRole('link', { name: 'View job recommendations' });
    expect(link).toHaveAttribute('href', '/databricks/compute/recommendations?object_type=JOB');
  });

  it('shows the empty state when the scope returns no job', async () => {
    apiMocks.getComputeJobsOverview.mockResolvedValue({
      ...computeJobsOverviewFixture,
      kpis: { total_cost_usd: 0, cost_delta_pct: null, active_jobs: 0 },
      items: [],
      total: 0,
    });

    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    expect(await screen.findByText('No jobs')).toBeInTheDocument();
  });

  it('does not hit the cost endpoint until the Cost tab is opened', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    await screen.findByText('nightly-ingest');
    // The Overview tab is active on mount: the cost endpoint stays untouched.
    expect(apiMocks.listComputeJobsCost).not.toHaveBeenCalled();
  });

  it('fetches the cost grain and ranks the top-cost job when the Cost tab opens', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    await screen.findByText('nightly-ingest');
    await user.click(screen.getByRole('tab', { name: 'Cost' }));

    // The cost endpoint is now hit on the same window / default cost sort.
    await waitFor(() => {
      const calls = apiMocks.listComputeJobsCost.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last?.window_days).toBe(1);
      expect(last?.sort).toBe('cost_desc');
    });

    // The top-cost job (rank 1, is_top_cost) carries the "Top" badge.
    const row = (
      await screen.findByText('nightly-ingest', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;
    expect(within(row).getByText('Top')).toBeInTheDocument();

    // The Cost tab is a billing reading: it renames its delta column like the
    // overview does, and **keeps** DBU.
    const headers = within(await screen.findByRole('table'))
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());
    expect(headers).toEqual(['Rank', 'Workspace', 'Job', 'Cost', 'Prev cost', 'DBU']);
  });

  it('offers the three sub-tabs, Efficiency included', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    expect(await screen.findByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Efficiency' })).toBeInTheDocument();
  });

  it('does not hit the efficiency endpoint until the Efficiency tab is opened', async () => {
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    await screen.findByText('nightly-ingest');
    expect(apiMocks.listComputeJobsEfficiency).not.toHaveBeenCalled();
  });

  it('lists the utilization at the job grain, with no Zombie column', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    await user.click(await screen.findByRole('tab', { name: 'Efficiency' }));

    await waitFor(() => {
      const calls = apiMocks.listComputeJobsEfficiency.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last?.window_days).toBe(1);
      expect(last?.sort).toBe('savings_desc');
    });

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    expect(headers).toEqual([
      'Workspace',
      'Job',
      'Clusters',
      'Driver node',
      'Worker node',
      'Autoscaling',
      'Workers avg',
      'Workers max',
      'Uptime',
      'Uptime prev',
      'Idle',
      'Idle prev',
      'CPU avg',
      'CPU p95',
      'Mem avg',
      'Mem p95',
      'Status',
      'Recommended node',
      'Est. savings',
    ]);
    // A job cluster dies with its run: a zombie column would be `false` everywhere
    // and read like a passing control (024 C1).
    expect(headers).not.toContain('Zombie');

    // The measured row carries its metrics; the idle delta is in points.
    const measured = (
      await within(table).findByText('nightly-ingest', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;
    expect(within(measured).getByText('84%')).toBeInTheDocument();
    expect(within(measured).getByText('-7.0 pts')).toBeInTheDocument();
    expect(within(measured).getByText('Overprovisioned')).toBeInTheDocument();
  });

  it('reads "—" and never 0 % on a job billed without a measured minute', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputeJobs />, { route: '/databricks/job-compute' });

    await user.click(await screen.findByRole('tab', { name: 'Efficiency' }));

    const table = await screen.findByRole('table');
    const row = (
      await within(table).findByText('job-2087', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;

    // Every metric of that row is unmeasured: em dashes, no invented zero.
    expect(within(row).getAllByText('—').length).toBeGreaterThan(5);
    expect(within(row).queryByText('0%')).not.toBeInTheDocument();
    expect(within(row).queryByText('$0.00')).not.toBeInTheDocument();
  });

  // A row is clickable on the three tabs, not only where the metrics live.
  it.each(['Overview', 'Cost', 'Efficiency'] as const)(
    'opens the job drawer from a row of the %s tab',
    async (tab) => {
      await openDrawerFrom(tab, 'nightly-ingest');

      const drawer = screen.getByRole('dialog', { name: 'Job details' });
      expect(within(drawer).getByText('job-1042')).toBeInTheDocument();
      expect(await within(drawer).findByText('84%')).toBeInTheDocument();

      await waitFor(() => {
        expect(apiMocks.getComputeJobDetail).toHaveBeenCalledWith(
          'job-1042',
          expect.objectContaining({ window_days: 1 })
        );
      });
    }
  );

  it('shows both trends and the technical specs in the drawer, and no governance block', async () => {
    await openDrawerFrom('Cost', 'nightly-ingest');

    const drawer = screen.getByRole('dialog', { name: 'Job details' });

    expect(within(drawer).getByText('Technical specs')).toBeInTheDocument();
    expect(within(drawer).getByText('Standard_DS3_v2')).toBeInTheDocument();
    expect(within(drawer).getByText('2 – 8')).toBeInTheDocument();
    expect(within(drawer).getByText('Cost trend (≈90 days)')).toBeInTheDocument();
    // The cumulated uptime of the runs, not a cluster lifetime.
    expect(within(drawer).getByText('Uptime trend (≈90 days)')).toBeInTheDocument();

    // Governance is a cluster-level snapshot and stays on the all-purpose grain (024 C2).
    expect(within(drawer).queryByText('Governance')).not.toBeInTheDocument();
    expect(within(drawer).queryByText('Tags')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.getComputeJobCostTrend).toHaveBeenCalledWith(
        'job-1042',
        expect.objectContaining({ granularity: 'week' })
      );
      expect(apiMocks.getComputeJobUptimeTrend).toHaveBeenCalledWith(
        'job-1042',
        expect.objectContaining({ granularity: 'week' })
      );
    });
  });

  it('keeps the drawer usable when the job has no efficiency row', async () => {
    apiMocks.getComputeJobDetail.mockResolvedValue(computeJobDetailWithoutEfficiencyFixture);

    await openDrawerFrom('Cost', 'job-2087');

    const drawer = screen.getByRole('dialog', { name: 'Job details' });

    // The cost block is real; the utilization block reads "—" with an explanation.
    expect(await within(drawer).findByText(/No utilization measured over this window/)).toBeInTheDocument();
    expect(within(drawer).getByText('$320.00')).toBeInTheDocument();
    expect(within(drawer).queryByText('0%')).not.toBeInTheDocument();
  });

  it('closes the drawer on Escape', async () => {
    const user = await openDrawerFrom('Cost', 'nightly-ingest');

    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Job details' })).not.toBeInTheDocument();
    });
  });
});
