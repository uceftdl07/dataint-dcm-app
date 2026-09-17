import type { ComputeState } from '../../types/api';

export const DATABRICKS_FOCUS_VIEWS = [
  'clusters',
  'jobs',
  'security-alerts',
  'governance',
  'costs',
  'workspaces',
] as const;

export type DatabricksFocusView = (typeof DATABRICKS_FOCUS_VIEWS)[number];

const CLUSTER_STATES: ComputeState[] = ['running', 'terminated', 'error', 'unknown'];

export const DATABRICKS_FOCUS_VIEW_LABELS: Record<DatabricksFocusView, string> = {
  clusters: 'Databricks clusters',
  jobs: 'Job runs',
  'security-alerts': 'Security alerts',
  governance: 'Governance checks',
  costs: 'Databricks costs',
  workspaces: 'Workspace overview',
};

export const DATABRICKS_FOCUS_VIEW_DESCRIPTIONS: Record<DatabricksFocusView, string> = {
  clusters: 'Select a cluster row to inspect its latest snapshot.',
  jobs: 'Pipeline runs and notebook activities for the selected period. Expand a row for full details.',
  'security-alerts': 'Active alerts linked to Databricks resources in your scope.',
  governance: 'Compliance checks scoped to identifiable Databricks resources.',
  costs: 'Cost lines matching Databricks, DBU, or Spark services.',
  workspaces: 'Cluster and cost roll-up by Databricks workspace.',
};

export function parseDatabricksFocusView(value: string | null): DatabricksFocusView | null {
  if (!value) {
    return null;
  }
  return DATABRICKS_FOCUS_VIEWS.includes(value as DatabricksFocusView)
    ? (value as DatabricksFocusView)
    : null;
}

export function parseClusterStateFromUrl(value: string | null): ComputeState | '' {
  if (!value) {
    return '';
  }
  return CLUSTER_STATES.includes(value as ComputeState) ? (value as ComputeState) : '';
}

export function isClusterState(value: string): value is ComputeState {
  return CLUSTER_STATES.includes(value as ComputeState);
}
