import { ChevronDown } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { formatCurrency } from '../../lib/domain/formatters';
import { cn } from '../../lib/utils';
import type { ServiceCostDetail } from '../../types/api';
import { Skeleton } from '../ui/skeleton';

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function BudgetBar({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-muted-foreground">—</span>;
  const clamped = Math.min(pct, 100);
  const color = clamped > 90 ? 'bg-danger' : clamped > 70 ? 'bg-warning' : 'bg-success';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${clamped}%` }} />
      </div>
      <span className="text-xs text-muted-foreground">{pct.toFixed(0)}%</span>
    </div>
  );
}

export function ServiceCostAccordion({
  services,
  loading,
  emptyMessage = 'No cost data in the period.',
  resetKey,
}: {
  services: ServiceCostDetail[];
  loading: boolean;
  emptyMessage?: string;
  resetKey?: string | number;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    setOpenId(null);
  }, [resetKey]);

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (services.length === 0) {
    return <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-2">
      {services.map((service, index) => {
        const key = `${service.service_name}-${index}`;
        const isOpen = openId === key;
        return (
          <div
            key={key}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === key ? null : key))}
            >
              <ChevronDown size={18} className={cn('mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200', isOpen && 'rotate-180')} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{service.service_name}</p>
                <p className="mt-1 text-xs text-muted-foreground capitalize">{service.cloud_provider} · {formatCurrency(service.total_cost_usd)}</p>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <DetailItem label="Cloud" value={service.cloud_provider.toUpperCase()} />
                  <DetailItem label="Total cost" value={formatCurrency(service.total_cost_usd)} />
                  <DetailItem label="Subscription" value={service.subscription_or_account_id ?? '—'} />
                  <DetailItem label="Budget consumed" value={<BudgetBar pct={service.avg_budget_consumed_pct} />} />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
