/**
 * DCM Frontend — root application component.
 *
 * Authentication architecture:
 * - MsalProvider (main.tsx) wraps the whole application
 * - MsalTokenProvider registers the token getter for API calls
 * - ProtectedRoute protects all private routes
 * - / (LandingPage) is the public page with the sign-in button
 * - Auth is only triggered when the user clicks Sign in on the landing page
 *
 * Layout: Sidebar (sticky) + page content for protected routes.
 */

import React, { Suspense } from 'react';
import { Navigate, Route, BrowserRouter as Router, Routes, useLocation, useNavigate } from 'react-router-dom';
import { protectedRoutes, routeRedirects } from './app-routes';
import { GlobalLoadingSpinner } from './components/GlobalLoadingSpinner';
import Header from './components/Header';
import MsalTokenProvider from './components/MsalTokenProvider';
import ProtectedRoute from './components/ProtectedRoute';
import { RoutePermissionWrapper } from './components/RoutePermissionWrapper';
import Sidebar from './components/Sidebar';
import { MonitoringScopeProvider } from './contexts/MonitoringScopeContext';
import { TimeRangeProvider } from './contexts/TimeRangeContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider } from './contexts/ToastContext';
import { DataIQAvatar } from './components/DataIQAvatar';
import { DATAIQ_BRAND } from './config/dataiq';
import LandingPage from './pages/LandingPage';
import { TourProvider } from './tour/TourContext';

const lazyProtectedRoutes = protectedRoutes.map((route) => ({
  ...route,
  Component: React.lazy(route.importPage),
}));

const PageLoadingFallback: React.FC = () => (
  <div role="status" aria-live="polite" className="flex min-h-[320px] items-center justify-center p-8">
    <div className="text-center">
      <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-b-2 border-primary" />
      <p className="text-sm font-medium text-muted-foreground">Loading latest view...</p>
    </div>
  </div>
);

/**
 * Layout for protected pages (with Sidebar + Header)
 */
const DataIQPageBubble: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();

  if (location.pathname === '/talk-to-data' || location.pathname === '/admin') return null;

  return (
    <button
      type="button"
      onClick={() => navigate('/talk-to-data')}
      data-tour="dataiq-assistant"
      className="fixed bottom-5 right-5 z-40 hidden items-center justify-center rounded-full p-0.5 shadow-xl shadow-primary/20 ring-2 ring-primary/20 transition-all hover:-translate-y-0.5 hover:scale-[1.04] active:scale-95 xl:flex"
      aria-label={DATAIQ_BRAND.openLabel}
      title={DATAIQ_BRAND.openLabel}
    >
      <DataIQAvatar size="sm" ring />
    </button>
  );
};

const ProtectedLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <Header />
        <main
          key={location.pathname}
          data-tour="page-content"
          className="guardian-scrollbar min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
        >
          {children}
        </main>
        <DataIQPageBubble />
        <GlobalLoadingSpinner />
      </div>
    </div>
  );
};

function renderProtectedPage(Component: React.LazyExoticComponent<React.ComponentType>) {
  return (
    <ProtectedRoute>
      <ProtectedLayout>
        <RoutePermissionWrapper>
          <Suspense fallback={<PageLoadingFallback />}>
            <Component />
          </Suspense>
        </RoutePermissionWrapper>
      </ProtectedLayout>
    </ProtectedRoute>
  );
}

const App: React.FC = () => (
  <Router future={{ v7_relativeSplatPath: true }}>
    <MsalTokenProvider>
      <ToastProvider>
        <ThemeProvider>
          <TimeRangeProvider defaultDays={30}>
            <MonitoringScopeProvider>
              <TourProvider>
              <Routes>
                {/* Public Route: Landing Page with Login */}
                <Route path="/" element={<LandingPage />} />

                {lazyProtectedRoutes.map(({ path, Component }) => (
                  <Route key={path} path={path} element={renderProtectedPage(Component)} />
                ))}

                {routeRedirects.map(({ from, to }) => (
                  <Route key={from} path={from} element={<Navigate to={to} replace />} />
                ))}

                {/* Catch-all: redirect to home */}
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
              </TourProvider>
            </MonitoringScopeProvider>
          </TimeRangeProvider>
        </ThemeProvider>
      </ToastProvider>
    </MsalTokenProvider>
  </Router>
);

export default App;
