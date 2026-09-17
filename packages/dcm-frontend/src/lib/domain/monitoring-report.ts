import type {
  CloudProvider,
  ComputeMetric,
  CostsByServiceResponse,
  DataProductUsage,
  DataProductUsageTrend,
  GovernanceScore,
  LandingZoneDetail,
  SecurityAlert,
  StandardCheck,
} from '../../types/api';

export type HealthStatus = 'Healthy' | 'Warning' | 'Critical' | 'Unknown';
export type FreshnessStatus = 'Fresh' | 'Stale' | 'Unknown';
export type MonitoringSortKey = 'status' | 'cost' | 'compliance' | 'freshness' | 'name';

export interface UnityCatalogAssetSummary {
  catalog: string;
  schema: string;
  name: string;
  type: 'table' | 'view' | 'volume' | 'unknown';
  owner?: string;
  tags: string[];
  classification?: string;
}

export interface MonitoringHistoryPoint {
  period: string;
  cloudProvider: CloudProvider;
  costUsd: number;
  requestCount: number;
  rowsRead: number;
  rowsWritten: number;
}

export interface MonitoringReportItem {
  dataProductId: string;
  dataProductName: string;
  domain: string;
  owner?: string;
  cloudProvider: CloudProvider;
  landingZoneId: string;
  landingZoneName: string;
  status: HealthStatus;
  statusReasons: string[];
  costUsd: number;
  costTrendPercent: number | null;
  complianceScore: number | null;
  passedChecks: number;
  failedChecks: number;
  warningChecks: number;
  freshnessStatus: FreshnessStatus;
  qualityScore: number | null;
  cpuUtilization: number | null;
  incidents: number;
  requestCount: number;
  rowsRead: number;
  rowsWritten: number;
  lastUsedAt: string | null;
  unityCatalogAssets: UnityCatalogAssetSummary[];
  failedCheckDetails: StandardCheck[];
  alertDetails: SecurityAlert[];
  history: MonitoringHistoryPoint[];
  recommendations: string[];
}

export interface MonitoringReportFilters {
  cloudProvider: CloudProvider | '';
  domain: string;
  landingZoneId: string;
  dataProductSearch: string;
  status: HealthStatus | '';
  dateStart: string;
  dateEnd: string;
}

export interface NormalizeMonitoringReportInput {
  usageRows: DataProductUsage[];
  landingZones: LandingZoneDetail[];
  standardChecks: StandardCheck[];
  securityAlerts: SecurityAlert[];
  computes: ComputeMetric[];
  costsByService: CostsByServiceResponse['items'];
  governanceScore?: GovernanceScore | null;
}

export interface MonitoringSummary {
  total: number;
  healthy: number;
  warning: number;
  critical: number;
  unknown: number;
  totalCostUsd: number;
  averageComplianceScore: number | null;
}

export interface CostChartDatum {
  period: string;
  azure: number;
  aws: number;
  total: number;
}

export interface NamedCountDatum {
  name: string;
  count: number;
}

export interface DataProductScoreDatum {
  name: string;
  value: number;
}

export interface DataProductHealthByDomainDatum {
  name: string;
  Healthy: number;
  Warning: number;
  Critical: number;
  Unknown: number;
}

interface Accumulator {
  dataProductId: string;
  dataProductName: string;
  cloudProvider: CloudProvider;
  landingZoneId: string;
  costUsd: number;
  requestCount: number;
  rowsRead: number;
  rowsWritten: number;
  lastUsedAt: string | null;
  history: Map<string, MonitoringHistoryPoint>;
  unityCatalogAssets: UnityCatalogAssetSummary[];
}

const HEALTH_WEIGHT: Record<HealthStatus, number> = {
  Critical: 0,
  Warning: 1,
  Unknown: 2,
  Healthy: 3,
};

const DEFAULT_FILTERS: MonitoringReportFilters = {
  cloudProvider: '',
  domain: '',
  landingZoneId: '',
  dataProductSearch: '',
  status: '',
  dateStart: '',
  dateEnd: '',
};

export function getDefaultMonitoringReportFilters(): MonitoringReportFilters {
  return { ...DEFAULT_FILTERS };
}

export function getActiveMonitoringFilterCount(filters: MonitoringReportFilters): number {
  return Object.values(filters).filter(Boolean).length;
}

export function normalizeMonitoringReportItems(input: NormalizeMonitoringReportInput): MonitoringReportItem[] {
  const landingZoneByScope = new Map(
    input.landingZones.map((landingZone) => [scopeKey(landingZone.cloud_provider, landingZone.lz_id), landingZone]),
  );
  const checksByScope = groupByScope(input.standardChecks);
  const alertsByScope = groupByScope(input.securityAlerts);
  const computesByScope = groupByScope(input.computes);
  const costByScope = input.costsByService.reduce<Map<string, number>>((acc, cost) => {
    if (!cost.source_lz_id) return acc;

    const key = scopeKey(cost.cloud_provider, cost.source_lz_id);
    acc.set(key, (acc.get(key) ?? 0) + cost.total_cost_usd);
    return acc;
  }, new Map());
  const scoreByScope = new Map(
    input.governanceScore?.by_landing_zone.map((score) => [
      scopeKey(score.cloud_provider, score.source_lz_id),
      score.score_pct,
    ]) ?? [],
  );

  const grouped = input.usageRows.reduce<Map<string, Accumulator>>((acc, row) => {
    const dataProductId = row.data_product_id || row.data_product_name || 'unknown-data-product';
    const dataProductName = row.data_product_name || row.data_product_id || 'Data Product unknown';
    const key = `${dataProductId}::${row.cloud_provider}::${row.source_lz_id}`;
    const current = acc.get(key) ?? {
      dataProductId,
      dataProductName,
      cloudProvider: row.cloud_provider,
      landingZoneId: row.source_lz_id,
      costUsd: 0,
      requestCount: 0,
      rowsRead: 0,
      rowsWritten: 0,
      lastUsedAt: null,
      history: new Map<string, MonitoringHistoryPoint>(),
      unityCatalogAssets: [],
    };

    current.costUsd += row.cost_usd;
    current.requestCount += row.request_count;
    current.rowsRead += row.rows_read;
    current.rowsWritten += row.rows_written;
    current.lastUsedAt = maxIsoDate(current.lastUsedAt, row.last_used_at ?? row.usage_date);

    const period = row.usage_date || 'unknown';
    const historyPoint = current.history.get(period) ?? {
      period,
      cloudProvider: row.cloud_provider,
      costUsd: 0,
      requestCount: 0,
      rowsRead: 0,
      rowsWritten: 0,
    };
    historyPoint.costUsd += row.cost_usd;
    historyPoint.requestCount += row.request_count;
    historyPoint.rowsRead += row.rows_read;
    historyPoint.rowsWritten += row.rows_written;
    current.history.set(period, historyPoint);

    const parsedAsset = parseUnityCatalogAsset(row);
    if (parsedAsset && !current.unityCatalogAssets.some((asset) => assetKey(asset) === assetKey(parsedAsset))) {
      current.unityCatalogAssets.push(parsedAsset);
    }

    acc.set(key, current);
    return acc;
  }, new Map());

  return Array.from(grouped.values())
    .map((item) => {
      const scope = scopeKey(item.cloudProvider, item.landingZoneId);
      const landingZone = landingZoneByScope.get(scope);
      const checks = checksByScope.get(scope) ?? [];
      const alerts = alertsByScope.get(scope) ?? [];
      const computes = computesByScope.get(scope) ?? [];
      const complianceScore = scoreByScope.get(scope) ?? calculateComplianceScore(checks);
      const failedChecks = checks.filter((check) => check.check_state === 'no_compliant').length;
      const warningChecks = checks.filter((check) => check.check_state === 'unknown').length;
      const passedChecks = checks.filter((check) => check.check_state === 'compliant').length;
      const activeAlerts = alerts.filter((alert) => alert.status === 'active');
      const criticalAlerts = activeAlerts.filter((alert) => alert.severity === 'critical' || alert.severity === 'high').length;
      const owner = resolveOwner(computes);
      const cpuUtilization = averageNullable(computes.map((compute) => compute.avg_cpu_utilization_pct));
      const history = Array.from(item.history.values()).sort((a, b) => a.period.localeCompare(b.period));
      const costUsd = item.costUsd || costByScope.get(scope) || 0;
      const costTrendPercent = calculateTrendPercent(history.map((point) => point.costUsd));
      const freshnessStatus = calculateFreshnessStatus(item.lastUsedAt);
      const qualityScore = calculateQualityScore({
        failedChecks,
        warningChecks,
        incidents: activeAlerts.length,
        freshnessStatus,
      });
      const status = calculateHealthStatus({
        owner,
        complianceScore,
        failedChecks,
        warningChecks,
        criticalAlerts,
        incidents: activeAlerts.length,
        costTrendPercent,
        freshnessStatus,
        hasUsage: item.requestCount > 0,
      });
      const statusReasons = getStatusReasons({
        owner,
        complianceScore,
        failedChecks,
        warningChecks,
        criticalAlerts,
        incidents: activeAlerts.length,
        costTrendPercent,
        freshnessStatus,
        hasUsage: item.requestCount > 0,
      });

      return {
        dataProductId: item.dataProductId,
        dataProductName: item.dataProductName,
        domain: landingZone?.ba_name || 'Unknown',
        owner,
        cloudProvider: item.cloudProvider,
        landingZoneId: item.landingZoneId,
        landingZoneName: landingZone?.lz_name || item.landingZoneId,
        status,
        statusReasons,
        costUsd,
        costTrendPercent,
        complianceScore,
        passedChecks,
        failedChecks,
        warningChecks,
        freshnessStatus,
        qualityScore,
        cpuUtilization,
        incidents: activeAlerts.length,
        requestCount: item.requestCount,
        rowsRead: item.rowsRead,
        rowsWritten: item.rowsWritten,
        lastUsedAt: item.lastUsedAt,
        unityCatalogAssets: item.unityCatalogAssets,
        failedCheckDetails: checks.filter((check) => check.check_state !== 'compliant'),
        alertDetails: activeAlerts,
        history,
        recommendations: buildRecommendations({
          owner,
          complianceScore,
          failedChecks,
          warningChecks,
          incidents: activeAlerts.length,
          costTrendPercent,
          freshnessStatus,
          hasUnityCatalogAssets: item.unityCatalogAssets.length > 0,
        }),
      } satisfies MonitoringReportItem;
    })
    .sort((a, b) => HEALTH_WEIGHT[a.status] - HEALTH_WEIGHT[b.status] || b.costUsd - a.costUsd);
}

export function filterMonitoringReportItems(
  items: MonitoringReportItem[],
  filters: MonitoringReportFilters,
): MonitoringReportItem[] {
  const search = filters.dataProductSearch.trim().toLowerCase();

  return items.filter((item) => {
    if (filters.cloudProvider && item.cloudProvider !== filters.cloudProvider) return false;
    if (filters.domain && item.domain !== filters.domain) return false;
    if (filters.landingZoneId && item.landingZoneId !== filters.landingZoneId) return false;
    if (filters.status && item.status !== filters.status) return false;
    if (search && !`${item.dataProductName} ${item.dataProductId}`.toLowerCase().includes(search)) return false;
    if (filters.dateStart && !item.history.some((point) => point.period >= filters.dateStart)) return false;
    if (filters.dateEnd && !item.history.some((point) => point.period <= filters.dateEnd)) return false;
    return true;
  });
}

export function sortMonitoringReportItems(
  items: MonitoringReportItem[],
  sortKey: MonitoringSortKey,
  direction: 'asc' | 'desc',
): MonitoringReportItem[] {
  const multiplier = direction === 'asc' ? 1 : -1;

  return [...items].sort((a, b) => {
    if (sortKey === 'name') return a.dataProductName.localeCompare(b.dataProductName) * multiplier;
    if (sortKey === 'status') return (HEALTH_WEIGHT[a.status] - HEALTH_WEIGHT[b.status]) * multiplier;
    if (sortKey === 'freshness') return a.freshnessStatus.localeCompare(b.freshnessStatus) * multiplier;
    if (sortKey === 'compliance') return ((a.complianceScore ?? -1) - (b.complianceScore ?? -1)) * multiplier;
    return (a.costUsd - b.costUsd) * multiplier;
  });
}

export function summarizeMonitoringReport(items: MonitoringReportItem[]): MonitoringSummary {
  const scoredItems = items.filter((item) => item.complianceScore !== null);

  return {
    total: items.length,
    healthy: items.filter((item) => item.status === 'Healthy').length,
    warning: items.filter((item) => item.status === 'Warning').length,
    critical: items.filter((item) => item.status === 'Critical').length,
    unknown: items.filter((item) => item.status === 'Unknown').length,
    totalCostUsd: items.reduce((sum, item) => sum + item.costUsd, 0),
    averageComplianceScore: scoredItems.length
      ? scoredItems.reduce((sum, item) => sum + (item.complianceScore ?? 0), 0) / scoredItems.length
      : null,
  };
}

export function buildCostChartData(items: MonitoringReportItem[], fallbackTrends: DataProductUsageTrend[] = []): CostChartDatum[] {
  const byPeriod = new Map<string, CostChartDatum>();

  items.forEach((item) => {
    item.history.forEach((point) => {
      const current = byPeriod.get(point.period) ?? { period: point.period, azure: 0, aws: 0, total: 0 };
      current[point.cloudProvider] += point.costUsd;
      current.total += point.costUsd;
      byPeriod.set(point.period, current);
    });
  });

  if (byPeriod.size === 0) {
    fallbackTrends.forEach((trend) => {
      byPeriod.set(trend.period_start, {
        period: trend.period_start,
        azure: 0,
        aws: 0,
        total: trend.cost_usd,
      });
    });
  }

  return Array.from(byPeriod.values()).sort((a, b) => a.period.localeCompare(b.period)).slice(-12);
}

export function buildStatusDistribution(items: MonitoringReportItem[]): NamedCountDatum[] {
  return (['Healthy', 'Warning', 'Critical', 'Unknown'] as HealthStatus[])
    .map((status) => ({ name: status, count: items.filter((item) => item.status === status).length }))
    .filter((item) => item.count > 0);
}

export function buildComplianceChartData(items: MonitoringReportItem[]): NamedCountDatum[] {
  return [
    { name: 'Passed', count: items.reduce((sum, item) => sum + item.passedChecks, 0) },
    { name: 'Warning', count: items.reduce((sum, item) => sum + item.warningChecks, 0) },
    { name: 'Failed', count: items.reduce((sum, item) => sum + item.failedChecks, 0) },
  ];
}

export function buildUnityCatalogCoverageData(items: MonitoringReportItem[]): NamedCountDatum[] {
  return [
    { name: 'Mapped UC', count: items.filter((item) => item.unityCatalogAssets.length > 0).length },
    { name: 'Missing UC', count: items.filter((item) => item.unityCatalogAssets.length === 0).length },
  ].filter((item) => item.count > 0);
}

export function buildTopCostData(items: MonitoringReportItem[], limit = 8): DataProductScoreDatum[] {
  return [...items]
    .filter((item) => item.costUsd > 0)
    .sort((a, b) => b.costUsd - a.costUsd)
    .slice(0, limit)
    .map((item) => ({
      name: item.dataProductName,
      value: Math.round(item.costUsd * 100) / 100,
    }));
}

export function buildTopUsageData(items: MonitoringReportItem[], limit = 8): DataProductScoreDatum[] {
  return [...items]
    .filter((item) => item.requestCount > 0)
    .sort((a, b) => b.requestCount - a.requestCount)
    .slice(0, limit)
    .map((item) => ({
      name: item.dataProductName,
      value: item.requestCount,
    }));
}

export function buildHealthByDomainData(items: MonitoringReportItem[], limit = 8): DataProductHealthByDomainDatum[] {
  const byDomain = items.reduce<Map<string, DataProductHealthByDomainDatum>>((acc, item) => {
    const current = acc.get(item.domain) ?? {
      name: item.domain,
      Healthy: 0,
      Warning: 0,
      Critical: 0,
      Unknown: 0,
    };

    current[item.status] += 1;
    acc.set(item.domain, current);
    return acc;
  }, new Map());

  return Array.from(byDomain.values())
    .sort((a, b) => (
      b.Critical - a.Critical
      || b.Warning - a.Warning
      || totalHealthCount(b) - totalHealthCount(a)
      || a.name.localeCompare(b.name)
    ))
    .slice(0, limit);
}

export function buildComputeChartData(items: MonitoringReportItem[]): DataProductScoreDatum[] {
  return items
    .filter((item) => item.cpuUtilization !== null)
    .sort((a, b) => (b.cpuUtilization ?? 0) - (a.cpuUtilization ?? 0))
    .slice(0, 8)
    .map((item) => ({
      name: item.dataProductName,
      value: Math.round(item.cpuUtilization ?? 0),
    }));
}

export function buildMonitoringReportCsv(items: MonitoringReportItem[]): string {
  const headers = [
    'dataProductId',
    'dataProductName',
    'status',
    'domain',
    'owner',
    'cloudProvider',
    'landingZoneId',
    'landingZoneName',
    'qualityScore',
    'complianceScore',
    'costUsd',
    'costTrendPercent',
    'freshnessStatus',
    'failedChecks',
    'warningChecks',
    'incidents',
    'cpuUtilization',
    'requestCount',
    'lastUsedAt',
  ];

  const rows = items.map((item) => [
    item.dataProductId,
    item.dataProductName,
    item.status,
    item.domain,
    item.owner ?? '',
    item.cloudProvider,
    item.landingZoneId,
    item.landingZoneName,
    item.qualityScore ?? '',
    item.complianceScore ?? '',
    item.costUsd.toFixed(2),
    item.costTrendPercent ?? '',
    item.freshnessStatus,
    item.failedChecks,
    item.warningChecks,
    item.incidents,
    item.cpuUtilization ?? '',
    item.requestCount,
    item.lastUsedAt ?? '',
  ]);

  return [headers, ...rows].map((row) => row.map(csvCell).join(',')).join('\n');
}

export function buildMonitoringReportJson(
  items: MonitoringReportItem[],
  filters: MonitoringReportFilters,
  exportedAt = new Date().toISOString(),
): string {
  return JSON.stringify({
    exportedAt,
    filters,
    itemCount: items.length,
    data: items.map(sanitizeForExport),
  }, null, 2);
}

export function buildMonitoringReportFileName(
  prefix: string,
  filters: MonitoringReportFilters,
  extension: 'csv' | 'json' | 'pdf',
  now = new Date(),
): string {
  const date = now.toISOString().slice(0, 10);
  const scope = [
    filters.cloudProvider,
    filters.domain,
    filters.landingZoneId,
    filters.status,
    filters.dataProductSearch.trim().replace(/\s+/g, '-').toLowerCase(),
  ].filter(Boolean).join('_') || 'all';

  return `${prefix}_${date}_${scope}.${extension}`;
}

export function calculateHealthStatus(input: {
  owner?: string;
  complianceScore: number | null;
  failedChecks: number;
  warningChecks: number;
  criticalAlerts: number;
  incidents: number;
  costTrendPercent: number | null;
  freshnessStatus: FreshnessStatus;
  hasUsage: boolean;
}): HealthStatus {
  if (!input.hasUsage && input.complianceScore === null && input.incidents === 0) return 'Unknown';
  if (
    input.failedChecks > 0
    || input.criticalAlerts > 0
    || (input.complianceScore !== null && input.complianceScore < 70)
  ) {
    return 'Critical';
  }

  if (
    !input.owner
    || input.warningChecks > 0
    || input.incidents > 0
    || input.freshnessStatus === 'Stale'
    || (input.complianceScore !== null && input.complianceScore < 90)
    || (input.costTrendPercent !== null && input.costTrendPercent > 15)
  ) {
    return 'Warning';
  }

  return 'Healthy';
}

function calculateFreshnessStatus(lastUsedAt: string | null): FreshnessStatus {
  if (!lastUsedAt) return 'Unknown';

  const ageMs = Date.now() - new Date(lastUsedAt).getTime();
  const ageDays = ageMs / (1000 * 60 * 60 * 24);
  return ageDays <= 7 ? 'Fresh' : 'Stale';
}

function calculateQualityScore(input: {
  failedChecks: number;
  warningChecks: number;
  incidents: number;
  freshnessStatus: FreshnessStatus;
}): number {
  const freshnessPenalty = input.freshnessStatus === 'Stale' ? 12 : input.freshnessStatus === 'Unknown' ? 6 : 0;
  return Math.max(0, 100 - input.failedChecks * 12 - input.warningChecks * 5 - input.incidents * 8 - freshnessPenalty);
}

function calculateComplianceScore(checks: StandardCheck[]): number | null {
  if (checks.length === 0) return null;

  const compliant = checks.filter((check) => check.check_state === 'compliant').length;
  return Math.round((compliant / checks.length) * 100);
}

function calculateTrendPercent(values: number[]): number | null {
  const noZeroValues = values.filter((value) => value > 0);
  if (noZeroValues.length < 2) return null;

  const first = noZeroValues[0];
  const last = noZeroValues[noZeroValues.length - 1];
  return first === 0 ? null : Math.round(((last - first) / first) * 100);
}

function getStatusReasons(input: Parameters<typeof calculateHealthStatus>[0]): string[] {
  const reasons: string[] = [];
  if (!input.owner) reasons.push('Owner manquant');
  if (input.failedChecks > 0) reasons.push(`${input.failedChecks} check(s) failed`);
  if (input.warningChecks > 0) reasons.push(`${input.warningChecks} check(s) unknown`);
  if (input.criticalAlerts > 0) reasons.push(`${input.criticalAlerts} alert(s) critical`);
  if (input.freshnessStatus === 'Stale') reasons.push('Freshness stale');
  if (input.complianceScore !== null && input.complianceScore < 90) reasons.push(`Compliance ${Math.round(input.complianceScore)}%`);
  if (input.costTrendPercent !== null && input.costTrendPercent > 15) reasons.push(`Cost +${input.costTrendPercent}%`);
  if (!input.hasUsage) reasons.push('No recent usage');
  return reasons;
}

function buildRecommendations(input: {
  owner?: string;
  complianceScore: number | null;
  failedChecks: number;
  warningChecks: number;
  incidents: number;
  costTrendPercent: number | null;
  freshnessStatus: FreshnessStatus;
  hasUnityCatalogAssets: boolean;
}): string[] {
  const recommendations: string[] = [];
  if (!input.owner) recommendations.push('Set a Data Product owner or an actionable owner tag.');
  if (!input.hasUnityCatalogAssets) recommendations.push('Publish the Data Product -> Unity Catalog asset mapping for drill-down.');
  if (input.failedChecks > 0) recommendations.push('Prioritize non-compliant Standard Checks on the Landing Zone.');
  if (input.warningChecks > 0) recommendations.push('Analyze unknown checks to distinguish missing data from real risk.');
  if (input.incidents > 0) recommendations.push('Handle active alerts before sharing the product more widely.');
  if (input.freshnessStatus === 'Stale') recommendations.push('Check the refresh chain and upstream pipelines.');
  if (input.costTrendPercent !== null && input.costTrendPercent > 15) recommendations.push('Review compute workloads and read/write costs.');
  if (input.complianceScore !== null && input.complianceScore < 90) recommendations.push('Fix governance controls below the 90% target threshold.');
  return recommendations.length ? recommendations : ['No immediate action detected in the filtered scope.'];
}

function resolveOwner(computes: ComputeMetric[]): string | undefined {
  for (const compute of computes) {
    const owner = readTag(compute.tags, ['owner', 'Owner', 'data_owner', 'business_owner', 'created_by']);
    if (owner) return owner;
  }

  return undefined;
}

function readTag(tags: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = tags[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }

  return undefined;
}

function parseUnityCatalogAsset(row: DataProductUsage): UnityCatalogAssetSummary | null {
  const candidate = row.data_product_id.includes('.') ? row.data_product_id : row.data_product_name ?? '';
  const parts = candidate.split('.').filter(Boolean);
  if (parts.length < 3) return null;

  return {
    catalog: parts[0],
    schema: parts[1],
    name: parts.slice(2).join('.'),
    type: 'table',
    tags: [row.cloud_provider, row.source_lz_id],
  };
}

function assetKey(asset: UnityCatalogAssetSummary): string {
  return `${asset.catalog}.${asset.schema}.${asset.name}`;
}

function groupByScope<T extends { cloud_provider: CloudProvider; source_lz_id: string }>(items: T[]): Map<string, T[]> {
  return items.reduce<Map<string, T[]>>((acc, item) => {
    const key = scopeKey(item.cloud_provider, item.source_lz_id);
    acc.set(key, [...(acc.get(key) ?? []), item]);
    return acc;
  }, new Map());
}

function scopeKey(cloudProvider: CloudProvider, landingZoneId: string): string {
  return `${cloudProvider}::${landingZoneId}`;
}

function maxIsoDate(current: string | null, next: string | null): string | null {
  if (!next) return current;
  if (!current) return next;
  return next > current ? next : current;
}

function averageNullable(values: Array<number | null | undefined>): number | null {
  const numericValues = values.filter((value): value is number => typeof value === 'number');
  if (numericValues.length === 0) return null;
  return numericValues.reduce((sum, value) => sum + value, 0) / numericValues.length;
}

function totalHealthCount(item: DataProductHealthByDomainDatum): number {
  return item.Healthy + item.Warning + item.Critical + item.Unknown;
}

function csvCell(value: string | number): string {
  const text = String(value);
  if (!/[",\n]/.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

function sanitizeForExport(item: MonitoringReportItem) {
  return {
    dataProductId: item.dataProductId,
    dataProductName: item.dataProductName,
    status: item.status,
    statusReasons: item.statusReasons,
    domain: item.domain,
    owner: item.owner ?? null,
    cloudProvider: item.cloudProvider,
    landingZoneId: item.landingZoneId,
    landingZoneName: item.landingZoneName,
    qualityScore: item.qualityScore,
    complianceScore: item.complianceScore,
    costUsd: item.costUsd,
    costTrendPercent: item.costTrendPercent,
    freshnessStatus: item.freshnessStatus,
    failedChecks: item.failedChecks,
    warningChecks: item.warningChecks,
    incidents: item.incidents,
    cpuUtilization: item.cpuUtilization,
    requestCount: item.requestCount,
    rowsRead: item.rowsRead,
    rowsWritten: item.rowsWritten,
    lastUsedAt: item.lastUsedAt,
    unityCatalogAssets: item.unityCatalogAssets,
    history: item.history,
    recommendations: item.recommendations,
  };
}
