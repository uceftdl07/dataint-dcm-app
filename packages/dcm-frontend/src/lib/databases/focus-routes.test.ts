import { describe, expect, it } from 'vitest';
import { buildDatabaseFocusPath } from './focus-routes';

describe('buildDatabaseFocusPath', () => {
  it('builds path without query for bare view', () => {
    expect(buildDatabaseFocusPath('inventory')).toBe('/databases/inventory');
    expect(buildDatabaseFocusPath('pressure')).toBe('/databases/pressure');
  });

  it('includes availability filter in query', () => {
    expect(buildDatabaseFocusPath('inventory', { avail: 'true' })).toBe('/databases/inventory?avail=true');
    expect(buildDatabaseFocusPath('inventory', { avail: 'false' })).toBe('/databases/inventory?avail=false');
  });

  it('includes engine type and capacity sort in query', () => {
    expect(buildDatabaseFocusPath('inventory', { type: 'postgresql' })).toBe('/databases/inventory?type=postgresql');
    expect(buildDatabaseFocusPath('capacity', { sort: 'connections' })).toBe('/databases/capacity?sort=connections');
  });
});
