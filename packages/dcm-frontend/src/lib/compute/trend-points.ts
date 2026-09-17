import { formatNumber, formatUsd } from './format';
import type { ComputeTrendPoint } from '../../components/domain/compute/compute-trend-chart';
import type { ComputeClusterCostTrendPoint } from '../../types/api';

/**
 * Cost trend points, shared by the cluster, job, pipeline and warehouse drawers:
 * the endpoints return the same bucket shape, and the hover readout must read
 * the same everywhere. Hors du module de graphe, qui n'exporte que des
 * composants (fast refresh).
 */
export function costTrendPoints(
  items: ComputeClusterCostTrendPoint[] | null | undefined
): ComputeTrendPoint[] {
  return (items ?? []).map((point) => ({
    label: point.bucket,
    value: point.cost_usd,
    tooltip: `${point.bucket} · ${formatUsd(point.cost_usd, 2)} · ${formatNumber(
      point.dbu_quantity
    )} DBU`,
  }));
}
