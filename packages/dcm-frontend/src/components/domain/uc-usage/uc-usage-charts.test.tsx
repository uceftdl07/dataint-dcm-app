import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  ucTableChartsFixture,
  ucFinopsChartsFixture,
  ucConsumerChartsFixture,
} from '../../../test/fixtures/uc-usage-charts';
import { UcUsageTimeChart } from './uc-usage-time-chart';
import { UcUsageActivityHeatmap } from './uc-usage-activity-heatmap';
import {
  UcUsageConsumerChartsPanel,
  UcUsageFinopsChartsPanel,
  UcUsageTableChartsPanel,
} from './uc-usage-charts';

describe('UC usage graphics', () => {
  it('conserve les couleurs, coupe les courbes aux valeurs absentes et masque une série', async () => {
    const series = [
      {
        key: 'a',
        label: 'Table A',
        points: [4, null, 0, 6].map((value, i) => ({ date: `2026-09-0${i + 1}`, value })),
      },
      { key: 'b', label: 'Table B', points: [{ date: '2026-09-01', value: 3 }] },
    ];
    const { container } = render(
      <UcUsageTimeChart
        series={series}
        unit="Read accesses / day"
        ariaLabel="Test des usages"
        formatValue={(v) => (v == null ? '—' : `${v}`)}
      />
    );
    const path = container.querySelector('[data-series-key="a"] path')!;
    expect(path.getAttribute('d')?.match(/M/g)).toHaveLength(2);
    expect(container.querySelectorAll('[data-series-key="a"] circle')).toHaveLength(3);
    const retainedColor = container
      .querySelector('[data-series-key="b"] path')!
      .getAttribute('stroke');
    await userEvent.click(screen.getByRole('button', { name: 'Table A' }));
    expect(screen.getByRole('button', { name: 'Table A' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(container.querySelector('[data-series-key="a"]')).toBeNull();
    expect(container.querySelector('[data-series-key="b"] path')).toHaveAttribute(
      'stroke',
      retainedColor
    );
    await userEvent.click(screen.getByRole('button', { name: 'Table A' }));
    expect(container.querySelector('[data-series-key="a"] path')).toHaveAttribute(
      'd',
      path.getAttribute('d')
    );
  });

  it('rend les zéros et les absences distinctement, avec des cellules accessibles au clavier', async () => {
    render(<UcUsageActivityHeatmap activity={ucTableChartsFixture.activity} />);
    const zero = screen.getByRole('button', { name: /orders.*2026-09-03.*0 reads/ });
    const missing = screen.getByRole('button', { name: /invoices.*2026-09-02.*No observation/ });
    expect(zero).toHaveTextContent('0');
    expect(missing).toHaveTextContent('—');
    await userEvent.click(missing);
    expect(screen.getAllByText(/main.finance.invoices.*No observation/).length).toBeGreaterThan(0);
  });

  it('adapte le classement à une seule table et conserve le détail consommateurs', () => {
    render(
      <UcUsageTableChartsPanel
        loading={false}
        error={null}
        onRetry={vi.fn()}
        data={{
          ...ucTableChartsFixture,
          ranking_mode: 'consumers',
          single_table_consumers: ucConsumerChartsFixture.ranking,
        }}
      />
    );
    const ranking = screen.getByRole('region', { name: 'Top consumers of this table' });
    expect(within(ranking).getByText('job-reporting')).toBeInTheDocument();
    expect(within(ranking).getAllByText(/2 tables/).length).toBeGreaterThan(0);
  });

  it('identifie la période précédente et garde les coûts inconnus non chiffrés', () => {
    const { unmount } = render(
      <UcUsageConsumerChartsPanel
        loading={false}
        error={null}
        onRetry={vi.fn()}
        data={ucConsumerChartsFixture}
      />
    );
    expect(screen.getByRole('button', { name: 'Previous period' })).toBeInTheDocument();
    expect(screen.getAllByText(/Observed on 29 Aug/).length).toBeGreaterThan(0);
    unmount();
    render(
      <UcUsageFinopsChartsPanel
        loading={false}
        error={null}
        onRetry={vi.fn()}
        data={{
          ...ucFinopsChartsFixture,
          unit_cost: [{ ...ucFinopsChartsFixture.unit_cost[0], value: null, coverage_pct: 0 }],
          cost_coverage_pct: 0,
        }}
      />
    );
    const unit = screen.getByRole('region', { name: 'Cost per 1,000 costed accesses' });
    expect(within(unit).getByText('No observations in this period.')).toBeInTheDocument();
    expect(within(unit).queryByText('$0.00')).not.toBeInTheDocument();
    expect(within(unit).getByText('0.0%')).toBeInTheDocument();
  });
});
