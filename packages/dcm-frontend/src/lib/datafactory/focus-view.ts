import type { PipelineStatus } from '../../types/api';

export const DATA_FACTORY_FOCUS_VIEWS = ['runs'] as const;
export type DataFactoryFocusView = (typeof DATA_FACTORY_FOCUS_VIEWS)[number];

export const DATA_FACTORY_FOCUS_VIEW_LABELS: Record<DataFactoryFocusView, string> = {
  runs: 'Azure pipeline runs',
};

export const DATA_FACTORY_FOCUS_VIEW_DESCRIPTIONS: Record<DataFactoryFocusView, string> = {
  runs: 'Latest Azure Data Factory runs. Click a row to expand full details.',
};

export function parseDataFactoryFocusView(value: string | null): DataFactoryFocusView | null {
  if (!value) return null;
  return DATA_FACTORY_FOCUS_VIEWS.includes(value as DataFactoryFocusView) ? (value as DataFactoryFocusView) : null;
}

const STATUSES: PipelineStatus[] = ['succeeded', 'failed', 'running', 'cancelled'];

export function parsePipelineStatusFromUrl(value: string | null): PipelineStatus | '' {
  if (!value) return '';
  return STATUSES.includes(value as PipelineStatus) ? (value as PipelineStatus) : '';
}
