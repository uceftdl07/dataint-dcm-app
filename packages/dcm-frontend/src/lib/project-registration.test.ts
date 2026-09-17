import { describe, expect, it } from 'vitest';
import type { ReferenceBusinessApplication } from '../types/api';
import { deriveBusinessAppOptions } from './project-registration';

function ba(overrides: Partial<ReferenceBusinessApplication>): ReferenceBusinessApplication {
  return {
    businessApplicationId: 'ba-1',
    businessApplicationName: 'Payments',
    ...overrides,
  };
}

describe('deriveBusinessAppOptions', () => {
  it('maps id + name and sorts by label', () => {
    const options = deriveBusinessAppOptions([
      ba({ businessApplicationId: 'ba-z', businessApplicationName: 'Zebra' }),
      ba({ businessApplicationId: 'ba-a', businessApplicationName: 'Alpha' }),
    ]);
    expect(options).toEqual([
      { businessAppId: 'ba-a', label: 'Alpha' },
      { businessAppId: 'ba-z', label: 'Zebra' },
    ]);
  });

  it('falls back to the id when the name is blank', () => {
    const options = deriveBusinessAppOptions([
      ba({ businessApplicationId: 'ba-blank', businessApplicationName: '  ' }),
    ]);
    expect(options[0]).toEqual({ businessAppId: 'ba-blank', label: 'ba-blank' });
  });
});
