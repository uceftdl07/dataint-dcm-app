import { ChevronDown, Clock3, Database, DollarSign, Tags } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import {
  clampPercent,
  formatCurrency,
  formatDatabaseType,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatStorage,
  getPressureColor,
  getPressureScore,
  getStoragePercent,
} from '../../lib/databases/database-utils';
import { cn } from '../../lib/utils';
import type { DatabaseMetric } from '../../types/api';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';

function DetailItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/70 bg-background/70 px-3 py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <div className="mt-1 break-words text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}

function metricBar(value: number | null | undefined, label: string) {
  if (value == null || Number.isNaN(value)) return null;
  const color = value > 85 ? 'bg-danger' : value > 65 ? 'bg-warning' : 'bg-info';
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span>{formatPercent(value)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(Math.max(value, 0), 100)}%` }} />
      </div>
    </div>
  );
}

function DatabaseDetails({ db }: { db: DatabaseMetric }) {
  const storagePercent = getStoragePercent(db);
  const tags = Object.entries(db.tags ?? {}).filter(([, value]) => value !== null && value !== undefined).slice(0, 8);
  const storageValue = `${formatStorage(db.storage_used_gb)} / ${formatStorage(db.storage_limit_gb)}`;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <DetailItem label="Server" value={db.server_name ?? '—'} />
        <DetailItem label="Region / zone" value={`${db.region ?? '—'}${db.availability_zone ? ` · ${db.availability_zone}` : ''}`} />
        <DetailItem label="Landing zone" value={db.source_lz_id || '—'} />
        <DetailItem label="Subscription/account" value={db.subscription_or_account_id ?? '—'} />
        <DetailItem label="Cloud" value={db.cloud_provider.toUpperCase()} />
        <DetailItem label="Engine" value={formatDatabaseType(db.db_type)} />
        <DetailItem label="Storage" value={storageValue} />
        <DetailItem label="Connections" value={formatNumber(db.active_connections)} />
        <DetailItem label="Storage cost impact" value={formatCurrency(db.storage_cost_impact_usd)} />
        <DetailItem label="Collected" value={formatDateTime(db.collected_at)} />
      </div>
      <div className="space-y-2">
        {metricBar(db.cpu_percent, 'CPU')}
        {metricBar(db.memory_percent, 'Memory')}
        {metricBar(storagePercent, 'Storage')}
        {db.dtus_used != null && metricBar(db.dtus_used, 'DTU')}
      </div>
      {(db.resource_group || tags.length > 0) && (
        <div className="rounded-2xl border border-border/70 bg-background/70 p-3">
          <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            <Tags size={12} />
            Tags & resource group
          </div>
          <div className="flex flex-wrap gap-2">
            {db.resource_group && <Badge variant="outline">{db.resource_group}</Badge>}
            {tags.map(([key, value]) => (
              <Badge key={key} variant="outline">
                {key}: {String(value)}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function DatabaseAccordion({
  databases,
  loading,
  emptyMessage = 'No database matches the selected filters.',
  resetKey,
}: {
  databases: DatabaseMetric[];
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

  if (databases.length === 0) {
    return (
      <div className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {databases.map((db) => {
        const isOpen = openId === db.db_id;
        const pressureScore = getPressureScore(db);
        const pressureColor = getPressureColor(pressureScore);
        const storagePercent = getStoragePercent(db);

        return (
          <div
            key={db.db_id}
            className={cn(
              'overflow-hidden rounded-2xl border border-border/70 bg-background/70 transition-colors',
              isOpen && 'border-primary/35 bg-primary/[0.02]',
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => setOpenId((current) => (current === db.db_id ? null : db.db_id))}
            >
              <ChevronDown
                size={18}
                className={cn(
                  'mt-0.5 shrink-0 text-muted-foreground transition-transform duration-200',
                  isOpen && 'rotate-180',
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Database size={14} className="shrink-0 text-muted-foreground" />
                  <p className="truncate font-medium text-foreground">{db.db_name ?? db.db_id}</p>
                  <Badge variant={db.is_available ? 'success' : 'destructive'}>
                    {db.is_available ? 'Available' : 'Unavailable'}
                  </Badge>
                  {pressureScore != null && (
                    <Badge variant={pressureScore >= 85 ? 'destructive' : pressureScore >= 70 ? 'warning' : 'outline'}>
                      Pressure {formatPercent(pressureScore)}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {formatDatabaseType(db.db_type)} · {db.cloud_provider.toUpperCase()} · {db.region ?? 'Unknown region'} · {db.db_id}
                </p>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                  <span>CPU {formatPercent(db.cpu_percent)}</span>
                  <span>Memory {formatPercent(db.memory_percent)}</span>
                  <span>Storage {formatPercent(storagePercent)}</span>
                  <span>{formatNumber(db.active_connections)} conn.</span>
                  {db.storage_cost_impact_usd != null && (
                    <span className="inline-flex items-center gap-1">
                      <DollarSign size={12} />
                      {formatCurrency(db.storage_cost_impact_usd)}
                    </span>
                  )}
                </div>
                {pressureScore != null && (
                  <div className="mt-2 h-1.5 max-w-xs overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${clampPercent(pressureScore)}%`, backgroundColor: pressureColor }}
                    />
                  </div>
                )}
              </div>
              <span className="hidden shrink-0 items-center gap-1 text-xs text-muted-foreground sm:inline-flex">
                <Clock3 size={12} />
                {formatDateTime(db.collected_at)}
              </span>
            </button>
            {isOpen && (
              <div className="border-t border-border/60 px-4 py-4">
                <DatabaseDetails db={db} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
