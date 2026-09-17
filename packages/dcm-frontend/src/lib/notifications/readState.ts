const STORAGE_PREFIX = 'dcm:notif-read';

function readKey(userId: string, alertId: string, sourceLzId: string | null | undefined) {
  return `${STORAGE_PREFIX}:${userId}:${alertId}:${sourceLzId ?? 'none'}`;
}

export function isNotificationRead(
  userId: string,
  alertId: string,
  sourceLzId: string | null | undefined,
): boolean {
  if (!userId) {
    return false;
  }
  try {
    return localStorage.getItem(readKey(userId, alertId, sourceLzId)) === '1';
  } catch {
    return false;
  }
}

export function markNotificationRead(
  userId: string,
  alertId: string,
  sourceLzId: string | null | undefined,
): void {
  if (!userId) {
    return;
  }
  try {
    localStorage.setItem(readKey(userId, alertId, sourceLzId), '1');
  } catch {
    // Ignore quota / private mode errors.
  }
}

export function markNotificationsRead(
  userId: string,
  items: Array<{ alertId: string; sourceLzId: string | null | undefined }>,
): void {
  items.forEach((item) => markNotificationRead(userId, item.alertId, item.sourceLzId));
}
