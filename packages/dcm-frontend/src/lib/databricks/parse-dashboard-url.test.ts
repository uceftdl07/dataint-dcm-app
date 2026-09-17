import { describe, expect, it } from 'vitest';
import { parseDatabricksDashboardUrl } from './parse-dashboard-url';

describe('parseDatabricksDashboardUrl', () => {
  it('parses a published dashboard URL', () => {
    const result = parseDatabricksDashboardUrl(
      'https://dbc-e25c222e-27eb.cloud.databricks.com/dashboardsv3/01f1666ab90c1d32ba3046df563db745/published?isDbOne=true&o=2505786830871273',
    );

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.workspace_host).toBe('https://dbc-e25c222e-27eb.cloud.databricks.com');
    expect(result.value.workspace_id).toBe('2505786830871273');
    expect(result.value.dashboard_id).toBe('01f1666ab90c1d32ba3046df563db745');
    expect(result.value.suggested_slug).toBe('dashboard-01f1666a');
  });

  it('parses an embed dashboard URL', () => {
    const result = parseDatabricksDashboardUrl(
      'https://totalenergies.databricks.com/embed/dashboardsv3/01f14eebf5b8161cad1b73cdc801d1ec?o=7474644903673004',
    );

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.workspace_host).toBe('https://totalenergies.databricks.com');
    expect(result.value.workspace_id).toBe('7474644903673004');
    expect(result.value.dashboard_id).toBe('01f14eebf5b8161cad1b73cdc801d1ec');
  });

  it('rejects URLs without workspace id', () => {
    const result = parseDatabricksDashboardUrl(
      'https://dbc-e25c222e-27eb.cloud.databricks.com/dashboardsv3/01f1666ab90c1d32ba3046df563db745/published',
    );

    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.error).toContain('?o=');
  });

  it('rejects non-dashboard URLs', () => {
    const result = parseDatabricksDashboardUrl('https://dbc-e25c222e-27eb.cloud.databricks.com/login');

    expect(result.ok).toBe(false);
  });
});
