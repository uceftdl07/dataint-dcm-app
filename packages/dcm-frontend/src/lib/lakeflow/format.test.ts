import { describe, expect, it } from 'vitest';
import { formatDataFreshness, formatDurationSeconds } from './format';

describe('formatDurationSeconds — NULL-safe (never 0)', () => {
  it('returns a dash for null/undefined instead of 0', () => {
    expect(formatDurationSeconds(null)).toBe('—');
    expect(formatDurationSeconds(undefined)).toBe('—');
  });

  it('returns a dash for negative values', () => {
    expect(formatDurationSeconds(-5)).toBe('—');
  });

  it('formats a real zero as seconds (explicit 0 stays 0 s)', () => {
    expect(formatDurationSeconds(0)).toBe('0 s');
  });
});

describe('formatDataFreshness — derived from as_of', () => {
  it('returns null when as_of is missing or invalid', () => {
    expect(formatDataFreshness(null)).toBeNull();
    expect(formatDataFreshness(undefined)).toBeNull();
    expect(formatDataFreshness('not-a-date')).toBeNull();
  });

  it('computes the age from now, not a static text', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(formatDataFreshness(twoHoursAgo)).toBe('données à ~2 h');
  });

  it('renders minutes for a recent timestamp', () => {
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    expect(formatDataFreshness(tenMinAgo)).toBe('données à ~10 min');
  });

  it('renders days for an old timestamp', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 3600 * 1000).toISOString();
    expect(formatDataFreshness(threeDaysAgo)).toBe('données à ~3 j');
  });
});
