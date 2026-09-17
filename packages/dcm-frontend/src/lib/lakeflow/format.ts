/** Shared Lakeflow Jobs formatters / status colors (maquette tokens). */

export const LAKEFLOW_STATUS_COLOR: Record<string, string> = {
  succeeded: 'var(--success)',
  failed: 'var(--danger)',
  timed_out: 'var(--chart-5, #fe9a00)',
  cancelled: 'var(--tdf-grey, #68707d)',
  running: 'var(--primary)',
  skipped: 'var(--muted)',
};

export function lakeflowStatusColor(status: string | null | undefined): string {
  if (!status) return 'var(--muted)';
  return LAKEFLOW_STATUS_COLOR[status.toLowerCase()] ?? 'var(--muted)';
}

export function lakeflowStatusLabel(status: string | null | undefined): string {
  const s = (status || '').trim().toLowerCase();
  if (!s) return 'Inconnu';
  if (s === 'succeeded') return 'Succès';
  if (s === 'failed') return 'Échec';
  if (s === 'timed_out') return 'Timeout';
  if (s === 'cancelled') return 'Annulé';
  if (s === 'running') return 'En cours';
  if (s === 'skipped') return 'Ignoré';
  return status ?? 'Inconnu';
}

export function formatDurationSeconds(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(Number(seconds))) return '—';
  const s = Math.round(Number(seconds));
  if (s < 0) return '—';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h} h ${m.toString().padStart(2, '0')}`;
  if (m > 0) return `${m} m ${sec.toString().padStart(2, '0')} s`;
  return `${sec} s`;
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(digits).replace('.', ',')} %`;
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '—';
  const diffMs = Date.now() - t;
  const abs = Math.abs(diffMs);
  const mins = Math.round(abs / 60000);
  if (mins < 1) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return `il y a ${days} j`;
}

/**
 * Data freshness label derived from the API `as_of` timestamp (age = now - as_of).
 * Returns null when `as_of` is absent/invalid so callers can hide the banner.
 */
export function formatDataFreshness(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const ageMs = Date.now() - t;
  if (ageMs < 60000) return "données à l'instant";
  const mins = Math.round(ageMs / 60000);
  if (mins < 60) return `données à ~${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `données à ~${hours} h`;
  const days = Math.round(hours / 24);
  return `données à ~${days} j`;
}

export const LAKEFLOW_PAGE_TABS = [
  { label: 'Overview', path: '/databricks/overview' },
  { label: 'Jobs & Pipelines', path: '/databricks/workflows' },
] as const;
