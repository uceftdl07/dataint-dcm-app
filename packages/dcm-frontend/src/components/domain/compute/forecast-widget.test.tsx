import { describe, expect, it } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { ForecastWidget } from './forecast-widget';
import type { ComputeForecastActualPoint, ComputeForecastPoint } from '../../../types/api';

function point(
  date: string,
  predicted: number,
  objectId = 'cluster-1',
  bounds: Partial<Pick<ComputeForecastPoint, 'lower_bound' | 'upper_bound'>> = {}
): ComputeForecastPoint {
  return {
    cloud_provider: 'azure',
    object_type: 'CLUSTER',
    object_id: objectId,
    metric_name: 'cost_usd',
    horizon_date: date,
    predicted_value: predicted,
    lower_bound: predicted - 10,
    upper_bound: predicted + 10,
    method: 'ai_forecast',
    ...bounds,
  };
}

function actual(date: string, value: number): ComputeForecastActualPoint {
  return { horizon_date: date, metric_name: 'cost_usd', actual_value: value };
}

// Two days observed, two projected: `periodEnd` is the cut between the solid and
// the dashed line.
const items = [
  point('2026-08-12', 100),
  point('2026-08-13', 120),
  point('2026-08-14', 130),
  point('2026-08-15', 140),
];

function renderWidget() {
  return render(
    <ForecastWidget
      items={items}
      metric="cost_usd"
      onMetricChange={() => {}}
      periodEnd="2026-08-13"
    />
  );
}

describe('ForecastWidget', () => {
  it('shows the day figures under the cursor, bounds included', () => {
    const { container } = renderWidget();
    const bands = container.querySelectorAll('rect[fill="transparent"]');

    expect(bands).toHaveLength(4);
    expect(container.querySelector('[data-testid="chart-hover-tooltip"]')).toBeNull();

    fireEvent.mouseEnter(bands[2]!);
    const tooltip = container.querySelector('[data-testid="chart-hover-tooltip"]');
    expect(tooltip?.textContent).toContain('2026-08-14');
    // The predicted value and its confidence interval, not just the date.
    expect(tooltip?.textContent).toContain('130');
    expect(tooltip?.textContent).toContain('120');
    expect(tooltip?.textContent).toContain('140');
  });

  it('plots both series on one scale so the dashed line resumes where the solid ends', () => {
    const { container } = renderWidget();
    const [historical, projected] = Array.from(container.querySelectorAll('polyline')).map((line) =>
      (line.getAttribute('points') ?? '').split(' ')
    );

    // The last observed point is the first projected one: same x, same y.
    expect(historical?.[historical.length - 1]).toBe(projected?.[0]);
  });

  it('leaves a day the model does not cover out of the curve instead of drawing it at zero', () => {
    // The projection starts after `periodEnd`: the two observed days are known by
    // the actuals only, and the model holds no row for them.
    const { container, queryByText } = render(
      <ForecastWidget
        items={[point('2026-08-14', 130), point('2026-08-15', 140)]}
        actuals={[actual('2026-08-12', 100), actual('2026-08-13', 120)]}
        metric="cost_usd"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    // A missing projection is not a projection of 0.
    expect(queryByText('$0.00')).toBeNull();

    const [historical, projected] = Array.from(container.querySelectorAll('polyline')).map((line) =>
      (line.getAttribute('points') ?? '').split(' ')
    );
    expect(historical).toHaveLength(2);
    // The dashed line hangs on the last observed point, not on the chart floor.
    expect(projected?.[0]).toBe(historical?.[historical.length - 1]);
  });

  it('combines the per-object bounds in quadrature instead of adding them', () => {
    const { container, getByText } = render(
      <ForecastWidget
        items={[
          point('2026-08-14', 130, 'cluster-1'),
          point('2026-08-14', 70, 'cluster-2'),
          point('2026-08-15', 140, 'cluster-1'),
          point('2026-08-15', 60, 'cluster-2'),
        ]}
        metric="cost_usd"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    expect(getByText(/Confidence interval over 2 objects \(combined\)/)).toBeInTheDocument();

    const bands = container.querySelectorAll('rect[fill="transparent"]');
    fireEvent.mouseEnter(bands[0]!);
    const tooltip = container.querySelector('[data-testid="chart-hover-tooltip"]');

    // 130 + 70 projected, each with a half-width of 10: √(10² + 10²) ≈ 14.14
    // around 200, where adding the bounds would have spanned $180 – $220.
    expect(tooltip?.textContent).toContain('$200.00');
    expect(tooltip?.textContent).toContain('$185.86');
    expect(tooltip?.textContent).toContain('$214.14');
    expect(tooltip?.textContent).not.toContain('$180.00');
    expect(tooltip?.textContent).not.toContain('$220.00');
  });

  it('skips a missing bound rather than counting it as zero', () => {
    const { container } = render(
      <ForecastWidget
        items={[
          point('2026-08-14', 130, 'cluster-1'),
          // No lower bound: the day keeps cluster-1's half-width alone, and a 0
          // here would have dropped the band to the chart floor.
          point('2026-08-14', 70, 'cluster-2', { lower_bound: null }),
        ]}
        metric="cost_usd"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    const bands = container.querySelectorAll('rect[fill="transparent"]');
    fireEvent.mouseEnter(bands[0]!);
    const tooltip = container.querySelector('[data-testid="chart-hover-tooltip"]');
    expect(tooltip?.textContent).toContain('$190.00');
    expect(tooltip?.textContent).toContain('$214.14');
  });

  it('averages a distribution metric across objects instead of summing it', () => {
    const cpu = (objectId: string, predicted: number): ComputeForecastPoint => ({
      ...point('2026-08-14', predicted, objectId),
      metric_name: 'cpu_util_p95_pct',
    });

    const { container, getAllByText, queryByText } = render(
      <ForecastWidget
        items={[cpu('cluster-1', 30), cpu('cluster-2', 50)]}
        metric="cpu_util_p95_pct"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    // A p95 utilisation does not add up: two clusters at 30 % and 50 % make a
    // fleet at 40 %, never at 80 % — let alone the 2000 % of a 50-cluster scope.
    expect(getAllByText('40%').length).toBeGreaterThan(0);
    expect(queryByText('80%')).toBeNull();

    const bands = container.querySelectorAll('rect[fill="transparent"]');
    fireEvent.mouseEnter(bands[0]!);
    const tooltip = container.querySelector('[data-testid="chart-hover-tooltip"]');
    expect(tooltip?.textContent).toContain('40%');
    // The band follows the same 1/N as the mean: √(10² + 10²) / 2 ≈ 7.07.
    expect(tooltip?.textContent).toContain('33%');
    expect(tooltip?.textContent).toContain('47%');
  });

  it('keeps summing an additive metric', () => {
    const { getAllByText, queryByText } = render(
      <ForecastWidget
        items={[point('2026-08-14', 130, 'cluster-1'), point('2026-08-14', 70, 'cluster-2')]}
        metric="cost_usd"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    // Cost is additive: the fleet spends the total, not the average of $100.
    expect(getAllByText('$200.00').length).toBeGreaterThan(0);
    expect(queryByText('$100.00')).toBeNull();
  });

  it('reports no band when the day carries no bound at all', () => {
    const { getByText } = render(
      <ForecastWidget
        items={[point('2026-08-14', 130, 'cluster-1', { lower_bound: null, upper_bound: null })]}
        metric="cost_usd"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    // A zero-width band would claim a certainty the model never expressed.
    expect(getByText(/Confidence interval unavailable/)).toBeInTheDocument();
  });

  it('keeps the confidence interval wording when a single object is plotted', () => {
    const { getByText } = renderWidget();

    expect(getByText(/Confidence interval:/)).toBeInTheDocument();
  });

  it('reports an empty scope instead of drawing an empty chart', () => {
    const { container, getByText } = render(
      <ForecastWidget
        items={[]}
        metric="cost_usd"
        onMetricChange={() => {}}
        periodEnd="2026-08-13"
      />
    );

    expect(getByText('No forecast data for this scope')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
  });
});
