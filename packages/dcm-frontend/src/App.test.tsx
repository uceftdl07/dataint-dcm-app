import { render, screen } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';
import { protectedRoutes, routeRedirects } from './app-routes';

vi.mock('./components/MsalTokenProvider', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));

vi.mock('./components/ProtectedRoute', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));

vi.mock('./components/Header', () => ({
  default: () => <header>Header</header>,
}));

vi.mock('./components/Sidebar', () => ({
  default: () => <aside>Sidebar</aside>,
}));

vi.mock('./components/GlobalLoadingSpinner', () => ({
  GlobalLoadingSpinner: () => null,
}));

vi.mock('./pages/LandingPage', () => ({
  default: () => <h1>Landing route</h1>,
}));

vi.mock('./pages/Dashboard', () => ({
  default: () => <h1>Dashboard route</h1>,
}));

describe('app route configuration', () => {
  it('keeps representative protected URLs registered', () => {
    const paths = protectedRoutes.map((route) => route.path);

    expect(paths).toEqual(expect.arrayContaining([
      '/dashboard',
      '/pipelines',
      '/datafactory',
      '/databricks',
      '/talk-to-data',
      '/admin',
      '/settings',
    ]));
  });

  it('keeps protected paths unique', () => {
    const paths = protectedRoutes.map((route) => route.path);

    expect(new Set(paths).size).toBe(paths.length);
  });

  it('preserves legacy redirect routes', () => {
    expect(routeRedirects).toEqual([
      { from: '/talk-to-your-data', to: '/talk-to-data' },
      { from: '/collection-status', to: '/status' },
      { from: '/database', to: '/databases' },
      { from: '/database/dashboard', to: '/databases' },
      { from: '/database/alerts', to: '/databasealerts' },
      { from: '/database/finops', to: '/databasefinops' },
      { from: '/database/governance', to: '/databasegovernance' },
      { from: '/databricks-genie-obs', to: '/databricks/insights/genie-obs' },
      { from: '/databricksalerts', to: '/databricks/alerts' },
      { from: '/databricksfinops', to: '/databricks/finops' },
      { from: '/databricksgovernance', to: '/databricks/governance' },
      { from: '/databricks/security-alerts', to: '/databricks/alerts' },
      { from: '/databricks/costs', to: '/databricks/finops' },
    ]);
  });
});

describe('App routing', () => {
  it('renders the public landing route', () => {
    window.history.pushState({}, '', '/');

    render(<App />);

    expect(screen.getByText('Landing route')).toBeInTheDocument();
  });

  it('renders a lazy protected route inside the protected layout', async () => {
    window.history.pushState({}, '', '/dashboard');

    render(<App />);

    expect(screen.getByRole('status')).toHaveTextContent('Loading latest view...');
    expect(await screen.findByText('Dashboard route')).toBeInTheDocument();
    expect(screen.getByText('Sidebar')).toBeInTheDocument();
    expect(screen.getByText('Header')).toBeInTheDocument();
  });
});
