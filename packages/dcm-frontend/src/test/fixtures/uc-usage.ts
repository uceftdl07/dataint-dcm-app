import type {
  UcUsageAttentionResponse,
  UcUsageConsumerRow,
  UcUsageCostByTableRow,
  UcUsageFilterOptions,
  UcUsageFinopsKpis,
  UcUsageForecastSeriesResponse,
  UcUsageGovernanceKpis,
  UcUsageLifecycle,
  UcUsageListEnvelope,
  UcUsageOverview,
  UcUsageRecommendation,
  UcUsageRecommendationsResponse,
  UcUsageRegistryRow,
  UcUsageTableRow,
  UcUsageTopConsumersResponse,
} from '../../types/api';

const period = { start: '2026-08-12', end: '2026-09-11' };

/**
 * Cycle de vie d'une table encore présente dans Unity Catalog (spec 027). Les
 * fixtures partagées décrivent un parc vivant : une suppression est un cas de
 * test, elle s'écrit dans le test qui l'observe.
 */
export const ucUsageLiveLifecycle: UcUsageLifecycle = {
  is_deleted: false,
  deleted_at: null,
  lifecycle_state: 'ACTIVE',
};

/** Table supprimée le 5 septembre 2026, à étaler sur la ligne à marquer. */
export const ucUsageDeletedLifecycle: UcUsageLifecycle = {
  is_deleted: true,
  deleted_at: '2026-09-05T04:00:00Z',
  lifecycle_state: 'DELETED',
};

export const ucUsageFilterOptionsFixture: UcUsageFilterOptions = {
  catalogs: ['main', 'lake'],
  schemas: ['sales', 'finance'],
  tables: [
    {
      table_full_name: 'main.sales.orders',
      catalog: 'main',
      schema: 'sales',
      ...ucUsageLiveLifecycle,
    },
    {
      table_full_name: 'main.finance.invoices',
      catalog: 'main',
      schema: 'finance',
      ...ucUsageLiveLifecycle,
    },
  ],
  truncated: false,
  limit: 500,
};

export const ucUsageRecommendationFixture: UcUsageRecommendation = {
  recommendation_id: 'rec-1',
  cloud_provider: 'azure',
  object_type: 'DATA_PRODUCT',
  object_id: 'main.sales.orders',
  object_name: 'orders',
  category: 'LIFECYCLE',
  mode: 'REACTIVE',
  title: 'Table inutilisée depuis 90 jours',
  detail: 'Aucune lecture depuis le 12 juin 2026.',
  recommended_action: 'Archiver la table',
  estimated_savings_usd: 128.4,
  // Majuscules côté recommandations, minuscules côté registre : c'est le cas
  // que la normalisation doit réconcilier (FR-015).
  severity: 'HIGH',
  personas: ['OWN', 'FIN'],
  status: 'OPEN',
  first_seen_date: '2026-07-01',
  last_seen_date: '2026-09-10',
  age_days: 72,
};

export const ucUsageOverviewFixture: UcUsageOverview = {
  tracked_tables: 412,
  request_count: 18_320,
  request_count_delta_pct: 12.4,
  distinct_consumers: 87,
  estimated_cost_usd: 1_284.55,
  estimated_cost_usd_delta_pct: -3.1,
  unused_tables: 46,
  access_failure_rate_pct: 1.8,
  trends: [
    {
      metric_name: 'request_count',
      points: [
        { horizon_date: '2026-09-12', predicted_value: 640, lower_bound: 520, upper_bound: 760 },
        { horizon_date: '2026-09-13', predicted_value: 655, lower_bound: 530, upper_bound: 780 },
      ],
    },
    {
      metric_name: 'estimated_cost_usd',
      points: [
        { horizon_date: '2026-09-12', predicted_value: 44.2, lower_bound: 38, upper_bound: 51 },
      ],
    },
  ],
  written_bytes_series: [
    { period_start: '2026-09-09', data_written_bytes: 1_073_741_824 },
    // `null` préservé : un jour sans mesure n'est pas un jour à zéro (SC-005).
    { period_start: '2026-09-10', data_written_bytes: null },
  ],
  attention: [ucUsageRecommendationFixture],
  period,
};

export const ucUsageTablesFixture: UcUsageListEnvelope<UcUsageTableRow> = {
  items: [
    {
      table_full_name: 'main.sales.orders',
      catalog: 'main',
      schema: 'sales',
      table_name: 'orders',
      table_type: 'MANAGED',
      request_count: 8_210,
      request_delta_pct: 9.3,
      distinct_consumers: 24,
      data_read_bytes: 5_368_709_120,
      estimated_cost_usd: 612.3,
      cost_attribution_method: 'equal_parts_fallback',
      cost_basis: 'warehouse_prorata',
      catalog_resolution_status: 'RESOLVED',
      last_used_at: '2026-09-10T22:14:00Z',
      query_count: 8_400,
      failed_count: 120,
      failure_rate_pct: 1.43,
      latency_p95_ms: 2_480,
      freshness_lag_hours: 3.5,
      freshness_basis: 'table_altered',
      last_write_at: '2026-09-10T18:00:00Z',
      ...ucUsageLiveLifecycle,
    },
    {
      table_full_name: 'main.finance.invoices',
      catalog: 'main',
      schema: 'finance',
      table_name: 'invoices',
      table_type: 'EXTERNAL',
      request_count: 1_120,
      request_delta_pct: null,
      distinct_consumers: 6,
      data_read_bytes: null,
      estimated_cost_usd: null,
      cost_attribution_method: null,
      cost_basis: null,
      catalog_resolution_status: 'NOT_VISIBLE_TO_PIPELINE',
      last_used_at: null,
      query_count: 1_120,
      failed_count: 0,
      failure_rate_pct: 0,
      latency_p95_ms: null,
      freshness_lag_hours: null,
      freshness_basis: null,
      last_write_at: null,
      ...ucUsageLiveLifecycle,
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  period,
};

export const ucUsageTopConsumersFixture: UcUsageTopConsumersResponse = {
  table_full_name: 'main.sales.orders',
  ...ucUsageLiveLifecycle,
  items: [
    {
      rank: 1,
      consumer_id: 'user-42',
      consumer_name: 'analytics.team',
      consumer_type: 'SERVICE_PRINCIPAL',
      request_count: 3_100,
      estimated_cost_usd: 210.5,
      last_used_at: '2026-09-10T21:00:00Z',
    },
    {
      rank: 2,
      consumer_id: 'job-77',
      consumer_name: null,
      // Vocabulaire ouvert : l'UI doit afficher la valeur inconnue, pas la masquer.
      consumer_type: 'MCP_CONNECTOR',
      request_count: 980,
      estimated_cost_usd: null,
      last_used_at: null,
    },
  ],
  period,
};

export const ucUsageConsumersFixture: UcUsageListEnvelope<UcUsageConsumerRow> = {
  items: [
    {
      rank: 1,
      consumer_id: 'user-42',
      consumer_name: 'analytics.team',
      consumer_type: 'SERVICE_PRINCIPAL',
      distinct_tables: 18,
      request_count: 4_200,
      data_read_bytes: 2_147_483_648,
      estimated_cost_usd: 310.2,
      last_used_at: '2026-09-10T21:00:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
  period,
};

export const ucUsageFinopsKpisFixture: UcUsageFinopsKpis = {
  total_cost_usd: 1_284.55,
  request_count: 18_320,
  costed_tables: 208,
  avg_cost_per_request_usd: 0.0701,
  is_lower_bound: true,
  top_costly_table: { table_full_name: 'main.sales.orders', estimated_cost_usd: 612.3 },
  period,
};

export const ucUsageCostByTableFixture: UcUsageListEnvelope<UcUsageCostByTableRow> = {
  items: [
    {
      table_full_name: 'main.sales.orders',
      estimated_cost_usd: 612.3,
      request_count: 8_210,
      data_read_bytes: 5_368_709_120,
      cost_per_request_usd: 0.0746,
      forecast_cost_usd_7d: 44.2,
      ...ucUsageLiveLifecycle,
    },
    {
      table_full_name: 'main.finance.invoices',
      estimated_cost_usd: 0,
      request_count: 1_120,
      data_read_bytes: null,
      cost_per_request_usd: null,
      // Pas de ligne de prévision : tiret attendu, jamais `$0` (SC-005).
      forecast_cost_usd_7d: null,
      ...ucUsageLiveLifecycle,
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  period,
};

export const ucUsageTrendsFixture: UcUsageForecastSeriesResponse = {
  series: ucUsageOverviewFixture.trends.map((entry) => ({
    ...entry,
    observed: [
      { period_start: '2026-09-09', value: 600 },
      // `null` préservé : une journée sans mesure n'est pas une journée à zéro.
      { period_start: '2026-09-10', value: null },
      { period_start: '2026-09-11', value: 620 },
    ],
  })),
};

export const ucUsageAttentionFixture: UcUsageAttentionResponse = {
  items: [ucUsageRecommendationFixture],
};

export const ucUsageGovernanceKpisFixture: UcUsageGovernanceKpis = {
  unused_tables: 46,
  stale_but_consumed_tables: 12,
  critical_tables: 8,
  tracked_tables: 412,
};

export const ucUsageRegistryFixture: UcUsageListEnvelope<UcUsageRegistryRow> = {
  items: [
    {
      table_full_name: 'main.sales.orders',
      catalog: 'main',
      schema: 'sales',
      table_name: 'orders',
      table_type: 'MANAGED',
      owner: null,
      last_operation: 'updateTables',
      last_operation_at: '2026-09-08T09:00:00Z',
      last_operation_by: 'svc-etl',
      downstream_fanout: 14,
      days_since_last_read: 1,
      is_unused: false,
      is_orphan: true,
      is_stale_but_consumed: false,
      is_critical: true,
      recommended_action: 'documenter',
      severity: 'medium',
      ...ucUsageLiveLifecycle,
    },
    {
      table_full_name: 'main.legacy.snapshot_2019',
      catalog: 'main',
      schema: 'legacy',
      table_name: 'snapshot_2019',
      table_type: 'MANAGED',
      owner: 'data.platform@example.com',
      last_operation: 'createTable',
      last_operation_at: '2019-04-02T10:00:00Z',
      last_operation_by: 'legacy-admin',
      downstream_fanout: 0,
      days_since_last_read: 512,
      is_unused: true,
      is_orphan: false,
      is_stale_but_consumed: false,
      is_critical: false,
      recommended_action: 'archiver',
      severity: 'high',
      ...ucUsageLiveLifecycle,
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
};

export const ucUsageRecommendationsFixture: UcUsageRecommendationsResponse = {
  items: [
    ucUsageRecommendationFixture,
    {
      ...ucUsageRecommendationFixture,
      recommendation_id: 'rec-2',
      category: 'FRESHNESS',
      title: 'Fraîcheur dégradée',
      severity: 'MEDIUM',
      estimated_savings_usd: null,
      object_id: 'main.finance.invoices',
      object_name: 'invoices',
    },
  ],
  total: 2,
  page: 1,
  page_size: 25,
  counts: {
    open_high: 1,
    open_medium: 1,
    open_total: 2,
    estimated_savings_usd: 128.4,
  },
};
