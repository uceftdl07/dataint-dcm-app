import { render, type RenderOptions } from '@testing-library/react';
import { type ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { MonitoringScopeProvider } from '../contexts/MonitoringScopeContext';
import { TimeRangeProvider } from '../contexts/TimeRangeContext';
import { ToastProvider } from '../contexts/ToastContext';
import { QueryClientTestProvider } from './query-client';

interface ProviderOptions {
  route?: string;
}

export function renderWithProviders(
  ui: ReactElement,
  options: RenderOptions & ProviderOptions = {},
) {
  const { route = '/', ...renderOptions } = options;

  return render(
    <MemoryRouter
      initialEntries={[route]}
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <QueryClientTestProvider>
        <ToastProvider>
          <TimeRangeProvider defaultDays={30}>
            <MonitoringScopeProvider>
              {ui}
            </MonitoringScopeProvider>
          </TimeRangeProvider>
        </ToastProvider>
      </QueryClientTestProvider>
    </MemoryRouter>,
    renderOptions,
  );
}

export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';

