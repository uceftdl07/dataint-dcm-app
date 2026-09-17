import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  ComputeStackedBar,
  ComputeStackedColumns,
  type ComputeStackedColumn,
  type ComputeStackedSegment,
  type ComputeStackedSeries,
} from './compute-stacked-bar';

const segments: ComputeStackedSegment[] = [
  {
    key: 'serverless',
    label: 'Serverless',
    value: 800,
    valueLabel: '$800 · 80.0%',
    color: 'var(--tdf-blue)',
  },
  {
    key: 'classic',
    label: 'Classic',
    value: 200,
    valueLabel: '$200 · 20.0%',
    color: 'var(--tdf-teal)',
  },
];

const series: ComputeStackedSeries[] = [
  { key: 'JOB', label: 'Jobs', color: 'var(--tdf-blue)' },
  { key: 'SQL_WAREHOUSE', label: 'SQL warehouses', color: 'var(--tdf-teal)' },
];

const columns: ComputeStackedColumn[] = [
  { label: '2026-09-07', values: { JOB: 60, SQL_WAREHOUSE: 40 }, tooltip: '2026-09-07 · $100' },
  { label: '2026-09-08', values: { JOB: 25, SQL_WAREHOUSE: 25 }, tooltip: '2026-09-08 · $50' },
  { label: '2026-09-09', values: { JOB: 0, SQL_WAREHOUSE: null }, tooltip: '2026-09-09 · $0' },
];

function filled(container: HTMLElement) {
  return Array.from(container.querySelectorAll('rect[fill]:not([fill="transparent"])'));
}

describe('ComputeStackedBar', () => {
  it('lays the two classes out along one bar, in proportion, and never as a pie', () => {
    const { container } = render(
      <ComputeStackedBar segments={segments} ariaLabel="Serverless share of spend" />
    );

    const bars = filled(container);
    expect(bars.map((bar) => bar.getAttribute('width'))).toEqual(['80', '20']);
    expect(bars.map((bar) => bar.getAttribute('x'))).toEqual(['0', '80']);
    // Two angles to compare would be a pie: there is no arc and no circle here.
    expect(container.querySelectorAll('circle, path')).toHaveLength(0);
  });

  it('keeps the figures in the legend, not only under the cursor', () => {
    render(<ComputeStackedBar segments={segments} ariaLabel="Serverless share of spend" />);

    const legend = screen.getByTestId('compute-stacked-bar-legend');
    expect(legend.textContent).toContain('Serverless');
    expect(legend.textContent).toContain('$800 · 80.0%');
    expect(legend.textContent).toContain('$200 · 20.0%');
  });

  it('shows the hovered class, and clears the readout when the cursor leaves', () => {
    const { container } = render(
      <ComputeStackedBar segments={segments} ariaLabel="Serverless share of spend" />
    );

    const bands = container.querySelectorAll('rect[fill="transparent"]');
    expect(bands).toHaveLength(2);

    fireEvent.mouseEnter(bands[1]!);
    expect(screen.getByTestId('chart-hover-tooltip').textContent).toBe('Classic · $200 · 20.0%');

    fireEvent.mouseLeave(screen.getByTestId('compute-stacked-bar'));
    expect(screen.queryByTestId('chart-hover-tooltip')).toBeNull();
  });

  it('renders an empty track when nothing was billed, rather than dividing by zero', () => {
    const { container } = render(
      <ComputeStackedBar
        segments={segments.map((segment) => ({ ...segment, value: 0, valueLabel: '$0 · —' }))}
        ariaLabel="Serverless share of spend"
      />
    );

    expect(filled(container)).toHaveLength(0);
    expect(container.innerHTML).not.toContain('NaN');
    // The classes are still named: an empty perimeter is not an unknown one.
    expect(screen.getByTestId('compute-stacked-bar-legend').textContent).toContain('Classic');
  });

  it('drops an unmeasured class from the bar but keeps it in the legend', () => {
    const { container } = render(
      <ComputeStackedBar
        segments={[segments[0]!, { ...segments[1]!, value: null, valueLabel: '—' }]}
        ariaLabel="Serverless share of spend"
      />
    );

    expect(filled(container)).toHaveLength(1);
    expect(filled(container)[0]!.getAttribute('width')).toBe('100');
    expect(screen.getByTestId('compute-stacked-bar-legend').textContent).toContain('Classic—');
  });

  it('renders nothing when there is no class at all', () => {
    const { container } = render(<ComputeStackedBar segments={[]} ariaLabel="Share" />);

    expect(container.querySelector('svg')).toBeNull();
  });
});

describe('ComputeStackedColumns', () => {
  it('stacks the series on a shared absolute scale, so a day that halves reads as half', () => {
    const { container } = render(
      <ComputeStackedColumns
        series={series}
        columns={columns}
        height={140}
        ariaLabel="Serverless spend per day"
      />
    );

    const bars = filled(container);
    // Two segments on each of the two billed days; the flat day draws none.
    expect(bars).toHaveLength(4);

    // 136 usable units for the tallest column: its top segment stops at the padding.
    expect(bars[1]!.getAttribute('y')).toBe('4');
    expect(bars[0]!.getAttribute('height')).toBe('81.6');
    // Half the spend, half the height — not a stack renormalised to 100 %.
    expect(bars[2]!.getAttribute('height')).toBe('34');
  });

  it('keeps a flat day hoverable and reports its own figures', () => {
    const { container } = render(
      <ComputeStackedColumns series={series} columns={columns} ariaLabel="Serverless spend" />
    );

    const bands = container.querySelectorAll('rect[fill="transparent"]');
    expect(bands).toHaveLength(3);

    fireEvent.mouseEnter(bands[2]!);
    expect(screen.getByTestId('chart-hover-tooltip').textContent).toBe('2026-09-09 · $0');

    fireEvent.mouseLeave(screen.getByTestId('compute-stacked-columns'));
    expect(screen.queryByTestId('chart-hover-tooltip')).toBeNull();
  });

  it('paints a series from its own key, so folding one out never repaints the others', () => {
    const { container } = render(
      <ComputeStackedColumns series={series} columns={columns} ariaLabel="Serverless spend" />
    );
    const before = filled(container)[0]!.getAttribute('fill');

    const { container: after } = render(
      <ComputeStackedColumns series={[series[0]!]} columns={columns} ariaLabel="Serverless spend" />
    );

    expect(filled(after)[0]!.getAttribute('fill')).toBe(before);
    expect(before).toBe('var(--tdf-blue)');
  });

  it('names every series in the legend and every bucket in text', () => {
    const { container } = render(
      <ComputeStackedColumns series={series} columns={columns} ariaLabel="Serverless spend" />
    );

    expect(screen.getByTestId('compute-stacked-bar-legend').textContent).toBe('JobsSQL warehouses');
    expect(
      Array.from(container.querySelectorAll('.sr-only li')).map((li) => li.textContent)
    ).toEqual(['2026-09-07 · $100', '2026-09-08 · $50', '2026-09-09 · $0']);
  });

  it('draws a baseline rather than dividing by zero on a perimeter with no spend', () => {
    const { container } = render(
      <ComputeStackedColumns
        series={series}
        columns={columns.map((column) => ({ ...column, values: { JOB: 0, SQL_WAREHOUSE: 0 } }))}
        ariaLabel="Serverless spend"
      />
    );

    expect(filled(container)).toHaveLength(0);
    expect(container.innerHTML).not.toContain('NaN');
  });

  it('renders nothing without a bucket or without a series', () => {
    const { container } = render(
      <ComputeStackedColumns series={series} columns={[]} ariaLabel="Serverless spend" />
    );
    expect(container.querySelector('svg')).toBeNull();
  });
});
