import type { PipelineStatus } from '../../types/api';

export const PIPELINES_FOCUS_VIEWS = ['runs'] as const;
export type PipelinesFocusView = (typeof PIPELINES_FOCUS_VIEWS)[number];

export const PIPELINES_FOCUS_VIEW_LABELS: Record<PipelinesFocusView, string> = {
  runs: 'Pipeline runs',
};

export const PIPELINES_FOCUS_VIEW_DESCRIPTIONS: Record<PipelinesFocusView, string> = {
  runs: 'Unified ADF, Glue, and Databricks job runs. Click a row to expand details.',
};

export function parsePipelinesFocusView(value: string | null): PipelinesFocusView | null {
  if (!value) return null;
  return PIPELINES_FOCUS_VIEWS.includes(value as PipelinesFocusView) ? (value as PipelinesFocusView) : null;
}

const STATUSES: PipelineStatus[] = ['succeeded', 'failed', 'running', 'cancelled'];

export function parsePipelineStatusFromUrl(value: string | null): PipelineStatus | '' {
  if (!value) return '';
  return STATUSES.includes(value as PipelineStatus) ? (value as PipelineStatus) : '';
}
