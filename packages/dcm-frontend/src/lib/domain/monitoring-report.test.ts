import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ComputeMetric,
  CostsByServiceResponse,
  DataProductUsage,
  GovernanceScore,
  LandingZoneDetail,
  SecurityAlert,
  StandardCheck,
} from '../../types/api';
import {
  buildComplianceChartData,
  buildHealthByDomainData,
  buildMonitoringReportCsv,
  buildMonitoringReportFileName,
  buildMonitoringReportJson,
  buildTopCostData,
  buildTopUsageData,
  buildUnityCatalogCoverageData,
  calculateHealthStatus,
  filterMonitoringReportItems,
  getDefaultMonitoringReportFilters,
  normalizeMonitoringReportItems,
  summarizeMonitoringReport,
} from './monitoring-report';

const usageRows: DataProductUsage[] = [
  {
    usage_date: '2026-05-24',
    data_product_id: 'catalog.crm.customer_360',
    data_product_name: 'Customer 360',
    consumer_id: 'consumer-1',
    consumer_name: 'Analytics',
    cloud_provider: 'azure',
    source_lz_id: 'lz-crm',
    subscription_or_account_id: 'sub-1',
    request_count: 10,
    rows_read: 1000,
    rows_written: 50,
    data_read_bytes: 2048,
    data_written_bytes: 1024,
    duration_seconds: 60,
    cost_usd: 100,
    last_used_at: '2026-05-24T10:00:00Z',
  },
  {
    usage_date: '2026-05-25',
    data_product_id: 'catalog.crm.customer_360',
    data_product_name: 'Customer 360',
    consumer_id: 'consumer-2',
    consumer_name: 'Endance',
    cloud_provider: 'azure',
    source_lz_id: 'lz-crm',
    subscription_or_account_id: 'sub-1',
    request_count: 15,
    rows_read: 2000,
    rows_written: 100,
    data_read_bytes: 4096,
    data_written_bytes: 2048,
    duration_seconds: 120,
    cost_usd: 150,
    last_used_at: '2026-05-25T10:00:00Z',
  },
];

const landingZones: LandingZoneDetail[] = [
  {
    lz_id: 'lz-crm',
    lz_name: 'analytics-prod',
    cloud_provider: 'azure',
    subscription_or_account_id: 'sub-1',
    environment: 'prod',
    ba_name: 'CRM',
    valid_from: '2026-01-01',
  },
];

const standardChecks: StandardCheck[] = [
  {
    check_id: 'check-1',
    check_name: 'PII classified',
    cloud_provider: 'azure',
    source_lz_id: 'lz-crm',
    subscription_or_account_id: 'sub-1',
    check_state: 'no_compliant',
    resource_id: 'catalog.crm.customer_360',
    resource_name: 'customer_360',
    resource_type: 'table',
    check_effect: 'deny',
    no_check_reasons: ['missing classification'],
    evaluated_at: '2026-05-25T08:00:00Z',
  },
  {
    check_id: 'check-2',
    check_name: 'Owner tag',
    cloud_provider: 'azure',
    source_lz_id: 'lz-crm',
    subscription_or_account_id: 'sub-1',
    check_state: 'compliant',
    resource_id: 'catalog.crm.customer_360',
    resource_name: 'customer_360',
    resource_type: 'table',
    check_effect: null,
    no_check_reasons: [],
    evaluated_at: '2026-05-25T08:00:00Z',
  },
];

const securityAlerts: SecurityAlert[] = [
  {
    alert_id: 'alert-1',
    cloud_provider: 'azure',
    source_lz_id: 'lz-crm',
    severity: 'high',
    title: 'Public table access',
    description: 'Unexpected grant detected.',
    status: 'active',
    resource_id: 'catalog.crm.customer_360',
    resource_type: 'table',
    detected_at: '2026-05-25T08:00:00Z',
  },
];

const computes: ComputeMetric[] = [
  {
    compute_resource_id: 'cluster-1',
    resource_name: 'crm-cluster',
    compute_type: 'databricks',
    cloud_provider: 'azure',
    source_lz_id: 'lz-crm',
    subscription_or_account_id: 'sub-1',
    workspace_id: 'workspace-1',
    state: 'running',
    num_workers: 4,
    autoscale_min: 2,
    autoscale_max: 8,
    node_type: 'Standard_DS3_v2',
    spark_version: '14.3',
    avg_cpu_utilization_pct: 55,
    avg_mem_utilization_pct: 70,
    tags: { owner: 'Data Domain CRM' },
    collected_at: '2026-05-25T08:00:00Z',
  },
];

const costsByService: CostsByServiceResponse['items'] = [];

const governanceScore: GovernanceScore = {
  global_score_pct: 50,
  compliant_count: 1,
  no_compliant_count: 1,
  total_evaluated: 2,
  by_landing_zone: [
    {
      cloud_provider: 'azure',
      source_lz_id: 'lz-crm',
      subscription_or_account_id: 'sub-1',
      compliant_count: 1,
      no_compliant_count: 1,
      total_evaluated: 2,
      score_pct: 50,
    },
  ],
};

function buildItems() {
  vi.setSystemTime(new Date('2026-05-25T12:00:00Z'));

  return normalizeMonitoringReportItems({
    usageRows,
    landingZones,
    standardChecks,
    securityAlerts,
    computes,
    costsByService,
    governanceScore,
  });
}

describe('monitoring report helpers', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('normalizes API responses into Data Product report items', () => {
    const items = buildItems();

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      dataProductName: 'Customer 360',
      domain: 'CRM',
      owner: 'Data Domain CRM',
      cloudProvider: 'azure',
      landingZoneName: 'analytics-prod',
      status: 'Critical',
      costUsd: 250,
      complianceScore: 50,
      failedChecks: 1,
      incidents: 1,
      cpuUtilization: 55,
      requestCount: 25,
    });
    expect(items[0].unityCatalogAssets[0]).toMatchObject({
      catalog: 'catalog',
      schema: 'crm',
      name: 'customer_360',
    });
    expect(items[0].recommendations).toContain('Prioritize non-compliant Standard Checks on the Landing Zone.');
  });

  it('filters and summarizes the normalized dataset', () => {
    const items = buildItems();
    const filters = {
      ...getDefaultMonitoringReportFilters(),
      cloudProvider: 'azure' as const,
      domain: 'CRM',
      status: 'Critical' as const,
      dataProductSearch: 'customer',
    };

    const filtered = filterMonitoringReportItems(items, filters);
    const summary = summarizeMonitoringReport(filtered);

    expect(filtered).toHaveLength(1);
    expect(summary).toMatchObject({
      total: 1,
      critical: 1,
      totalCostUsd: 250,
      averageComplianceScore: 50,
    });
  });

  it('builds compliance chart data and safe CSV/JSON exports', () => {
    const items = buildItems();
    const filters = getDefaultMonitoringReportFilters();

    expect(buildComplianceChartData(items)).toEqual([
      { name: 'Passed', count: 1 },
      { name: 'Warning', count: 0 },
      { name: 'Failed', count: 1 },
    ]);
    expect(buildMonitoringReportCsv(items)).toContain('catalog.crm.customer_360,Customer 360,Critical');
    expect(buildMonitoringReportJson(items, filters, '2026-05-25T12:00:00.000Z')).toContain('"itemCount": 1');
    expect(buildMonitoringReportFileName('monitoring-report', filters, 'csv', new Date('2026-05-25T12:00:00Z'))).toBe('monitoring-report_2026-05-25_all.csv');
  });

  it('builds Data Product bar and circle diagram datasets', () => {
    const items = buildItems();

    expect(buildUnityCatalogCoverageData(items)).toEqual([{ name: 'Mapped UC', count: 1 }]);
    expect(buildTopCostData(items)).toEqual([{ name: 'Customer 360', value: 250 }]);
    expect(buildTopUsageData(items)).toEqual([{ name: 'Customer 360', value: 25 }]);
    expect(buildHealthByDomainData(items)).toEqual([{
      name: 'CRM',
      Healthy: 0,
      Warning: 0,
      Critical: 1,
      Unknown: 0,
    }]);
  });

  it('calculates health status from critical and warning signals', () => {
    expect(calculateHealthStatus({
      owner: 'owner',
      complianceScore: 95,
      failedChecks: 0,
      warningChecks: 0,
      criticalAlerts: 0,
      incidents: 0,
      costTrendPercent: 0,
      freshnessStatus: 'Fresh',
      hasUsage: true,
    })).toBe('Healthy');

    expect(calculateHealthStatus({
      owner: undefined,
      complianceScore: 95,
      failedChecks: 0,
      warningChecks: 0,
      criticalAlerts: 0,
      incidents: 0,
      costTrendPercent: 0,
      freshnessStatus: 'Fresh',
      hasUsage: true,
    })).toBe('Warning');

    expect(calculateHealthStatus({
      owner: 'owner',
      complianceScore: 95,
      failedChecks: 1,
      warningChecks: 0,
      criticalAlerts: 0,
      incidents: 0,
      costTrendPercent: 0,
      freshnessStatus: 'Fresh',
      hasUsage: true,
    })).toBe('Critical');
  });
});
