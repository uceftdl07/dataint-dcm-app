const CACHE_KEY_PREFIX = 'dcm:user-verification:';

export interface CachedUserVerification {
  isRegistered: boolean;
  accountStatus: 'active';
  userEmail: string;
  verifiedAt: number;
}

function cacheKey(accountId: string): string {
  return `${CACHE_KEY_PREFIX}${accountId}`;
}

export function readUserVerificationCache(accountId: string): CachedUserVerification | null {
  try {
    const raw = sessionStorage.getItem(cacheKey(accountId));
    if (!raw) return null;
    return JSON.parse(raw) as CachedUserVerification;
  } catch {
    return null;
  }
}

export function writeUserVerificationCache(
  accountId: string,
  value: CachedUserVerification,
): void {
  sessionStorage.setItem(cacheKey(accountId), JSON.stringify(value));
}

export function clearUserVerificationCache(accountId?: string): void {
  if (accountId) {
    sessionStorage.removeItem(cacheKey(accountId));
    return;
  }

  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index);
    if (key?.startsWith(CACHE_KEY_PREFIX)) {
      sessionStorage.removeItem(key);
    }
  }
}
