/**
 * Databricks Overview — layout aligned to maquette/maquette_overview.html
 * (DCM tokens). Vertical sidebar nav only — no horizontal tab strip.
 */
import { useCallback, useMemo, type ReactNode, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts';
import { RefreshCw } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { Content, ContentMain, ContentTitle } from '../components/layout/content';
import { Skeleton } from '../components/ui/skeleton';
import { cn } from '../lib/utils';
import { useLakeflowOverviewData } from '../hooks/useLakeflowOverviewData';
import type { LakeflowWindow } from '../hooks/useLakeflowOverviewData';
import { useGlobalTimeRange } from '../contexts/time-range';
import type {
  LakeflowTimelinePoint,
  LakeflowUnstableWorkflow,
  LakeflowRecentError,
} from '../types/api';

// ─── Tokens (maquette / DCM) ─────────────────────────────────────────────────

const ST = {
  succeeded: 'var(--success)',
  failed: 'var(--danger)',
  timed_out: 'var(--chart-5, #fe9a00)',
  cancelled: 'var(--tdf-grey, #68707d)',
  blue: 'var(--tdf-blue)',
  blueSubtle: 'var(--tdf-blue-subtle)',
  blueBorder: 'var(--tdf-blue-border)',
  muted: 'var(--muted)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
  success: 'var(--success)',
} as const;

const WINDOW_LABELS: Record<LakeflowWindow, string> = {
  today: "Aujourd'hui",
  '7d': '7 jours',
  '30d': '30 jours',
};

function isoDateUtc(d: Date): string {
  return d.toISOString().split('T')[0]!;
}

/** Inclusive date range matching backend `_resolve_window`. */
function datesForWindow(window: LakeflowWindow): {
  start: string;
  end: string;
  description: string;
} {
  const end = new Date();
  const endStr = isoDateUtc(end);
  if (window === 'today') {
    return { start: endStr, end: endStr, description: WINDOW_LABELS.today };
  }
  const days = window === '7d' ? 7 : 30;
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return {
    start: isoDateUtc(start),
    end: endStr,
    description: WINDOW_LABELS[window],
  };
}

function matchWindowFromDates(start: string, end: string): LakeflowWindow | null {
  for (const w of Object.keys(WINDOW_LABELS) as LakeflowWindow[]) {
    const preset = datesForWindow(w);
    if (preset.start === start && preset.end === end) return w;
  }
  return null;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '—';
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h} h ${m.toString().padStart(2, '0')}`;
  if (m > 0) return `${m} m ${sec.toString().padStart(2, '0')} s`;
  return `${sec} s`;
}

function formatPct(rate: number | null | undefined, digits = 1): string {
  if (rate == null) return '—';
  return `${rate.toFixed(digits).replace('.', ',')} %`;
}

function formatDateLabel(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'dd/MM');
  } catch {
    return dateStr.slice(5, 10);
  }
}

function reliabilityColor(rate: number | null, n?: number): string {
  if (rate == null || (n !== undefined && n < 5)) return 'var(--muted-foreground)';
  if (rate > 95) return ST.success;
  if (rate >= 90) return ST.warning;
  return ST.danger;
}

function taskFailureColor(rate: number | null): string {
  if (rate == null) return 'var(--muted-foreground)';
  if (rate < 2) return ST.success;
  if (rate < 5) return ST.warning;
  return ST.danger;
}

// ─── Primitives ──────────────────────────────────────────────────────────────

function SectionEyebrow({ label }: { label: string }) {
  return (
    <div className="mb-3 mt-6 flex items-center gap-3 first:mt-0">
      <span className="text-[10px] font-black uppercase tracking-[2px] text-muted-foreground">
        {label}
      </span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

function OvBadge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'ok' | 'warn' | 'ko' | 'info' | 'neutral';
}) {
  const tones = {
    ok: 'border-success-border bg-success-subtle text-success',
    warn: 'border-warning-border bg-warning-subtle text-warning',
    ko: 'border-danger-border bg-danger-subtle text-danger',
    info: 'border-info-border bg-info-subtle text-info',
    neutral: 'border-border bg-muted text-muted-foreground',
  } as const;
  return (
    <span
      className={cn(
        'whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[9px] font-black uppercase tracking-[1.1px]',
        tones[tone]
      )}
    >
      {children}
    </span>
  );
}

function OvCard({
  title,
  badge,
  children,
  alert,
  warn,
  hrefLabel,
  onClick,
  className,
}: {
  title: string;
  badge?: ReactNode;
  children: ReactNode;
  alert?: boolean;
  warn?: boolean;
  hrefLabel?: string;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
        if (!onClick) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        'group relative rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] px-5 py-4 shadow-[var(--card-shadow)] transition-[box-shadow,transform,border-color] duration-150',
        onClick &&
          'cursor-pointer hover:-translate-y-0.5 hover:border-ring hover:shadow-[0_18px_42px_#0f172a1f]',
        alert &&
          'border-danger-border bg-gradient-to-b from-danger-subtle from-0% to-[var(--card-background)] to-[46%]',
        warn &&
          'border-warning-border bg-gradient-to-b from-warning-subtle from-0% to-[var(--card-background)] to-[46%]',
        className
      )}
    >
      <div className="flex min-h-5 items-start justify-between gap-2.5">
        <span className="text-[9.5px] font-black uppercase tracking-[1.5px] text-muted-foreground">
          {title}
        </span>
        {badge}
      </div>
      {children}
      {hrefLabel && onClick ? (
        <div className="pointer-events-none absolute bottom-3 right-[18px] text-[9.5px] font-black uppercase tracking-[1.3px] text-[var(--tdf-blue)] opacity-0 transition-opacity group-hover:opacity-100">
          {hrefLabel} →
        </div>
      ) : null}
    </div>
  );
}

function SegBar({ parts }: { parts: Array<{ pct: number; color: string; title?: string }> }) {
  return (
    <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted">
      {parts
        .filter((p) => p.pct > 0)
        .map((p, i) => (
          <i
            key={i}
            title={p.title}
            className="block h-full"
            style={{ width: `${p.pct}%`, background: p.color }}
          />
        ))}
    </div>
  );
}

function LegendRow({ items }: { items: Array<{ label: string; color: string }> }) {
  return (
    <div className="mt-2.5 flex flex-wrap gap-3 text-[11px] font-medium text-muted-foreground">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <s
            className="inline-block size-2 rounded-sm no-underline"
            style={{ background: it.color }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** Semi-circular gauge (maquette). */
function SemiGauge({ pct, color }: { pct: number; color: string }) {
  const clamped = Math.max(0, Math.min(100, pct));
  const cx = 47;
  const cy = 47;
  const r = 36;
  const a = Math.PI * (1 - clamped / 100);
  const x = cx + r * Math.cos(a);
  const y = cy - r * Math.sin(a);
  return (
    <svg width="94" height="55" viewBox="0 0 94 55" aria-hidden>
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none"
        stroke="var(--muted)"
        strokeWidth="10"
        strokeLinecap="round"
      />
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)}`}
        fill="none"
        stroke={color}
        strokeWidth="10"
        strokeLinecap="round"
      />
    </svg>
  );
}

function PercentileTrack({ p50, p95, p99 }: { p50: number; p95: number; p99: number }) {
  const max = Math.max(p99, p95, p50, 1);
  const marks: Array<[string, number, string]> = [
    ['p50', (p50 / max) * 100, ST.blue],
    ['p95', (p95 / max) * 100, ST.warning],
    ['p99', (p99 / max) * 100, ST.danger],
  ];
  return (
    <svg viewBox="0 0 300 36" width="100%" height="36" className="mt-2.5" aria-hidden>
      <rect x="0" y="12" width="300" height="9" rx="4.5" fill="var(--muted)" />
      <rect
        x="0"
        y="12"
        width={Math.min(300 * (p95 / max), 300)}
        height="9"
        rx="4.5"
        fill="var(--tdf-blue-subtle)"
      />
      {marks.map(([label, v, c]) => {
        const x = Math.min((300 * v) / 100, 286);
        return (
          <g key={label}>
            <line x1={x} y1="7" x2={x} y2="26" stroke={c} strokeWidth="2.6" strokeLinecap="round" />
            <text
              x={x}
              y="35"
              fontSize="9"
              fontWeight="700"
              fill="var(--muted-foreground)"
              textAnchor="middle"
            >
              {label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function WindowSelector({
  value,
  onChange,
}: {
  value: LakeflowWindow | null;
  onChange: (w: LakeflowWindow) => void;
}) {
  return (
    <div className="flex overflow-hidden rounded-[var(--radius)] border border-ring bg-white">
      {(Object.keys(WINDOW_LABELS) as LakeflowWindow[]).map((w, i, arr) => (
        <button
          key={w}
          type="button"
          onClick={() => onChange(w)}
          className={cn(
            'px-3.5 py-1.5 text-[9.5px] font-black uppercase tracking-[1.4px] transition-colors',
            i < arr.length - 1 && 'border-r border-border',
            value === w
              ? 'bg-[var(--tdf-blue)] text-white'
              : 'bg-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          {WINDOW_LABELS[w]}
        </button>
      ))}
    </div>
  );
}

// ─── Cards ───────────────────────────────────────────────────────────────────

/** `HH:mm` d'un horodatage de sparkline, ou la valeur brute si elle n'est pas ISO. */
function sparklineTimeLabel(raw: unknown): string {
  if (typeof raw !== 'string') return '';
  try {
    return format(parseISO(raw), 'HH:mm');
  } catch {
    return raw;
  }
}

function ActiveRunsCard({
  value,
  sparkline,
  asOf,
  onClick,
}: {
  value: number | null;
  sparkline: Array<{ t: string; v: number }>;
  asOf: string | null;
  onClick?: () => void;
}) {
  let timeLabel = '';
  if (asOf) {
    try {
      timeLabel = format(parseISO(asOf), 'HH:mm');
    } catch {
      timeLabel = '';
    }
  }
  return (
    <OvCard
      title="Runs actifs"
      badge={timeLabel ? <OvBadge tone="neutral">à {timeLabel}</OvBadge> : undefined}
      hrefLabel="Runs en cours"
      onClick={onClick}
    >
      <div className="mt-2.5 text-2xl font-black tracking-tight">
        {value == null ? '—' : value.toLocaleString('fr-FR')}
      </div>
      <div className="text-[13px] font-medium text-muted-foreground">
        Concurrence reconstruite — pas de sonde temps réel
      </div>
      {sparkline.length > 0 ? (
        <div className="mt-2.5 h-[46px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkline} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              {/* Sans axes, la courbe seule ne dit pas combien de runs ni à quelle
                  heure : le survol est la seule façon de lire un point. */}
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--popover)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                // Le graphe n'a pas d'axe X : le libellé par défaut serait l'index du
                // point, pas son heure.
                labelFormatter={(_label, payload) => sparklineTimeLabel(payload?.[0]?.payload?.t)}
                formatter={(value) => [`${Number(value).toLocaleString('fr-FR')} runs`, 'Actifs']}
              />
              <Line
                type="monotone"
                dataKey="v"
                stroke="var(--tdf-blue)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </OvCard>
  );
}

function RunsCompletedCard({
  runsByStatus,
  windowLabel,
  onClick,
}: {
  runsByStatus: { succeeded: number; failed: number; timed_out: number; cancelled: number };
  windowLabel: string;
  onClick?: () => void;
}) {
  const total =
    runsByStatus.succeeded + runsByStatus.failed + runsByStatus.timed_out + runsByStatus.cancelled;
  const pct = (n: number) => (total > 0 ? (n / total) * 100 : 0);
  return (
    <OvCard title="Runs terminés" hrefLabel="Tous les workflows" onClick={onClick}>
      <div className="mt-2.5 text-2xl font-black tracking-tight">
        {total.toLocaleString('fr-FR')}
      </div>
      <div className="text-[13px] font-medium text-muted-foreground">{windowLabel}</div>
      <SegBar
        parts={[
          { pct: pct(runsByStatus.succeeded), color: ST.succeeded, title: 'succès' },
          { pct: pct(runsByStatus.failed), color: ST.failed, title: 'échecs' },
          { pct: pct(runsByStatus.timed_out), color: ST.timed_out, title: 'timeout' },
          { pct: pct(runsByStatus.cancelled), color: ST.cancelled, title: 'annulés' },
        ]}
      />
      <LegendRow
        items={[
          { label: `${runsByStatus.succeeded} succès`, color: ST.succeeded },
          { label: `${runsByStatus.failed} échecs`, color: ST.failed },
          { label: `${runsByStatus.timed_out} timeout`, color: ST.timed_out },
          { label: `${runsByStatus.cancelled} annulés`, color: ST.cancelled },
        ]}
      />
    </OvCard>
  );
}

function FailedRunsCard({
  koCount,
  koDelta,
  distinctKoWorkflows,
  onClick,
}: {
  koCount: number;
  koDelta: number | null;
  distinctKoWorkflows: number;
  onClick?: () => void;
}) {
  const deltaNode =
    koDelta == null ? null : koDelta < 0 ? (
      <span className="font-extrabold text-success">▼ {Math.abs(koDelta)}</span>
    ) : koDelta > 0 ? (
      <span className="font-extrabold text-danger">▲ {koDelta}</span>
    ) : (
      <span className="font-extrabold text-muted-foreground">= 0</span>
    );

  return (
    <OvCard
      title="Runs en échec"
      badge={koCount > 0 ? <OvBadge tone="ko">à traiter</OvBadge> : undefined}
      alert={koCount > 0}
      hrefLabel="Workflows en échec"
      onClick={koCount > 0 ? onClick : undefined}
    >
      <div
        className="mt-2.5 text-2xl font-black tracking-tight"
        style={{ color: koCount > 0 ? ST.danger : undefined }}
      >
        {koCount.toLocaleString('fr-FR')}
      </div>
      <div className="text-[13px] font-medium text-muted-foreground">
        {deltaNode} {deltaNode ? 'vs période précédente' : null}
        {distinctKoWorkflows > 0
          ? `${deltaNode ? ' · ' : ''}${distinctKoWorkflows} workflow${distinctKoWorkflows > 1 ? 's' : ''} touché${distinctKoWorkflows > 1 ? 's' : ''}`
          : null}
      </div>
    </OvCard>
  );
}

function SuccessRateCard({
  title,
  rate,
  n,
  delta,
  badgeTone,
  badgeLabel,
}: {
  title: string;
  rate: number | null;
  n: number;
  delta: number | null;
  badgeTone: 'ok' | 'warn' | 'ko' | 'neutral';
  badgeLabel: string;
}) {
  const color = reliabilityColor(rate, n);
  const showGauge = rate != null && n >= 5;
  const deltaStr =
    delta == null
      ? null
      : delta >= 0
        ? `▲ ${delta.toFixed(1).replace('.', ',')} pt`
        : `▼ ${Math.abs(delta).toFixed(1).replace('.', ',')} pt`;
  const deltaClass = delta == null ? '' : delta >= 0 ? 'text-success' : 'text-danger';

  return (
    <OvCard title={title} badge={<OvBadge tone={badgeTone}>{badgeLabel}</OvBadge>}>
      <div className="mt-1.5 flex items-center gap-4">
        {showGauge ? <SemiGauge pct={rate} color={color} /> : <div className="h-[55px] w-[94px]" />}
        <div>
          <div className="text-[26px] font-black leading-tight tracking-tight" style={{ color }}>
            {formatPct(rate)}
          </div>
          <div className="text-[13px] font-medium text-muted-foreground">
            n = {n.toLocaleString('fr-FR')}
            {deltaStr ? (
              <>
                {' · '}
                <span className={cn('font-extrabold', deltaClass)}>{deltaStr}</span>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </OvCard>
  );
}

function TaskFailureCard({
  rate,
  failed,
  total,
}: {
  rate: number | null;
  failed: number;
  total: number;
}) {
  const color = taskFailureColor(rate);
  let badgeTone: 'ok' | 'warn' | 'ko' | 'neutral' = 'neutral';
  let badgeLabel = 'n/a';
  if (rate != null) {
    if (rate < 2) {
      badgeTone = 'ok';
      badgeLabel = '< 2 %';
    } else if (rate < 5) {
      badgeTone = 'warn';
      badgeLabel = '2–5 %';
    } else {
      badgeTone = 'ko';
      badgeLabel = '> 5 %';
    }
  }
  return (
    <OvCard title="Tâches en échec" badge={<OvBadge tone={badgeTone}>{badgeLabel}</OvBadge>}>
      <div className="mt-2.5 text-2xl font-black tracking-tight" style={{ color }}>
        {formatPct(rate)}
      </div>
      <div className="text-[13px] font-medium text-muted-foreground">
        {failed.toLocaleString('fr-FR')} tâches KO sur {total.toLocaleString('fr-FR')}
      </div>
      <SegBar parts={[{ pct: Math.min(rate ?? 0, 100), color: ST.warning }]} />
    </OvCard>
  );
}

function AvgDurationCard({
  avgSeconds,
  driftPct,
  baselineSeconds,
  onClick,
}: {
  avgSeconds: number | null;
  driftPct: number | null;
  baselineSeconds: number | null;
  onClick?: () => void;
}) {
  const isDrift = driftPct != null && driftPct > 20;
  const driftStr =
    driftPct == null
      ? null
      : `${driftPct >= 0 ? '+' : ''}${driftPct.toFixed(1).replace('.', ',')} % ${driftPct >= 0 ? '↗' : '↘'}`;
  return (
    <OvCard
      title="Durée moyenne"
      badge={isDrift ? <OvBadge tone="warn">⚠ dérive</OvBadge> : undefined}
      warn={isDrift}
      hrefLabel="Trier par dérive"
      onClick={onClick}
    >
      <div className="mt-2.5 text-2xl font-black tracking-tight">{formatDuration(avgSeconds)}</div>
      <div className="text-[13px] font-medium text-muted-foreground">
        {driftStr ? (
          <span className={cn('font-extrabold', driftPct! >= 0 ? 'text-danger' : 'text-success')}>
            {driftStr}
          </span>
        ) : null}
        {baselineSeconds != null && driftStr
          ? ` vs baseline 14 j (${formatDuration(baselineSeconds)})`
          : null}
      </div>
    </OvCard>
  );
}

function DurationDistributionCard({
  p50,
  p95,
  p99,
}: {
  p50: number | null;
  p95: number | null;
  p99: number | null;
}) {
  return (
    <OvCard title="Distribution des durées">
      <div className="mt-2.5 text-2xl font-black tracking-tight">
        {formatDuration(p95)}
        <small className="ml-1.5 text-[11px] font-bold tracking-normal text-muted-foreground">
          p95
        </small>
      </div>
      <div className="text-[13px] font-medium text-muted-foreground">
        p50 <b className="text-foreground">{formatDuration(p50)}</b>
        {' · '}
        p99 <b className="text-foreground">{formatDuration(p99)}</b>
      </div>
      {p50 != null && p95 != null && p99 != null ? (
        <PercentileTrack p50={p50} p95={p95} p99={p99} />
      ) : null}
    </OvCard>
  );
}

function QueueCard({ avgQueued, avgLag }: { avgQueued: number | null; avgLag: number | null }) {
  const q = avgQueued ?? 0;
  const lag = avgLag ?? 0;
  const total = q + lag;
  const qPct = total > 0 ? (q / total) * 100 : 0;
  const lagPct = total > 0 ? (lag / total) * 100 : 0;
  return (
    <OvCard title="Attente avant exécution">
      <div className="mt-2.5 text-2xl font-black tracking-tight">
        {formatDuration(total || null)}
      </div>
      <div className="text-[13px] font-medium text-muted-foreground">
        Provisionnement cluster vs retard d&apos;orchestration
      </div>
      <SegBar
        parts={[
          { pct: qPct, color: ST.blue },
          { pct: lagPct, color: ST.blueBorder },
        ]}
      />
      <LegendRow
        items={[
          { label: `File d'attente ${formatDuration(avgQueued)}`, color: ST.blue },
          { label: `Retard planif. ${formatDuration(avgLag)}`, color: ST.blueBorder },
        ]}
      />
    </OvCard>
  );
}

function TimelineChart({ data }: { data: LakeflowTimelinePoint[] }) {
  if (data.length === 0) return null;
  const chartData = data.map((d) => ({
    date: formatDateLabel(d.date),
    Succès: d.succeeded,
    Échec: d.failed,
    Timeout: d.timed_out,
    Annulé: d.cancelled,
  }));
  return (
    <div className="mt-4 overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
        <h3 className="m-0 text-[15px] font-extrabold tracking-tight">Runs terminés par statut</h3>
        <div className="text-[11px] font-medium text-muted-foreground">
          grain jour — masqué en fenêtre « aujourd&apos;hui »
        </div>
      </div>
      <div className="px-5 py-4">
        <ResponsiveContainer width="100%" height={190}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fontWeight: 700 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--popover)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="Succès" stackId="a" fill={ST.succeeded} isAnimationActive={false} />
            <Bar dataKey="Échec" stackId="a" fill={ST.failed} isAnimationActive={false} />
            <Bar dataKey="Timeout" stackId="a" fill={ST.timed_out} isAnimationActive={false} />
            <Bar dataKey="Annulé" stackId="a" fill={ST.cancelled} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function TopUnstableTable({ items }: { items: LakeflowUnstableWorkflow[] }) {
  if (items.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
        <h3 className="m-0 text-[15px] font-extrabold tracking-tight">Top 5 workflows instables</h3>
        <div className="text-[11px] font-medium text-muted-foreground">fenêtre courante</div>
      </div>
      <div className="px-2 pb-2 pt-1">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr>
              <th className="border-b border-border px-2.5 py-2 text-left text-[9.5px] font-black uppercase tracking-[1.4px] text-muted-foreground">
                Workflow
              </th>
              <th className="w-[52px] border-b border-border px-2.5 py-2 text-left text-[9.5px] font-black uppercase tracking-[1.4px] text-muted-foreground">
                KO
              </th>
              <th className="w-[118px] border-b border-border px-2.5 py-2 text-left text-[9.5px] font-black uppercase tracking-[1.4px] text-muted-foreground">
                Fiabilité
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const rate = row.total > 0 ? ((row.total - row.ko) / row.total) * 100 : null;
              const color = reliabilityColor(rate);
              return (
                <tr key={row.workflow_id} className="hover:bg-muted">
                  <td className="border-b border-muted px-2.5 py-2.5 align-middle">
                    <div className="font-bold">{row.workflow_name}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">
                      workflow_id {row.workflow_id}
                    </div>
                  </td>
                  <td className="border-b border-muted px-2.5 py-2.5 align-middle">
                    <OvBadge tone="ko">{row.ko}</OvBadge>
                  </td>
                  <td className="border-b border-muted px-2.5 py-2.5 align-middle">
                    {rate != null ? (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="inline-block h-1.5 w-16 overflow-hidden rounded-full bg-muted align-middle">
                          <i
                            className="block h-full rounded-full"
                            style={{ width: `${rate}%`, background: color }}
                          />
                        </span>
                        <span className="font-extrabold" style={{ color }}>
                          {rate.toFixed(1).replace('.', ',')}%
                        </span>
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RecentErrorsTable({ items }: { items: LakeflowRecentError[] }) {
  if (items.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]">
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3.5">
        <h3 className="m-0 text-[15px] font-extrabold tracking-tight">Derniers runs en échec</h3>
        <div className="text-[11px] font-medium text-muted-foreground">5 derniers</div>
      </div>
      <div className="px-2 pb-2 pt-1">
        <table className="w-full border-collapse text-[12.5px]">
          <thead>
            <tr>
              <th className="border-b border-border px-2.5 py-2 text-left text-[9.5px] font-black uppercase tracking-[1.4px] text-muted-foreground">
                Workflow
              </th>
              <th className="w-[60px] border-b border-border px-2.5 py-2 text-left text-[9.5px] font-black uppercase tracking-[1.4px] text-muted-foreground">
                Heure
              </th>
              <th className="border-b border-border px-2.5 py-2 text-left text-[9.5px] font-black uppercase tracking-[1.4px] text-muted-foreground">
                Erreur
              </th>
              <th className="w-[30px] border-b border-border px-2.5 py-2" />
            </tr>
          </thead>
          <tbody>
            {items.slice(0, 5).map((row, i) => {
              let timeStr = '';
              try {
                timeStr = format(parseISO(row.start_time), 'HH:mm');
              } catch {
                timeStr = row.start_time.slice(11, 16);
              }
              return (
                <tr key={`${row.run_id}-${i}`} className="hover:bg-muted">
                  <td className="border-b border-muted px-2.5 py-2.5 font-bold align-middle">
                    {row.workflow_name}
                  </td>
                  <td className="border-b border-muted px-2.5 py-2.5 font-mono text-[11px] text-muted-foreground align-middle">
                    {timeStr}
                  </td>
                  <td className="border-b border-muted px-2.5 py-2.5 align-middle">
                    <span
                      className="block max-w-[330px] truncate text-muted-foreground"
                      title={row.error_message}
                    >
                      {row.error_message || '—'}
                    </span>
                  </td>
                  <td className="border-b border-muted px-2.5 py-2.5 align-middle">
                    {row.run_page_url ? (
                      <a
                        href={row.run_page_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-black text-[var(--tdf-blue)] no-underline"
                        title="Ouvrir le run"
                      >
                        ↗
                      </a>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function successBadge(
  rate: number | null,
  n: number
): { tone: 'ok' | 'warn' | 'ko' | 'neutral'; label: string } {
  if (rate == null || n < 5) return { tone: 'neutral', label: `n = ${n}` };
  if (rate > 95) return { tone: 'ok', label: '≥ 95 %' };
  if (rate >= 90) return { tone: 'warn', label: '90–95 %' };
  return { tone: 'ko', label: '< 90 %' };
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function LakeflowOverview() {
  const { updateTimeRange, getApiParams, getDisplayRange } = useGlobalTimeRange();
  const { start_date, end_date } = getApiParams();
  const display = getDisplayRange();

  const matchedWindow = useMemo(
    () => matchWindowFromDates(start_date, end_date),
    [start_date, end_date]
  );
  // API still accepts window as soft hint; header dates always win on the backend.
  const queryWindow: LakeflowWindow = matchedWindow ?? '30d';

  const { data, loading, error, refetch } = useLakeflowOverviewData(queryWindow);
  const navigate = useNavigate();

  const handleWindowChange = useCallback(
    (next: LakeflowWindow) => {
      const { start, end, description } = datesForWindow(next);
      updateTimeRange(start, end, description);
    },
    [updateTimeRange]
  );

  const handleFailedClick = useCallback(() => {
    navigate('/databricks/workflows?status=failed,timed_out');
  }, [navigate]);

  const asOfTime = useMemo(() => {
    if (!data?.as_of && !data?.activity?.concurrency_as_of) return '';
    const raw = data.activity.concurrency_as_of || data.as_of;
    try {
      return format(parseISO(raw), 'HH:mm');
    } catch {
      return '';
    }
  }, [data]);

  const rangeDays =
    data?.window?.from && data?.window?.to
      ? Math.max(
          1,
          Math.round(
            (parseISO(data.window.to).getTime() - parseISO(data.window.from).getTime()) /
              (24 * 60 * 60 * 1000)
          ) + 1
        )
      : display.daysCount;

  const windowSub =
    rangeDays <= 1
      ? 'sur le jour courant'
      : `du ${display.startDate} au ${display.endDate} (${rangeDays} j)`;

  const showTimeline = rangeDays > 1;

  const badge24 = successBadge(
    data?.reliability.success_rate_24h_pct ?? null,
    data?.reliability.success_rate_24h_n ?? 0
  );
  const badge7 = successBadge(
    data?.reliability.success_rate_7d_pct ?? null,
    data?.reliability.success_rate_7d_n ?? 0
  );

  return (
    <Content className="mx-auto max-w-[1360px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentTitle>Databricks Overview</ContentTitle>

      {/* Page presets sync header From/To; custom header dates drive the API */}
      <div className="mb-5 flex flex-wrap items-center gap-2.5 rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] px-[18px] py-2.5 shadow-[var(--card-shadow)]">
        <WindowSelector value={matchedWindow} onChange={handleWindowChange} />
        <div className="flex-1" />
        <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-muted-foreground">
          <i className="inline-block size-1.5 rounded-full bg-success" />
          {asOfTime ? `Collecte ${asOfTime} · rafraîchissement 60 s` : 'Rafraîchissement 60 s'}
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded p-1 text-muted-foreground hover:text-foreground"
          aria-label="Rafraîchir"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-[var(--card-radius)] border border-danger-border bg-danger-subtle px-4 py-3 text-sm text-danger">
          Impossible de charger les données Overview.{' '}
          <button type="button" onClick={() => refetch()} className="underline">
            Réessayer
          </button>
        </div>
      )}

      <ContentMain className="gap-0">
        <SectionEyebrow label="Activité" />
        {loading && !data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Skeleton className="h-36" />
            <Skeleton className="h-36" />
            <Skeleton className="h-36" />
          </div>
        ) : data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <ActiveRunsCard
              value={data.activity.concurrent_runs_active}
              sparkline={data.activity.concurrency_sparkline}
              asOf={data.activity.concurrency_as_of}
              onClick={() => navigate('/databricks/workflows?status=running')}
            />
            <RunsCompletedCard
              runsByStatus={data.activity.runs_by_status}
              windowLabel={windowSub}
              onClick={() => navigate('/databricks/workflows')}
            />
            <FailedRunsCard
              koCount={data.activity.runs_ko}
              koDelta={data.activity.runs_ko_delta}
              distinctKoWorkflows={data.activity.distinct_ko_workflows}
              onClick={handleFailedClick}
            />
          </div>
        ) : null}

        <SectionEyebrow label="Fiabilité" />
        {loading && !data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        ) : data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <SuccessRateCard
              title="Taux de succès · aujourd'hui"
              rate={data.reliability.success_rate_24h_pct}
              n={data.reliability.success_rate_24h_n}
              delta={data.reliability.success_rate_24h_delta}
              badgeTone={badge24.tone}
              badgeLabel={badge24.label}
            />
            <SuccessRateCard
              title="Taux de succès · 7 jours"
              rate={data.reliability.success_rate_7d_pct}
              n={data.reliability.success_rate_7d_n}
              delta={data.reliability.success_rate_7d_delta}
              badgeTone={badge7.tone}
              badgeLabel={badge7.label}
            />
            <TaskFailureCard
              rate={data.reliability.task_failure_rate_pct}
              failed={data.reliability.tasks_failed}
              total={data.reliability.tasks_total}
            />
          </div>
        ) : null}

        <SectionEyebrow label="Performance" />
        {loading && !data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        ) : data ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <AvgDurationCard
              avgSeconds={data.performance.avg_duration_seconds}
              driftPct={data.performance.duration_drift_pct}
              baselineSeconds={data.performance.baseline_avg_duration_seconds}
              onClick={() => navigate('/databricks/workflows')}
            />
            <DurationDistributionCard
              p50={data.performance.p50}
              p95={data.performance.p95}
              p99={data.performance.p99}
            />
            <QueueCard
              avgQueued={data.performance.avg_queued_duration_seconds}
              avgLag={data.performance.avg_schedule_lag_seconds}
            />
          </div>
        ) : null}

        {loading && !data ? (
          <Skeleton className="mt-4 h-56" />
        ) : data && showTimeline ? (
          <TimelineChart data={data.timeline} />
        ) : null}

        {loading && !data ? (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Skeleton className="h-48" />
            <Skeleton className="h-48" />
          </div>
        ) : data && (data.top_unstable.length > 0 || data.recent_errors.length > 0) ? (
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <TopUnstableTable items={data.top_unstable} />
            <RecentErrorsTable items={data.recent_errors} />
          </div>
        ) : null}
      </ContentMain>
    </Content>
  );
}
