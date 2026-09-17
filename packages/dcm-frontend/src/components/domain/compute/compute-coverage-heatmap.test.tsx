import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import {
  ComputeCoverageHeatmap,
  type ComputeCoverageColumn,
  type ComputeCoverageRow,
} from './compute-coverage-heatmap';

const columns: ComputeCoverageColumn[] = [
  { key: 'owner_tag', label: 'Owner tag', description: 'Share of dollars carrying an owner tag.' },
  { key: 'budget_policy', label: 'Budget policy' },
  { key: 'identity', label: 'Identity' },
];

const rows: ComputeCoverageRow[] = [
  {
    key: 'JOB',
    label: 'Jobs',
    sublabel: '$1,000',
    cells: {
      owner_tag: { pct: 100, tooltip: 'Jobs · owner tag · $1,000 of $1,000' },
      budget_policy: { pct: 50, tooltip: 'Jobs · budget policy · $500 of $1,000' },
      identity: { pct: 0, tooltip: 'Jobs · identity · $0 of $1,000' },
    },
  },
  {
    key: 'NETWORKING',
    label: 'Networking',
    sublabel: '$40',
    cells: {
      owner_tag: { pct: null, tooltip: 'Networking · owner tag · not measurable' },
      budget_policy: { pct: 50, tooltip: 'Networking · budget policy · $20 of $40' },
      identity: { pct: null, tooltip: 'Networking · identity · not measurable' },
    },
  },
];

function cells(label: string) {
  const row = screen.getByRole('rowheader', { name: new RegExp(label) }).closest('tr')!;
  return within(row).getAllByRole('cell');
}

describe('ComputeCoverageHeatmap', () => {
  it('writes the percentage in every cell, so no cell is readable by hue alone', () => {
    render(
      <ComputeCoverageHeatmap rows={rows} columns={columns} ariaLabel="Coverage per surface" />
    );

    expect(cells('Jobs').map((cell) => cell.textContent)).toEqual(['100.0%', '50.0%', '0.0%']);
  });

  it('ramps a single hue with the coverage, in the same direction on every column', () => {
    render(
      <ComputeCoverageHeatmap rows={rows} columns={columns} ariaLabel="Coverage per surface" />
    );

    const intensities = cells('Jobs').map((cell) =>
      Number(cell.firstElementChild?.getAttribute('data-intensity'))
    );
    expect(intensities).toEqual([65, 38, 10]);
    // Strictly decreasing with the value: the encoding is a magnitude, not a category.
    expect(intensities[0]).toBeGreaterThan(intensities[1]!);
    expect(intensities[1]).toBeGreaterThan(intensities[2]!);
  });

  it('reads "—" on a dimension that does not apply, never a coloured 0 %', () => {
    render(
      <ComputeCoverageHeatmap rows={rows} columns={columns} ariaLabel="Coverage per surface" />
    );

    const networking = cells('Networking');
    expect(networking.map((cell) => cell.textContent)).toEqual(['—', '50.0%', '—']);
    expect(networking[0]!.firstElementChild?.getAttribute('data-intensity')).toBeNull();
    // A measured 0 % and an unmeasured cell must not read the same.
    expect(networking[0]!.textContent).not.toBe('0.0%');
  });

  it('shows the dollars behind a percentage on hover, and clears them on leave', () => {
    render(
      <ComputeCoverageHeatmap rows={rows} columns={columns} ariaLabel="Coverage per surface" />
    );

    const cell = cells('Jobs')[1]!;
    fireEvent.mouseEnter(cell);
    expect(screen.getByTestId('chart-hover-tooltip').textContent).toBe(
      'Jobs · budget policy · $500 of $1,000'
    );

    fireEvent.mouseLeave(cell);
    expect(screen.queryByTestId('chart-hover-tooltip')).toBeNull();
  });

  it('names its axes and explains a dimension that has a description', () => {
    render(
      <ComputeCoverageHeatmap
        rows={rows}
        columns={columns}
        rowHeader="Serverless surface"
        ariaLabel="Coverage per surface"
      />
    );

    expect(screen.getByRole('columnheader', { name: 'Serverless surface' })).toBeInTheDocument();
    // One info tip, on the only column carrying a description.
    expect(screen.getAllByRole('button', { name: 'Field description' })).toHaveLength(1);
  });

  it('renders nothing without a row or without a dimension', () => {
    const { container } = render(
      <ComputeCoverageHeatmap rows={[]} columns={columns} ariaLabel="Coverage" />
    );
    expect(container.firstChild).toBeNull();

    const { container: noColumns } = render(
      <ComputeCoverageHeatmap rows={rows} columns={[]} ariaLabel="Coverage" />
    );
    expect(noColumns.firstChild).toBeNull();
  });
});
