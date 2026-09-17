import { TrendingDown, TrendingUp } from 'lucide-react';
import { getTrendLabel, type TrendDirection } from '../../lib/domain/finops';

export function TrendCell({
  direction,
  percentageChange,
}: {
  direction: TrendDirection;
  percentageChange: number;
}) {
  const icon = direction === 'up'
    ? <TrendingUp className="size-4 text-red-700" />
    : direction === 'down'
      ? <TrendingDown className="size-4 text-emerald-700" />
      : <div className="size-4 rounded-full bg-slate-500" />;

  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      {icon}
      {getTrendLabel(direction)}
      <span className="text-xs">({percentageChange.toFixed(1)}%)</span>
    </div>
  );
}
