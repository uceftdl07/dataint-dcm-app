import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, type RenderHookOptions } from '@testing-library/react';
import { type ReactNode } from 'react';

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

export function QueryClientTestProvider({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={createTestQueryClient()}>
      {children}
    </QueryClientProvider>
  );
}

export function renderHookWithQueryClient<Result, Props>(
  callback: (props: Props) => Result,
  options: Omit<RenderHookOptions<Props>, 'wrapper'> & {
    queryClient?: QueryClient;
  } = {},
) {
  const queryClient = options.queryClient ?? createTestQueryClient();

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return {
    queryClient,
    ...renderHook(callback, { ...options, wrapper }),
  };
}

