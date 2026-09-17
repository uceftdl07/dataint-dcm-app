import { beforeEach, describe, expect, it, vi } from 'vitest';
import { protectedRoutes } from '../app-routes';
import { getPageMeta } from '../config/navigation';
import { ROUTE_PERMISSIONS } from '../config/role-permissions';
import {
  computeServerlessCostTrendFixture,
  computeServerlessGovernanceFixture,
  computeServerlessLevers7dFixture,
  computeServerlessLeversFixture,
  computeServerlessLeversUnmeasurableFixture,
  computeServerlessNotebookObjectsFixture,
  computeServerlessObjectCostTrendFixture,
  computeServerlessObjectDetailFixture,
  computeServerlessObjectsFixture,
  computeServerlessOverviewFixture,
  computeServerlessSurfacesFixture,
} from '../test/fixtures/compute-serverless';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../test/render';
import ComputeServerless from './ComputeServerless';

vi.mock('../api/dcmApiClient', () => ({
  getComputeServerlessOverview: vi.fn(),
  listComputeServerlessSurfaces: vi.fn(),
  getComputeServerlessCostTrend: vi.fn(),
  listComputeServerlessGovernance: vi.fn(),
  getComputeServerlessLevers: vi.fn(),
  listComputeServerlessObjects: vi.fn(),
  getComputeServerlessObjectDetail: vi.fn(),
  getComputeServerlessObjectCostTrend: vi.fn(),
  listDatabricksWorkspaces: vi.fn(),
  getComputeFilterOptions: vi.fn(),
}));

import {
  getComputeServerlessCostTrend,
  getComputeServerlessLevers,
  getComputeServerlessObjectCostTrend,
  getComputeServerlessObjectDetail,
  getComputeServerlessOverview,
  listComputeServerlessGovernance,
  listComputeServerlessObjects,
  listComputeServerlessSurfaces,
  listDatabricksWorkspaces,
} from '../api/dcmApiClient';

const apiMocks = {
  getComputeServerlessOverview: vi.mocked(getComputeServerlessOverview),
  listComputeServerlessSurfaces: vi.mocked(listComputeServerlessSurfaces),
  getComputeServerlessCostTrend: vi.mocked(getComputeServerlessCostTrend),
  listComputeServerlessGovernance: vi.mocked(listComputeServerlessGovernance),
  getComputeServerlessLevers: vi.mocked(getComputeServerlessLevers),
  listComputeServerlessObjects: vi.mocked(listComputeServerlessObjects),
  getComputeServerlessObjectDetail: vi.mocked(getComputeServerlessObjectDetail),
  getComputeServerlessObjectCostTrend: vi.mocked(getComputeServerlessObjectCostTrend),
  listDatabricksWorkspaces: vi.mocked(listDatabricksWorkspaces),
};

/**
 * The table a column belongs to, resolved through the `<colgroup>`.
 *
 * `ComputeDataTable` puts no test id on its `<table>` and three of them are on this page at
 * once, so the column id is the only stable discriminator: `performance_target` is the
 * objects table, `identity_source` the governance one, `target` the performance-target one.
 * A header label would not do — "Budget policy" appears in two of the three.
 */
function tableWithColumn(columnId: string): HTMLElement {
  const col = document.body.querySelector(`col[data-column-id="${columnId}"]`);
  const table = col?.closest('table');
  if (!table) throw new Error(`No rendered table exposes the column "${columnId}"`);
  return table as HTMLElement;
}

function headerTexts(table: HTMLElement): string[] {
  return within(table)
    .getAllByRole('columnheader')
    .map((cell) => cell.textContent?.trim() ?? '');
}

function rowFor(table: HTMLElement, label: string | RegExp): HTMLElement {
  // `getAllByText(...)[0]`: several rows can carry the same workspace name, and the first
  // match is the row this helper is asked about.
  const row = within(table).getAllByText(label)[0]?.closest('tr');
  if (!row) throw new Error(`No row matching ${String(label)}`);
  return row as HTMLElement;
}

/**
 * Text of one cell, addressed by its column **header** rather than by index, so a column
 * inserted before it does not silently move the assertion onto a neighbour.
 */
function cellText(table: HTMLElement, rowLabel: string | RegExp, header: string): string {
  const columns = headerTexts(table);
  const index = columns.indexOf(header);
  if (index < 0) throw new Error(`No column "${header}" among [${columns.join(' | ')}]`);
  const row = rowFor(table, rowLabel);
  // A `<th scope="row">` is column 0 and is a `rowheader`, not a `cell`.
  const offset = row.querySelector('th') ? 1 : 0;
  return within(row).getAllByRole('cell')[index - offset]?.textContent?.trim() ?? '';
}

/**
 * Fills of the daily stacked columns, in DOM order.
 *
 * `:not([fill="transparent"])` drops the invisible hover overlay — one rect per column —
 * which would otherwise be counted as a segment and break the colour assertions.
 */
function stackedFills(): string[] {
  return Array.from(
    document.body.querySelectorAll<SVGRectElement>(
      '[data-testid="compute-stacked-columns"] rect[fill]:not([fill="transparent"])'
    )
  ).map((rect) => rect.getAttribute('fill') ?? '');
}

/** Labels of a ranked-bars list — the first inner `<div>`, i.e. without the sublabel. */
function rankedLabels(list: HTMLElement): string[] {
  return within(list)
    .getAllByTestId('compute-ranked-bars-row')
    .map((row) => row.querySelector('div > div')?.textContent?.trim() ?? '');
}

/**
 * The objects payload the server would return for one surface.
 *
 * Filtering here is what makes the drill-down tabs testable: the fixture holds rows of
 * three surfaces, and a tab returning all of them would let an assertion pass on a row the
 * tab is not supposed to show.
 */
function objectsForSurface(surface?: string) {
  if (!surface) return computeServerlessObjectsFixture;
  const items = computeServerlessObjectsFixture.items.filter(
    (item) => item.serverless_surface === surface
  );
  return {
    ...computeServerlessObjectsFixture,
    items,
    total: items.length,
    object_count: items.length,
    total_cost_usd: items.reduce<number>((sum, item) => sum + (item.cost_usd ?? 0), 0),
  };
}

function renderPage() {
  return renderWithProviders(<ComputeServerless />, { route: '/databricks/serverless' });
}

beforeEach(() => {
  vi.clearAllMocks();

  apiMocks.getComputeServerlessOverview.mockResolvedValue(computeServerlessOverviewFixture);
  apiMocks.listComputeServerlessSurfaces.mockResolvedValue(computeServerlessSurfacesFixture);
  apiMocks.getComputeServerlessCostTrend.mockResolvedValue(computeServerlessCostTrendFixture);
  apiMocks.listComputeServerlessGovernance.mockResolvedValue(computeServerlessGovernanceFixture);
  // Two windows, two payloads: the only way to prove the page reads the rate it displays
  // instead of printing a constant.
  apiMocks.getComputeServerlessLevers.mockImplementation((params) =>
    Promise.resolve(
      params?.window_days === 7 ? computeServerlessLevers7dFixture : computeServerlessLeversFixture
    )
  );
  apiMocks.listComputeServerlessObjects.mockImplementation((params) =>
    Promise.resolve(
      params?.surface === 'NOTEBOOK'
        ? computeServerlessNotebookObjectsFixture
        : objectsForSurface(params?.surface)
    )
  );
  apiMocks.getComputeServerlessObjectDetail.mockResolvedValue(computeServerlessObjectDetailFixture);
  apiMocks.getComputeServerlessObjectCostTrend.mockResolvedValue(
    computeServerlessObjectCostTrendFixture
  );
  apiMocks.listDatabricksWorkspaces.mockResolvedValue({
    items: [
      {
        workspace_id: 'ws-1',
        display_name: 'dbw-analytics-prod',
        source_lz_id: 'lz-1',
        cluster_count: 0,
      },
    ],
  } as never);
});

describe('ComputeServerless — block 1, what serverless weighs', () => {
  it('frames the share as a share that is not growing', async () => {
    renderPage();

    // The headline figure and its sentence, and nothing that turns a falling share into an
    // explosion: what justifies the page is the absolute uncovered mass instead.
    expect(await screen.findByText('79.3%')).toBeInTheDocument();
    expect(screen.getByText(/of compute spend is serverless/)).toBeInTheDocument();

    const framing = screen.getByRole('region', { name: 'What serverless weighs' });
    expect(framing).toHaveTextContent('its share is not growing');
    expect(framing).toHaveTextContent('classic spend is rising faster over this window');
    expect(framing).toHaveTextContent('the absolute mass that nothing attributes');
  });

  it('splits the share into two segments and says why not three', async () => {
    renderPage();

    const chart = await screen.findByRole('img', { name: 'Serverless share of compute spend' });
    const legend = within(
      chart.closest('[data-testid="compute-stacked-bar"]') as HTMLElement
    ).getByTestId('compute-stacked-bar-legend');

    const entries = within(legend).getAllByRole('listitem');
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent('Serverless');
    expect(entries[0]).toHaveTextContent('$285,000.00 · 79.3%');
    expect(entries[1]).toHaveTextContent('Classic');

    // The warehouse dollars missing from the utilization snapshot are named, not folded
    // into a third segment that would change the denominator.
    expect(screen.getByText(/serverless \/ \(serverless \+ classic\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/\$2,100.00 of warehouse spend is absent from the utilization snapshot/)
    ).toBeInTheDocument();
  });

  it('shows the four framing KPIs with their own window and denominator', async () => {
    renderPage();

    // Scoped to the block: the same dollars are restated in the chargeback tiles and in the
    // governance table, so an unscoped lookup would pass on either of them.
    const framing = await screen.findByRole('region', { name: 'What serverless weighs' });
    expect(await within(framing).findByText('$285,000.00')).toBeInTheDocument();
    expect(within(framing).getByText('Last 30d · 1,240,000 DBU')).toBeInTheDocument();
    expect(within(framing).getByText('+5.2%')).toBeInTheDocument();
    expect(within(framing).getByText('$271,000.00 previously')).toBeInTheDocument();

    // The uncovered dollars are a share of the **governance** snapshot, which has its own
    // 90-day span: dividing them by the window total would read 14.5 % instead.
    expect(within(framing).getByText('$41,200.00')).toBeInTheDocument();
    expect(
      within(framing).getByText('55.8% of the snapshot · 2026-06-12 → 2026-09-09')
    ).toBeInTheDocument();
    expect(
      within(framing).getByText('Whole perimeter · 2026-06-12 → 2026-09-09')
    ).toBeInTheDocument();
  });

  it('ranks the twelve surfaces as sorted bars in a single hue', async () => {
    renderPage();

    const ranking = await screen.findByRole('list', { name: 'Serverless spend per surface' });
    expect(rankedLabels(ranking).slice(0, 5)).toEqual([
      'Jobs',
      'SQL warehouses',
      'DLT pipelines',
      'Notebooks',
      'Apps',
    ]);

    // Twelve surfaces are a magnitude, not twelve categories: one hue, and the ranking
    // itself carries the comparison.
    const bars = Array.from(ranking.querySelectorAll<SVGRectElement>('rect[fill]'));
    expect(bars).toHaveLength(12);
    for (const bar of bars) {
      expect(bar.getAttribute('fill')).toMatch(/var\(--tdf-blue/);
    }
    const intensities = bars.map((bar) => Number(bar.getAttribute('data-intensity')));
    expect(intensities[0]).toBeGreaterThan(intensities[intensities.length - 1]);
  });

  it('keeps every surface on its own colour when one is filtered out', async () => {
    const { unmount } = renderPage();

    await waitFor(() => expect(stackedFills()).toHaveLength(18));
    const before = stackedFills();
    // Column-major order: the first segment of the first column is the first series.
    expect(before[0]).toBe('var(--tdf-blue)');
    expect(before).toContain('var(--tdf-purple)');

    unmount();

    apiMocks.getComputeServerlessCostTrend.mockResolvedValue({
      ...computeServerlessCostTrendFixture,
      items: computeServerlessCostTrendFixture.items.filter(
        (item) => item.serverless_surface !== 'SQL_WAREHOUSE'
      ),
      series: computeServerlessCostTrendFixture.series.filter(
        (series) => series !== 'SQL_WAREHOUSE'
      ),
    });
    renderPage();

    await waitFor(() => expect(stackedFills()).toHaveLength(15));
    const after = stackedFills();
    expect(after[0]).toBe('var(--tdf-blue)');
    expect(after).not.toContain('var(--tdf-purple)');
    // The survivors kept their fills: a colour follows its surface, never its rank.
    expect(new Set(after)).toEqual(new Set(before.filter((fill) => fill !== 'var(--tdf-purple)')));
  });
});

describe('ComputeServerless — block 2, attribution and chargeback', () => {
  it('separates dollars without an owner from dollars billed to a workspace', async () => {
    renderPage();

    // Two tiles, two notions, each on the governance denominator — never one tile whose
    // percentage silently mixes "nobody to charge" with "billed to a workspace".
    expect(await screen.findByText('55.8% of the snapshot')).toBeInTheDocument();
    expect(screen.getByText('No resolvable owner')).toBeInTheDocument();
    expect(screen.getByText('17.5% of the snapshot')).toBeInTheDocument();
    expect(screen.getByText('No object key')).toBeInTheDocument();

    // The second notion is a grain, not a defect — and the page has to say so, otherwise it
    // reads as 17.5 % of spend waiting to be tagged.
    const attribution = screen.getByRole('region', { name: 'Attribution and chargeback' });
    expect(attribution).toHaveTextContent('A different notion, and not a defect');
    expect(attribution).toHaveTextContent(
      'There is no object to attach, so there is nothing here to fix'
    );
  });

  it('shows coverage per workspace and surface, with unmeasured cells left empty', async () => {
    renderPage();

    const heatmap = await screen.findByTestId('compute-coverage-heatmap');
    const jobs = within(heatmap).getByText('Jobs').closest('tr') as HTMLElement;
    expect(
      within(jobs)
        .getAllByRole('cell')
        .map((cell) => cell.textContent?.trim())
    ).toEqual(['45.9%', '30.1%', '8.4%', '94.9%']);

    // Genie is billed to the workspace: no identity to cover, so "—" and never `0`.
    const genie = within(heatmap).getByText('Genie').closest('tr') as HTMLElement;
    expect(
      within(genie)
        .getAllByRole('cell')
        .map((cell) => cell.textContent?.trim())
    ).toEqual(['0.0%', '0.0%', '0.0%', '—']);
  });

  it('ranks notebook consumers without a second axis, and states concentration apart', async () => {
    renderPage();

    const ranking = await screen.findByRole('list', {
      name: 'Top notebook consumers of serverless spend',
    });
    expect(rankedLabels(ranking).slice(0, 2)).toEqual(['exploration-carbon', 'adhoc-query']);
    // Dollars only inside the bars: a cumulative percentage next to them would be the
    // second axis this page refuses.
    expect(ranking.textContent).not.toMatch(/%/);

    // The concentration is a figure of its own, stated in prose with its population.
    expect(screen.getByText('7.0%')).toBeInTheDocument();
    expect(
      screen.getByText(/these 3 of 461 billed notebook objects — \$1,687.10 of \$24,130.00/)
    ).toBeInTheDocument();
  });

  it('lists budget-policy and identity coverage per workspace in a table', async () => {
    renderPage();

    await screen.findByTestId('compute-coverage-heatmap');
    const governance = tableWithColumn('identity_source');

    expect(headerTexts(governance)).toEqual([
      'Workspace',
      'Surface',
      'Cost',
      'Owner tag',
      'Cost center',
      'Budget policy',
      'Policies',
      'Identity',
      'Identity source',
    ]);
    expect(cellText(governance, 'dbw-analytics-prod', 'Budget policy')).toBe('8.4%');
    expect(cellText(governance, 'dbw-analytics-prod', 'Policies')).toBe('2');
    expect(cellText(governance, 'dbw-analytics-prod', 'Identity source')).toBe('RUN_AS');
  });
});

describe('ComputeServerless — block 3, the levers that exist', () => {
  it('shows the performance-target split as exposed dollars, with no saving figure', async () => {
    renderPage();

    await screen.findByRole('img', { name: 'Serverless spend per performance target' });
    const targets = tableWithColumn('target');

    // No "estimated saving" column, and none possible: both modes bill the same SKU.
    expect(headerTexts(targets)).toEqual([
      'Perf. target',
      'Cost exposed',
      'Share',
      'Objects',
      'DBU',
      'Runs',
    ]);
    expect(cellText(targets, 'Unset', 'Cost exposed')).toBe('$203,775.00');
    expect(cellText(targets, 'Unset', 'Share')).toBe('71.5%');
    expect(screen.getByText(/No estimated saving, deliberately/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'The levers that exist' })).toHaveTextContent(
      'the dollars below are exposed, not recoverable'
    );
  });

  // The window-wide cost-per-run histogram was withdrawn from the page on 2026-09-11: the
  // distribution now lives per object, in the drawer, and per surface, in the `$/run p50`
  // and `$/run p99` columns of block 4 — both still covered below.
  it('keeps no window-wide cost-per-run chart in the levers block', async () => {
    renderPage();

    await screen.findByRole('region', { name: 'The levers that exist' });
    expect(screen.queryByRole('list', { name: 'Cost per run bands' })).toBeNull();
    expect(screen.queryByLabelText('Distribution of cost per serverless run')).toBeNull();
    expect(screen.queryByRole('heading', { name: 'Cost per run' })).toBeNull();
  });

  it('presents the DLT comparison as a correlation carrying its own window', async () => {
    renderPage();

    const caption = await screen.findByText(/Per requested execution, over/);
    const dlt = caption.closest('table') as HTMLElement;

    expect(caption.textContent).toContain('2026-08-11');
    expect(caption.textContent).toContain('2026-09-09');
    expect(caption.textContent).toContain('top 10 failing pipelines');

    expect(headerTexts(dlt)).toEqual([
      'Cloud',
      'Compute',
      'Requests',
      'Failure rate',
      'Duration p50',
      'Duration p95',
      'Pipelines',
      'Failure concentration',
    ]);

    const region = screen.getByRole('region', { name: 'The levers that exist' });
    expect(region).toHaveTextContent('never a promise of a gain');
    expect(region).toHaveTextContent('deduplicated by request_id');
    expect(region).toHaveTextContent(
      'the direction of the failure gap reverses between this window and full history'
    );
  });

  it('labels each rate by its cloud provider, and publishes none below the floor', async () => {
    renderPage();

    const dlt = (await screen.findByText(/Per requested execution, over/)).closest(
      'table'
    ) as HTMLElement;

    // A rate that does not say which cloud it is about is a rate nobody can act on.
    expect(
      within(dlt)
        .getAllByRole('rowheader')
        .map((cell) => cell.textContent?.trim())
    ).toEqual(['aws', 'aws', 'azure', 'azure']);
    expect(within(dlt).getByText('1.99%')).toBeInTheDocument();
    expect(within(dlt).getByText('13.31%')).toBeInTheDocument();

    // 6 requests is below the endpoint's floor of 30: the count is shown, never a
    // percentage computed on six rows.
    const scarce = within(dlt).getByText('Comparison not significant').closest('tr') as HTMLElement;
    expect(scarce).toHaveTextContent('6 requests');
    expect(scarce.textContent).not.toMatch(/%/);
  });

  it('reads the failure rate from the response instead of printing a constant', async () => {
    renderPage();

    const dlt = (await screen.findByText(/Per requested execution, over/)).closest(
      'table'
    ) as HTMLElement;
    expect(within(dlt).getByText('1.99%')).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole('button', { name: 'Last 7d' }));

    await waitFor(() => {
      const table = screen
        .getByText(/Per requested execution, over/)
        .closest('table') as HTMLElement;
      expect(within(table).getByText('4.67%')).toBeInTheDocument();
    });
    const refreshed = screen
      .getByText(/Per requested execution, over/)
      .closest('table') as HTMLElement;
    expect(within(refreshed).queryByText('1.99%')).toBeNull();
    // The label follows the figures: a 7-day rate under a 30-day caption is a wrong rate.
    expect(refreshed.querySelector('caption')?.textContent).toContain('2026-09-03');
  });

  it('states what a perimeter cannot measure instead of showing zeros', async () => {
    apiMocks.getComputeServerlessLevers.mockResolvedValue(
      computeServerlessLeversUnmeasurableFixture
    );
    renderPage();

    expect(await screen.findByText(/No DLT comparison on this perimeter/)).toBeInTheDocument();
    expect(screen.queryByText(/Per requested execution, over/)).toBeNull();
  });
});

describe('ComputeServerless — block 4, drill down per surface', () => {
  it('shows runs and cost per run only on the surfaces that count executions', async () => {
    renderPage();

    // The tab strip is derived from the surfaces query, so the first tab is only selected
    // once that query resolves — and the run columns only exist from then on, with the rows
    // of that surface arriving one query later.
    await screen.findByRole('tab', { name: 'Jobs', selected: true });
    await screen.findByText('daily-ingest');
    const jobs = tableWithColumn('performance_target');
    expect(headerTexts(jobs)).toContain('Runs');
    expect(headerTexts(jobs)).toContain('$/run p50');
    expect(cellText(jobs, 'daily-ingest', 'Runs')).toBe('8,902');
    expect(cellText(jobs, 'daily-ingest', '$/run p50')).toBe('$0.28p99 $2.10');

    await userEvent.setup().click(screen.getByRole('tab', { name: 'Genie' }));

    const genie = tableWithColumn('performance_target');
    // Workspace grain: no object key, so no object column and no run columns — a column of
    // dashes would claim the metric was measured and came back empty.
    expect(headerTexts(genie)).not.toContain('Object');
    expect(headerTexts(genie)).not.toContain('Runs');
    expect(headerTexts(genie)).not.toContain('$/run p50');
    expect(screen.getByText('Billed at workspace grain.')).toBeInTheDocument();
  });

  it('opens the drawer on a row that has an object key, and not on one that has none', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole('tab', { name: 'Jobs', selected: true });
    await user.click(await screen.findByText('daily-ingest'));

    const drawer = await screen.findByRole('dialog', { name: 'Serverless object details' });
    expect(within(drawer).getByText('Object ID')).toBeInTheDocument();
    await user.click(within(drawer).getByRole('button', { name: 'Close drawer' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    await user.click(screen.getByRole('tab', { name: 'Genie' }));
    const genie = await waitFor(() => {
      const table = tableWithColumn('performance_target');
      expect(within(table).getByText('$4,190.00')).toBeInTheDocument();
      return table;
    });

    // `object_id` is null, so the detail endpoint would answer 404: the row carries real
    // cost and no drill-down.
    await user.click(within(genie).getByText('$4,190.00'));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(apiMocks.getComputeServerlessObjectDetail).toHaveBeenCalledTimes(1);
  });
});

describe('ComputeServerless — block 5, what the page cannot tell', () => {
  it('states its blind spots as assumed absences', async () => {
    renderPage();

    const blind = await screen.findByRole('region', { name: 'What this page cannot tell you' });
    expect(
      within(blind).getByText('No CPU, memory or idle time, and no node rightsizing.')
    ).toBeInTheDocument();
    expect(
      within(blind).getByText('97.1 % of warehouse queries have no identifiable source.')
    ).toBeInTheDocument();
    expect(within(blind).getByText('No cost per SQL query.')).toBeInTheDocument();
    expect(
      within(blind).getByText('A column with no serverless equivalent is absent, not empty.')
    ).toBeInTheDocument();
    expect(blind).toHaveTextContent('which is empty on this perimeter');
  });
});

describe('ComputeServerless — route, navigation and permission', () => {
  it('registers /databricks/serverless ahead of the focus-view catch-all', async () => {
    const serverless = protectedRoutes.findIndex(
      (route) => route.path === '/databricks/serverless'
    );
    const focus = protectedRoutes.findIndex((route) => route.path === '/databricks/:view');
    expect(serverless).toBeGreaterThanOrEqual(0);
    expect(focus).toBeGreaterThanOrEqual(0);
    // Declared after the catch-all, `serverless` would match as a `:view` and render the
    // focus page instead of this one.
    expect(serverless).toBeLessThan(focus);

    const loaded = await protectedRoutes[serverless].importPage();
    expect(loaded.default).toBe(ComputeServerless);
  });

  it('titles the page from the menu and gates it on the databricks permission', () => {
    expect(getPageMeta('/databricks/serverless').title).toBe('Compute — Serverless');
    expect(ROUTE_PERMISSIONS['/databricks/serverless']).toBe('page:databricks');
  });
});
