/**
 * Utility for acquiring an MSAL access token for API calls.
 *
 * Usage:
 * ```ts
 * const token = await acquireAccessToken(msalInstance);
 * fetch(url, { headers: { Authorization: `Bearer ${token}` } });
 * ```
 */

import type { IPublicClientApplication } from "@azure/msal-browser";

const API_SCOPES = import.meta.env.VITE_AZURE_SCOPE
  ? import.meta.env.VITE_AZURE_SCOPE.split(",").map((s: string) => s.trim()).filter(Boolean)
  : [];

export function peekJwtClaims(token: string): Record<string, unknown> | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(normalized)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Audiences the frontend expects from VITE_AZURE_SCOPE (api://uuid/scope → api://uuid + uuid). */
export function expectedAudiencesFromScope(): Set<string> {
  const audiences = new Set<string>();
  for (const scope of API_SCOPES) {
    if (scope.startsWith("api://") && scope.includes("/")) {
      const appIdUri = scope.slice(0, scope.lastIndexOf("/"));
      audiences.add(appIdUri);
      audiences.add(appIdUri.replace(/^api:\/\//, ""));
    } else if (scope) {
      audiences.add(scope);
    }
  }
  return audiences;
}

export function tokenAudienceMatchesScope(claims: Record<string, unknown>): boolean {
  const expected = expectedAudiencesFromScope();
  if (expected.size === 0) return true;
  const aud = claims.aud;
  if (typeof aud === "string") return expected.has(aud);
  if (Array.isArray(aud)) return aud.some((value) => expected.has(String(value)));
  return false;
}

export async function acquireAccessToken(msalInstance: IPublicClientApplication, forceRefresh = false): Promise<string | null> {
  const activeAccount = msalInstance.getActiveAccount();
  const accounts = msalInstance.getAllAccounts();

  if (!activeAccount && accounts.length === 0) {
    console.warn("⚠️ [AUTH] No connected user");
    return null;
  }

  const account = activeAccount || accounts[0];
  const scopes = API_SCOPES.length > 0 ? API_SCOPES : ["User.Read"];

  if (API_SCOPES.length === 0) {
    console.warn("⚠️ [AUTH] VITE_AZURE_SCOPE is empty — falling back to User.Read (API Gateway will reject)");
  }

  try {
    const response = await msalInstance.acquireTokenSilent({ 
      scopes, 
      account,
      forceRefresh // force refresh on retry
    });
    return response.accessToken;
  } catch (silentError) {
    console.warn("⚠️ [AUTH] Silent token acquisition failed, trying popup...", silentError);
    try {
      const response = await msalInstance.acquireTokenPopup({ scopes, account });
      return response.accessToken;
    } catch (popupError) {
      console.error("❌ [AUTH] Unable to acquire API access token:", popupError);
      return null;
    }
  }
}
