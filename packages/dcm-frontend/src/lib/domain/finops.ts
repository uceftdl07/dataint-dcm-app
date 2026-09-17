export type TrendDirection = 'up' | 'down' | 'stable';
export type BudgetFilter = '' | 'controlled' | 'watch' | 'overBudget';

export interface FinOpsServiceCost {
  serviceName: string;
  cloudProvider: string;
  monthlyCost: number;
  budgetPercentage: number | null;
  contextLabel: string;
  contextValue: string;
  trend: {
    direction: TrendDirection;
    percentageChange: number;
  };
}

export function getBudgetStatus(percentage: number): Exclude<BudgetFilter, ''> {
  if (percentage >= 100) return 'overBudget';
  if (percentage >= 80) return 'watch';
  return 'controlled';
}

export function getBudgetLabel(percentage: number) {
  const status = getBudgetStatus(percentage);
  if (status === 'overBudget') return 'Over budget';
  if (status === 'watch') return 'To monitor';
  return 'Controlled';
}

export function getBudgetPillClass(percentage: number) {
  const status = getBudgetStatus(percentage);
  if (status === 'overBudget') return 'border-red-200 bg-red-50 text-red-700';
  if (status === 'watch') return 'border-orange-200 bg-orange-50 text-orange-700';
  return 'border-emerald-200 bg-emerald-50 text-emerald-700';
}

export function getBudgetBarClass(percentage: number) {
  const status = getBudgetStatus(percentage);
  if (status === 'overBudget') return 'bg-red-500 shadow-red-500/30';
  if (status === 'watch') return 'bg-orange-500 shadow-orange-500/30';
  return 'bg-emerald-500 shadow-emerald-500/30';
}

export function getTrendLabel(direction: TrendDirection) {
  if (direction === 'up') return 'Increasing';
  if (direction === 'down') return 'Decreasing';
  return 'Stable';
}

export interface FinOpsFilters {
  service?: string;
  provider?: string;
  budgetStatus?: BudgetFilter;
  trend?: TrendDirection | '';
}

export function filterFinOpsServiceCosts(items: FinOpsServiceCost[], filters: FinOpsFilters) {
  return items.filter((item) => {
    if (filters.service && item.serviceName !== filters.service) return false;
    if (filters.provider && item.cloudProvider !== filters.provider) return false;
    if (
      filters.budgetStatus
      && (
        item.budgetPercentage === null
        || getBudgetStatus(item.budgetPercentage) !== filters.budgetStatus
      )
    ) {
      return false;
    }
    if (filters.trend && item.trend.direction !== filters.trend) return false;
    return true;
  });
}
