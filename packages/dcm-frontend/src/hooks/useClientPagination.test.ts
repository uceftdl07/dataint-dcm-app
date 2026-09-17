import { describe, expect, it } from 'vitest';
import { useClientPagination } from './useClientPagination';
import { renderHook, act } from '@testing-library/react';

describe('useClientPagination', () => {
  const items = Array.from({ length: 25 }, (_, index) => ({ id: index + 1 }));

  it('returns first page by default', () => {
    const { result } = renderHook(() => useClientPagination(items, 10));

    expect(result.current.currentPage).toBe(1);
    expect(result.current.pageItems).toHaveLength(10);
    expect(result.current.pageItems[0].id).toBe(1);
    expect(result.current.totalPages).toBe(3);
    expect(result.current.hasNextPage).toBe(true);
    expect(result.current.hasPreviousPage).toBe(false);
  });

  it('navigates to next page', () => {
    const { result } = renderHook(() => useClientPagination(items, 10));

    act(() => {
      result.current.nextPage();
    });

    expect(result.current.currentPage).toBe(2);
    expect(result.current.pageItems[0].id).toBe(11);
    expect(result.current.hasPreviousPage).toBe(true);
  });

  it('resets to page 1 when item count changes', () => {
    const { result, rerender } = renderHook(
      ({ list }) => useClientPagination(list, 10),
      { initialProps: { list: items } },
    );

    act(() => {
      result.current.goToPage(3);
    });
    expect(result.current.currentPage).toBe(3);

    rerender({ list: items.slice(0, 5) });

    expect(result.current.currentPage).toBe(1);
    expect(result.current.totalPages).toBe(1);
  });
});
