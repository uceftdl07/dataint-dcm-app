const GLOBAL_KEY = 'dcm-tour-global-status';
const PAGE_KEY = 'dcm-tour-page-status';

export type GlobalTourStatus = 'pending' | 'completed' | 'skipped';

type PageTourStatus = Record<string, 'completed' | 'skipped'>;

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function getGlobalTourStatus(): GlobalTourStatus {
  return (localStorage.getItem(GLOBAL_KEY) as GlobalTourStatus | null) ?? 'pending';
}

export function setGlobalTourStatus(status: Exclude<GlobalTourStatus, 'pending'>) {
  localStorage.setItem(GLOBAL_KEY, status);
}

export function getPageTourStatus(tourKey: string): 'pending' | 'completed' | 'skipped' {
  const pages = readJson<PageTourStatus>(PAGE_KEY, {});
  return pages[tourKey] ?? 'pending';
}

export function setPageTourStatus(tourKey: string, status: 'completed' | 'skipped') {
  const pages = readJson<PageTourStatus>(PAGE_KEY, {});
  pages[tourKey] = status;
  localStorage.setItem(PAGE_KEY, JSON.stringify(pages));
}

export function resetAllTours() {
  localStorage.removeItem(GLOBAL_KEY);
  localStorage.removeItem(PAGE_KEY);
}
