import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '../test/render';
import MonitoringReports from './MonitoringReports';

vi.mock('../api/dcmApiClient', () => ({
  getMonitoringReportsFull: vi.fn(),
  queryUnityCatalogTableGeneric: vi.fn(),
}));

// The legacy panel is gated on `page:unity-catalog`, so the permission has to be
// steerable per test — the real hook would need the whole /auth/me + /permissions pair.
const { canAccessMock } = vi.hoisted(() => ({ canAccessMock: vi.fn() }));

vi.mock('../hooks/useRolePermissions', () => ({
  useRolePermissions: () => ({
    canAccess: canAccessMock,
    permissions: { role: 'viewer', pages: [], widgets: [], features: [], allowed: [] },
    loading: false,
    ready: true,
    error: null,
    reload: vi.fn(),
  }),
}));

import {
  getMonitoringReportsFull,
  queryUnityCatalogTableGeneric,
} from '../api/dcmApiClient';

const apiMocks = {
  getMonitoringReportsFull: vi.mocked(getMonitoringReportsFull),
  queryUnityCatalogTableGeneric: vi.mocked(queryUnityCatalogTableGeneric),
};

describe('MonitoringReports', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    canAccessMock.mockReturnValue(true);

    apiMocks.getMonitoringReportsFull.mockResolvedValue({
      data_product_usage: {
        items: [
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
            usage_date: '2026-05-24',
            data_product_id: 'catalog.finance.risk',
            data_product_name: 'Endance Risk Dataset',
            consumer_id: 'consumer-2',
            consumer_name: 'Risk',
            cloud_provider: 'aws',
            source_lz_id: 'lz-finance',
            subscription_or_account_id: 'acct-1',
            request_count: 8,
            rows_read: 500,
            rows_written: 20,
            data_read_bytes: 1024,
            data_written_bytes: 512,
            duration_seconds: 45,
            cost_usd: 40,
            last_used_at: '2026-05-24T10:00:00Z',
          },
        ],
        total: 2,
        limit: 200,
        offset: 0,
        period: { start: '2026-04-25', end: '2026-05-25' },
      },
      usage_trends: {
        grain: 'day',
        items: [{
          period_start: '2026-05-24',
          data_product_count: 2,
          consumer_count: 2,
          request_count: 18,
          rows_read: 1500,
          rows_written: 70,
          data_read_bytes: 3072,
          data_written_bytes: 1536,
          cost_usd: 140,
        }],
        period: { start: '2026-04-25', end: '2026-05-25' },
      },
      standard_checks: {
        items: [
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
            no_check_reasons: [],
            evaluated_at: '2026-05-25T08:00:00Z',
          },
        ],
        total: 1,
        limit: 200,
        offset: 0,
      },
      landing_zones: {
        items: [
          { lz_id: 'lz-crm', lz_name: 'analytics-prod', cloud_provider: 'azure', subscription_or_account_id: 'sub-1', environment: 'prod', ba_name: 'CRM', valid_from: '2026-01-01' },
          { lz_id: 'lz-finance', lz_name: 'finance-prod', cloud_provider: 'aws', subscription_or_account_id: 'acct-1', environment: 'prod', ba_name: 'Endance', valid_from: '2026-01-01' },
        ],
        total: 2,
      },
      security_alerts: { items: [], total: 0, limit: 200, offset: 0 },
      computes: {
        items: [
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
        ],
      },
      pipelines: {
        items: [
          {
            run_id: 'run-1',
            pipeline_id: 'pipe-1',
            pipeline_name: 'crm_customer_refresh',
            cloud_provider: 'azure',
            source_lz_id: 'lz-crm',
            pipeline_type: 'job',
            trigger_type: 'scheduled',
            status: 'failed',
            start_time: '2026-05-25T07:00:00Z',
            end_time: '2026-05-25T07:10:00Z',
            duration_seconds: 600,
            error_message: 'Notebook failed',
          },
          {
            run_id: 'run-2',
            pipeline_id: 'pipe-2',
            pipeline_name: 'finance_risk_refresh',
            cloud_provider: 'aws',
            source_lz_id: 'lz-finance',
            pipeline_type: 'job',
            trigger_type: 'scheduled',
            status: 'succeeded',
            start_time: '2026-05-25T07:00:00Z',
            end_time: '2026-05-25T07:05:00Z',
            duration_seconds: 300,
            error_message: null,
          },
        ],
        total: 2,
        limit: 200,
        offset: 0,
      },
      cost_summary: {
        total_usd: 140,
        by_cloud: { azure: 100, aws: 40 },
        by_service: [],
        period: { start: '2026-04-25', end: '2026-05-25' },
      },
      costs_by_service: { items: [] },
      governance: {
        global_score_pct: 50,
        compliant_count: 0,
        no_compliant_count: 1,
        total_evaluated: 1,
        by_landing_zone: [
          {
            cloud_provider: 'azure',
            source_lz_id: 'lz-crm',
            subscription_or_account_id: 'sub-1',
            compliant_count: 0,
            no_compliant_count: 1,
            total_evaluated: 1,
            score_pct: 50,
          },
        ],
      },
    });
    apiMocks.queryUnityCatalogTableGeneric.mockResolvedValue({
      Status: 'SUCCESS',
      FullTableName: 'it.ba_data_connect_monitoring__d.curated_activity_runs',
      RowsRetrieved: 1,
      ColumnsCount: 10,
      Columns: ['nom_script', 'nom_table', 'date_maj', 'nombre_ligne', 'statut', 'erreur', 'dt_debt_traitement', 'dt_fin_traitement', 'job_name', 'job_id', 'run_id'],
      Data: [['script.py', 'table_a', '2026-05-24T10:00:00Z', 42, 'OK', '', '2026-05-24T10:00:00Z', '2026-05-24T10:01:00Z', 'job_a', 'job-1', 'run-1']],
      Rows: [
        {
          nom_script: 'script.py',
          nom_table: 'table_a',
          date_maj: '2026-05-24T10:00:00Z',
          nombre_ligne: 42,
          statut: 'OK',
          erreur: '',
          dt_debt_traitement: '2026-05-24T10:00:00Z',
          dt_fin_traitement: '2026-05-24T10:01:00Z',
          job_name: 'job_a',
          job_id: 'job-1',
          run_id: 'run-1',
        },
      ],
      SqlQuery: 'SELECT * FROM it.ba_data_connect_monitoring__d.curated_activity_runs',
      ExecutionTime: 0.1,
      data: {
        columns: ['nom_script', 'nom_table', 'date_maj', 'nombre_ligne', 'statut', 'erreur', 'dt_debt_traitement', 'dt_fin_traitement', 'job_name', 'job_id', 'run_id'],
        rows: [
          {
            nom_script: 'script.py',
            nom_table: 'table_a',
            date_maj: '2026-05-24T10:00:00Z',
            nombre_ligne: 42,
            statut: 'OK',
            erreur: '',
            dt_debt_traitement: '2026-05-24T10:00:00Z',
            dt_fin_traitement: '2026-05-24T10:01:00Z',
            job_name: 'job_a',
            job_id: 'job-1',
            run_id: 'run-1',
          },
        ],
      },
    });
  });

  it('renders an API-backed Databricks report with investigation links', async () => {
    renderWithProviders(<MonitoringReports />, { route: '/monitoringreports' });

    expect(screen.getByRole('button', { name: /Refresh/i })).toBeDisabled();
    expect(await screen.findByText('Immediate conclusion')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export CSV/i })).toBeEnabled();
    expect(screen.queryByText('PDF uniquement')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Exporter PDF/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Format export')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Export JSON/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Databricks is Critical/i)).toBeInTheDocument();
    expect(screen.getByText("Investigation path")).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Data trust/i })).toHaveAttribute('href', '/data-product-usage');
    expect(screen.getByRole('link', { name: /PO priority/i })).toHaveAttribute('href', '/databricks/governance');
    expect(screen.getByRole('link', { name: /Budget Databricks/i })).toHaveAttribute('href', '/databricks/finops');
    expect(screen.getByText('Jobs failed vs success')).toBeInTheDocument();
    expect(screen.getByText('Top actions')).toBeInTheDocument();
    expect(screen.getByText(/Fix job crm_customer_refresh failed/i)).toBeInTheDocument();
    expect(screen.getByText('Databricks summary report')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Compute Databricks/i })).toHaveAttribute('href', '/databricks');
    expect(screen.getByRole('link', { name: /Jobs and pipelines/i })).toHaveAttribute('href', '/pipelines');
    expect(screen.getByRole('link', { name: /Governance Databricks/i })).toHaveAttribute('href', '/databricks/governance');
    expect(screen.getAllByRole('link', { name: /Unity Catalog/i }).some((link) => link.getAttribute('href') === '/unitycatalogexplorer')).toBe(true);
    expect(screen.getAllByText('Critical').length).toBeGreaterThan(0);
    expect(apiMocks.getMonitoringReportsFull).toHaveBeenCalledWith(expect.objectContaining({
      usage_limit: 200,
      list_limit: 200,
    }));
  });

  it('uses the global header scope instead of a local report scope filter', async () => {
    renderWithProviders(<MonitoringReports />, { route: '/monitoringreports' });

    expect(await screen.findByText('Immediate conclusion')).toBeInTheDocument();
    expect(screen.queryByText('Report scope')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Cloud')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Domain')).not.toBeInTheDocument();
    expect(apiMocks.getMonitoringReportsFull).toHaveBeenCalledWith(expect.objectContaining({
      usage_limit: 200,
      list_limit: 200,
    }));
  });

  it('skips the raw-table panel for a project-scoped caller and says why', async () => {
    // curated_activity_runs is read through the Unity Catalog explorer, which the
    // backend reserves for unrestricted callers: firing the request would only
    // return a 403 the user cannot act on.
    canAccessMock.mockImplementation((key: string) => key !== 'page:unity-catalog');

    renderWithProviders(<MonitoringReports />, { route: '/monitoringreports' });

    expect(await screen.findByText('Immediate conclusion')).toBeInTheDocument();
    expect(screen.getByText('Outside your project scope')).toBeInTheDocument();
    expect(screen.getByText(/reserved for platform admins/i)).toBeInTheDocument();
    expect(apiMocks.queryUnityCatalogTableGeneric).not.toHaveBeenCalled();
  });

  it('loads the raw-table panel for an unrestricted caller', async () => {
    renderWithProviders(<MonitoringReports />, { route: '/monitoringreports' });

    expect(await screen.findByText('Immediate conclusion')).toBeInTheDocument();
    expect(screen.queryByText('Outside your project scope')).not.toBeInTheDocument();
    expect(apiMocks.queryUnityCatalogTableGeneric).toHaveBeenCalled();
  });
});
