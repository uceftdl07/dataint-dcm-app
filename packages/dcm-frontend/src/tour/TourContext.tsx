import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { WelcomeTourModal } from './WelcomeTourModal';
import { PageTourPrompt } from './PageTourPrompt';
import { resolveTourKey } from './resolve-tour-key';
import { runTour } from './run-tour';
import {
  getGlobalTourStatus,
  getPageTourStatus,
  resetAllTours,
  setGlobalTourStatus,
  setPageTourStatus,
} from './tour-storage';
import { getPageTourSteps, getWelcomeTourSteps } from './tour-steps';

interface TourContextValue {
  startPageTour: (tourKey?: string) => void;
  startWelcomeTour: () => void;
  resetTours: () => void;
  tourKey: string;
}

const TourContext = createContext<TourContextValue | null>(null);

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext);
  if (!ctx) throw new Error('useTour must be used within TourProvider');
  return ctx;
}

export const TourProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { pathname } = useLocation();
  const tourKey = resolveTourKey(pathname);
  const [showWelcome, setShowWelcome] = useState(false);
  const [showPagePrompt, setShowPagePrompt] = useState(false);

  const startPageTour = useCallback(
    (key?: string) => {
      const activeKey = key ?? tourKey;
      setShowPagePrompt(false);

      // Let layout paint before highlighting targets
      window.setTimeout(() => {
        runTour({
          steps: getPageTourSteps(activeKey),
          onComplete: () => setPageTourStatus(activeKey, 'completed'),
          onSkip: () => setPageTourStatus(activeKey, 'skipped'),
        });
      }, 120);
    },
    [tourKey],
  );

  const startWelcomeTour = useCallback(() => {
    setShowWelcome(false);
    window.setTimeout(() => {
      runTour({
        steps: getWelcomeTourSteps(),
        onComplete: () => {
          setGlobalTourStatus('completed');
          setPageTourStatus('dashboard', 'completed');
        },
        onSkip: () => setGlobalTourStatus('skipped'),
      });
    }, 120);
  }, []);

  const resetTours = useCallback(() => {
    resetAllTours();
    setShowWelcome(false);
    setShowPagePrompt(false);
  }, []);

  useEffect(() => {
    if (pathname === '/' || pathname.startsWith('/admin')) return;

    const globalStatus = getGlobalTourStatus();

    if (pathname === '/dashboard' && globalStatus === 'pending') {
      const timer = window.setTimeout(() => setShowWelcome(true), 600);
      return () => window.clearTimeout(timer);
    }

    const pageStatus = getPageTourStatus(tourKey);
    if (pageStatus === 'pending' && globalStatus !== 'pending') {
      const timer = window.setTimeout(() => setShowPagePrompt(true), 800);
      return () => window.clearTimeout(timer);
    }
  }, [pathname, tourKey]);

  const value = useMemo(
    () => ({ startPageTour, startWelcomeTour, resetTours, tourKey }),
    [startPageTour, startWelcomeTour, resetTours, tourKey],
  );

  return (
    <TourContext.Provider value={value}>
      {children}
      {showWelcome && (
        <WelcomeTourModal
          onAccept={() => startWelcomeTour()}
          onDecline={() => {
            setGlobalTourStatus('skipped');
            setShowWelcome(false);
          }}
        />
      )}
      {showPagePrompt && (
        <PageTourPrompt
          tourKey={tourKey}
          onStart={() => startPageTour()}
          onDismiss={() => {
            setPageTourStatus(tourKey, 'skipped');
            setShowPagePrompt(false);
          }}
        />
      )}
    </TourContext.Provider>
  );
};
