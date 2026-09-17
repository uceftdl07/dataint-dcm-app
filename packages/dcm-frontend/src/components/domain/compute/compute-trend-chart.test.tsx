import { describe, expect, it } from 'vitest';
import { fireEvent, render } from '@testing-library/react';
import { ComputeTrendChart, type ComputeTrendPoint } from './compute-trend-chart';

const points: ComputeTrendPoint[] = [
  { label: '2026-06-15', value: 100, tooltip: '2026-06-15 · $100' },
  { label: '2026-06-22', value: null, tooltip: '2026-06-22 · no data' },
  { label: '2026-06-29', value: 50, tooltip: '2026-06-29 · $50' },
];

function renderChart(variant: 'bar' | 'line') {
  const { container } = render(
    <ComputeTrendChart points={points} variant={variant} ariaLabel="Cost trend" />
  );
  return container;
}

describe('ComputeTrendChart', () => {
  it('renders one bar per measured bucket and none for a null one', () => {
    const container = renderChart('bar');

    expect(container.querySelectorAll('rect[fill]:not([fill="transparent"])')).toHaveLength(2);
  });

  it('breaks the line instead of joining through a missing bucket', () => {
    const container = renderChart('line');

    // Two isolated points, so no segment of two or more: nothing to join.
    expect(container.querySelectorAll('polyline')).toHaveLength(0);
    expect(container.querySelectorAll('circle')).toHaveLength(2);
  });

  it('joins consecutive measured buckets', () => {
    const { container } = render(
      <ComputeTrendChart
        points={[points[0]!, { label: '2026-06-22', value: 80, tooltip: '2026-06-22 · $80' }]}
        variant="line"
        ariaLabel="Cost trend"
      />
    );

    expect(container.querySelectorAll('polyline')).toHaveLength(1);
  });

  it('shows the hovered bucket figures, and clears them when the cursor leaves', () => {
    const container = renderChart('bar');
    const bands = container.querySelectorAll('rect[fill="transparent"]');

    // One band per bucket, so a zero-height bar and a missing bucket stay hoverable.
    expect(bands).toHaveLength(3);
    expect(container.querySelector('[data-testid="chart-hover-tooltip"]')).toBeNull();

    fireEvent.mouseEnter(bands[0]!);
    expect(container.querySelector('[data-testid="chart-hover-tooltip"]')?.textContent).toBe(
      '2026-06-15 · $100'
    );

    // The bucket without measure has figures of its own to report.
    fireEvent.mouseEnter(bands[1]!);
    expect(container.querySelector('[data-testid="chart-hover-tooltip"]')?.textContent).toBe(
      '2026-06-22 · no data'
    );

    fireEvent.mouseLeave(container.querySelector('[data-testid="compute-trend-chart"]')!);
    expect(container.querySelector('[data-testid="chart-hover-tooltip"]')).toBeNull();
  });

  it('exposes every bucket in text, the SVG being a single image to a screen reader', () => {
    const container = renderChart('bar');

    const readable = Array.from(container.querySelectorAll('.sr-only li')).map(
      (li) => li.textContent
    );
    expect(readable).toEqual(['2026-06-15 · $100', '2026-06-22 · no data', '2026-06-29 · $50']);
  });

  it('renders a flat baseline for an all-zero series rather than dividing by zero', () => {
    const { container } = render(
      <ComputeTrendChart
        points={[
          { label: 'a', value: 0, tooltip: 'a · 0' },
          { label: 'b', value: 0, tooltip: 'b · 0' },
        ]}
        variant="bar"
        height={88}
        ariaLabel="Cost trend"
      />
    );

    for (const bar of container.querySelectorAll('rect[fill]:not([fill="transparent"])')) {
      expect(bar.getAttribute('height')).toBe('0');
      expect(bar.getAttribute('y')).toBe('88');
    }
  });

  it('renders nothing when there is no point at all', () => {
    const { container } = render(<ComputeTrendChart points={[]} ariaLabel="Cost trend" />);

    expect(container.querySelector('svg')).toBeNull();
  });
});
