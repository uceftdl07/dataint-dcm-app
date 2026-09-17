import { describe, expect, it, vi } from 'vitest';
import { getScrollBehavior } from './useMetricSectionFocus';

describe('getScrollBehavior', () => {
  it('returns auto when reduced motion is preferred', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );

    expect(getScrollBehavior()).toBe('auto');
    vi.unstubAllGlobals();
  });

  it('returns smooth when motion is allowed', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );

    expect(getScrollBehavior()).toBe('smooth');
    vi.unstubAllGlobals();
  });
});
