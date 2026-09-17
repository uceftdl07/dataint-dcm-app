import type { ComputeMetric, SecurityAlert, ServiceCostDetail, StandardCheck } from '../../types/api';
import type { WorkloadAccordionRow } from '../../components/domain/workload-accordion';

export interface DatabricksComputeMetric extends ComputeMetric {
  start_time?: string | null;
  creator?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  terminated_at?: string | null;
  terminated_time?: string | null;
  estimated_hourly_cost_usd?: number | null;
  hourly_cost_usd?: number | null;
  hourly_cost?: number | null;
  cost_per_hour?: number | null;
}

export interface DatabricksWorkspaceSummary {
  id: string;
  name: string;
  running: number;
  total: number;
  costUsd: number;
}

export interface DatabricksFocusViewData {
  loading: boolean;
  filteredClusters: DatabricksComputeMetric[];
  selectedCluster: DatabricksComputeMetric | null;
  selectedClusterTags: Record<string, unknown>;
  onSelectCluster: (clusterId: string) => void;
  filteredWorkloadRows: WorkloadAccordionRow[];
  avgWorkloadDuration: number | null;
  costItems: ServiceCostDetail[];
  databricksAlerts: SecurityAlert[];
  databricksChecks: StandardCheck[];
  workspaceSummaries: DatabricksWorkspaceSummary[];
}

export function pct(value: number | null) {
  return value === null ? '—' : `${Math.round(value)}%`;
}

export function formatCurrency(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat('en-GB', {
    currency: 'USD',
    maximumFractionDigits: 2,
    style: 'currency',
  }).format(value);
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('en-GB');
}

export function formatDuration(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)} min`;
}

export function normalizeTags(tags: ComputeMetric['tags'] | string | null | undefined): Record<string, unknown> {
  if (!tags) return {};
  if (typeof tags === 'string') {
    try {
      const parsed = JSON.parse(tags) as unknown;
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return tags;
}

export function getClusterCreator(cluster: DatabricksComputeMetric) {
  return cluster.creator ?? cluster.created_by ?? null;
}

export function getClusterStartTime(cluster: DatabricksComputeMetric) {
  return cluster.start_time ?? cluster.created_at ?? null;
}

export function getClusterTerminatedTime(cluster: DatabricksComputeMetric) {
  return cluster.terminated_at ?? cluster.terminated_time ?? null;
}

export function getClusterHourlyCost(cluster: DatabricksComputeMetric) {
  return cluster.estimated_hourly_cost_usd ?? cluster.hourly_cost_usd ?? cluster.hourly_cost ?? cluster.cost_per_hour ?? null;
}

export function formatWorkers(cluster: DatabricksComputeMetric) {
  const workers = cluster.num_workers ?? '—';
  if (cluster.autoscale_min != null && cluster.autoscale_max != null) {
    return `${workers} (${cluster.autoscale_min}-${cluster.autoscale_max})`;
  }
  return workers;
}
