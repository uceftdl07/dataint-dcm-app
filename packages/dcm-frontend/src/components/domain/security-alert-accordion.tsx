import { ChevronDown } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { cn } from '../../lib/utils';
import type { SecurityAlert } from '../../types/api';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';
import { StatusBadge } from '../ui/status';

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

export function SecurityAlertAccordion({
  alerts,
  loading,
  emptyMessage = 'No alerts match the selected filters.',
  initialOpenId,
  resetKey,
}: {
  alerts: SecurityAlert[];
  loading: boolean;
  emptyMessage?: string;
  initialOpenId?: string | null;
  resetKey?: string | number;
}) {
  const [openId, setOpenId] = useState<string | null>(initialOpenId ?? null);

  useEffect(() => {
    setOpenId(initialOpenId ?? null);
  }, [initialOpenId, resetKey]);

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14" />
        ))}
      </div>
    );
  }

  if (alerts.length === 0) {
    return <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert) => {
        const isOpen = openId === alert.alert_id;
        return (
          <div
            key={alert.alert_id}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === alert.alert_id ? null : alert.alert_id))}
            >
              <ChevronDown size={18} className={cn('mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200', isOpen && 'rotate-180')} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-medium">{alert.title}</p>
                  <StatusBadge value={alert.severity} />
                  <StatusBadge value={alert.status} />
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{alert.description ?? 'No details'}</p>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <DetailItem label="Alert ID" value={alert.alert_id} />
                  <DetailItem label="Cloud" value={<Badge variant="outline">{alert.cloud_provider}</Badge>} />
                  <DetailItem label="Resource" value={alert.resource_type ?? alert.resource_id ?? '—'} />
                  <DetailItem label="Resource ID" value={alert.resource_id ?? '—'} />
                  <DetailItem label="Landing zone" value={alert.source_lz_id ?? '—'} />
                  <DetailItem label="Detected" value={new Date(alert.detected_at).toLocaleString('en-GB')} />
                  <DetailItem label="Description" value={alert.description ?? '—'} />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
