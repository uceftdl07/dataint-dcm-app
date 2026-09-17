import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '../../test/render';
import { WorkloadAccordion, type WorkloadAccordionRow } from './workload-accordion';

const sampleWorkloads: WorkloadAccordionRow[] = [
  {
    dataReadBytes: 1024,
    dataWrittenBytes: 512,
    durationSeconds: 120,
    endTime: '2026-06-04T12:00:00Z',
    errorMessage: null,
    id: 'run-1',
    name: 'prod-etl-job',
    parentName: 'pipeline-a',
    rowsRead: 1000,
    rowsWritten: 500,
    source: 'Pipeline',
    sourceLzId: 'lz-azure-prod',
    startTime: '2026-06-04T11:58:00Z',
    status: 'succeeded',
    subscriptionOrAccountId: 'sub-1',
    type: 'Databricks Job',
  },
  {
    durationSeconds: 30,
    endTime: null,
    errorMessage: 'Cluster not available',
    id: 'run-2',
    name: 'failed-notebook',
    parentName: 'parent-pipeline',
    source: 'Activity',
    sourceLzId: 'lz-azure-prod',
    startTime: '2026-06-04T10:00:00Z',
    status: 'failed',
    subscriptionOrAccountId: null,
    type: 'databricks_notebook',
  },
];

describe('WorkloadAccordion', () => {
  it('renders empty state when there are no workloads', () => {
    render(<WorkloadAccordion workloads={[]} loading={false} emptyMessage="No jobs" />);
    expect(screen.getByText('No jobs')).toBeInTheDocument();
  });

  it('expands a single workload at a time', () => {
    render(<WorkloadAccordion workloads={sampleWorkloads} loading={false} />);

    const firstRow = screen.getByRole('button', { name: /prod-etl-job/i });
    fireEvent.click(firstRow);

    expect(screen.getByText('pipeline-a')).toBeInTheDocument();
    expect(screen.queryByText('Cluster not available')).not.toBeInTheDocument();

    const secondRow = screen.getByRole('button', { name: /failed-notebook/i });
    fireEvent.click(secondRow);

    expect(screen.getByText('Cluster not available')).toBeInTheDocument();
    expect(screen.queryByText('pipeline-a')).not.toBeInTheDocument();
  });

  it('collapses an open workload when clicked again', () => {
    render(<WorkloadAccordion workloads={sampleWorkloads} loading={false} />);

    const firstRow = screen.getByRole('button', { name: /prod-etl-job/i });
    fireEvent.click(firstRow);
    expect(screen.getByText('pipeline-a')).toBeInTheDocument();

    fireEvent.click(firstRow);
    expect(screen.queryByText('pipeline-a')).not.toBeInTheDocument();
  });
});
