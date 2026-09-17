export const COSTS_FOCUS_VIEWS = ['services'] as const;
export type CostsFocusView = (typeof COSTS_FOCUS_VIEWS)[number];

export const COSTS_FOCUS_VIEW_LABELS: Record<CostsFocusView, string> = {
  services: 'Cost by service',
};

export const COSTS_FOCUS_VIEW_DESCRIPTIONS: Record<CostsFocusView, string> = {
  services: 'Billed services for the selected period. Click a row to expand details.',
};

export function parseCostsFocusView(value: string | null): CostsFocusView | null {
  if (!value) return null;
  return COSTS_FOCUS_VIEWS.includes(value as CostsFocusView) ? (value as CostsFocusView) : null;
}

export function buildCostsFocusPath(view: CostsFocusView): string {
  return `/costs/${view}`;
}
