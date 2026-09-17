import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import { format, parseISO } from 'date-fns';
import type { LakeflowJobHistoryBar } from '../../../types/api';
import { cn } from '../../../lib/utils';
import {
  formatDurationSeconds,
  lakeflowStatusColor,
  lakeflowStatusLabel,
} from '../../../lib/lakeflow/format';

interface HistoryBarsProps {
  workflowId: string;
  history: LakeflowJobHistoryBar[];
  periodLabel?: string;
  className?: string;
}

const LEGEND = [
  { key: 'succeeded', label: 'Succès' },
  { key: 'failed', label: 'Échec' },
  { key: 'timed_out', label: 'Timeout' },
  { key: 'cancelled', label: 'Annulé' },
  { key: 'running', label: 'En cours' },
] as const;

function formatBarDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'dd/MM/yyyy HH:mm');
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}

function formatBarDateShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return format(parseISO(iso), 'dd/MM');
  } catch {
    return iso.slice(5, 10);
  }
}

function truncateRunId(runId: string, head = 6, tail = 4): string {
  if (runId.length <= head + tail + 1) return runId;
  return `${runId.slice(0, head)}…${runId.slice(-tail)}`;
}

function HoverPortal({
  anchorRef,
  open,
  children,
  align = 'center',
}: {
  anchorRef: React.RefObject<HTMLElement | null>;
  open: boolean;
  children: ReactNode;
  align?: 'center' | 'left';
}) {
  const [position, setPosition] = useState({ top: 0, left: 0 });

  const updatePosition = useCallback(() => {
    const rect = anchorRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      top: rect.top - 8,
      left: align === 'center' ? rect.left + rect.width / 2 : rect.left,
    });
  }, [anchorRef, align]);

  useEffect(() => {
    if (open) updatePosition();
  }, [open, updatePosition]);

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div
      role="tooltip"
      className={cn(
        'pointer-events-none fixed z-[9999] -translate-y-full rounded-lg border border-border bg-popover px-3 py-2.5 text-popover-foreground shadow-lg',
        align === 'center' ? '-translate-x-1/2' : ''
      )}
      style={{ top: position.top, left: position.left }}
    >
      {children}
    </div>,
    document.body
  );
}

function BarTooltipContent({ bar }: { bar: LakeflowJobHistoryBar }) {
  const status = lakeflowStatusLabel(bar.status);
  return (
    <div className="w-[196px] space-y-1.5 text-[11px] leading-snug">
      <div className="font-semibold tabular-nums text-foreground">
        {formatBarDate(bar.start_time)}
      </div>
      <div className="flex items-center gap-1.5">
        <span
          className="inline-block size-2 shrink-0 rounded-full"
          style={{ background: lakeflowStatusColor(bar.status) }}
          aria-hidden
        />
        <span className="font-bold text-foreground">{status}</span>
      </div>
      <div className="text-muted-foreground">
        Durée{' '}
        <span className="font-semibold text-foreground">
          {formatDurationSeconds(bar.duration_seconds)}
        </span>
      </div>
      {bar.retry_count != null && bar.retry_count > 0 ? (
        <div className="text-muted-foreground">
          Retries <span className="font-semibold text-foreground">{bar.retry_count}</span>
        </div>
      ) : null}
      <div className="font-mono text-[10px] text-muted-foreground">{truncateRunId(bar.run_id)}</div>
      <div className="pt-0.5 text-[10px] font-semibold text-[var(--tdf-blue)]">
        Cliquer pour ouvrir le run →
      </div>
    </div>
  );
}

function ChartSummaryTooltip({
  bars,
  periodLabel,
  rangeCaption,
}: {
  bars: LakeflowJobHistoryBar[];
  periodLabel?: string;
  rangeCaption: string;
}) {
  const koCount = bars.filter((b) => {
    const s = (b.status || '').toLowerCase();
    return s === 'failed' || s === 'timed_out';
  }).length;

  return (
    <div className="w-[240px] space-y-2 text-[11px] leading-snug">
      <div>
        <div className="font-bold text-foreground">
          {bars.length} run{bars.length > 1 ? 's' : ''} sur la période
        </div>
        <div className="text-muted-foreground">{periodLabel ?? rangeCaption}</div>
        <div className="text-muted-foreground">{rangeCaption}</div>
      </div>

      <div className="flex flex-wrap gap-x-2 gap-y-1">
        {LEGEND.map((item) => (
          <span
            key={item.key}
            className="inline-flex items-center gap-1 text-[10px] text-muted-foreground"
          >
            <span
              className="inline-block size-2 rounded-sm"
              style={{ background: lakeflowStatusColor(item.key) }}
              aria-hidden
            />
            {item.label}
          </span>
        ))}
      </div>

      <div className="text-[10px] text-muted-foreground">
        Gauche = plus ancien · Droite = plus récent · Hauteur = durée relative
        {koCount > 0 ? (
          <>
            {' '}
            · <span className="font-semibold text-danger">{koCount} KO</span>
          </>
        ) : null}
      </div>

      <div className="max-h-[140px] space-y-1 overflow-y-auto border-t border-border/70 pt-2">
        {[...bars].reverse().map((bar) => (
          <div key={bar.run_id} className="flex items-center gap-2 text-[10px]">
            <span
              className="inline-block size-2 shrink-0 rounded-sm"
              style={{ background: lakeflowStatusColor(bar.status) }}
              aria-hidden
            />
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {formatBarDateShort(bar.start_time)}
            </span>
            <span className="min-w-0 truncate font-medium text-foreground">
              {lakeflowStatusLabel(bar.status)}
            </span>
            <span className="ml-auto shrink-0 tabular-nums text-muted-foreground">
              {formatDurationSeconds(bar.duration_seconds)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function HistoryBar({
  workflowId,
  bar,
  heightPct,
  onHoverChange,
}: {
  workflowId: string;
  bar: LakeflowJobHistoryBar;
  heightPct: number;
  onHoverChange: (runId: string | null) => void;
}) {
  const anchorRef = useRef<HTMLAnchorElement>(null);
  const [open, setOpen] = useState(false);
  const color = lakeflowStatusColor(bar.status);

  const show = () => {
    onHoverChange(bar.run_id);
    setOpen(true);
  };
  const hide = () => {
    onHoverChange(null);
    setOpen(false);
  };

  return (
    <>
      <Link
        ref={anchorRef}
        to={`/databricks/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(bar.run_id)}`}
        className="block w-2.5 rounded-sm border border-black/10 transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tdf-blue)]/40"
        style={{ height: `${heightPct}%`, background: color, minHeight: 6 }}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onClick={(e) => e.stopPropagation()}
        aria-label={`${formatBarDate(bar.start_time)}, ${lakeflowStatusLabel(bar.status)}, ${formatDurationSeconds(bar.duration_seconds)}`}
      />
      <HoverPortal anchorRef={anchorRef} open={open}>
        <BarTooltipContent bar={bar} />
      </HoverPortal>
    </>
  );
}

/** Mini sparkline: up to 10 runs, color = status, height = relative duration. */
export function LakeflowHistoryBars({
  workflowId,
  history,
  periodLabel,
  className,
}: HistoryBarsProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);
  const [chartHovered, setChartHovered] = useState(false);
  const [footerHovered, setFooterHovered] = useState(false);
  const [hoveredBarId, setHoveredBarId] = useState<string | null>(null);
  const summaryOpen = (chartHovered || footerHovered) && !hoveredBarId;
  const bars = [...history].reverse();

  if (bars.length === 0) {
    return (
      <div className={cn('min-w-[88px]', className)}>
        <span className="text-xs text-muted-foreground">Aucun run sur la période</span>
      </div>
    );
  }

  const maxDur = Math.max(1, ...bars.map((b) => Number(b.duration_seconds) || 1));
  const oldest = bars[0]?.start_time;
  const newest = bars[bars.length - 1]?.start_time;
  const rangeCaption =
    oldest && newest
      ? `${formatBarDateShort(oldest)} → ${formatBarDateShort(newest)}`
      : `${bars.length} run${bars.length > 1 ? 's' : ''}`;

  return (
    <div className={cn('min-w-[108px]', className)}>
      <div
        ref={chartRef}
        className="flex h-9 items-end gap-0.5"
        role="img"
        aria-label={`Historique de ${bars.length} exécutions du ${rangeCaption}`}
        onMouseEnter={() => setChartHovered(true)}
        onMouseLeave={() => setChartHovered(false)}
      >
        {bars.map((bar) => {
          const h = Math.max(16, Math.round(((Number(bar.duration_seconds) || 1) / maxDur) * 100));
          return (
            <HistoryBar
              key={bar.run_id}
              workflowId={workflowId}
              bar={bar}
              heightPct={h}
              onHoverChange={setHoveredBarId}
            />
          );
        })}
      </div>

      <HoverPortal anchorRef={chartRef} open={summaryOpen} align="left">
        <ChartSummaryTooltip bars={bars} periodLabel={periodLabel} rangeCaption={rangeCaption} />
      </HoverPortal>

      <div
        ref={footerRef}
        className="mt-1 flex items-center justify-between gap-1 text-[9px] font-medium text-muted-foreground"
        onMouseEnter={() => setFooterHovered(true)}
        onMouseLeave={() => setFooterHovered(false)}
      >
        <span className="truncate">{formatBarDateShort(oldest)}</span>
        <span className="shrink-0 tabular-nums">{bars.length}/10</span>
        <span className="truncate text-right">{formatBarDateShort(newest)}</span>
      </div>
    </div>
  );
}
