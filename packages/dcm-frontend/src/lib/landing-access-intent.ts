/** Set when a visitor starts "new member → request access" from the public landing page. */
export const ACCESS_REQUEST_INTENT_KEY = 'dcm.openAccessRequest';

export function setAccessRequestIntent() {
  sessionStorage.setItem(ACCESS_REQUEST_INTENT_KEY, '1');
}

export function consumeAccessRequestIntent(): boolean {
  const value = sessionStorage.getItem(ACCESS_REQUEST_INTENT_KEY);
  if (value !== '1') return false;
  sessionStorage.removeItem(ACCESS_REQUEST_INTENT_KEY);
  return true;
}
