/** Shared React Query cache timings for the DCM frontend. */

export const QUERY_STALE_DEFAULT_MS = 5 * 60 * 1000;
export const QUERY_GC_DEFAULT_MS = 10 * 60 * 1000;

export const QUERY_STALE_ADMIN_MS = 2 * 60 * 1000;
export const QUERY_GC_ADMIN_MS = 5 * 60 * 1000;

/** Health checks refresh more often than aggregated page bundles. */
export const QUERY_STALE_HEALTH_MS = 30 * 1000;

/** Collection Status page auto-refresh interval. */
export const HEALTH_POLL_MS = 60_000;

/** Header bell and lightweight preference reads. */
export const QUERY_STALE_NOTIFICATIONS_MS = 60 * 1000;
