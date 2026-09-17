import { categoricalFill } from '../../components/domain/compute/compute-chart-colors';
import { formatUsd } from './format';

/**
 * The serverless surface vocabulary, in the order the backend enum declares it.
 *
 * The order is a contract, not a presentation choice: a surface's colour is its
 * **index here**, so filtering one out or reordering a chart cannot repaint the
 * survivors (spec 025 FR-028). Anything read from gold that is not in this list is
 * still rendered — as itself, in the fallback colour — rather than dropped: a
 * thirteenth surface appearing in billing is news, not a bug to hide.
 */
export const SERVERLESS_SURFACES = [
  'JOB',
  'DLT_PIPELINE',
  'MV_ST_REFRESH',
  'SQL_WAREHOUSE',
  'NOTEBOOK',
  'APP',
  'AI_ENDPOINT',
  'LAKEBASE',
  'GENIE',
  'NETWORKING',
  'PLATFORM_AUTO',
  'OTHER',
] as const;

export type ServerlessSurface = (typeof SERVERLESS_SURFACES)[number];

/**
 * The residual bucket of the cost trend — **not** a surface.
 *
 * Named with the suffix by the API precisely because `OTHER` is itself one of the
 * twelve, and a bucket named after it would be indistinguishable from it.
 */
export const SERVERLESS_OTHER_SURFACES_BUCKET = 'OTHER_SURFACES';

const SURFACE_LABELS: Record<ServerlessSurface, string> = {
  JOB: 'Jobs',
  DLT_PIPELINE: 'DLT pipelines',
  MV_ST_REFRESH: 'MV / ST refresh',
  SQL_WAREHOUSE: 'SQL warehouses',
  NOTEBOOK: 'Notebooks',
  APP: 'Apps',
  AI_ENDPOINT: 'AI endpoints',
  LAKEBASE: 'Lakebase',
  GENIE: 'Genie',
  NETWORKING: 'Networking',
  PLATFORM_AUTO: 'Platform (automatic)',
  OTHER: 'Other',
};

/**
 * Surfaces billed at **workspace** grain: gold has nothing listable for them, so every
 * row carries `object_id: null` and `has_object_key: false`.
 *
 * They are not a defect to fix — Databricks bills them to the workspace, not to an
 * object — so their tab announces the grain and shows no object column instead of a
 * column of dashes (025 SC-008).
 */
const WORKSPACE_GRAIN_SURFACES = new Set<string>(['GENIE', 'NETWORKING', 'PLATFORM_AUTO', 'OTHER']);

/**
 * The three surfaces that count executions. Everywhere else `run_count` is `null` —
 * never `0` — because the surface does not report runs at all: a warehouse is billed for
 * being up, an app for being served, Genie to the workspace.
 *
 * Used to decide whether the runs and `$`/run **columns exist**, not to decide what to
 * print in them: a column of dashes claims the metric was measured and came back empty
 * (025 SC-016).
 */
const RUN_COUNTING_SURFACES = new Set<string>(['JOB', 'DLT_PIPELINE', 'MV_ST_REFRESH']);

export function isServerlessSurface(value: string): value is ServerlessSurface {
  return (SERVERLESS_SURFACES as readonly string[]).includes(value);
}

/** Human label of a surface, or the raw value when gold sends an unknown one. */
export function serverlessSurfaceLabel(value: string | null | undefined): string {
  if (!value) return '—';
  if (value === SERVERLESS_OTHER_SURFACES_BUCKET) return 'Other surfaces';
  return isServerlessSurface(value) ? SURFACE_LABELS[value] : value;
}

/**
 * `true` when the surface bills the workspace rather than an object.
 *
 * Read from the vocabulary and not from the rows: a page of rows that all happen to
 * lack an object key does not prove the surface has none, and the answer must be the
 * same on an empty page.
 */
export function isWorkspaceGrainSurface(value: string | null | undefined): boolean {
  return value != null && WORKSPACE_GRAIN_SURFACES.has(value);
}

/**
 * `true` when the surface reports executions, and therefore when a runs or `$`/run
 * column has something to be about.
 *
 * Read from the vocabulary rather than from the rows, for the same reason as
 * `isWorkspaceGrainSurface`: a page whose rows all carry `run_count: null` does not
 * prove the surface counts none, and the answer must be the same on an empty page.
 */
export function countsRuns(value: string | null | undefined): boolean {
  return value != null && RUN_COUNTING_SURFACES.has(value);
}

/**
 * Palette slot of each surface — written out rather than derived from the array index.
 *
 * The mapping is what pins a colour to an entity (FR-028): a surface keeps its fill
 * across windows, filters and refreshes, and folding one series out cannot repaint the
 * others. Two slots are chosen and not arbitrary: `OTHER` takes the muted grey, because
 * grey is what "everything else" looks like, and `PLATFORM_AUTO` takes the solid grey
 * for the same reason — automatic platform spend is nobody's object.
 */
const SURFACE_COLOR_SLOT: Record<ServerlessSurface, number> = {
  JOB: 0,
  DLT_PIPELINE: 1,
  SQL_WAREHOUSE: 2,
  NOTEBOOK: 3,
  APP: 4,
  PLATFORM_AUTO: 5,
  MV_ST_REFRESH: 7,
  AI_ENDPOINT: 8,
  LAKEBASE: 9,
  GENIE: 10,
  NETWORKING: 6,
  OTHER: 11,
};

/**
 * Fill of the trend's residual bucket — deliberately **outside** the categorical
 * palette.
 *
 * `OTHER_SURFACES` is not an entity: it is whatever fell below the API's top-N cut, so
 * its membership changes with the window while a palette slot is supposed to mean one
 * thing forever. A neutral derived from `--foreground` also cannot collide with a real
 * surface, which twelve surfaces plus a bucket in a twelve-fill palette otherwise would.
 */
const RESIDUAL_FILL = 'color-mix(in oklch, var(--foreground) 35%, var(--card-background))';

/** The fill pinned to a surface, or the neutral of the residual bucket. */
export function serverlessSurfaceColor(value: string): string {
  if (value === SERVERLESS_OTHER_SURFACES_BUCKET) return RESIDUAL_FILL;
  // An unknown surface reads as residual rather than borrowing a pinned slot: it is
  // shown, named by its raw value, and no existing surface changes colour.
  return isServerlessSurface(value) ? categoricalFill(SURFACE_COLOR_SLOT[value]) : RESIDUAL_FILL;
}

/**
 * `performance_target` labels. `null` is a **fourth** value and not missing data, so it
 * reads "Unset" — the bucket that carries most of the dollars, and therefore the lever.
 */
export function performanceTargetLabel(value: string | null | undefined): string {
  if (value == null || value === 'NULL') return 'Unset';
  if (value === 'PERFORMANCE_OPTIMIZED') return 'Performance optimized';
  if (value === 'STANDARD') return 'Standard';
  if (value === 'MIXED') return 'Mixed';
  return value;
}

/** `CLASSIC_COMPUTE` / `SERVERLESS_COMPUTE`, as they appear in the DLT comparison. */
export function dltComputeTypeLabel(value: string | null | undefined): string {
  if (value === 'SERVERLESS_COMPUTE') return 'Serverless';
  if (value === 'CLASSIC_COMPUTE') return 'Classic';
  return value ?? '—';
}

/**
 * Label of one `$`/run histogram band, read from the bounds the API sends.
 *
 * The bands are quasi-logarithmic because the distribution is: the last one is
 * open-ended and reads `> $50`, since a closed label there would invent a ceiling the
 * server never gave — and it is exactly the band that carries the tail.
 */
export function costPerRunBucketLabel(bucket: { from_usd: number; to_usd: number | null }): string {
  const from = formatUsd(bucket.from_usd);
  if (bucket.to_usd == null) return `> ${from}`;
  return `${from} – ${formatUsd(bucket.to_usd)}`;
}

/**
 * `true` when a percentile falls in this band — how p50 and p99 get annotated on the
 * histogram rather than quoted beside it.
 *
 * Half-open `[from, to)`, so a value sitting exactly on a boundary is annotated once and
 * not twice. The open-ended last band takes everything above its floor.
 */
export function costPerRunBucketContains(
  bucket: { from_usd: number; to_usd: number | null },
  value: number | null | undefined
): boolean {
  if (value == null || Number.isNaN(Number(value))) return false;
  if (value < bucket.from_usd) return false;
  return bucket.to_usd == null || value < bucket.to_usd;
}
