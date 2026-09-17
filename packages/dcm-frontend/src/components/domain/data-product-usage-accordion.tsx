import { ChevronDown } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { formatCurrency, formatDateTime } from '../../lib/domain/formatters';
import { cn } from '../../lib/utils';
import type { DataProductUsage as DataProductUsageRow } from '../../types/api';
import { Skeleton } from '../ui/skeleton';

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat('en-GB').format(value ?? 0);
}

function formatBytes(bytes: number | null | undefined) {
  const value = bytes ?? 0;
  if (value < 1024) return `${formatNumber(value)} B`;
  const units = ['KB', 'MB', 'GB', 'TB', 'PB'];
  let amount = value / 1024;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

function UsageDetails({ row }: { row: DataProductUsageRow }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <DetailItem label="Data product ID" value={row.data_product_id} />
      <DetailItem label="Consumer ID" value={row.consumer_id} />
      <DetailItem label="Cloud" value={row.cloud_provider.toUpperCase()} />
      <DetailItem label="Landing zone" value={row.source_lz_id ?? '—'} />
      <DetailItem label="Subscription" value={row.subscription_or_account_id ?? '—'} />
      <DetailItem label="Usage date" value={formatDateTime(row.usage_date)} />
      <DetailItem label="Requests" value={formatNumber(row.request_count)} />
      <DetailItem label="Rows read" value={formatNumber(row.rows_read)} />
      <DetailItem label="Rows written" value={formatNumber(row.rows_written)} />
      <DetailItem label="Data read" value={formatBytes(row.data_read_bytes)} />
      <DetailItem label="Data written" value={formatBytes(row.data_written_bytes)} />
      <DetailItem label="Cost" value={formatCurrency(row.cost_usd)} />
      <DetailItem label="Last used" value={formatDateTime(row.last_used_at)} />
    </div>
  );
}

export function DataProductUsageAccordion({
  rows,
  loading,
  emptyMessage = 'No usage rows match the selected filters.',
  resetKey,
}: {
  rows: DataProductUsageRow[];
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

  if (rows.length === 0) {
    return <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">{emptyMessage}</div>;
  }

  return (
    <div className="space-y-2">
      {rows.map((row, index) => {
        const rowKey = `${row.data_product_id}-${row.consumer_id}-${row.usage_date}-${index}`;
        const isOpen = openId === rowKey;
        return (
          <div
            key={rowKey}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === rowKey ? null : rowKey))}
            >
              <ChevronDown
                size={18}
                className={cn('mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200', isOpen && 'rotate-180')}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-foreground">{row.data_product_name || row.data_product_id}</p>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {row.consumer_name || row.consumer_id} · {formatBytes(row.data_read_bytes)} · {formatCurrency(row.cost_usd)}
                </p>
              </div>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <UsageDetails row={row} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
