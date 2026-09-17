import { useEffect, useState, useSyncExternalStore } from 'react';
import { getPendingApiRequestCount, subscribeToApiLoading } from '../api/dcmApiClient';
import { TotalEnergiesIcon } from './icons/te';

const LOADING_DELAY_MS = 150;
const MAX_VISIBLE_MS = 45_000;

function usePendingApiRequestCount(): number {
  return useSyncExternalStore(
    subscribeToApiLoading,
    getPendingApiRequestCount,
    getPendingApiRequestCount,
  );
}

export function GlobalLoadingSpinner() {
  const pendingRequestCount = usePendingApiRequestCount();
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (pendingRequestCount === 0) {
      setIsVisible(false);
      return;
    }

    const showTimer = window.setTimeout(() => setIsVisible(true), LOADING_DELAY_MS);
    const hideTimer = window.setTimeout(() => setIsVisible(false), MAX_VISIBLE_MS);

    return () => {
      window.clearTimeout(showTimer);
      window.clearTimeout(hideTimer);
    };
  }, [pendingRequestCount]);

  if (!isVisible) return null;

  return (
    <div
      className="pointer-events-none fixed inset-0 z-[70] flex items-center justify-center px-4"
      role="status"
      aria-live="polite"
      aria-label="Loading data"
    >
      <div className="relative flex size-20 items-center justify-center" aria-hidden="true">
        <div className="absolute inset-0 rounded-full bg-background/35 blur-xl" />
        <div className="absolute inset-1 rounded-full border border-primary/10" />
        <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-r-tdf-teal border-t-tdf-blue [animation-duration:950ms]" />
        <div className="absolute inset-3 animate-ping rounded-full border border-tdf-purple/30 [animation-duration:1.7s]" />
        <div className="relative flex size-12 animate-pulse items-center justify-center rounded-2xl bg-background/70 shadow-lg shadow-primary/10 ring-1 ring-border/50 backdrop-blur-md">
          <TotalEnergiesIcon className="h-7 w-9" />
        </div>
      </div>
      <span className="sr-only">Loading data</span>
    </div>
  );
}
