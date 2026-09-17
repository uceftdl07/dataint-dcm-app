import { describe, expect, it } from 'vitest';
import { getFocusPageTitle, isFocusDetailRoute, showsHeaderBackButton } from './page-navigation';

describe('page-navigation', () => {
  it('detects focus drill-down routes', () => {
    expect(isFocusDetailRoute('/databricks/workspaces')).toBe(true);
    expect(isFocusDetailRoute('/databricks/clusters')).toBe(true);
    expect(isFocusDetailRoute('/pipelines/runs')).toBe(true);
    expect(isFocusDetailRoute('/databases/inventory')).toBe(true);

    expect(isFocusDetailRoute('/databricks/alerts')).toBe(false);
    expect(isFocusDetailRoute('/databricks/finops')).toBe(false);
    expect(isFocusDetailRoute('/databricks/overview')).toBe(false);
    expect(isFocusDetailRoute('/databricks')).toBe(false);
    expect(isFocusDetailRoute('/dashboard')).toBe(false);
  });

  it('hides header back on focus pages and guide', () => {
    expect(showsHeaderBackButton('/databricks/workspaces')).toBe(false);
    expect(showsHeaderBackButton('/guide/lz-onboarding')).toBe(false);
    expect(showsHeaderBackButton('/dashboard')).toBe(false);

    expect(showsHeaderBackButton('/databricks')).toBe(true);
    expect(showsHeaderBackButton('/databricks/overview')).toBe(true);
    expect(showsHeaderBackButton('/settings')).toBe(true);
  });

  it('resolves focus page titles for the header', () => {
    expect(getFocusPageTitle('/databricks/workspaces')).toBe('Workspace overview');
    expect(getFocusPageTitle('/clusters/inventory')).toBe('Compute inventory');
    expect(getFocusPageTitle('/databricks/alerts')).toBeNull();
  });
});
