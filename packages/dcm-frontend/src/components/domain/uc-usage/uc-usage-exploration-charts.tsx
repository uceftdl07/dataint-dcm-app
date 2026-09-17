import { useState } from 'react';
import { Database, ListOrdered, Table2, EyeOff } from 'lucide-react';
import { formatNumber, formatPct, formatUsd } from '../../../lib/compute/format';
import { formatBytes } from '../../../lib/uc-usage/labels';
import { cn } from '../../../lib/utils';
import type {
  UcUsageCostChanges,
  UcUsageFinopsCharts,
  UcUsageWriteCharts,
} from '../../../types/api';
import { ComputeKpiCard } from '../compute/compute-kpi-card';
import { ComputeRankedBars } from '../compute/compute-ranked-bars';
import { UcUsageChartCard, UcUsageChartStatus } from './uc-usage-charts';
import { ucUsageCostChangeBarWidth } from './uc-usage-chart-utils';
import { UcUsageTimeChart } from './uc-usage-time-chart';
interface State<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  onRetry: () => unknown;
}
export function UcUsageWriteChartsPanel(props: State<UcUsageWriteCharts>) {
  const { data, loading, error } = props;
  if (loading || error || !data) return <UcUsageChartStatus {...props} />;
  return (
    <section aria-label="Write activity" className="mb-6 space-y-4">
      <div>
        <h2 className="text-sm font-semibold">Write activity</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Observed volumes and rows written in your selected scope. A dash means the volume is
          unknown.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <ComputeKpiCard
          title="Bytes written"
          icon={Database}
          description="Sum of observed written bytes in the selected scope and period."
          value={formatBytes(data.summary.data_written_bytes)}
          tone="info"
        />
        <ComputeKpiCard
          title="Rows written"
          icon={ListOrdered}
          description="Observed rows written, retaining allocation across multiple target tables."
          value={formatNumber(data.summary.rows_written, 1)}
          tone="purple"
        />
        <ComputeKpiCard
          title="Tables with writes"
          icon={Table2}
          description="Tables with positive observed written volume or row count, counted separately per cloud."
          value={formatNumber(data.summary.tables_with_writes)}
          tone="success"
        />
        <ComputeKpiCard
          title="Written without reads"
          icon={EyeOff}
          description="Tables with observed writes and no recorded read accesses in the period. Review downstream use before taking action."
          value={formatNumber(data.summary.written_without_reads)}
          tone="warning"
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <UcUsageChartCard
          title="Read and write volumes"
          subtitle="How do consumption and production evolve together?"
          note="Volumes may be allocated across multiple source or target tables. They are not table storage sizes or write-operation counts."
        >
          <UcUsageTimeChart
            ariaLabel="Daily read and write volumes"
            unit="Bytes / day"
            formatValue={formatBytes}
            formatAxis={formatBytes}
            series={[
              {
                key: 'read-volume',
                label: 'Read volume',
                color: 'var(--tdf-blue)',
                points: data.daily.map((p) => ({ date: p.date, value: p.data_read_bytes })),
              },
              {
                key: 'write-volume',
                label: 'Written volume',
                color: 'var(--tdf-teal)',
                points: data.daily.map((p) => ({ date: p.date, value: p.data_written_bytes })),
              },
            ]}
          />
        </UcUsageChartCard>
        <UcUsageChartCard
          title="Written volume by table"
          subtitle="Which tables receive the most data?"
          note={`${data.ranking.length} of ${data.summary.tables_with_writes} tables with observed writes · Top 10 by written bytes.`}
        >
          {data.ranking.length ? (
            <ComputeRankedBars
              ariaLabel="Tables ranked by written volume"
              items={data.ranking.map((row) => ({
                key: row.key,
                label: row.label,
                sublabel: `${row.cloud_provider ?? ''} · ${formatNumber(row.rows_written, 1)} rows written · ${formatNumber(row.request_count)} reads`,
                value: row.value,
                valueLabel: formatBytes(row.value),
                tooltip: `${row.label} · ${row.cloud_provider ?? ''} · ${formatBytes(row.value)} written`,
              }))}
            />
          ) : (
            <p className="py-16 text-center text-xs text-muted-foreground">
              No positive write volume or row count observed in this period.
            </p>
          )}
        </UcUsageChartCard>
      </div>
    </section>
  );
}
function CostChangeBar({
  delta,
  maximum,
  excluded,
}: {
  delta: number;
  maximum: number;
  excluded: boolean;
}) {
  // The zero line stays drawn either way, so excluding a row never shifts the layout.
  const width = excluded ? 0 : ucUsageCostChangeBarWidth(delta, maximum);
  const savings = delta < 0;
  return (
    <div className="relative flex h-6 items-center" aria-hidden>
      <div className="absolute inset-y-0 left-1/2 border-l border-border" />
      <div
        className="absolute h-3 rounded-sm"
        style={{
          // `--warning` is the theme-aware orange; a cost increase reads warm, savings cool.
          background: savings ? 'var(--tdf-teal)' : 'var(--warning)',
          width: `${width}%`,
          // Anchored at the zero line, so the pixel minimum grows away from it.
          minWidth: width > 0 ? '4px' : undefined,
          ...(savings ? { right: '50%' } : { left: '50%' }),
        }}
      />
    </div>
  );
}
export function UcUsageCostChangesPanel(props: State<UcUsageCostChanges>) {
  const { data, loading, error } = props;
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  if (loading || error || !data) return <UcUsageChartStatus {...props} />;
  // Rescaling on the remaining rows is the point: one dominant table would otherwise
  // flatten every other bar. The row itself stays — the backend picked this top 10 once
  // and does not re-query, so hiding it would imply an 11th table takes its place.
  const scaled = data.items.filter((row) => !excluded.has(row.key));
  const maximum = Math.max(0, ...scaled.map((row) => Math.abs(row.delta_usd ?? 0)));
  // Counted on the rows actually on screen: a new period can drop a table out of the
  // top 10 while its key lingers in the set, and the reset label must not overstate.
  const excludedHere = data.items.length - scaled.length;
  const toggle = (key: string) =>
    setExcluded((current) => {
      const next = new Set(current);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  return (
    <div className="mb-6">
      <UcUsageChartCard
        title="Largest cost changes"
        subtitle="Which tables explain the change from the previous period?"
        note={`Comparison: ${data.previous_period.start} → ${data.previous_period.end}, with the same number of days. Changes require cost observations in both periods. ${data.items.length} of ${data.entity_count} tables shown. Select a table to exclude it from the bar scale and compare the rest.`}
      >
        <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          <span>
            Current: <strong>{formatUsd(data.current_total)}</strong>
          </span>
          <span>
            Previous: <strong>{formatUsd(data.previous_total)}</strong>
          </span>
          {excludedHere ? (
            <button
              type="button"
              onClick={() => setExcluded(new Set())}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              {excludedHere} excluded from the scale · reset
            </button>
          ) : null}
        </div>
        {data.items.length ? (
          <div className="space-y-4">
            {data.items.map((row) => {
              const off = excluded.has(row.key);
              return (
                <div
                  key={row.key}
                  className="grid items-center gap-2 sm:grid-cols-[minmax(130px,1fr)_minmax(120px,2fr)_120px]"
                >
                  <button
                    type="button"
                    aria-pressed={off}
                    aria-label={`${row.label} · exclude from the bar scale`}
                    onClick={() => toggle(row.key)}
                    className={cn('min-w-0 text-left', off && 'opacity-40')}
                  >
                    <p title={row.label} className="truncate text-xs font-medium">
                      {row.label}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {row.cloud_provider} · {formatUsd(row.previous_cost)} →{' '}
                      {formatUsd(row.current_cost)}
                    </p>
                  </button>
                  {row.delta_usd == null ? (
                    <p className="text-xs text-muted-foreground">
                      {row.previous_cost == null
                        ? 'No previous cost observation'
                        : 'No current cost observation'}
                    </p>
                  ) : (
                    <CostChangeBar delta={row.delta_usd} maximum={maximum} excluded={off} />
                  )}
                  <p
                    className={cn(
                      'text-right text-xs font-semibold tabular-nums',
                      off && 'opacity-40'
                    )}
                  >
                    {row.delta_usd != null && row.delta_usd > 0 ? '+' : ''}
                    {formatUsd(row.delta_usd)}
                    {row.delta_pct == null
                      ? ''
                      : ` · ${row.delta_pct > 0 ? '+' : ''}${formatPct(row.delta_pct, 1)}`}
                  </p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="py-12 text-center text-xs text-muted-foreground">
            No cost observations for these periods.
          </p>
        )}
      </UcUsageChartCard>
    </div>
  );
}
export function UcUsageCostCoverage({ data }: { data: UcUsageFinopsCharts }) {
  return (
    <div className="mb-6">
      <UcUsageChartCard
        title="Cost attribution coverage"
        subtitle="Is the measured share of accesses stable enough to compare costs?"
        note="Share of accesses with an attributed cost each day. A gap means the coverage could not be calculated."
      >
        <UcUsageTimeChart
          ariaLabel="Daily cost attribution coverage"
          unit="Attributed accesses (%)"
          maxValue={100}
          formatAxis={(v) => `${v}%`}
          formatValue={(v) => formatPct(v, 1)}
          series={[
            {
              key: 'coverage',
              label: 'Cost attribution coverage',
              color: 'var(--tdf-teal)',
              points: data.unit_cost.map((p) => ({ date: p.date, value: p.coverage_pct })),
            },
          ]}
        />
      </UcUsageChartCard>
    </div>
  );
}
