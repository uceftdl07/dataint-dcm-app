/**
 * Deux décimales par défaut, comme les autres modules (`lib/domain/formatters.ts`,
 * `lib/databricks/view-data.ts`) : un coût arrondi à l'entier efface la moitié des
 * lignes d'un tableau où beaucoup de ressources coûtent moins d'un dollar par jour.
 *
 * Les appels qui demandent 3 chiffres (coût DBU, coût par requête) restent plus
 * précis, `minimumFractionDigits` valant 2 par défaut pour l'USD.
 */
export function formatUsd(value: number | null | undefined, maximumFractionDigits = 2): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits,
    }).format(value);
  } catch {
    // Même nombre de décimales que la branche `Intl`, dont l'USD impose 2 au minimum.
    return `$${value.toLocaleString('en-US', {
      minimumFractionDigits: Math.min(2, maximumFractionDigits),
      maximumFractionDigits,
    })}`;
  }
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * Durée reçue **en heures**, rendue en composantes : `5d 17h 28m 56s`.
 *
 * Pourquoi pas `137.5 h` : au-delà de quelques heures, la partie décimale ne se lit
 * pas — personne ne convertit `0,4823 h` de tête, et deux lignes à `137.5 h` et
 * `137.4 h` se comparent moins bien que `5d 17h 30m` et `5d 17h 24m`.
 *
 * Les composantes nulles sont omises (`2h 30m`, `36s`), sauf pour une durée
 * réellement nulle : elle rend `0s`, et non `—`, réservé à l'absence de mesure.
 */
export function formatHours(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const totalSeconds = Math.round(Number(value) * 3600);
  // Une durée négative n'est pas une durée : la traiter comme une valeur absente
  // plutôt que d'afficher `-1h`, qui laisserait croire à une mesure.
  if (totalSeconds < 0) return '—';
  if (totalSeconds === 0) return '0s';

  const parts = [
    [Math.floor(totalSeconds / 86_400), 'd'],
    [Math.floor((totalSeconds % 86_400) / 3600), 'h'],
    [Math.floor((totalSeconds % 3600) / 60), 'm'],
    [totalSeconds % 60, 's'],
  ] as const;

  return parts
    .filter(([amount]) => amount > 0)
    .map(([amount, unit]) => `${amount}${unit}`)
    .join(' ');
}

export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${value.toFixed(digits)}%`;
}

export function formatDeltaPct(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const abs = Math.abs(value).toFixed(digits);
  if (value > 0) return `+${abs}%`;
  if (value < 0) return `-${abs}%`;
  return '0%';
}

/**
 * A variation of a percentage reads in percentage *points*: `idle_pct` going
 * from 38 % to 41 % is `+3 pts`, never `+7.9 %`.
 */
export function formatDeltaPts(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const abs = Math.abs(value).toFixed(digits);
  if (value > 0) return `+${abs} pts`;
  if (value < 0) return `-${abs} pts`;
  return '0 pts';
}

/**
 * Worker sizing of a cluster: the configured autoscaling bounds when it
 * autoscales, otherwise its fixed worker count. Never the observed maximum
 * (`worker_count_max`), which is a different notion.
 */
export function formatWorkerBounds(bounds: {
  autoscale_min_workers?: number | null;
  autoscale_max_workers?: number | null;
  configured_worker_count?: number | null;
}): string {
  const { autoscale_min_workers, autoscale_max_workers, configured_worker_count } = bounds;
  if (autoscale_min_workers != null && autoscale_max_workers != null) {
    return `${formatNumber(autoscale_min_workers)} – ${formatNumber(autoscale_max_workers)}`;
  }
  if (configured_worker_count != null) return `${formatNumber(configured_worker_count)} fixed`;
  return '—';
}

export function autoscalingLabel(enabled: boolean | null | undefined): string {
  if (enabled == null) return '—';
  return enabled ? 'On' : 'Off';
}

export type UtilizationStatus = 'OVER' | 'UNDER' | 'OPTIMAL' | 'ZOMBIE' | string;

export function utilizationLabel(status: UtilizationStatus | null | undefined): string {
  const s = (status || '').trim().toUpperCase();
  if (!s) return '—';
  if (s === 'OVER') return 'Overprovisioned';
  if (s === 'UNDER') return 'Underprovisioned';
  if (s === 'OPTIMAL') return 'Optimal';
  if (s === 'ZOMBIE') return 'Zombie';
  return status ?? '—';
}

export type Severity = 'HIGH' | 'MEDIUM' | 'LOW' | string;

export function severityLabel(severity: Severity | null | undefined): string {
  const s = (severity || '').trim().toUpperCase();
  if (!s) return '—';
  if (s === 'HIGH') return 'High';
  if (s === 'MEDIUM') return 'Medium';
  if (s === 'LOW') return 'Low';
  return severity ?? '—';
}

export function skuGroupLabel(value: string | null | undefined): string {
  if (!value) return '—';
  return value;
}

export function clusterTypeLabel(value: string | null | undefined): string {
  if (!value?.trim()) return '—';
  return value
    .trim()
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Backwards-compatible aliases (older compute UI prototypes).
export function formatUtilizationStatus(status: UtilizationStatus | null | undefined): string {
  return utilizationLabel(status);
}

export function formatSeverity(value: Severity | null | undefined): string {
  return severityLabel(value);
}

function isoDateUtc(d: Date): string {
  return d.toISOString().split('T')[0]!;
}

export function subtractDaysIso(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return isoDateUtc(d);
}

export function todayIsoUtc(): string {
  return isoDateUtc(new Date());
}

/**
 * Plage des `days` derniers jours, bornes incluses, finissant aujourd'hui.
 *
 * Sert aux pages compute dont l'en-tête n'expose plus de dates : leurs tableaux
 * lisent un instantané par fenêtre, mais deux ou trois endpoints demandent encore
 * des bornes explicites. Elles sont alors calculées ici, ancrées sur aujourd'hui,
 * et non lues dans la plage globale — invisible sur ces pages, donc modifiable
 * seulement depuis une page voisine, ce qui décalerait ces écrans sans rien
 * montrer.
 */
export function lastNDaysPeriodIso(
  days: number,
  endIso: string = todayIsoUtc()
): { period_start: string; period_end: string } {
  return { period_start: subtractDaysIso(endIso, Math.max(0, days - 1)), period_end: endIso };
}

export function capPeriodToLastNDays(params: {
  period_start: string;
  period_end: string;
  maxDays: number;
}): { period_start: string; period_end: string } {
  const { period_start, period_end, maxDays } = params;
  if (!period_start || !period_end) return { period_start, period_end };
  const start = new Date(`${period_start}T00:00:00Z`).getTime();
  const end = new Date(`${period_end}T00:00:00Z`).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return { period_start, period_end };
  const days = Math.abs(Math.round((end - start) / (24 * 60 * 60 * 1000))) + 1;
  if (days <= maxDays) return { period_start, period_end };
  return { period_start: subtractDaysIso(period_end, maxDays - 1), period_end };
}
