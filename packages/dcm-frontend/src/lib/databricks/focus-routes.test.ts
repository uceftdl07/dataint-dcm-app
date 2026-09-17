import { describe, expect, it } from 'vitest';
import {
  assertAllDatabricksWidgetTargetsScoped,
  assertDatabricksWidgetTarget,
  buildDatabricksFocusPath,
  DATABRICKS_MODULE_FOCUS_PATHS,
  DATABRICKS_WIDGET_TARGETS,
  isDatabricksScopedPath,
} from './focus-routes';
import { DATABRICKS_FOCUS_VIEWS } from './focus-view';

describe('isDatabricksScopedPath', () => {
  it('accepts /databricks and nested focus routes', () => {
    expect(isDatabricksScopedPath('/databricks')).toBe(true);
    expect(isDatabricksScopedPath('/databricks/clusters')).toBe(true);
    expect(isDatabricksScopedPath('/databricks/insights/genie-obs')).toBe(true);
  });

  it('rejects global module routes', () => {
    expect(isDatabricksScopedPath('/clusters')).toBe(false);
    expect(isDatabricksScopedPath('/costs')).toBe(false);
    expect(isDatabricksScopedPath('/security')).toBe(false);
    expect(isDatabricksScopedPath('/databricksalerts')).toBe(false);
  });
});

describe('assertDatabricksWidgetTarget', () => {
  it('allows databricks focus paths', () => {
    expect(assertDatabricksWidgetTarget('/databricks/clusters?state=running')).toBe('/databricks/clusters?state=running');
  });

  it('blocks global targets', () => {
    expect(() => assertDatabricksWidgetTarget('/clusters')).toThrow(/must stay under \/databricks/);
    expect(() => assertDatabricksWidgetTarget('/costs')).toThrow(/must stay under \/databricks/);
  });
});

describe('DATABRICKS_MODULE_FOCUS_PATHS', () => {
  it('maps legacy menu targets to full /databricks/** pages', () => {
    expect(DATABRICKS_MODULE_FOCUS_PATHS.alerts).toBe('/databricks/alerts');
    expect(DATABRICKS_MODULE_FOCUS_PATHS.costs).toBe('/databricks/finops');
    expect(DATABRICKS_MODULE_FOCUS_PATHS.governance).toBe('/databricks/governance');
  });
});

describe('DATABRICKS_WIDGET_TARGETS', () => {
  it('keeps every widget target under /databricks/**', () => {
    expect(() => assertAllDatabricksWidgetTargetsScoped()).not.toThrow();
    for (const path of Object.values(DATABRICKS_WIDGET_TARGETS)) {
      expect(path.startsWith('/databricks')).toBe(true);
    }
  });
});

describe('buildDatabricksFocusPath', () => {
  it('builds path without query for bare view', () => {
    expect(buildDatabricksFocusPath('clusters')).toBe('/databricks/clusters');
    expect(buildDatabricksFocusPath('jobs')).toBe('/databricks/jobs');
  });

  it('includes cluster state in query', () => {
    expect(buildDatabricksFocusPath('clusters', { state: 'running' })).toBe('/databricks/clusters?state=running');
    expect(buildDatabricksFocusPath('clusters', { state: 'error' })).toBe('/databricks/clusters?state=error');
  });

  it('includes job status in query', () => {
    expect(buildDatabricksFocusPath('jobs', { jobStatus: 'failed' })).toBe('/databricks/jobs?jobStatus=failed');
  });

  it('combines state and job status when both provided', () => {
    const path = buildDatabricksFocusPath('jobs', { state: 'running', jobStatus: 'failed' });
    expect(path.startsWith('/databricks/jobs?')).toBe(true);
    expect(path).toContain('jobStatus=failed');
    expect(path).toContain('state=running');
  });

  it('covers every focus view under /databricks/**', () => {
    for (const view of DATABRICKS_FOCUS_VIEWS) {
      expect(buildDatabricksFocusPath(view).startsWith('/databricks/')).toBe(true);
    }
  });
});
