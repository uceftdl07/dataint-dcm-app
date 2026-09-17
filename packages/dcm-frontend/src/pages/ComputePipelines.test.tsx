import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  computePipelineCostTrendFixture,
  computePipelineDetailFixture,
  computePipelineDetailWithoutEfficiencyFixture,
  computePipelineUptimeTrendFixture,
  computePipelinesCostFixture,
  computePipelinesEfficiencyFixture,
  computePipelinesOverviewFixture,
} from '../test/fixtures/compute-pipelines';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import ComputePipelines from './ComputePipelines';

vi.mock('../api/dcmApiClient', () => ({
  getComputePipelinesOverview: vi.fn(),
  listComputePipelinesCost: vi.fn(),
  listComputePipelinesEfficiency: vi.fn(),
  getComputePipelineDetail: vi.fn(),
  getComputePipelineCostTrend: vi.fn(),
  getComputePipelineUptimeTrend: vi.fn(),
  listDatabricksWorkspaces: vi.fn(),
}));

import {
  getComputePipelineCostTrend,
  getComputePipelineDetail,
  getComputePipelineUptimeTrend,
  getComputePipelinesOverview,
  listComputePipelinesCost,
  listComputePipelinesEfficiency,
  listDatabricksWorkspaces,
} from '../api/dcmApiClient';

const apiMocks = {
  getComputePipelinesOverview: vi.mocked(getComputePipelinesOverview),
  listComputePipelinesCost: vi.mocked(listComputePipelinesCost),
  listComputePipelinesEfficiency: vi.mocked(listComputePipelinesEfficiency),
  getComputePipelineDetail: vi.mocked(getComputePipelineDetail),
  getComputePipelineCostTrend: vi.mocked(getComputePipelineCostTrend),
  getComputePipelineUptimeTrend: vi.mocked(getComputePipelineUptimeTrend),
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
  renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

  if (tab !== 'Overview') await user.click(await screen.findByRole('tab', { name: tab }));

  // Scoped to the table: the "Top costly" KPI card names the same pipeline.
  const table = await screen.findByRole('table');
  await user.click(await within(table).findByText(label, { selector: 'div.font-semibold' }));
  await screen.findByRole('dialog', { name: 'Pipeline details' });

  return user;
}

describe('ComputePipelines', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getComputePipelinesOverview.mockResolvedValue(computePipelinesOverviewFixture);
    apiMocks.listComputePipelinesCost.mockResolvedValue(computePipelinesCostFixture);
    apiMocks.listComputePipelinesEfficiency.mockResolvedValue(computePipelinesEfficiencyFixture);
    apiMocks.getComputePipelineDetail.mockResolvedValue(computePipelineDetailFixture);
    apiMocks.getComputePipelineCostTrend.mockResolvedValue(computePipelineCostTrendFixture);
    apiMocks.getComputePipelineUptimeTrend.mockResolvedValue(computePipelineUptimeTrendFixture);
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

  it('renders the pipeline name, with the id below and as fallback when empty', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    expect(await screen.findByText('bronze-to-silver')).toBeInTheDocument();
    expect(screen.getByText('dlt-7781')).toBeInTheDocument();

    // Unnamed pipeline: the dlt id is the visible fallback (main label + mono line).
    expect(screen.getAllByText('dlt-9902')).toHaveLength(2);
  });

  it('grains on the DLT pipeline id', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    const call = await waitFor(() => {
      const calls = apiMocks.getComputePipelinesOverview.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last).toBeTruthy();
      return last!;
    });
    expect(call.window_days).toBe(1);
    expect(call.sort).toBe('cost_desc');
  });

  it('switches the rolling window and refetches on that window', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    await screen.findByText('bronze-to-silver');
    await user.click(screen.getByRole('button', { name: 'Last 90d' }));

    await waitFor(() => {
      const calls = apiMocks.getComputePipelinesOverview.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last?.window_days).toBe(90);
    });
  });

  it('shows the utilization beside the cost on the Overview tab, and no DBU column', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());

    // Same reading as the all-purpose overview, minus the cluster count: the cost
    // rollup is billing-direct at this grain, it never resolves a cluster.
    expect(headers).toEqual([
      'Workspace',
      'Pipeline',
      'Cost',
      'Prev cost',
      'Lifetime',
      'Prev lifetime',
      'Utilization',
    ]);
    // DBU is a billing unit, not a reading of the compute: it stays on the Cost tab.
    expect(headers).not.toContain('DBU');

    const measured = (
      await within(table).findByText('bronze-to-silver', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;
    // 63.25 h cumulated over the window, 70 h over the previous one: −9.6 %.
    expect(within(measured).getByText('2d 15h 15m')).toBeInTheDocument();
    expect(within(measured).getByText('2d 22h')).toBeInTheDocument();
    expect(within(measured).getByText('-9.6%')).toBeInTheDocument();
    expect(within(measured).getByText('Optimal')).toBeInTheDocument();
  });

  it('reads the same uptime under Lifetime on Overview and under Uptime on Efficiency', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    // Same column of the same snapshot: the Overview joins the very row the Efficiency
    // tab lists, so the two tabs cannot disagree on a measured pipeline.
    const onOverview = await cellsByHeader('bronze-to-silver', ['Lifetime', 'Prev lifetime']);
    await user.click(screen.getByRole('tab', { name: 'Efficiency' }));
    const onEfficiency = await cellsByHeader('bronze-to-silver', ['Uptime', 'Uptime prev']);

    expect(onOverview).toEqual(onEfficiency);
    expect(onOverview[0]).toBe('2d 15h 15m');
  });

  it('reads "—" on the Overview tab for a serverless pipeline, billed but unmeasured', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    // dlt-9902 has no predecessor window and no efficiency row: prev cost, lifetime,
    // prev lifetime and utilization all read the em dash. A `0` would claim the
    // pipeline never ran, and `0 %` that it ran flat out.
    const row = (await screen.findByText('dlt-9902', { selector: 'div.font-semibold' })).closest(
      'tr'
    ) as HTMLElement;
    const cells = within(row)
      .getAllByRole('cell')
      .map((cell) => cell.textContent?.trim());

    expect(cells.slice(3, 7)).toEqual(['—', '—', '—', '—']);
    expect(cells.join(' ')).not.toMatch(/NaN/);
  });

  it('links the recommendations card to the PIPELINE family', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    const link = await screen.findByRole('link', { name: 'View pipeline recommendations' });
    expect(link).toHaveAttribute(
      'href',
      '/databricks/compute/recommendations?object_type=PIPELINE'
    );
  });

  it('shows the empty state when the scope returns no pipeline', async () => {
    apiMocks.getComputePipelinesOverview.mockResolvedValue({
      ...computePipelinesOverviewFixture,
      kpis: { total_cost_usd: 0, cost_delta_pct: null, active_pipelines: 0 },
      items: [],
      total: 0,
    });

    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    expect(await screen.findByText('No pipelines')).toBeInTheDocument();
  });

  it('does not hit the cost endpoint until the Cost tab is opened', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    await screen.findByText('bronze-to-silver');
    // The Overview tab is active on mount: the cost endpoint stays untouched.
    expect(apiMocks.listComputePipelinesCost).not.toHaveBeenCalled();
  });

  it('fetches the cost grain and ranks the top-cost pipeline when the Cost tab opens', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    await screen.findByText('bronze-to-silver');
    await user.click(screen.getByRole('tab', { name: 'Cost' }));

    // The cost endpoint is now hit on the same window / default cost sort.
    await waitFor(() => {
      const calls = apiMocks.listComputePipelinesCost.mock.calls;
      const last = calls[calls.length - 1]?.[0];
      expect(last?.window_days).toBe(1);
      expect(last?.sort).toBe('cost_desc');
    });

    // The top-cost pipeline (rank 1, is_top_cost) carries the "Top" badge.
    const row = (
      await screen.findByText('bronze-to-silver', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;
    expect(within(row).getByText('Top')).toBeInTheDocument();

    // The Cost tab is a billing reading: it renames its delta column like the
    // overview does, and **keeps** DBU.
    const headers = within(await screen.findByRole('table'))
      .getAllByRole('columnheader')
      .map((cell) => cell.textContent?.trim());
    expect(headers).toEqual(['Rank', 'Workspace', 'Pipeline', 'Cost', 'Prev cost', 'DBU']);
  });

  it('offers the three sub-tabs, Efficiency included', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    expect(await screen.findByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Cost' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Efficiency' })).toBeInTheDocument();
  });

  it('does not hit the efficiency endpoint until the Efficiency tab is opened', async () => {
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    await screen.findByText('bronze-to-silver');
    expect(apiMocks.listComputePipelinesEfficiency).not.toHaveBeenCalled();
  });

  it('lists the utilization at the pipeline grain, with no Zombie column', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    await user.click(await screen.findByRole('tab', { name: 'Efficiency' }));

    await waitFor(() => {
      const calls = apiMocks.listComputePipelinesEfficiency.mock.calls;
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
      'Pipeline',
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
    // A pipeline cluster dies with its update: a zombie column would be `false`
    // everywhere and read like a passing control (024 C1).
    expect(headers).not.toContain('Zombie');

    // The measured row carries its metrics; the idle delta is in points.
    const measured = (
      await within(table).findByText('bronze-to-silver', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;
    expect(within(measured).getByText('72%')).toBeInTheDocument();
    expect(within(measured).getByText('+4.0 pts')).toBeInTheDocument();
    expect(within(measured).getByText('Optimal')).toBeInTheDocument();
  });

  it('reads "—" and never 0 % on a serverless pipeline, billed but unmeasured', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ComputePipelines />, { route: '/databricks/pipeline-compute' });

    await user.click(await screen.findByRole('tab', { name: 'Efficiency' }));

    const table = await screen.findByRole('table');
    const row = (
      await within(table).findByText('dlt-9902', { selector: 'div.font-semibold' })
    ).closest('tr') as HTMLElement;

    // Every metric of that row is unmeasured: em dashes, no invented zero.
    expect(within(row).getAllByText('—').length).toBeGreaterThan(5);
    expect(within(row).queryByText('0%')).not.toBeInTheDocument();
    expect(within(row).queryByText('$0.00')).not.toBeInTheDocument();
  });

  // A row is clickable on the three tabs, not only where the metrics live.
  it.each(['Overview', 'Cost', 'Efficiency'] as const)(
    'opens the pipeline drawer from a row of the %s tab',
    async (tab) => {
      await openDrawerFrom(tab, 'bronze-to-silver');

      const drawer = screen.getByRole('dialog', { name: 'Pipeline details' });
      expect(within(drawer).getByText('dlt-7781')).toBeInTheDocument();
      expect(await within(drawer).findByText('72%')).toBeInTheDocument();

      await waitFor(() => {
        expect(apiMocks.getComputePipelineDetail).toHaveBeenCalledWith(
          'dlt-7781',
          expect.objectContaining({ window_days: 1 })
        );
      });
    }
  );

  it('shows both trends and the technical specs in the drawer, and no governance block', async () => {
    await openDrawerFrom('Cost', 'bronze-to-silver');

    const drawer = screen.getByRole('dialog', { name: 'Pipeline details' });

    expect(within(drawer).getByText('Technical specs')).toBeInTheDocument();
    expect(within(drawer).getByText('Standard_DS3_v2')).toBeInTheDocument();
    // Autoscaling off: the configured fixed worker count, not the observed maximum.
    expect(within(drawer).getByText('4 fixed')).toBeInTheDocument();
    expect(within(drawer).getByText('Cost trend (≈90 days)')).toBeInTheDocument();
    // The cumulated uptime of the updates, not a cluster lifetime.
    expect(within(drawer).getByText('Uptime trend (≈90 days)')).toBeInTheDocument();

    // Governance is a cluster-level snapshot and stays on the all-purpose grain (024 C2).
    expect(within(drawer).queryByText('Governance')).not.toBeInTheDocument();
    expect(within(drawer).queryByText('Tags')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(apiMocks.getComputePipelineCostTrend).toHaveBeenCalledWith(
        'dlt-7781',
        expect.objectContaining({ granularity: 'week' })
      );
      expect(apiMocks.getComputePipelineUptimeTrend).toHaveBeenCalledWith(
        'dlt-7781',
        expect.objectContaining({ granularity: 'week' })
      );
    });
  });

  it('keeps the drawer usable when the pipeline has no efficiency row', async () => {
    apiMocks.getComputePipelineDetail.mockResolvedValue(
      computePipelineDetailWithoutEfficiencyFixture
    );

    await openDrawerFrom('Cost', 'dlt-9902');

    const drawer = screen.getByRole('dialog', { name: 'Pipeline details' });

    // The cost block is real; the utilization block reads "—" with an explanation.
    expect(
      await within(drawer).findByText(/No utilization measured over this window/)
    ).toBeInTheDocument();
    expect(within(drawer).getByText('$150.00')).toBeInTheDocument();
    expect(within(drawer).queryByText('0%')).not.toBeInTheDocument();
  });

  it('closes the drawer on Escape', async () => {
    const user = await openDrawerFrom('Cost', 'bronze-to-silver');

    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Pipeline details' })).not.toBeInTheDocument();
    });
  });
});
