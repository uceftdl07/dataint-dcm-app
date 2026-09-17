import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ComputeRankedBars, type ComputeRankedItem } from './compute-ranked-bars';

const items: ComputeRankedItem[] = [
  {
    key: 'SQL_WAREHOUSE',
    label: 'SQL warehouses',
    value: 500,
    valueLabel: '$500',
    tooltip: 'SQL warehouses · $500 · 41 objects',
  },
  {
    key: 'JOB',
    label: 'Jobs',
    sublabel: '1 204 objects',
    value: 1000,
    valueLabel: '$1,000',
    tooltip: 'Jobs · $1,000 · 1 204 objects',
  },
  {
    key: 'NOTEBOOK',
    label: 'Notebooks',
    value: 200,
    valueLabel: '$200',
    tooltip: 'Notebooks · $200 · 461 objects',
  },
];

function labels() {
  return screen.getAllByTestId('compute-ranked-bars-row').map((row) => {
    const [label] = row.textContent?.split('$') ?? [];
    return label?.trim();
  });
}

function bars(container: HTMLElement) {
  return Array.from(container.querySelectorAll('rect'));
}

describe('ComputeRankedBars', () => {
  it('sorts the rows by magnitude, whatever order the caller passed', () => {
    render(<ComputeRankedBars items={items} ariaLabel="Spend per surface" />);

    expect(labels()).toEqual(['Jobs1 204 objects', 'SQL warehouses', 'Notebooks']);
  });

  it('encodes the magnitude on a single sequential hue, never one colour per entity', () => {
    const { container } = render(<ComputeRankedBars items={items} ariaLabel="Spend per surface" />);

    const fills = bars(container).map((bar) => bar.getAttribute('fill'));
    expect(fills).toHaveLength(3);
    for (const fill of fills) expect(fill).toContain('var(--tdf-blue)');
    // One hue, three intensities: nothing here is a category.
    expect(new Set(fills).size).toBe(3);

    expect(bars(container).map((bar) => bar.getAttribute('width'))).toEqual(['100', '50', '20']);
    expect(bars(container).map((bar) => bar.getAttribute('data-intensity'))).toEqual([
      '100',
      '55',
      '28',
    ]);
  });

  it('reads the intensity off the value, not off the rank', () => {
    // Two surfaces at the same spend: same intensity although they sit at rank 2 and 3.
    const { container } = render(
      <ComputeRankedBars
        items={[items[1]!, items[0]!, { ...items[2]!, value: 500, valueLabel: '$500' }]}
        ariaLabel="Spend per surface"
      />
    );

    const intensities = bars(container).map((bar) => bar.getAttribute('data-intensity'));
    expect(intensities[1]).toBe(intensities[2]);
  });

  it('draws no bar for an unmeasured row but keeps it listed', () => {
    const { container } = render(
      <ComputeRankedBars
        items={[items[1]!, { ...items[0]!, value: null, valueLabel: '—' }]}
        ariaLabel="Spend per surface"
      />
    );

    expect(screen.getAllByTestId('compute-ranked-bars-row')).toHaveLength(2);
    // The unmeasured row lands last and reads the em dash, never a zero-length bar.
    expect(bars(container)).toHaveLength(1);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('shows the row figures on hover and clears them when the cursor leaves', () => {
    render(<ComputeRankedBars items={items} ariaLabel="Spend per surface" />);

    const row = screen.getAllByTestId('compute-ranked-bars-row')[0]!;
    fireEvent.mouseEnter(row);
    expect(screen.getByTestId('chart-hover-tooltip').textContent).toBe(
      'Jobs · $1,000 · 1 204 objects'
    );

    fireEvent.mouseLeave(row);
    expect(screen.queryByTestId('chart-hover-tooltip')).toBeNull();
  });

  it('keeps the label and the figure as real text, readable without a pointer', () => {
    render(<ComputeRankedBars items={items} ariaLabel="Spend per surface" />);

    expect(screen.getByRole('list', { name: 'Spend per surface' })).toBeInTheDocument();
    expect(screen.getByText('$1,000')).toBeInTheDocument();
    expect(screen.getByText('1 204 objects')).toBeInTheDocument();
  });

  it('renders a flat list rather than dividing by zero when every value is zero', () => {
    const { container } = render(
      <ComputeRankedBars
        items={items.map((item) => ({ ...item, value: 0, valueLabel: '$0' }))}
        ariaLabel="Spend per surface"
      />
    );

    expect(bars(container).map((bar) => bar.getAttribute('width'))).toEqual(['0', '0', '0']);
    expect(container.innerHTML).not.toContain('NaN');
  });

  it('renders nothing when the ranking is empty', () => {
    const { container } = render(<ComputeRankedBars items={[]} ariaLabel="Spend per surface" />);

    expect(container.firstChild).toBeNull();
  });
});
