import type { ReactNode } from 'react';
import type {
  UcUsageChartRank,
  UcUsageConsumerCharts,
  UcUsageFinopsCharts,
  UcUsageTableCharts,
} from '../../../types/api';
import { formatNumber, formatPct, formatUsd } from '../../../lib/compute/format';
import { cn } from '../../../lib/utils';
import { Button } from '../../ui/button';
import { Skeleton } from '../../ui/skeleton';
import { ComputeRankedBars } from '../compute/compute-ranked-bars';
import { ComputeStackedBar } from '../compute/compute-stacked-bar';
import { UcUsageActivityHeatmap } from './uc-usage-activity-heatmap';
import { UcUsageTimeChart, UcUsageTableTimeChart } from './uc-usage-time-chart';
import { ucUsageShortDate } from './uc-usage-chart-utils';

interface ChartState<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  onRetry: () => unknown;
}

export function UcUsageChartCard({
  title,
  subtitle,
  note,
  wide = false,
  children,
}: {
  title: string;
  subtitle: string;
  note?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className={cn(
        'min-w-0 rounded-[var(--card-radius,1.375rem)] border border-border bg-card p-4 shadow-[var(--card-shadow)]',
        wide && 'lg:col-span-2'
      )}
    >
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-foreground">
        {title}
      </h3>
      <p className="mb-4 mt-1 text-xs text-muted-foreground">{subtitle}</p>
      {children}
      {note ? (
        <div className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">{note}</div>
      ) : null}
    </section>
  );
}

export function UcUsageChartStatus({ loading, error, onRetry }: Omit<ChartState<unknown>, 'data'>) {
  if (loading)
    return (
      <div aria-label="Loading charts" role="status" className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-80" />
        <Skeleton className="h-80" />
        <Skeleton className="h-64 lg:col-span-2" />
      </div>
    );
  if (error)
    return (
      <div
        role="alert"
        className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--card-radius,1.375rem)] border border-border bg-card p-4"
      >
        <p className="text-sm">Unable to load charts for this scope.</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            onRetry();
          }}
        >
          Retry charts
        </Button>
      </div>
    );
  return <p className="py-8 text-center text-xs text-muted-foreground">No chart data available.</p>;
}

function Ranking({
  rows,
  cost = false,
  ariaLabel,
}: {
  rows: UcUsageChartRank[];
  cost?: boolean;
  ariaLabel: string;
}) {
  if (rows.length === 0)
    return (
      <p className="py-12 text-center text-xs text-muted-foreground">No results for this period.</p>
    );
  return (
    <ComputeRankedBars
      ariaLabel={ariaLabel}
      labelWidthClassName="w-28 sm:w-36"
      items={rows.map((row) => ({
        key: row.key,
        label: row.label,
        sublabel: [
          row.cloud_provider,
          row.distinct_tables != null ? `${formatNumber(row.distinct_tables)} tables` : null,
          row.share_pct != null ? `${formatPct(row.share_pct, 1)} of total` : null,
        ]
          .filter(Boolean)
          .join(' · '),
        value: row.value,
        valueLabel: cost ? formatUsd(row.value) : formatNumber(row.value),
        tooltip: `${row.label} · ${row.cloud_provider ?? ''} · ${cost ? formatUsd(row.value) : `${formatNumber(row.value)} reads`}${row.consumer_type ? ` · ${row.consumer_type}` : ''}`,
      }))}
    />
  );
}

const grid = 'mb-6 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]';
const accesses = (value: number | null) => `${formatNumber(value)}${value == null ? '' : ' reads'}`;

export function UcUsageTableChartsPanel(props: ChartState<UcUsageTableCharts>) {
  const { data, loading, error } = props;
  if (loading || error || !data) return <UcUsageChartStatus {...props} />;
  const consumerRanking = data.ranking_mode === 'consumers';
  return (
    <div className={grid}>
      <UcUsageChartCard
        title="Daily reads by table"
        subtitle="Which tables explain changes in activity?"
        note={
          <>
            {data.summary.entity_count > 5
              ? 'Top 5 for the period. Other tables are shown separately with their own scale. '
              : ''}
            Observed reads and UC accesses; one SQL query may reference multiple tables.
          </>
        }
      >
        <UcUsageTableTimeChart
          series={data.series}
          ariaLabel="Daily reads by table"
          unit="Read accesses / day"
          formatValue={accesses}
        />
      </UcUsageChartCard>
      <UcUsageChartCard
        title={consumerRanking ? 'Top consumers of this table' : 'Most read tables'}
        subtitle="Where is usage concentrated across the period?"
        note={
          consumerRanking
            ? 'Consumers ranked within the selected table.'
            : `${data.ranking.length} tables shown out of ${formatNumber(data.summary.entity_count)} observed · ${formatPct(data.summary.top_10_share_pct, 1)} of accesses.`
        }
      >
        <Ranking
          rows={consumerRanking ? data.single_table_consumers : data.ranking}
          ariaLabel="Usage ranking"
        />
      </UcUsageChartCard>
      <UcUsageChartCard
        wide
        title="Usage regularity"
        subtitle="Is usage daily, occasional or concentrated on particular days?"
        note={`The ${data.activity.rows.length} most read tables · granularity ${data.activity.grain === 'week' ? 'weekly, restricted to the selected period' : 'daily'}. Each table uses its own colour scale by default; a shared scale is available.`}
      >
        <UcUsageActivityHeatmap activity={data.activity} />
      </UcUsageChartCard>
    </div>
  );
}

export function UcUsageConsumerChartsPanel(props: ChartState<UcUsageConsumerCharts>) {
  const { data, loading, error } = props;
  if (loading || error || !data) return <UcUsageChartStatus {...props} />;
  const previousAvailable = data.active_consumers.some((point) => point.previous_value != null);
  return (
    <div className={grid}>
      <UcUsageChartCard
        title="Usage by consumer type"
        subtitle="Which consumer types drive daily activity?"
        note={`${formatNumber(data.total_requests)} observed accesses to the tables in scope. Colours identify consumer types.`}
      >
        <UcUsageTimeChart
          series={data.by_type.map((entry) => ({
            ...entry,
            legendDetail: formatPct(entry.share_pct, 1),
          }))}
          variant="stacked"
          ariaLabel="Daily accesses by consumer type"
          unit="Read accesses / day"
          formatValue={accesses}
        />
      </UcUsageChartCard>
      <UcUsageChartCard
        title="Top consumers"
        subtitle="Who uses the selected tables most?"
        note="Top 10 by read accesses. Distinct tables are counted across the entire selected period."
      >
        <Ranking rows={data.ranking} ariaLabel="Top consumers" />
      </UcUsageChartCard>
      <UcUsageChartCard
        wide
        title="Daily active consumers"
        subtitle="Is usage reaching more consumers?"
        note={
          <>
            A consumer counts once per day in its cloud, even when accessing multiple tables.{' '}
            {previousAvailable
              ? `Comparison: ${data.previous_period.start} → ${data.previous_period.end}. The dashed line represents observations from the previous period.`
              : 'No observations available for the previous period.'}
          </>
        }
      >
        <UcUsageTimeChart
          ariaLabel="Active consumers: selected and previous periods"
          unit="Distinct consumers / day"
          formatValue={formatNumber}
          series={[
            {
              key: 'current',
              label: 'Selected period',
              color: 'var(--tdf-blue)',
              points: data.active_consumers,
            },
            ...(previousAvailable
              ? [
                  {
                    key: 'previous',
                    label: 'Previous period',
                    color: 'var(--tdf-grey)',
                    dashed: true,
                    points: data.active_consumers.map((point) => ({
                      date: point.date,
                      value: point.previous_value,
                    })),
                    details: Object.fromEntries(
                      data.active_consumers.map((point) => [
                        point.date,
                        `Observed on ${ucUsageShortDate(point.previous_date)}`,
                      ])
                    ),
                  },
                ]
              : []),
          ]}
        />
      </UcUsageChartCard>
    </div>
  );
}

function attributionLabel(value: string | null): string {
  const labels: Record<string, string> = {
    equal_parts_fallback: 'equal allocation across referenced objects',
    warehouse_prorata: 'prorated warehouse billing',
    cluster_prorata: 'prorated cluster billing',
    serverless_job_prorata: 'prorated serverless job billing',
    mixed: 'multiple allocation methods or billing bases',
  };
  return value == null ? 'unknown' : (labels[value] ?? value);
}

export function UcUsageFinopsChartsPanel(props: ChartState<UcUsageFinopsCharts>) {
  const { data, loading, error } = props;
  if (loading || error || !data) return <UcUsageChartStatus {...props} />;
  return (
    <div className={grid}>
      <UcUsageChartCard
        title="Daily cost by table"
        subtitle="Which tables explain changes in attributed cost?"
        note={
          <>
            {data.summary.entity_count > 5
              ? 'Top 5 for the period. Other tables are shown separately with their own scale. '
              : ''}
            Observed estimated costs. Attribution: {attributionLabel(data.cost_attribution_method)}.
            Base : {attributionLabel(data.cost_basis)}.
          </>
        }
      >
        <UcUsageTableTimeChart
          series={data.series}
          ariaLabel="Daily cost by table"
          unit="USD / day"
          formatValue={formatUsd}
        />
      </UcUsageChartCard>
      <UcUsageChartCard
        title="Cost concentration"
        subtitle="Which tables account for most of the known cost?"
        note={`${data.summary.unmeasured_entity_count} table(s) without attributed cost. Shares use known costs.`}
      >
        <Ranking rows={data.ranking} cost ariaLabel="Tables ranked by estimated cost" />
        {data.summary.total != null ? (
          <ComputeStackedBar
            className="mt-5"
            ariaLabel="Cost split between the top 5 and other tables"
            segments={[
              {
                key: 'top',
                label: 'Top 5',
                value: data.summary.top_5_total,
                valueLabel: `${formatUsd(data.summary.top_5_total)} · ${formatPct(data.summary.top_5_share_pct, 1)}`,
                color: 'var(--tdf-blue)',
              },
              ...(data.summary.entity_count > 5
                ? [
                    {
                      key: 'other',
                      label: 'Other',
                      value: data.summary.other_total,
                      valueLabel: formatUsd(data.summary.other_total),
                      color: 'var(--tdf-grey)',
                    },
                  ]
                : []),
            ]}
          />
        ) : null}
      </UcUsageChartCard>
      <UcUsageChartCard
        wide
        title="Cost per 1,000 costed accesses"
        subtitle="Does cost change at the same pace as usage?"
        note={
          <>
            Attribution coverage:{' '}
            <strong className="font-semibold text-foreground">
              {formatPct(data.cost_coverage_pct, 1)}
            </strong>{' '}
            of accesses. Only accesses with attributed cost enter the denominator; changing coverage
            can affect comparisons.
          </>
        }
      >
        <UcUsageTimeChart
          ariaLabel="Cost per 1,000 costed accesses"
          unit="USD / 1,000 costed accesses"
          formatValue={(value) => formatUsd(value, 4)}
          series={[
            {
              key: 'unit-cost',
              label: 'Cost per 1,000 costed accesses',
              color: 'var(--tdf-teal)',
              points: data.unit_cost,
              details: Object.fromEntries(
                data.unit_cost.map((point) => [
                  point.date,
                  `${formatNumber(point.costed_request_count)} costed accesses / ${formatNumber(point.request_count)} accesses · coverage ${formatPct(point.coverage_pct, 1)} · ${attributionLabel(point.cost_basis)}`,
                ])
              ),
            },
          ]}
        />
      </UcUsageChartCard>
    </div>
  );
}
