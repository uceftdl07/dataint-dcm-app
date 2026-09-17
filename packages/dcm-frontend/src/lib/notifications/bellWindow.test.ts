import { describe, expect, it } from 'vitest';
import { BELL_WINDOW_DAYS, getBellWindowApiParams } from './bellWindow';

describe('getBellWindowApiParams', () => {
  it('returns a 90-day sliding window ending today', () => {
    const reference = new Date('2026-06-04T15:30:00Z');
    const { start_date, end_date } = getBellWindowApiParams(reference);

    expect(end_date).toBe('2026-06-04');
    expect(start_date).toBe('2026-03-06');
    expect(BELL_WINDOW_DAYS).toBe(90);
  });
});
