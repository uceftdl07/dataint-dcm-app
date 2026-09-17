import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '../../test/render';
import { ClusterAccordion } from './cluster-accordion';
import type { DatabricksComputeMetric } from '../../lib/databricks/view-data';

const sampleClusters: DatabricksComputeMetric[] = [
  {
    avg_cpu_utilization_pct: 67,
    avg_mem_utilization_pct: 54,
    cloud_provider: 'azure',
    collected_at: '2026-06-04T12:00:00Z',
    compute_resource_id: '0312-151347-reef123',
    compute_type: 'databricks',
    node_type: 'Standard_DS3_v2',
    resource_name: 'prod-etl-cluster',
    source_lz_id: 'lz-azure-prod',
    spark_version: '14.3.x-scala2.12',
    state: 'running',
    subscription_or_account_id: 'fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a',
    tags: { env: 'prod' },
    workspace_id: 'adb-3059738143768593',
  },
  {
    avg_cpu_utilization_pct: null,
    avg_mem_utilization_pct: null,
    cloud_provider: 'azure',
    collected_at: '2026-06-04T10:00:00Z',
    compute_resource_id: '0312-999999-fail456',
    compute_type: 'databricks',
    node_type: 'Standard_DS4_v2',
    resource_name: 'dev-analytics',
    source_lz_id: 'lz-azure-dev',
    spark_version: '13.3.x-scala2.12',
    state: 'error',
    subscription_or_account_id: 'sub-dev',
    tags: null,
    workspace_id: 'adb-dev',
  },
];

describe('ClusterAccordion', () => {
  it('renders empty state when there are no clusters', () => {
    render(<ClusterAccordion clusters={[]} loading={false} emptyMessage="No clusters" />);
    expect(screen.getByText('No clusters')).toBeInTheDocument();
  });

  it('expands cluster details inline when clicked', () => {
    render(<ClusterAccordion clusters={sampleClusters} loading={false} />);

    fireEvent.click(screen.getByRole('button', { name: /prod-etl-cluster/i }));

    expect(screen.getByText('lz-azure-prod')).toBeInTheDocument();
    expect(screen.getByText('env: prod')).toBeInTheDocument();
    expect(screen.queryByText('lz-azure-dev')).not.toBeInTheDocument();
  });

  it('collapses when the same cluster is clicked again', () => {
    render(<ClusterAccordion clusters={sampleClusters} loading={false} />);

    const row = screen.getByRole('button', { name: /prod-etl-cluster/i });
    fireEvent.click(row);
    expect(screen.getByText('env: prod')).toBeInTheDocument();

    fireEvent.click(row);
    expect(screen.queryByText('env: prod')).not.toBeInTheDocument();
  });
});
