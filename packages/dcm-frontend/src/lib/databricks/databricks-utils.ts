import type { SecurityAlert, ServiceCostDetail, StandardCheck } from '../../types/api';
import type { DatabricksComputeMetric } from './view-data';

export const DATABASE_UNAVAILABLE_MESSAGE =
  'DCM API is running, but the Databricks warehouse connection is not initialized. Check backend Databricks credentials/warehouse configuration, then refresh this page.';

export function formatPipelineType(type?: string | null) {
  if (!type) return '—';
  return type === 'databricks_job' ? 'Databricks Job' : type.replace(/_/g, ' ');
}

export function isDatabricksCompute(cluster: DatabricksComputeMetric) {
  const computeType = cluster.compute_type?.toLowerCase() ?? '';
  const sparkVersion = cluster.spark_version?.toLowerCase() ?? '';
  return (
    computeType.includes('databricks')
    || computeType === 'dbx'
    || Boolean(cluster.workspace_id?.startsWith('adb-'))
    || sparkVersion.includes('databricks')
  );
}

export function isDatabricksCost(item: ServiceCostDetail) {
  const serviceName = item.service_name.toLowerCase();
  return serviceName.includes('databricks') || serviceName.includes('dbu') || serviceName.includes('spark');
}

export function containsDatabricksSignal(values: Array<string | null | undefined>, knownIds: Set<string> = new Set()) {
  const text = values.filter(Boolean).join(' ').toLowerCase();
  return (
    text.includes('databricks')
    || text.includes('dbu')
    || text.includes('spark')
    || text.includes('adb-')
    || Array.from(knownIds).some((id) => id && text.includes(id.toLowerCase()))
  );
}

export function isDatabricksSecurityAlert(alert: SecurityAlert) {
  return containsDatabricksSignal([
    alert.title,
    alert.description,
    alert.resource_id,
    alert.resource_type,
    alert.source_lz_id,
  ]);
}

export function isDatabricksGovernanceCheck(check: StandardCheck) {
  return containsDatabricksSignal([
    check.check_name,
    check.resource_id,
    check.resource_name,
    check.resource_type,
    check.source_lz_id,
    check.check_effect,
  ]);
}

export function downloadCsv(filename: string, headers: string[], rows: unknown[][]) {
  const csvCell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const csv = [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
