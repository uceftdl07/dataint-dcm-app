import type { ReactNode } from 'react';
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { useDatabricksFocusView } from './useDatabricksFocusView';

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={['/databricks']}>{children}</MemoryRouter>;
}

describe('useDatabricksFocusView', () => {
  it('sets view query param when opening a focus view', () => {
    const { result } = renderHook(() => useDatabricksFocusView(), { wrapper });

    act(() => {
      result.current.openView('jobs');
    });

    expect(result.current.view).toBe('jobs');
  });

  it('sets cluster state in the URL when opening running clusters', () => {
    const { result } = renderHook(() => useDatabricksFocusView(), { wrapper });

    act(() => {
      result.current.openView('clusters', { state: 'running' });
    });

    expect(result.current.view).toBe('clusters');
    expect(result.current.clusterState).toBe('running');
  });

  it('clears view when toggling the same card', () => {
    const { result } = renderHook(() => useDatabricksFocusView(), { wrapper });

    act(() => {
      result.current.openView('costs');
    });
    expect(result.current.view).toBe('costs');

    act(() => {
      result.current.openView('costs');
    });
    expect(result.current.view).toBeNull();
  });
});
