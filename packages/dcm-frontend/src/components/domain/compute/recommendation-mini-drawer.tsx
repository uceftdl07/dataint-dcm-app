import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { Badge } from '../../ui/badge';
import { cn } from '../../../lib/utils';
import { severityBadgeVariant } from '../../../lib/compute/badges';
import {
  categoryBadgeVariant,
  categoryLabel,
  daysSince,
  formatRecommendationSavings,
  objectDetailPath,
  objectTypeLabel,
  recommendationStatusBadgeVariant,
  recommendationStatusLabel,
} from '../../../lib/compute/recommendations';
import { severityLabel } from '../../../lib/compute/format';
import type { ComputeRecommendationItem } from '../../../types/api';

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
        {label}
      </div>
      <div className="truncate text-sm font-semibold text-foreground" title={value}>
        {value}
      </div>
    </div>
  );
}

export function RecommendationMiniDrawer({
  open,
  onClose,
  item,
  periodEnd,
}: {
  open: boolean;
  onClose: () => void;
  item: ComputeRecommendationItem | null;
  periodEnd: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open || !item) return null;

  const objectLabel = objectTypeLabel(item.object_type);
  const detailPath = objectDetailPath(item.object_type);
  const displayName = item.object_name || item.object_id;

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/40"
        aria-label="Close recommendation summary"
        onClick={onClose}
      />
      <aside
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-2xl',
          'animate-in slide-in-from-right duration-200'
        )}
        aria-labelledby="reco-drawer-title"
        role="dialog"
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <p className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
              {objectLabel}
            </p>
            <h2 id="reco-drawer-title" className="truncate text-lg font-bold text-foreground">
              {displayName}
            </h2>
            <p className="font-mono text-[10px] text-muted-foreground">{item.object_id}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <div className="grid grid-cols-2 gap-3 rounded-[var(--radius)] border border-border bg-card px-4 py-3 text-sm shadow-[var(--card-shadow)]">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                Category
              </div>
              <Badge variant={categoryBadgeVariant(item.category)} className="mt-1">
                {categoryLabel(item.category)}
              </Badge>
            </div>
            <div>
              <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                Severity
              </div>
              <Badge variant={severityBadgeVariant(item.severity)} className="mt-1">
                {severityLabel(item.severity)}
              </Badge>
            </div>
            <Field
              label="Estimated savings"
              value={formatRecommendationSavings(item.estimated_savings_usd)}
            />
            <Field
              label="Actual cost (period)"
              value={formatRecommendationSavings(item.actual_cost_usd)}
            />
            <Field label="Open since" value={daysSince(item.first_seen_date, periodEnd)} />
            <div>
              <div className="text-[10px] font-black uppercase tracking-[1.2px] text-muted-foreground">
                Status
              </div>
              <Badge variant={recommendationStatusBadgeVariant(item.status)} className="mt-1">
                {recommendationStatusLabel(item.status)}
              </Badge>
            </div>
            <Field label="Workspace" value={item.workspace_id} />
          </div>

          <section>
            <div className="mb-2 text-[10px] font-black uppercase tracking-[1.5px] text-muted-foreground">
              Recommendation
            </div>
            <div className="rounded-[var(--radius)] border border-border bg-card px-4 py-3 text-sm shadow-[var(--card-shadow)]">
              <p className="font-semibold text-foreground">{item.title || '—'}</p>
              {item.detail ? (
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
              ) : null}
              {item.recommended_action ? (
                <p className="mt-3 border-t border-border/70 pt-3 text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">Recommended action:</span>{' '}
                  {item.recommended_action}
                </p>
              ) : null}
            </div>
          </section>

          <Link
            to={detailPath}
            className="block rounded-[var(--radius)] border border-info-border bg-info-subtle px-4 py-3 text-center text-sm font-bold text-info hover:bg-info-subtle/80"
          >
            Open full {objectLabel.toLowerCase()} record →
          </Link>
        </div>
      </aside>
    </>
  );
}
