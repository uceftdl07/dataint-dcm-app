import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { UcUsageActivityHeatmap } from './uc-usage-activity-heatmap';
import { UcUsageTableTimeChart } from './uc-usage-time-chart';
import { UcUsageColumnFilter } from './uc-usage-column-filter';
import { UcUsageDetailDrawer } from './uc-usage-detail-drawer';
import { ucEntityDetailFixture } from '../../../test/fixtures/uc-usage-exploration';
import { ucTableChartsFixture } from '../../../test/fixtures/uc-usage-charts';
import { ucRecommendationCopy } from '../../../lib/uc-usage/recommendation-copy';
import { ucUsageRecommendationsFixture } from '../../../test/fixtures/uc-usage';
import { ucUsageCostChangeBarWidth } from './uc-usage-chart-utils';
import { UcUsageCostChangesPanel } from './uc-usage-exploration-charts';
import { ucCostChangesFixture } from '../../../test/fixtures/uc-usage-exploration';

describe('UC usage exploration', () => {
  it('uses each table’s peak by default and keeps a selectable shared scale', async () => {
    const activity = {
      ...ucTableChartsFixture.activity,
      rows: ucTableChartsFixture.activity.rows.map((row, index) => ({
        ...row,
        cells: [1, 0.5, 0].map((factor) => ({
          value: factor * (index === 0 ? 10 : 10000),
          observed_days: 1,
          expected_days: 1,
        })),
      })),
    };
    render(<UcUsageActivityHeatmap activity={activity} />);
    const small = screen.getByRole('button', { name: /orders.*2026-09-01/ });
    const large = screen.getByRole('button', { name: /invoices.*2026-09-01/ });
    expect(small).toHaveAttribute('data-scale-max', '10');
    expect(large).toHaveAttribute('data-scale-max', '10000');
    expect(small.style.background).toBe(large.style.background);
    await userEvent.selectOptions(screen.getByRole('combobox'), 'shared');
    expect(small).toHaveAttribute('data-scale-max', '10000');
    expect(small.style.background).not.toBe(large.style.background);
  });

  it('keeps a huge Other aggregate out of the individual-table axis', async () => {
    const { container } = render(
      <UcUsageTableTimeChart
        ariaLabel="Daily reads"
        unit="Reads"
        formatValue={(v) => String(v)}
        series={[
          { key: 'small', label: 'Small table', points: [{ date: '2026-09-01', value: 10 }] },
          {
            key: 'other-tables',
            label: 'Other',
            entity_count: 99,
            points: [{ date: '2026-09-01', value: 1000000 }],
          },
        ]}
      />
    );
    const main = screen.getByRole('img', { name: 'Daily reads' });
    expect(within(main).getByText('20')).toBeInTheDocument();
    expect(main.querySelector('[data-series-key="other-tables"]')).toBeNull();
    const detail = container.querySelector('details')!;
    expect(detail).not.toHaveAttribute('open');
    await userEvent.click(container.querySelector('summary')!);
    expect(detail).toHaveAttribute('open');
    const other = screen.getByRole('img', { name: 'Daily reads — other tables combined' });
    expect(within(other).getByText(/^2m$/i)).toBeInTheDocument();
    expect(within(main).getByText('20')).toBeInTheDocument();
  });

  it('validates numeric ranges and converts GB to bound byte values', async () => {
    const change = vi.fn();
    render(
      <UcUsageColumnFilter
        label="Bytes written"
        definition={{ kind: 'number', unit: 'GB', scale: 1024 ** 3 }}
        onChange={change}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Filter Bytes written' }));
    await userEvent.selectOptions(screen.getByLabelText('Condition'), 'between');
    await userEvent.type(screen.getByLabelText('Minimum (GB)'), '2');
    await userEvent.type(screen.getByLabelText('Maximum (GB)'), '1');
    expect(screen.getByRole('button', { name: 'Apply filter' })).toBeDisabled();
    await userEvent.clear(screen.getByLabelText('Maximum (GB)'));
    await userEvent.type(screen.getByLabelText('Maximum (GB)'), '3');
    await userEvent.click(screen.getByRole('button', { name: 'Apply filter' }));
    expect(change).toHaveBeenCalledWith('between:2147483648,3221225472');
  });

  it('keeps missing-value filters distinct from zero', async () => {
    const change = vi.fn();
    render(
      <UcUsageColumnFilter
        label="Cost"
        definition={{ kind: 'number' }}
        value="isnull:"
        onChange={change}
      />
    );
    await userEvent.click(screen.getByRole('button', { name: 'Filter Cost (active)' }));
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Apply filter' }));
    expect(change).toHaveBeenCalledWith('isnull:');
    await userEvent.click(screen.getByRole('button', { name: 'Filter Cost (active)' }));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(change).toHaveBeenLastCalledWith(null);
  });

  it('does not display old detail data during errors and restores body scrolling', async () => {
    const retry = vi.fn();
    const before = document.body.style.overflow;
    const { unmount } = render(
      <UcUsageDetailDrawer
        selection={{ kind: 'table', id: 'main.sales.orders', label: 'orders' }}
        data={ucEntityDetailFixture}
        loading={false}
        error={new Error('offline')}
        onClose={vi.fn()}
        onRetry={retry}
      />
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Unable to load usage details');
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry details' }));
    expect(retry).toHaveBeenCalledOnce();
    unmount();
    expect(document.body.style.overflow).toBe(before);
  });

  it('paints a cost increase with a defined token, not just savings', () => {
    // A cost increase used to ask for `--tdf-orange`, which no theme defines: the
    // declaration was dropped and only the teal savings bars were ever painted.
    const increase = { ...ucCostChangesFixture.items[0], delta_usd: 6, delta_pct: 150 };
    const { container } = render(
      <UcUsageCostChangesPanel
        data={{ ...ucCostChangesFixture, items: [increase] }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
      />
    );
    const bar = container.querySelector<HTMLElement>('.rounded-sm[style]');
    expect(bar).not.toBeNull();
    expect(bar!.style.background).toBe('var(--warning)');
    expect(bar!.style.background).not.toContain('tdf-orange');
    expect(bar!.style.left).toBe('50%');
  });

  it('anchors savings on the zero line so a pixel minimum cannot cross it', () => {
    const savings = { ...ucCostChangesFixture.items[0], delta_usd: -6, delta_pct: -60 };
    const { container } = render(
      <UcUsageCostChangesPanel
        data={{ ...ucCostChangesFixture, items: [savings] }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
      />
    );
    const bar = container.querySelector<HTMLElement>('.rounded-sm[style]');
    expect(bar!.style.background).toBe('var(--tdf-teal)');
    expect(bar!.style.right).toBe('50%');
    expect(bar!.style.left).toBe('');
  });

  it('rescales the remaining bars when a dominant table is excluded', async () => {
    // A $500 table flattens a $10 one: 1% of the row. Excluding it must give the $10
    // table the full half-width, which is the whole reason the toggle exists.
    const items = [
      { ...ucCostChangesFixture.items[0], key: 'huge', label: 'main.sales.huge', delta_usd: 500 },
      { ...ucCostChangesFixture.items[0], key: 'small', label: 'main.sales.small', delta_usd: 10 },
    ];
    const { container } = render(
      <UcUsageCostChangesPanel
        data={{ ...ucCostChangesFixture, items, entity_count: 2 }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
      />
    );
    const bars = () =>
      [...container.querySelectorAll<HTMLElement>('.rounded-sm[style]')].map((b) => b.style.width);
    expect(bars()).toEqual(['49%', '0.98%']);

    await userEvent.click(
      screen.getByRole('button', { name: 'main.sales.huge · exclude from the bar scale' })
    );
    // The excluded row keeps its place and its figures, but no longer sets the scale.
    expect(bars()).toEqual(['0%', '49%']);
    expect(container.textContent).toContain('+$500.00');

    const reset = screen.getByRole('button', { name: '1 excluded from the scale · reset' });
    await userEvent.click(reset);
    expect(bars()).toEqual(['49%', '0.98%']);
    expect(
      screen.queryByRole('button', { name: /excluded from the scale/ })
    ).not.toBeInTheDocument();
  });

  it('counts only on-screen exclusions, so a stale key cannot overstate the reset', async () => {
    const items = [
      { ...ucCostChangesFixture.items[0], key: 'kept', label: 'main.sales.kept', delta_usd: 5 },
    ];
    const data = { ...ucCostChangesFixture, items, entity_count: 1 };
    const { rerender } = render(
      <UcUsageCostChangesPanel data={data} loading={false} error={null} onRetry={vi.fn()} />
    );
    await userEvent.click(
      screen.getByRole('button', { name: 'main.sales.kept · exclude from the bar scale' })
    );
    expect(screen.getByRole('button', { name: '1 excluded from the scale · reset' })).toBeVisible();

    // A new period drops that table out of the backend's top 10; its key stays in state.
    const next = [
      { ...ucCostChangesFixture.items[0], key: 'fresh', label: 'main.sales.fresh', delta_usd: 9 },
    ];
    rerender(
      <UcUsageCostChangesPanel
        data={{ ...data, items: next }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
      />
    );
    expect(
      screen.queryByRole('button', { name: /excluded from the scale/ })
    ).not.toBeInTheDocument();
  });

  it('exposes the exclusion as a toggle, and never excludes every row silently', async () => {
    const items = [
      { ...ucCostChangesFixture.items[0], key: 'only', label: 'main.sales.only', delta_usd: 8.82 },
    ];
    const { container } = render(
      <UcUsageCostChangesPanel
        data={{ ...ucCostChangesFixture, items, entity_count: 1 }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
      />
    );
    const toggle = screen.getByRole('button', {
      name: 'main.sales.only · exclude from the bar scale',
    });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    // Excluding the last row leaves an empty scale rather than crashing or dividing by 0.
    expect(container.textContent).toContain('+$8.82');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps a cent-scale cost change visible next to a large one', () => {
    expect(ucUsageCostChangeBarWidth(420, 420)).toBe(49);
    expect(ucUsageCostChangeBarWidth(-420, 420)).toBe(49);
    // Sub-pixel on its own; the component's 4px minimum is what keeps it readable.
    expect(ucUsageCostChangeBarWidth(0.73, 420)).toBeGreaterThan(0);
    expect(ucUsageCostChangeBarWidth(0, 420)).toBe(0);
  });

  it('scales cost changes against the period peak, not an arbitrary dollar', () => {
    expect(ucUsageCostChangeBarWidth(0.02, 0.04)).toBe(24.5);
    expect(ucUsageCostChangeBarWidth(1, 0)).toBe(0);
  });

  it('translates Gold recommendation templates and preserves numerical evidence', () => {
    const copy = ucRecommendationCopy({
      ...ucUsageRecommendationsFixture.items[0],
      title: 'Data product perime mais toujours consomme',
      category: 'FRESHNESS',
      detail: 'freshness_lag_hours=36.5h, derniere lecture il y a 2 jours.',
      recommended_action: 'Corriger le pipeline amont ; prevenir les consommateurs',
    });
    expect(copy.title).toBe('Stale data product still being consumed');
    expect(copy.detail).toBe('Write age=36.5 hours, last read 2 days ago.');
    expect(copy.action).toBe('Fix the upstream pipeline and notify consumers.');
  });
});
