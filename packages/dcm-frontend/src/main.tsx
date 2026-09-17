/**
 * DCM Frontend entry point.
 *
 * Authentication is managed by AuthProvider in App.tsx.
 * The API client token getter is registered dynamically.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';

import App from './App';
import './index.css';
import { MsalProvider } from '@azure/msal-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DcmApiError } from './api/dcmApiClient';
import { msalInstance } from './config/msal';
import { QUERY_STALE_HEALTH_MS } from './hooks/query-config';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Extra retries for gateway blips (ECS recycle / ALB drain) so UI recovers without hard refresh.
      retry: (failureCount, error) => {
        if (error instanceof DcmApiError && [502, 503, 504].includes(error.statusCode)) {
          return failureCount < 3;
        }
        return failureCount < 1;
      },
      retryDelay: (attemptIndex) => Math.min(500 * 2 ** attemptIndex, 4000),
      refetchOnWindowFocus: true,
      staleTime: QUERY_STALE_HEALTH_MS,
    },
  },
});

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <MsalProvider instance={msalInstance}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </MsalProvider>
  </React.StrictMode>
);
