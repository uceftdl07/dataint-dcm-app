import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { DollarSign, RefreshCw, ShieldCheck, TrendingUp, UserX } from 'lucide-react';
import type {
  ComputeServerlessGovernanceParams,
  ComputeServerlessObjectsSort,
} from '../api/dcmApiClient';
import { categoricalFill } from '../components/domain/compute/compute-chart-colors';
import { COLUMN_WIDTH } from '../components/domain/compute/compute-column-widths';
import {
  ComputeCoverageHeatmap,
  type ComputeCoverageCell,
  type ComputeCoverageColumn,
  type ComputeCoverageRow,
} from '../components/domain/compute/compute-coverage-heatmap';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
} from '../components/domain/compute/compute-data-table';
import { ComputeEmptyState } from '../components/domain/compute/compute-empty-state';
import { ComputeInfoTip } from '../components/domain/compute/compute-info-tip';
import { ComputeKpiCard } from '../components/domain/compute/compute-kpi-card';
import {
  ComputeRankedBars,
  type ComputeRankedItem,
} from '../components/domain/compute/compute-ranked-bars';
import { ComputeServerlessDrawer } from '../components/domain/compute/compute-serverless-drawer';
import {
  ComputeStackedBar,
  ComputeStackedColumns,
  type ComputeStackedColumn,
  type ComputeStackedSegment,
  type ComputeStackedSeries,
} from '../components/domain/compute/compute-stacked-bar';
import { Content, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import {
  useComputeServerlessCostTrend,
  useComputeServerlessGovernance,
  useComputeServerlessLevers,
  useComputeServerlessObjectCostTrend,
  useComputeServerlessObjectDetail,
  useComputeServerlessObjects,
  useComputeServerlessOverview,
  useComputeServerlessSurfaces,
} from '../hooks/useComputeServerlessQueries';
import { useWorkspaceLabelResolver } from '../hooks/useWorkspaceLabelResolver';
import {
  computeServerlessFieldDescriptions,
  computeServerlessKpiDescriptions,
} from '../lib/compute/field-descriptions';
import {
  formatDeltaPct,
  formatNumber,
  formatPct,
  formatUsd,
  lastNDaysPeriodIso,
} from '../lib/compute/format';
import { serverPaginationProps } from '../lib/compute/server-pagination';
import {
  countsRuns,
  dltComputeTypeLabel,
  isWorkspaceGrainSurface,
  performanceTargetLabel,
  serverlessSurfaceColor,
  serverlessSurfaceLabel,
  SERVERLESS_OTHER_SURFACES_BUCKET,
  SERVERLESS_SURFACES,
} from '../lib/compute/serverless-surfaces';
import { cn } from '../lib/utils';
import type {
  ComputeClusterWindow,
  ComputeColumnFilterValues,
  ComputeJobWindowDays,
  ComputeMetricsOptionalPeriodRange,
  ComputeMetricTrendGranularity,
  ComputeServerlessDltComparisonItem,
  ComputeServerlessGovernanceItem,
  ComputeServerlessObjectItem,
  ComputeServerlessPerformanceTargetItem,
} from '../types/api';

const PAGE_SIZE = 25;

/**
 * The governance snapshot read a **second** time, unfiltered and unpaged, for the
 * coverage matrix and for the denominator of the "no owner" share.
 *
 * 200 is the server's own `page_size` ceiling, so a perimeter wider than that is
 * reported as truncated rather than quietly presented as the whole. The rollup sums
 * **dollars** and never averages per-row percentages: the average of percentages is
 * not the percentage of the whole.
 */
const GOVERNANCE_ROLLUP_PAGE_SIZE = 200;

/** Days of history the framing trend and the drawer trend cover. */
const TREND_DAYS = 30;

/**
 * Ceiling of categorical series in the daily stack, residual bucket excluded.
 *
 * The API already folds everything below its own top-N into `OTHER_SURFACES`; this cap
 * is what keeps the form rule ("7–8 categorical series, then a residual") true even if
 * the server later widens `series`.
 */
const TREND_SERIES_CEILING = 7;

/** How many notebook consumers the concentration ranking lists. */
const TOP_NOTEBOOK_CONSUMERS = 10;

/** Sort keys the governance endpoint allowlists — anything else is ignored. */
const GOVERNANCE_SORTS = [
  'cost',
  'workspace',
  'surface',
  'owner_tag',
  'cost_center_tag',
  'budget_policy',
  'identity',
] as const;

type GovernanceSort = NonNullable<ComputeServerlessGovernanceParams['sort']>;

/** Sort keys the objects endpoint allowlists — `surface` excluded, the tabs own it. */
const OBJECT_SORTS = [
  'cost',
  'object',
  'workspace',
  'dbu',
  'runs',
  'cost_per_run',
  'delta',
] as const;

const NO_FILTERS: ComputeColumnFilterValues = {};

/**
 * The four windows materialized in gold, as on the other compute pages. 30 days is the
 * default here and not `1`: every figure this page frames — coverage, percentiles, the
 * DLT comparison — is noise over a single day.
 */
const ROLLING_WINDOWS: { value: ComputeJobWindowDays; label: string }[] = [
  { value: 1, label: 'Daily' },
  { value: 7, label: 'Last 7d' },
  { value: 30, label: 'Last 30d' },
  { value: 90, label: 'Last 90d' },
];

/** The covered window as reported by the API — read from the response, never recomputed. */
function coveredPeriodLabel(window: ComputeClusterWindow | null | undefined): string {
  if (!window?.from_date || !window?.to_date) return '—';
  return `${window.from_date} → ${window.to_date}`;
}

/** The governance snapshot's own span, which is **not** the selected window. */
function governancePeriodLabel(
  period: ComputeMetricsOptionalPeriodRange | null | undefined
): string {
  if (!period?.from || !period?.to) return '—';
  return `${period.from} → ${period.to}`;
}

/** Exclusive chip group for the rolling window. */
function WindowChipGroup({
  options,
  value,
  onChange,
}: {
  options: { value: ComputeJobWindowDays; label: string }[];
  value: ComputeJobWindowDays;
  onChange: (next: ComputeJobWindowDays) => void;
}) {
  return (
    <div
      className="flex shrink-0 items-center gap-0.5 rounded-full border border-border bg-muted/30 p-0.5"
      role="group"
      aria-label="Rolling window"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-full px-3 py-1.5 text-xs font-bold transition-colors',
            value === option.value
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-card hover:text-foreground'
          )}
          aria-pressed={value === option.value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** One of the five blocks: a heading, a lead sentence, and its content. */
function Block({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4">
      <div>
        <h2 id={id} className="text-base font-extrabold tracking-tight text-foreground">
          {title}
        </h2>
        <p className="mt-1 max-w-4xl text-xs leading-relaxed text-muted-foreground">{lead}</p>
      </div>
      {children}
    </section>
  );
}

/** Card wrapper for a chart or a small table inside a block. */
function Panel({
  title,
  description,
  footnote,
  className,
  children,
}: {
  title: string;
  description?: string;
  footnote?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        'rounded-[var(--card-radius)] border border-border bg-card px-4 py-4 shadow-[var(--card-shadow)]',
        className
      )}
    >
      <div className="mb-3 flex items-center gap-1.5">
        <h3 className="text-[11px] font-black uppercase tracking-[1.2px] text-muted-foreground">
          {title}
        </h3>
        {description ? <ComputeInfoTip description={description} /> : null}
      </div>
      {children}
      {footnote ? (
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">{footnote}</p>
      ) : null}
    </div>
  );
}

/** A stated absence: the block exists, the measurement does not. */
function NotMeasurable({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
      {children}
    </p>
  );
}

/** The identity of a serverless object: its name, with the id below and as fallback. */
function ObjectCell({ item }: { item: ComputeServerlessObjectItem }) {
  return (
    <div className="min-w-0">
      <div className="truncate font-semibold text-foreground">
        {item.object_name || item.object_id || '—'}
      </div>
      {item.object_id ? (
        <div className="truncate font-mono text-[10px] text-muted-foreground">{item.object_id}</div>
      ) : null}
    </div>
  );
}

/**
 * The four dimensions of the coverage matrix.
 *
 * Owner tag and cost centre are *tags*; budget policy and identity are not — they are
 * grouped in one matrix because the question is the same one (is this dollar
 * chargeable?), and each cell says which population it was measured on.
 */
const COVERAGE_DIMENSIONS = ['owner_tag', 'cost_center_tag', 'budget_policy', 'identity'] as const;
type CoverageDimension = (typeof COVERAGE_DIMENSIONS)[number];

const COVERAGE_COLUMNS: ComputeCoverageColumn[] = [
  {
    key: 'owner_tag',
    label: 'Owner tag',
    description: computeServerlessFieldDescriptions.ownerTagCoverage,
  },
  {
    key: 'cost_center_tag',
    label: 'Cost center',
    description: computeServerlessFieldDescriptions.costCenterTagCoverage,
  },
  {
    key: 'budget_policy',
    label: 'Budget policy',
    description: computeServerlessFieldDescriptions.budgetPolicy,
  },
  {
    key: 'identity',
    label: 'Identity',
    description: computeServerlessFieldDescriptions.identity,
  },
];

/**
 * Dollars **covered** for one dimension, or `null` when the row does not measure it.
 *
 * Identity is served as its complement (`cost_usd_without_identity`) and comes with its
 * own coverage percentage; when that percentage is `null` — Genie, whose spend has no
 * principal to resolve — the row is unmeasurable and must not be folded in as 0 %.
 */
function coveredDollars(
  item: ComputeServerlessGovernanceItem,
  dimension: CoverageDimension
): number | null {
  switch (dimension) {
    case 'owner_tag':
      return item.cost_usd_with_owner_tag;
    case 'cost_center_tag':
      return item.cost_usd_with_cost_center_tag;
    case 'budget_policy':
      return item.cost_usd_with_budget_policy;
    case 'identity':
      if (item.identity_coverage_pct == null || item.cost_usd_without_identity == null) return null;
      return Math.max((item.cost_usd ?? 0) - item.cost_usd_without_identity, 0);
  }
}

type CoverageAccumulator = { measured: number; covered: number; unmeasured: number };

function emptyCoverage(): Record<CoverageDimension, CoverageAccumulator> {
  return {
    owner_tag: { measured: 0, covered: 0, unmeasured: 0 },
    cost_center_tag: { measured: 0, covered: 0, unmeasured: 0 },
    budget_policy: { measured: 0, covered: 0, unmeasured: 0 },
    identity: { measured: 0, covered: 0, unmeasured: 0 },
  };
}

function coverageCell(accumulator: CoverageAccumulator): ComputeCoverageCell {
  const pct = accumulator.measured > 0 ? (accumulator.covered / accumulator.measured) * 100 : null;
  const measured = `${formatUsd(accumulator.covered)} of ${formatUsd(accumulator.measured)} covered`;
  return {
    pct,
    tooltip:
      accumulator.unmeasured > 0
        ? `${measured} · ${formatUsd(accumulator.unmeasured)} not measurable`
        : measured,
  };
}

export default function ComputeServerless() {
  const { scope } = useMonitoringScope();
  const { resolveWithId } = useWorkspaceLabelResolver(true);

  const [windowDays, setWindowDays] = useState<ComputeJobWindowDays>(30);

  const [governanceSort, setGovernanceSort] = useState<GovernanceSort>('cost');
  const [governanceDirection, setGovernanceDirection] = useState<'asc' | 'desc'>('desc');
  const [governancePage, setGovernancePage] = useState(1);
  const [governanceFilters, setGovernanceFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);

  const [surfaceTab, setSurfaceTab] = useState<string | null>(null);
  const [objectSort, setObjectSort] = useState<ComputeServerlessObjectsSort>('cost');
  const [objectDirection, setObjectDirection] = useState<'asc' | 'desc'>('desc');
  const [objectPage, setObjectPage] = useState(1);
  const [objectFilters, setObjectFilters] = useState<ComputeColumnFilterValues>(NO_FILTERS);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');

  // The drawer is keyed on the (surface, id) pair — the same id is billed under two
  // surfaces for a handful of objects — and carries its own title so the header stays
  // readable while the detail request is in flight.
  const [selectedObject, setSelectedObject] = useState<{
    id: string;
    surface: string;
    title: string;
  } | null>(null);
  const [drawerGranularity, setDrawerGranularity] = useState<ComputeMetricTrendGranularity>('day');

  useEffect(() => {
    const t = window.setTimeout(() => {
      setSearch(searchInput.trim());
      // The page is cut server-side: a narrower search can leave page 7 empty.
      setObjectPage(1);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput]);

  // Another window, another surface, another sort is another population: page 7 of the
  // daily window may not exist over 90 days, and the reverse.
  useEffect(() => {
    setObjectPage(1);
  }, [windowDays, surfaceTab, objectSort, objectDirection]);

  useEffect(() => {
    setGovernancePage(1);
  }, [governanceSort, governanceDirection]);

  const overview = useComputeServerlessOverview(windowDays);
  const surfaces = useComputeServerlessSurfaces({ window_days: windowDays });
  const levers = useComputeServerlessLevers(windowDays);

  // Frozen at mount: a range recomputed each render would churn the trend cache keys
  // without changing the data.
  const trendPeriod = useMemo(() => lastNDaysPeriodIso(TREND_DAYS), []);
  const costTrend = useComputeServerlessCostTrend({ ...trendPeriod, granularity: 'day' });

  const governanceRollup = useComputeServerlessGovernance({
    pageSize: GOVERNANCE_ROLLUP_PAGE_SIZE,
  });
  const governance = useComputeServerlessGovernance({
    sort: governanceSort,
    sortDirection: governanceDirection,
    page: governancePage,
    pageSize: PAGE_SIZE,
    filters: governanceFilters,
  });

  const objects = useComputeServerlessObjects({
    window_days: windowDays,
    surface: surfaceTab ?? undefined,
    search,
    sort: objectSort,
    sortDirection: objectDirection,
    page: objectPage,
    pageSize: PAGE_SIZE,
    filters: objectFilters,
    enabled: Boolean(surfaceTab),
  });

  // The notebook ranking is its own read: it is a top-10 by cost over the whole notebook
  // population, not the page the tabs happen to be showing.
  const notebookConsumers = useComputeServerlessObjects({
    window_days: windowDays,
    surface: 'NOTEBOOK',
    sort: 'cost',
    sortDirection: 'desc',
    pageSize: TOP_NOTEBOOK_CONSUMERS,
  });

  const objectDetail = useComputeServerlessObjectDetail(
    selectedObject?.id ?? null,
    selectedObject?.surface ?? null,
    windowDays
  );
  const objectTrend = useComputeServerlessObjectCostTrend({
    objectId: selectedObject?.id ?? null,
    surface: selectedObject?.surface ?? null,
    granularity: drawerGranularity,
    ...trendPeriod,
  });

  const kpis = overview.data?.kpis ?? null;
  const share = kpis?.serverless_share ?? null;
  const coveredPeriod = coveredPeriodLabel(overview.data?.window);
  const governanceSpan = governancePeriodLabel(
    overview.data?.governance_period ?? governance.data?.governance_period
  );

  /**
   * The share bar carries exactly **two** segments, because `serverless_share.pct` is
   * `serverless / (serverless + classic)`. A third segment for the unclassified
   * warehouse dollars would draw a bar that contradicts the percentage printed on it,
   * so those dollars are stated in the footnote instead.
   */
  const shareSegments: ComputeStackedSegment[] = useMemo(() => {
    if (!share) return [];
    const classicPct = share.pct == null ? null : Math.max(100 - share.pct, 0);
    return [
      {
        key: 'SERVERLESS',
        label: 'Serverless',
        value: share.serverless_cost_usd,
        valueLabel: `${formatUsd(share.serverless_cost_usd)} · ${formatPct(share.pct, 1)}`,
        color: categoricalFill(0),
      },
      {
        key: 'CLASSIC',
        label: 'Classic',
        value: share.classic_cost_usd,
        valueLabel: `${formatUsd(share.classic_cost_usd)} · ${formatPct(classicPct, 1)}`,
        color: categoricalFill(5),
      },
    ];
  }, [share]);

  const surfaceItems = useMemo(() => surfaces.data?.items ?? [], [surfaces.data?.items]);

  const surfaceRanking: ComputeRankedItem[] = useMemo(
    () =>
      surfaceItems.map((item) => {
        const grain = isWorkspaceGrainSurface(item.serverless_surface)
          ? 'workspace grain'
          : `${formatNumber(item.object_count)} objects`;
        const runs = countsRuns(item.serverless_surface)
          ? `${formatNumber(item.run_count)} runs`
          : 'no runs counted';
        return {
          key: item.serverless_surface,
          label: serverlessSurfaceLabel(item.serverless_surface),
          sublabel: `${formatPct(item.share_pct, 1)} of serverless · ${
            item.cost_usd_prev_window == null
              ? 'no comparable window'
              : `${formatDeltaPct(item.cost_delta_pct)} vs previous`
          }`,
          value: item.cost_usd,
          valueLabel: formatUsd(item.cost_usd),
          tooltip: `${serverlessSurfaceLabel(item.serverless_surface)} · ${formatUsd(
            item.cost_usd
          )} · ${formatNumber(item.dbu_quantity)} DBU · ${grain} · ${runs}`,
        };
      }),
    [surfaceItems]
  );

  /**
   * The daily stack, pivoted from the long-format response: the API returns one row per
   * (bucket, surface), and the chart wants one column per bucket.
   *
   * Series beyond the ceiling are folded into the residual bucket rather than dropped —
   * the columns must still add up to the day's spend.
   */
  const { trendSeries, trendColumns } = useMemo(() => {
    const data = costTrend.data;
    if (!data)
      return {
        trendSeries: [] as ComputeStackedSeries[],
        trendColumns: [] as ComputeStackedColumn[],
      };

    const served = data.series.filter((key) => key !== SERVERLESS_OTHER_SURFACES_BUCKET);
    const kept = served.slice(0, TREND_SERIES_CEILING);
    const keptKeys = new Set(kept);

    const perBucket = new Map<string, Record<string, number | null>>();
    const totals = new Map<string, number>();
    let foldedAny = false;

    data.items.forEach((item) => {
      const folded = !keptKeys.has(item.serverless_surface);
      if (folded) foldedAny = true;
      const key = folded ? SERVERLESS_OTHER_SURFACES_BUCKET : item.serverless_surface;
      const values = perBucket.get(item.bucket) ?? {};
      values[key] = (values[key] ?? 0) + item.cost_usd;
      perBucket.set(item.bucket, values);
      totals.set(item.bucket, (totals.get(item.bucket) ?? 0) + item.cost_usd);
    });

    const seriesKeys = foldedAny ? [...kept, SERVERLESS_OTHER_SURFACES_BUCKET] : kept;

    return {
      trendSeries: seriesKeys.map((key) => ({
        key,
        label: serverlessSurfaceLabel(key),
        color: serverlessSurfaceColor(key),
      })),
      trendColumns: [...perBucket.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([label, values]) => ({
          label,
          values,
          tooltip: [
            `${label} · ${formatUsd(totals.get(label) ?? null)}`,
            ...seriesKeys
              .filter((key) => values[key] != null)
              .map((key) => `${serverlessSurfaceLabel(key)} ${formatUsd(values[key])}`),
          ].join(' · '),
        })),
    };
  }, [costTrend.data]);

  /**
   * Coverage per surface, aggregated from the unfiltered governance rollup.
   *
   * Dollars are summed and the percentage derived once, per dimension: averaging the
   * per-workspace percentages of a surface would weight a $12 workspace like a $60k one.
   */
  const coverageRows: ComputeCoverageRow[] = useMemo(() => {
    const items = governanceRollup.data?.items ?? [];
    const bySurface = new Map<
      string,
      { cost: number; dimensions: Record<CoverageDimension, CoverageAccumulator> }
    >();

    items.forEach((item) => {
      const entry = bySurface.get(item.serverless_surface) ?? {
        cost: 0,
        dimensions: emptyCoverage(),
      };
      const cost = item.cost_usd ?? 0;
      entry.cost += cost;
      COVERAGE_DIMENSIONS.forEach((dimension) => {
        const covered = coveredDollars(item, dimension);
        const accumulator = entry.dimensions[dimension];
        if (covered == null) {
          accumulator.unmeasured += cost;
          return;
        }
        accumulator.measured += cost;
        accumulator.covered += covered;
      });
      bySurface.set(item.serverless_surface, entry);
    });

    return [...bySurface.entries()]
      .sort(([, left], [, right]) => right.cost - left.cost)
      .map(([surface, entry]) => ({
        key: surface,
        label: serverlessSurfaceLabel(surface),
        sublabel: formatUsd(entry.cost),
        cells: Object.fromEntries(
          COVERAGE_DIMENSIONS.map((dimension) => [
            dimension,
            coverageCell(entry.dimensions[dimension]),
          ])
        ) as Record<string, ComputeCoverageCell>,
      }));
  }, [governanceRollup.data?.items]);

  const rollupTruncated =
    (governanceRollup.data?.total ?? 0) > (governanceRollup.data?.items.length ?? 0);

  /**
   * Share of the governance snapshot with no resolvable owner.
   *
   * The denominator is the **snapshot's** total, not the window's spend: the numerator
   * is measured over 90 days, and dividing it by 30 days of spend would overstate it.
   */
  const withoutIdentitySharePct = useMemo(() => {
    const dollars = kpis?.cost_usd_without_identity ?? null;
    const total = governanceRollup.data?.totals.cost_usd ?? null;
    if (dollars == null || total == null || total <= 0) return null;
    return (dollars / total) * 100;
  }, [kpis?.cost_usd_without_identity, governanceRollup.data?.totals.cost_usd]);

  const withoutObjectKeySharePct = useMemo(() => {
    const dollars = kpis?.cost_usd_without_object_key ?? null;
    const total = governanceRollup.data?.totals.cost_usd ?? null;
    if (dollars == null || total == null || total <= 0) return null;
    return (dollars / total) * 100;
  }, [kpis?.cost_usd_without_object_key, governanceRollup.data?.totals.cost_usd]);

  /**
   * Notebook consumers, ranked. Deliberately **not** a Pareto with a cumulative curve on
   * a second axis: two axes on one picture make the reader compare a dollar against a
   * percentage, and the concentration figure is stated in the tile beside it instead.
   */
  const notebookRanking: ComputeRankedItem[] = useMemo(
    () =>
      (notebookConsumers.data?.items ?? []).map((item) => ({
        key: `${item.workspace_id}-${item.object_id ?? item.identity_principal ?? 'unknown'}`,
        label: item.object_name || item.object_id || item.identity_principal || '—',
        sublabel: `${resolveWithId(item.workspace_id).label}${
          item.identity_principal ? ` · ${item.identity_principal}` : ''
        }`,
        value: item.cost_usd,
        valueLabel: formatUsd(item.cost_usd),
        tooltip: `${item.object_name || item.object_id || '—'} · ${formatUsd(
          item.cost_usd
        )} · ${formatNumber(item.dbu_quantity)} DBU · ${resolveWithId(item.workspace_id).label}`,
      })),
    [notebookConsumers.data?.items, resolveWithId]
  );

  const notebookConcentration = useMemo(() => {
    const data = notebookConsumers.data;
    if (!data) return null;
    const listed = data.items.reduce<number>((sum, item) => sum + (Number(item.cost_usd) || 0), 0);
    const population = data.object_count ?? data.total;
    if (data.total_cost_usd <= 0) return { listed, population, pct: null };
    return { listed, population, pct: (listed / data.total_cost_usd) * 100 };
  }, [notebookConsumers.data]);

  /**
   * `performance_target` as parts of a whole. The colours are pinned per **value** —
   * unset takes the muted slot, each target its own — so the picture does not repaint
   * when the ranking of the buckets changes between two windows.
   */
  const performanceTargetSegments: ComputeStackedSegment[] = useMemo(() => {
    const items = levers.data?.performance_target.items ?? [];
    const slot: Record<string, number> = {
      UNSET: 5,
      PERFORMANCE_OPTIMIZED: 0,
      STANDARD: 1,
      MIXED: 2,
    };
    return items.map((item) => {
      const key = item.performance_target ?? 'UNSET';
      return {
        key,
        label: performanceTargetLabel(item.performance_target),
        value: item.cost_usd,
        valueLabel: `${formatUsd(item.cost_usd)} · ${formatPct(item.share_pct, 1)}`,
        color: categoricalFill(slot[key] ?? 4),
      };
    });
  }, [levers.data?.performance_target.items]);

  const dltComparison = levers.data?.dlt_comparison ?? null;

  const objectItems = useMemo(() => objects.data?.items ?? [], [objects.data?.items]);

  /**
   * The tabs are the surfaces actually billed, ordered by the **vocabulary** and not by
   * cost: an order that follows the spend would reshuffle the tab strip every time the
   * window changes.
   */
  const surfaceTabs = useMemo(() => {
    const billed = new Set(surfaceItems.map((item) => item.serverless_surface));
    const known = SERVERLESS_SURFACES.filter((surface) => billed.has(surface));
    const unknown = [...billed].filter(
      (surface) => !(SERVERLESS_SURFACES as readonly string[]).includes(surface)
    );
    return [...known, ...unknown.sort()];
  }, [surfaceItems]);

  useEffect(() => {
    if (surfaceTab != null || surfaceTabs.length === 0) return;
    setSurfaceTab(surfaceTabs[0]!);
  }, [surfaceTab, surfaceTabs]);

  const workspaceGrainTab = isWorkspaceGrainSurface(surfaceTab);
  const runCountingTab = countsRuns(surfaceTab);

  const openObject = useCallback((row: ComputeServerlessObjectItem) => {
    // The detail endpoint answers 404 without an object key: a row billed to the
    // workspace has nothing to drill into, so it stays a row.
    if (!row.object_id) return;
    setSelectedObject({
      id: row.object_id,
      surface: row.serverless_surface,
      title: row.object_name || row.object_id,
    });
  }, []);
  const closeObject = useCallback(() => setSelectedObject(null), []);

  const governanceColumns: ComputeDataTableColumn<ComputeServerlessGovernanceItem>[] = useMemo(
    () => [
      {
        id: 'workspace',
        width: COLUMN_WIDTH.name,
        header: 'Workspace',
        description: computeServerlessFieldDescriptions.workspace,
        sortable: true,
        filterKey: 'workspace',
        cell: (row) => (
          <div className="min-w-0">
            <div
              className="truncate font-semibold text-foreground"
              title={`${resolveWithId(row.workspace_id).label} · ${row.workspace_id}`}
            >
              {resolveWithId(row.workspace_id).label}
            </div>
            <div className="truncate text-[10px] uppercase text-muted-foreground">
              {row.cloud_provider}
            </div>
          </div>
        ),
      },
      {
        id: 'surface',
        width: COLUMN_WIDTH.label,
        header: 'Surface',
        description: computeServerlessFieldDescriptions.surface,
        sortable: true,
        filterKey: 'surface',
        cell: (row) => (
          <span className="font-medium">{serverlessSurfaceLabel(row.serverless_surface)}</span>
        ),
      },
      {
        id: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: computeServerlessFieldDescriptions.cost,
        align: 'right',
        sortable: true,
        filterKey: 'cost',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</span>
        ),
      },
      {
        id: 'owner_tag',
        width: COLUMN_WIDTH.metric,
        header: 'Owner tag',
        description: computeServerlessFieldDescriptions.ownerTagCoverage,
        align: 'right',
        sortable: true,
        filterKey: 'owner_tag',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatPct(row.owner_tag_coverage_pct, 1)}
          </span>
        ),
      },
      {
        id: 'cost_center_tag',
        width: COLUMN_WIDTH.metric,
        header: 'Cost center',
        description: computeServerlessFieldDescriptions.costCenterTagCoverage,
        align: 'right',
        sortable: true,
        filterKey: 'cost_center_tag',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatPct(row.cost_center_tag_coverage_pct, 1)}
          </span>
        ),
      },
      {
        id: 'budget_policy',
        width: COLUMN_WIDTH.metric,
        header: 'Budget policy',
        description: computeServerlessFieldDescriptions.budgetPolicy,
        align: 'right',
        sortable: true,
        filterKey: 'budget_policy',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatPct(row.budget_policy_coverage_pct, 1)}
          </span>
        ),
      },
      {
        id: 'policy_count',
        width: COLUMN_WIDTH.number,
        header: 'Policies',
        description: computeServerlessFieldDescriptions.policyCount,
        align: 'right',
        filterKey: 'policy_count',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatNumber(row.budget_policy_count)}
          </span>
        ),
      },
      {
        id: 'identity',
        width: COLUMN_WIDTH.metric,
        header: 'Identity',
        description: computeServerlessFieldDescriptions.identity,
        align: 'right',
        sortable: true,
        filterKey: 'identity',
        cell: (row) => (
          <span className="font-semibold tabular-nums">
            {formatPct(row.identity_coverage_pct, 1)}
          </span>
        ),
      },
      {
        id: 'identity_source',
        width: COLUMN_WIDTH.tag,
        header: 'Identity source',
        description: computeServerlessFieldDescriptions.identitySource,
        cell: (row) =>
          row.identity_source_mix.length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <div className="flex flex-wrap gap-1">
              {row.identity_source_mix.map((source) => (
                <Badge key={source} variant="outline">
                  {source}
                </Badge>
              ))}
            </div>
          ),
      },
    ],
    [resolveWithId]
  );

  const objectColumns: ComputeDataTableColumn<ComputeServerlessObjectItem>[] = useMemo(() => {
    const columns: ComputeDataTableColumn<ComputeServerlessObjectItem>[] = [];

    // A surface billed to the workspace has no object column at all — not a column of
    // dashes, which would claim the object was looked for and not found (025 SC-008).
    if (!workspaceGrainTab) {
      columns.push({
        id: 'object',
        width: COLUMN_WIDTH.name,
        header: 'Object',
        description: computeServerlessFieldDescriptions.object,
        sortable: true,
        filterKey: 'object',
        cell: (row) => <ObjectCell item={row} />,
      });
    }

    columns.push(
      {
        id: 'workspace',
        width: COLUMN_WIDTH.name,
        header: 'Workspace',
        description: computeServerlessFieldDescriptions.workspace,
        sortable: true,
        filterKey: 'workspace',
        cell: (row) => (
          <div className="min-w-0">
            <div
              className="truncate font-semibold text-foreground"
              title={`${resolveWithId(row.workspace_id).label} · ${row.workspace_id}`}
            >
              {resolveWithId(row.workspace_id).label}
            </div>
            <div className="truncate text-[10px] uppercase text-muted-foreground">
              {row.cloud_provider}
            </div>
          </div>
        ),
      },
      {
        id: 'cost',
        width: COLUMN_WIDTH.metric,
        header: 'Cost',
        description: computeServerlessFieldDescriptions.cost,
        align: 'right',
        sortable: true,
        filterKey: 'cost',
        cell: (row) => (
          <div>
            <div className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</div>
            {row.is_top_cost ? <Badge variant="warning">Top</Badge> : null}
          </div>
        ),
      },
      {
        id: 'delta',
        width: COLUMN_WIDTH.metric,
        header: 'Δ vs prev',
        description: computeServerlessFieldDescriptions.costDelta,
        align: 'right',
        sortable: true,
        cell: (row) =>
          row.cost_usd_prev_window == null ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <div>
              <div className="font-semibold tabular-nums">{formatDeltaPct(row.cost_delta_pct)}</div>
              <div className="text-[10px] tabular-nums text-muted-foreground">
                {formatUsd(row.cost_usd_prev_window)}
              </div>
            </div>
          ),
      },
      {
        id: 'dbu',
        width: COLUMN_WIDTH.metric,
        header: 'DBU',
        description: computeServerlessFieldDescriptions.dbu,
        align: 'right',
        sortable: true,
        filterKey: 'dbu',
        cell: (row) => (
          <span className="font-semibold tabular-nums">{formatNumber(row.dbu_quantity)}</span>
        ),
      }
    );

    // Runs and $/run exist only where the surface counts executions. Elsewhere the
    // columns are absent: gold carries no `run_count = 0` there, and a dash would
    // suggest a measurement came back empty.
    if (runCountingTab) {
      columns.push(
        {
          id: 'runs',
          width: COLUMN_WIDTH.metric,
          header: 'Runs',
          description: computeServerlessFieldDescriptions.runs,
          align: 'right',
          sortable: true,
          filterKey: 'runs',
          cell: (row) => (
            <span className="font-semibold tabular-nums">{formatNumber(row.run_count)}</span>
          ),
        },
        {
          id: 'cost_per_run',
          width: COLUMN_WIDTH.metric,
          header: '$/run p50',
          description: computeServerlessFieldDescriptions.costPerRun,
          align: 'right',
          sortable: true,
          filterKey: 'cost_per_run',
          cell: (row) => (
            <div>
              <div className="font-semibold tabular-nums">
                {row.cost_per_run_p50_usd == null ? '—' : formatUsd(row.cost_per_run_p50_usd, 3)}
              </div>
              <div className="text-[10px] tabular-nums text-muted-foreground">
                {row.cost_per_run_p99_usd == null
                  ? '—'
                  : `p99 ${formatUsd(row.cost_per_run_p99_usd, 3)}`}
              </div>
            </div>
          ),
        }
      );
    }

    columns.push(
      {
        id: 'performance_target',
        width: COLUMN_WIDTH.label,
        header: 'Perf. target',
        description: computeServerlessFieldDescriptions.performanceTarget,
        filterKey: 'performance_target',
        cell: (row) => (
          <span className="font-medium">{performanceTargetLabel(row.performance_target)}</span>
        ),
      },
      {
        id: 'budget_policy',
        width: COLUMN_WIDTH.identifier,
        header: 'Budget policy',
        description: computeServerlessFieldDescriptions.budgetPolicy,
        filterKey: 'budget_policy',
        cell: (row) => (
          <span className="truncate font-mono text-[11px]">{row.budget_policy_id ?? '—'}</span>
        ),
      },
      {
        id: 'identity',
        width: COLUMN_WIDTH.tag,
        header: 'Identity',
        description: computeServerlessFieldDescriptions.identity,
        filterKey: 'identity',
        cell: (row) => (
          <div className="min-w-0">
            <div className="truncate font-medium" title={row.identity_principal ?? undefined}>
              {row.identity_principal ?? '—'}
            </div>
            <div className="truncate text-[10px] uppercase text-muted-foreground">
              {row.identity_source ?? '—'}
            </div>
          </div>
        ),
      }
    );

    return columns;
  }, [resolveWithId, runCountingTab, workspaceGrainTab]);

  const performanceTargetColumns: ComputeDataTableColumn<ComputeServerlessPerformanceTargetItem>[] =
    useMemo(
      () => [
        {
          id: 'target',
          width: COLUMN_WIDTH.label,
          header: 'Perf. target',
          description: computeServerlessFieldDescriptions.performanceTarget,
          cell: (row) => (
            <span className="font-semibold">{performanceTargetLabel(row.performance_target)}</span>
          ),
        },
        {
          id: 'cost',
          width: COLUMN_WIDTH.metric,
          header: 'Cost exposed',
          description:
            'Dollars billed under this target over the window. Exposed, not recoverable: both modes bill the same SKU, so the figure is the size of the population to look at, never a saving.',
          align: 'right',
          cell: (row) => (
            <span className="font-semibold tabular-nums">{formatUsd(row.cost_usd)}</span>
          ),
        },
        {
          id: 'share',
          width: COLUMN_WIDTH.number,
          header: 'Share',
          description: 'Share of the window’s serverless dollars carried by this target.',
          align: 'right',
          cell: (row) => (
            <span className="font-semibold tabular-nums">{formatPct(row.share_pct, 1)}</span>
          ),
        },
        {
          id: 'objects',
          width: COLUMN_WIDTH.number,
          header: 'Objects',
          description: 'Distinct objects seen under this target — the population to review.',
          align: 'right',
          cell: (row) => (
            <span className="font-semibold tabular-nums">{formatNumber(row.object_count)}</span>
          ),
        },
        {
          id: 'dbu',
          width: COLUMN_WIDTH.metric,
          header: 'DBU',
          description: computeServerlessFieldDescriptions.dbu,
          align: 'right',
          cell: (row) => (
            <span className="font-semibold tabular-nums">{formatNumber(row.dbu_quantity)}</span>
          ),
        },
        {
          id: 'runs',
          width: COLUMN_WIDTH.metric,
          header: 'Runs',
          description: computeServerlessFieldDescriptions.runs,
          align: 'right',
          cell: (row) => (
            <span className="font-semibold tabular-nums">{formatNumber(row.run_count)}</span>
          ),
        },
      ],
      []
    );

  const handleGovernanceSort = (key: string) => {
    if (!(GOVERNANCE_SORTS as readonly string[]).includes(key)) return;
    setGovernanceDirection(
      key === governanceSort ? (governanceDirection === 'desc' ? 'asc' : 'desc') : 'desc'
    );
    setGovernanceSort(key as GovernanceSort);
  };

  const handleObjectSort = (key: string) => {
    if (!(OBJECT_SORTS as readonly string[]).includes(key)) return;
    setObjectDirection(key === objectSort ? (objectDirection === 'desc' ? 'asc' : 'desc') : 'desc');
    setObjectSort(key as ComputeServerlessObjectsSort);
  };

  const handleObjectFilters = (next: ComputeColumnFilterValues) => {
    setObjectFilters(next);
    setObjectPage(1);
  };

  const handleGovernanceFilters = (next: ComputeColumnFilterValues) => {
    setGovernanceFilters(next);
    setGovernancePage(1);
  };

  const governancePagination = useMemo(
    () =>
      serverPaginationProps(
        governance.data ? { ...governance.data, itemCount: governance.data.items.length } : null,
        governancePage,
        setGovernancePage
      ),
    [governance.data, governancePage]
  );

  const objectPagination = useMemo(
    () =>
      serverPaginationProps(
        objects.data ? { ...objects.data, itemCount: objectItems.length } : null,
        objectPage,
        setObjectPage
      ),
    [objects.data, objectItems.length, objectPage]
  );

  const objectFilterScope = useMemo(() => ({ windowDays }), [windowDays]);
  const windowLabel =
    ROLLING_WINDOWS.find((option) => option.value === windowDays)?.label ?? `${windowDays}d`;

  return (
    <Content className="mx-auto max-w-[1600px] gap-0 p-4 pb-24 lg:px-6 lg:pb-28">
      <ContentHeader>
        <div>
          <ContentTitle>Serverless</ContentTitle>
          <p className="mt-2 text-sm text-muted-foreground">
            Serverless spend across every surface Databricks bills it on — {scope.label}.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            void overview.refetch();
            void surfaces.refetch();
            void costTrend.refetch();
            void governanceRollup.refetch();
            void governance.refetch();
            void levers.refetch();
            void objects.refetch();
          }}
          disabled={overview.fetching}
        >
          <RefreshCw className={overview.fetching ? 'animate-spin' : ''} />
          Refresh
        </Button>
      </ContentHeader>

      <ContentMain className="gap-8">
        <div className="flex flex-wrap items-center gap-3">
          <WindowChipGroup options={ROLLING_WINDOWS} value={windowDays} onChange={setWindowDays} />
          <span className="text-xs text-muted-foreground">
            Covered period{' '}
            <span className="font-mono font-semibold text-foreground">{coveredPeriod}</span>
          </span>
          <span className="text-xs text-muted-foreground">
            Governance snapshot{' '}
            <span className="font-mono font-semibold text-foreground">{governanceSpan}</span>
          </span>
        </div>

        {/* ─── Block 1 — what serverless weighs ─────────────────────────────── */}
        <Block
          id="serverless-framing"
          title="What serverless weighs"
          lead={
            <>
              Serverless is the larger half of the compute bill, and its share is{' '}
              <strong className="font-semibold text-foreground">not</strong> growing: classic spend
              is rising faster over this window. What justifies looking at it is the absolute mass
              that nothing attributes — the dollars below, not a trend.
            </>
          }
        >
          <Panel
            title="Serverless share of compute spend"
            description={computeServerlessKpiDescriptions.serverlessShare}
            footnote={
              share ? (
                <>
                  Two segments and not three: the percentage is{' '}
                  <code>serverless / (serverless + classic)</code>.{' '}
                  {formatUsd(share.unclassified_warehouse_cost_usd)} of warehouse spend is absent
                  from the utilization snapshot — proven neither serverless nor classic — and is
                  therefore in neither segment. Dollars, never DBUs: a serverless DBU and a classic
                  DBU are different units at different prices.
                </>
              ) : null
            }
          >
            {overview.loading && !overview.data ? (
              <Skeleton className="h-16" />
            ) : shareSegments.length > 0 ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-black tabular-nums tracking-tight text-foreground">
                    {formatPct(share?.pct, 1)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    of compute spend is serverless
                  </span>
                </div>
                <ComputeStackedBar
                  segments={shareSegments}
                  ariaLabel="Serverless share of compute spend"
                  height={18}
                />
              </div>
            ) : (
              <NotMeasurable>
                The classic side of the ratio could not be read on this perimeter, so no share is
                published — a serverless-only total would read as 100 %.
              </NotMeasurable>
            )}
          </Panel>

          <div className="grid grid-cols-1 gap-4 overflow-visible sm:grid-cols-2 xl:grid-cols-4">
            {overview.loading && !overview.data ? (
              Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-32" />)
            ) : (
              <>
                <ComputeKpiCard
                  title="Serverless spend"
                  description={computeServerlessKpiDescriptions.serverlessCost}
                  value={formatUsd(kpis?.cost_usd)}
                  subtitle={`${windowLabel} · ${formatNumber(kpis?.dbu_quantity ?? null)} DBU`}
                  tone="info"
                  icon={DollarSign}
                />
                <ComputeKpiCard
                  title="Δ vs previous window"
                  description={computeServerlessKpiDescriptions.costDelta}
                  value={formatDeltaPct(kpis?.cost_delta_pct)}
                  subtitle={
                    kpis?.cost_usd_prev_window == null
                      ? 'No comparable window'
                      : `${formatUsd(kpis.cost_usd_prev_window)} previously`
                  }
                  tone="purple"
                  icon={TrendingUp}
                />
                <ComputeKpiCard
                  title="Spend with no owner"
                  description={computeServerlessKpiDescriptions.costWithoutIdentity}
                  value={formatUsd(kpis?.cost_usd_without_identity)}
                  subtitle={`${formatPct(withoutIdentitySharePct, 1)} of the snapshot · ${governanceSpan}`}
                  tone="warning"
                  icon={UserX}
                />
                <ComputeKpiCard
                  title="Covered by a budget policy"
                  description={computeServerlessKpiDescriptions.budgetPolicyCoverage}
                  value={formatPct(kpis?.budget_policy_coverage_pct, 1)}
                  subtitle={`Whole perimeter · ${governanceSpan}`}
                  tone="success"
                  icon={ShieldCheck}
                />
              </>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Panel
              title="Spend per surface"
              description={computeServerlessFieldDescriptions.surface}
              footnote="Sorted bars on one hue: this is a ranking of magnitudes, and eleven colours would read as eleven kinds of thing."
            >
              {surfaces.loading && !surfaces.data ? (
                <Skeleton className="h-56" />
              ) : surfaceRanking.length > 0 ? (
                <ComputeRankedBars
                  items={surfaceRanking}
                  ariaLabel="Serverless spend per surface"
                  labelWidthClassName="w-44"
                />
              ) : (
                <ComputeEmptyState
                  title="No serverless spend"
                  description="No serverless surface was billed over this window and perimeter."
                />
              )}
            </Panel>

            <Panel
              title={`Daily spend per surface (≈${TREND_DAYS} days)`}
              description="Daily serverless cost split by surface, read from the daily table — so it follows this period and not the window chips."
              footnote={
                trendSeries.some((entry) => entry.key === SERVERLESS_OTHER_SURFACES_BUCKET)
                  ? '“Other surfaces” is the residual of the split, not the OTHER surface: its membership changes with the period, which is why it is drawn in a neutral outside the palette.'
                  : undefined
              }
            >
              {costTrend.loading && !costTrend.data ? (
                <Skeleton className="h-56" />
              ) : trendColumns.length > 0 ? (
                <ComputeStackedColumns
                  series={trendSeries}
                  columns={trendColumns}
                  ariaLabel="Daily serverless spend per surface"
                  height={180}
                />
              ) : (
                <ComputeEmptyState
                  title="No daily spend"
                  description="No daily serverless cost over this period and perimeter."
                />
              )}
            </Panel>
          </div>
        </Block>

        {/* ─── Block 2 — attribution and chargeback ─────────────────────────── */}
        <Block
          id="serverless-attribution"
          title="Attribution and chargeback"
          lead={
            <>
              Everything in this block is measured on the governance snapshot (
              <span className="font-mono">{governanceSpan}</span>), which is wider than the selected
              window and has its own cadence — captioning it with the window would misstate which
              days the coverage was measured on.
            </>
          }
        >
          <Panel
            title="Coverage per surface"
            description="Share of each surface’s dollars that carry an owner tag, a cost centre, a budget policy and a resolvable identity."
            footnote={
              <>
                Percentages are derived from summed dollars, never averaged from the rows: a $12
                workspace would otherwise weigh as much as a $60k one. A cell reads “—” when the
                dimension is not measurable on that surface — Genie spend has no principal to
                resolve — and its tooltip states the dollars left out.
                {rollupTruncated
                  ? ` Rolled up from the first ${formatNumber(
                      governanceRollup.data?.items.length ?? null
                    )} of ${formatNumber(
                      governanceRollup.data?.total ?? null
                    )} snapshot rows: the remainder is not in this matrix.`
                  : ''}
              </>
            }
          >
            {governanceRollup.loading && !governanceRollup.data ? (
              <Skeleton className="h-48" />
            ) : coverageRows.length > 0 ? (
              <ComputeCoverageHeatmap
                rows={coverageRows}
                columns={COVERAGE_COLUMNS}
                ariaLabel="Serverless attribution coverage per surface"
              />
            ) : (
              <ComputeEmptyState
                title="No governance snapshot"
                description="No serverless governance row over this perimeter."
              />
            )}
          </Panel>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Panel
              title="No resolvable owner"
              description={computeServerlessKpiDescriptions.costWithoutIdentity}
            >
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black tabular-nums tracking-tight text-foreground">
                  {formatUsd(kpis?.cost_usd_without_identity)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatPct(withoutIdentitySharePct, 1)} of the snapshot
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                Spend nobody can be charged for: the principal could not be resolved from any of the
                fields that carry one. This is the backlog to work down.
              </p>
            </Panel>

            <Panel
              title="No object key"
              description={computeServerlessKpiDescriptions.costWithoutObjectKey}
            >
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-black tabular-nums tracking-tight text-foreground">
                  {formatUsd(kpis?.cost_usd_without_object_key)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatPct(withoutObjectKeySharePct, 1)} of the snapshot
                </span>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                A different notion, and not a defect: Databricks bills Genie, networking and
                automatic platform activity to the <strong>workspace</strong>. There is no object to
                attach, so there is nothing here to fix — only a grain to know about.
              </p>
            </Panel>
          </div>

          <Panel
            title={`Top ${TOP_NOTEBOOK_CONSUMERS} notebook consumers`}
            description={computeServerlessFieldDescriptions.object}
            footnote="No cumulative curve on a second axis: a dual axis makes the reader compare dollars against a percentage. The concentration figure is written out instead."
          >
            {notebookConsumers.loading && !notebookConsumers.data ? (
              <Skeleton className="h-56" />
            ) : notebookRanking.length > 0 ? (
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start">
                <ComputeRankedBars
                  items={notebookRanking}
                  ariaLabel="Top notebook consumers of serverless spend"
                  className="min-w-0 flex-1"
                  labelWidthClassName="w-52"
                />
                <div className="shrink-0 rounded-[var(--radius)] border border-border bg-muted/20 px-4 py-3 xl:w-64">
                  <div className="text-2xl font-black tabular-nums tracking-tight text-foreground">
                    {formatPct(notebookConcentration?.pct ?? null, 1)}
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                    of notebook spend is carried by these {formatNumber(notebookRanking.length)} of{' '}
                    {formatNumber(notebookConcentration?.population ?? null)} billed notebook
                    objects — {formatUsd(notebookConcentration?.listed ?? null)} of{' '}
                    {formatUsd(notebookConsumers.data?.total_cost_usd ?? null)}.
                  </p>
                </div>
              </div>
            ) : (
              <ComputeEmptyState
                title="No notebook spend"
                description="No serverless notebook cost over this window and perimeter."
              />
            )}
          </Panel>

          <ComputeDataTable
            tableId="compute-serverless-governance"
            columns={governanceColumns}
            rows={governance.data?.items ?? []}
            rowKey={(row) => `${row.cloud_provider}-${row.workspace_id}-${row.serverless_surface}`}
            loading={governance.loading && !governance.data}
            emptyTitle="No governance rows"
            emptyDescription="No serverless governance row over this perimeter."
            sort={{ key: governanceSort, direction: governanceDirection }}
            onSortChange={handleGovernanceSort}
            pagination={governancePagination}
            filterView="serverless-governance"
            filters={governanceFilters}
            onFiltersChange={handleGovernanceFilters}
            minWidthClassName="min-w-[1400px]"
          />
        </Block>

        {/* ─── Block 3 — the levers that exist ──────────────────────────────── */}
        <Block
          id="serverless-levers"
          title="The levers that exist"
          lead={
            <>
              Three measured levers, and no savings figure anywhere: both performance modes bill the
              same SKU, so the overcost of an unset target is a quantity of DBUs and not a price.
              What each block gives is the size of a population to look at.
            </>
          }
        >
          <Panel
            title="Performance target"
            description={computeServerlessFieldDescriptions.performanceTarget}
            footnote={
              <>
                No estimated saving, deliberately: the two modes share the SKU, so the dollars below
                are <strong>exposed</strong>, not recoverable.{' '}
                {levers.data?.performance_target.unset_share_pct == null
                  ? null
                  : `Unset carries ${formatPct(
                      levers.data.performance_target.unset_share_pct,
                      1
                    )} of the window’s serverless dollars, which is why it is shown and not hidden as missing data.`}
              </>
            }
          >
            {levers.loading && !levers.data ? (
              <Skeleton className="h-40" />
            ) : performanceTargetSegments.length > 0 ? (
              <div className="flex flex-col gap-4">
                <ComputeStackedBar
                  segments={performanceTargetSegments}
                  ariaLabel="Serverless spend per performance target"
                  height={18}
                />
                <ComputeDataTable
                  tableId="compute-serverless-performance-target"
                  columns={performanceTargetColumns}
                  rows={levers.data?.performance_target.items ?? []}
                  rowKey={(row) => row.performance_target ?? 'UNSET'}
                  emptyTitle="No performance target"
                  emptyDescription="No serverless spend over this window and perimeter."
                  minWidthClassName="min-w-[900px]"
                />
              </div>
            ) : (
              <NotMeasurable>
                No serverless spend over this window and perimeter, so there is no target
                distribution to show.
              </NotMeasurable>
            )}
          </Panel>

          <Panel
            title="DLT: serverless vs classic"
            description={computeServerlessFieldDescriptions.dltFailureRate}
            footnote={
              dltComparison ? (
                <>
                  A <strong>correlation</strong> over this window, never a promise of a gain:
                  nothing here shows that moving a pipeline changes its outcome, and neither compute
                  form is the more reliable one — the direction of the failure gap reverses between
                  this window and full history. Rates are per <strong>requested</strong> execution,
                  deduplicated by <code>request_id</code> and restricted to the window shown in the
                  caption, and they are labelled per cloud because they differ between clouds. Below{' '}
                  {formatNumber(dltComparison.min_requests)} requests no rate is published at all.
                  The one gap that holds without reserve is <strong>duration</strong>.
                </>
              ) : null
            }
          >
            {levers.loading && !levers.data ? (
              <Skeleton className="h-40" />
            ) : dltComparison && dltComparison.items.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <caption className="pb-2 text-left text-[11px] text-muted-foreground">
                    Per requested execution, over{' '}
                    {dltComparison.window
                      ? `${dltComparison.window.from} → ${dltComparison.window.to}`
                      : windowLabel}{' '}
                    ({windowLabel}) · failure concentration over the top{' '}
                    {formatNumber(dltComparison.top_failing_pipelines)} failing pipelines
                  </caption>
                  <thead>
                    <tr className="border-b border-border/70 text-left text-[10px] font-black uppercase tracking-[1.1px] text-muted-foreground">
                      <th scope="col" className="px-3 py-2">
                        Cloud
                      </th>
                      <th scope="col" className="px-3 py-2">
                        Compute
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Requests
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Failure rate
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Duration p50
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Duration p95
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Pipelines
                      </th>
                      <th scope="col" className="px-3 py-2 text-right">
                        Failure concentration
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {dltComparison.items.map((row: ComputeServerlessDltComparisonItem) => (
                      <tr
                        key={`${row.cloud_provider}-${row.compute_type}`}
                        className="border-b border-border/40 last:border-0"
                      >
                        <th scope="row" className="px-3 py-2 text-left font-semibold uppercase">
                          {row.cloud_provider}
                        </th>
                        <td className="px-3 py-2 font-medium">
                          {dltComputeTypeLabel(row.compute_type)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatNumber(row.requests)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {/* Below the server's own floor no percentage is shown at all —
                              2 failures out of 6 requests is 33.33 %, and printing that
                              would be noise shaped like a metric (025 SC-018). */}
                          {row.comparable && row.failure_rate_pct != null ? (
                            <span className="font-semibold tabular-nums">
                              {formatPct(row.failure_rate_pct, 2)}
                            </span>
                          ) : (
                            <div className="text-[11px] text-muted-foreground">
                              <div className="font-semibold">Comparison not significant</div>
                              <div className="tabular-nums">
                                {formatNumber(row.requests)} requests
                              </div>
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {row.duration_p50_sec == null
                            ? '—'
                            : `${formatNumber(row.duration_p50_sec)} s`}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {row.duration_p95_sec == null
                            ? '—'
                            : `${formatNumber(row.duration_p95_sec)} s`}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatNumber(row.pipeline_count)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {row.comparable ? formatPct(row.failure_concentration_pct, 1) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <NotMeasurable>
                No DLT comparison on this perimeter: the endpoint publishes nothing below its
                request floor, and a rate read off a handful of executions is noise shaped like a
                metric.
              </NotMeasurable>
            )}
          </Panel>

          <NotMeasurable>
            The run and dollar concentrations of the heaviest jobs are not served at this grain: the
            levers endpoint gives the distribution above, not the dollars behind each band. Sort the
            drill-down table below by runs or by $/run to reach the same objects.
          </NotMeasurable>
        </Block>

        {/* ─── Block 4 — drill down per surface ─────────────────────────────── */}
        <Block
          id="serverless-objects"
          title="Drill down per surface"
          lead="One tab per surface actually billed, in the order of the surface vocabulary — not by spend, which would reshuffle the strip on every window change. Each tab shows only the columns its surface has."
        >
          {surfaces.loading && !surfaces.data ? (
            <Skeleton className="h-10 w-96" />
          ) : surfaceTabs.length > 0 ? (
            <Tabs>
              <TabsList aria-label="Serverless surfaces" className="flex-wrap">
                {surfaceTabs.map((surfaceKey) => (
                  <TabsTrigger
                    key={surfaceKey}
                    active={surfaceTab === surfaceKey}
                    onClick={() => setSurfaceTab(surfaceKey)}
                  >
                    {serverlessSurfaceLabel(surfaceKey)}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          ) : null}

          {workspaceGrainTab ? (
            <p className="rounded-[var(--radius)] border border-dashed border-border/80 bg-muted/20 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
              <strong className="font-semibold text-foreground">Billed at workspace grain.</strong>{' '}
              Databricks bills {serverlessSurfaceLabel(surfaceTab)} to the workspace, not to an
              object: these rows carry real cost and no object key, so there is no object column and
              no drill-down — nothing is missing.
            </p>
          ) : null}

          <ComputeDataTable
            tableId="compute-serverless-objects"
            columns={objectColumns}
            rows={objectItems}
            rowKey={(row) =>
              `${row.cloud_provider}-${row.workspace_id}-${row.serverless_surface}-${
                row.object_id ?? 'no-object'
              }`
            }
            loading={objects.loading && !objects.data}
            emptyTitle="No objects"
            emptyDescription="No serverless spend on this surface over the window and perimeter."
            onRowClick={workspaceGrainTab ? undefined : openObject}
            sort={{ key: objectSort, direction: objectDirection }}
            onSortChange={handleObjectSort}
            pagination={objectPagination}
            filterView="serverless-objects"
            filterScope={objectFilterScope}
            filters={objectFilters}
            onFiltersChange={handleObjectFilters}
            minWidthClassName="min-w-[1600px]"
            toolbar={
              <div className="flex flex-wrap items-center gap-3">
                <div className="relative w-full max-w-[280px] shrink-0">
                  <Input
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value)}
                    placeholder="Search object name or id…"
                    className="h-8 rounded-full text-xs"
                    aria-label="Search serverless objects"
                  />
                </div>
                <span className="text-xs text-muted-foreground">
                  {formatNumber(objects.data?.object_count ?? null)} objects ·{' '}
                  {formatUsd(objects.data?.total_cost_usd ?? null)}
                </span>
              </div>
            }
          />
        </Block>

        {/* ─── Block 5 — what this page cannot tell you ─────────────────────── */}
        <Block
          id="serverless-blind-spots"
          title="What this page cannot tell you"
          lead="Stated once here rather than as empty columns everywhere: a dash claims a metric was measured and came back empty, which is not the case for any of the following."
        >
          <div className="rounded-[var(--card-radius)] border border-border bg-card px-4 py-4 shadow-[var(--card-shadow)]">
            <ul className="flex flex-col gap-3 text-xs leading-relaxed text-muted-foreground">
              <li>
                <strong className="font-semibold text-foreground">
                  No CPU, memory or idle time, and no node rightsizing.
                </strong>{' '}
                Those metrics come from <code>node_timeline</code>, which does not exist for
                serverless compute: there is no node to observe. Not a gap to fill later — the
                measurement has no serverless grain at all.
              </li>
              <li>
                <strong className="font-semibold text-foreground">
                  97.1 % of warehouse queries have no identifiable source.
                </strong>{' '}
                <code>query_source</code> attaches a query to a job (89.9 % of the attached ones) or
                to a DLT pipeline (0.7 %), and to nothing at all for the rest — so no per-query
                attribution is offered here rather than one built on 2.9 % of the traffic.
              </li>
              <li>
                <strong className="font-semibold text-foreground">No cost per SQL query.</strong> It
                would come from <code>system.billing.usage.attributed_usage</code>, which is empty
                on this perimeter. The block is not built rather than built on nothing — the day
                that table fills, it becomes measurable.
              </li>
              <li>
                <strong className="font-semibold text-foreground">
                  A column with no serverless equivalent is absent, not empty.
                </strong>{' '}
                Runs and $/run only appear on the three surfaces that count executions, and the
                object column only where an object is billed. A value that does not apply reads “—”,
                never <code>0</code>.
              </li>
            </ul>
          </div>
        </Block>
      </ContentMain>

      <ComputeServerlessDrawer
        open={Boolean(selectedObject)}
        onClose={closeObject}
        title={selectedObject?.title ?? ''}
        surface={selectedObject?.surface ?? null}
        detail={objectDetail.data}
        detailLoading={objectDetail.loading}
        detailError={objectDetail.error}
        trend={objectTrend.data}
        trendLoading={objectTrend.loading}
        trendError={objectTrend.error}
        granularity={drawerGranularity}
        onGranularityChange={setDrawerGranularity}
        resolveWorkspaceLabel={(workspaceId) => resolveWithId(workspaceId).label}
      />
    </Content>
  );
}
