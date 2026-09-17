/**
 * Pure helpers for the self-service project register/join forms (feature 016).
 *
 * The public Business-Application catalog (`/reference/business-applications`)
 * only exposes id + display name. Landing-zone / workspace scopes are resolved
 * server-side when the authenticated register endpoint runs.
 */

import type { ReferenceBusinessApplication } from '../types/api';

/** One Business Application option for the register dropdown. */
export interface BusinessAppOption {
  /** BA identifier (`business_application_id`) — also the project id. */
  businessAppId: string;
  /** Human-readable label shown in the dropdown. */
  label: string;
}

/** Map the public BA catalog into sorted dropdown options. */
export function deriveBusinessAppOptions(
  businessApplications: readonly ReferenceBusinessApplication[]
): BusinessAppOption[] {
  return businessApplications
    .map((ba) => ({
      businessAppId: ba.businessApplicationId,
      label: ba.businessApplicationName?.trim() || ba.businessApplicationId,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}
