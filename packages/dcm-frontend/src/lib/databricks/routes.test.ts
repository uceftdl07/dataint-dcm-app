import { describe, expect, it } from 'vitest';
import {
  isDatabricksModuleRoute,
  showsDatabricksWorkspaceFilter,
  showsGlobalHeaderDateRange,
  showsGlobalHeaderFilters,
  showsGlobalHeaderTimePresets,
  showsLandingZoneFilter,
} from './routes';

describe('isDatabricksModuleRoute', () => {
  it('matches Databricks module routes', () => {
    expect(isDatabricksModuleRoute('/databricks')).toBe(true);
    expect(isDatabricksModuleRoute('/databricks/clusters')).toBe(true);
    expect(isDatabricksModuleRoute('/monitoringreports')).toBe(true);
  });

  it('does not match legacy flat databricks routes', () => {
    expect(isDatabricksModuleRoute('/databricksalerts')).toBe(false);
  });

  it('does not match other modules', () => {
    expect(isDatabricksModuleRoute('/databases')).toBe(false);
    expect(isDatabricksModuleRoute('/datafactory')).toBe(false);
    expect(isDatabricksModuleRoute('/dashboard')).toBe(false);
  });
});

describe('showsDatabricksWorkspaceFilter', () => {
  it('includes only /databricks routes', () => {
    expect(showsDatabricksWorkspaceFilter('/databricks')).toBe(true);
    expect(showsDatabricksWorkspaceFilter('/databricks/clusters')).toBe(true);
    expect(showsDatabricksWorkspaceFilter('/databricks/security-alerts')).toBe(true);
  });

  it('excludes dashboard and other global modules', () => {
    expect(showsDatabricksWorkspaceFilter('/dashboard')).toBe(false);
    expect(showsDatabricksWorkspaceFilter('/databases')).toBe(false);
    expect(showsDatabricksWorkspaceFilter('/databricksalerts')).toBe(false);
    expect(showsDatabricksWorkspaceFilter('/datafactory')).toBe(false);
  });

  it('excludes embedded insights routes', () => {
    expect(showsDatabricksWorkspaceFilter('/databricks/insights')).toBe(false);
    expect(showsDatabricksWorkspaceFilter('/databricks/insights/genie-obs')).toBe(false);
  });
});

describe('showsGlobalHeaderFilters', () => {
  it('excludes insights routes from global header filters', () => {
    expect(showsGlobalHeaderFilters('/databricks/insights')).toBe(false);
    expect(showsGlobalHeaderFilters('/databricks/insights/genie-obs')).toBe(false);
  });

  it('keeps global header filters on operational pages', () => {
    expect(showsGlobalHeaderFilters('/databricks')).toBe(true);
    expect(showsGlobalHeaderFilters('/dashboard')).toBe(true);
  });
});

describe('showsLandingZoneFilter', () => {
  it('shows it on the workspace-keyed Databricks pages', () => {
    // These read gold_dbx_workflow_* and the compute metrics tables: keyed on
    // workspace_id. The backend resolves the selected LZ to its workspaces
    // (dim_dbx_workspace ⋈ dim_landing_zone), so the control scopes them too.
    expect(showsLandingZoneFilter('/databricks')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/overview')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/workflows')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/workflows/42/runs/7')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/cluster')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/sql-warehouse')).toBe(true);
  });

  it('keeps it on the Databricks pages whose tables are LZ-keyed', () => {
    expect(showsLandingZoneFilter('/databricks/alerts')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/finops')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/governance')).toBe(true);
  });

  it('keeps it on every other module', () => {
    expect(showsLandingZoneFilter('/dashboard')).toBe(true);
    expect(showsLandingZoneFilter('/databases')).toBe(true);
    expect(showsLandingZoneFilter('/datafactory')).toBe(true);
    // A flat legacy route is not part of the Databricks module.
    expect(showsLandingZoneFilter('/databricksalerts')).toBe(true);
  });

  it('follows the routes that carry no global header filter at all', () => {
    expect(showsLandingZoneFilter('/databricks/insights')).toBe(false);
    expect(showsLandingZoneFilter('/talk-to-data')).toBe(false);
    expect(showsLandingZoneFilter('/admin')).toBe(false);
  });
});

describe('showsGlobalHeaderDateRange', () => {
  it('hides the range on compute pages served by predefined windows', () => {
    expect(showsGlobalHeaderDateRange('/databricks/cluster')).toBe(false);
    expect(showsGlobalHeaderDateRange('/databricks/sql-warehouse')).toBe(false);
  });

  it('keeps the rest of the global filters on those pages', () => {
    // Only the dates are inert there: workspace / landing zone still narrow.
    expect(showsGlobalHeaderFilters('/databricks/cluster')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/sql-warehouse')).toBe(true);
  });

  it('keeps the range where a table really filters on bounds', () => {
    expect(showsGlobalHeaderDateRange('/databricks/compute/recommendations')).toBe(true);
    expect(showsGlobalHeaderDateRange('/databricks/workflows')).toBe(true);
    expect(showsGlobalHeaderDateRange('/dashboard')).toBe(true);
  });

  it('does not match the legacy plural clusters route on a prefix', () => {
    // `/databricks/clusters` is a different page, and one that still filters.
    expect(showsGlobalHeaderDateRange('/databricks/clusters')).toBe(true);
  });

  it('stays false where no global filter shows at all', () => {
    expect(showsGlobalHeaderDateRange('/databricks/insights')).toBe(false);
    expect(showsGlobalHeaderDateRange('/talk-to-data')).toBe(false);
  });
});

describe('showsGlobalHeaderTimePresets', () => {
  it('hides 30d/90d/6m/1y on Databricks Overview but keeps page eligible for From/To', () => {
    expect(showsGlobalHeaderTimePresets('/databricks/overview')).toBe(false);
    expect(showsGlobalHeaderFilters('/databricks/overview')).toBe(true);
  });

  it('keeps time presets on other Databricks pages', () => {
    expect(showsGlobalHeaderTimePresets('/databricks')).toBe(true);
    expect(showsGlobalHeaderTimePresets('/databricks/workflows')).toBe(true);
  });

  it('drops the presets wherever the range itself is hidden', () => {
    // They write into that same range — alone they would be a control that
    // filters nothing.
    expect(showsGlobalHeaderTimePresets('/databricks/cluster')).toBe(false);
    expect(showsGlobalHeaderTimePresets('/databricks/sql-warehouse')).toBe(false);
  });
});

describe('isUcUsageRoute', () => {
  it('hides the workspace and landing-zone filters on the UC usage pages', () => {
    // Les 8 tables `gold_dbx_usage_*` ne portent ni workspace_id ni source_lz_id.
    expect(showsDatabricksWorkspaceFilter('/databricks/usage-tables')).toBe(false);
    expect(showsDatabricksWorkspaceFilter('/databricks/usage-governance')).toBe(false);
    expect(showsLandingZoneFilter('/databricks/usage-tables')).toBe(false);
    expect(showsLandingZoneFilter('/databricks/usage-governance')).toBe(false);
  });

  it('keeps the period selector, which Appliquer reads', () => {
    expect(showsGlobalHeaderDateRange('/databricks/usage-tables')).toBe(true);
    expect(showsGlobalHeaderDateRange('/databricks/usage-governance')).toBe(true);
  });

  it('does not spill onto a neighbouring Databricks route', () => {
    expect(showsDatabricksWorkspaceFilter('/databricks/usage-data-product')).toBe(true);
    expect(showsLandingZoneFilter('/databricks/cluster')).toBe(true);
  });
});
