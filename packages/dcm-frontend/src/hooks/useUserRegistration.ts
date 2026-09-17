/**
 * Hook to verify if the authenticated user is registered in DCM.
 * 
 * This hook is called after Entra ID authentication to check if the user
 * exists in the dcm_app_users table. If not registered, access is denied.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useState } from 'react';
import { useMsal } from '@azure/msal-react';
import type { CurrentDcmUser } from '../types/api';
import { acquireAccessToken, peekJwtClaims, tokenAudienceMatchesScope } from '../lib/auth';
import { currentUserQueryKeys } from './query-keys';
import {
  clearUserVerificationCache,
  readUserVerificationCache,
  writeUserVerificationCache,
} from '../lib/userVerificationCache';

export type AccountStatus =
  | 'active'
  | 'pending'
  | 'inactive'
  | 'not_registered'
  | 'auth_error'
  /** User IS registered in DCM, but Entra ID app registration blocks the connection. */
  | 'app_reg_error'
  | 'verification_error';

interface UserRegistrationState {
  isLoading: boolean;
  isRegistered: boolean | null;
  accountStatus: AccountStatus | null;
  error: string | null;
  userEmail: string | null;
}

interface DcmRegistrationStatus {
  registered: boolean;
  isActive: boolean;
}

/**
 * Unauthenticated check: is this email registered in DCM (dcm_app_users)?
 * Lets us distinguish "no DCM account" from "DCM account OK but Entra ID
 * app registration broken" when token acquisition fails.
 */
async function fetchDcmRegistrationStatus(
  apiBaseUrl: string,
  email: string,
): Promise<DcmRegistrationStatus | null> {
  try {
    const response = await fetch(
      `${apiBaseUrl}/api/v1/access-requests/status?email=${encodeURIComponent(email)}`,
    );
    if (!response.ok) return null;
    const data = await response.json();
    return { registered: Boolean(data.registered), isActive: Boolean(data.is_active) };
  } catch {
    return null;
  }
}

function networkErrorMessage(error: unknown): string {
  if (error instanceof TypeError && error.message === 'Failed to fetch') {
    return 'Cannot reach the DCM backend. In dev, start dcm-backend on port 8000, then retry.';
  }
  return error instanceof Error ? error.message : 'Unable to reach the API';
}

export function useUserRegistration(): UserRegistrationState & { retry: () => void } {
  const queryClient = useQueryClient();
  const { instance, accounts } = useMsal();
  const account = accounts[0] ?? null;
  const accountId = account?.localAccountId ?? null;
  const userEmail = account?.username || account?.name || null;

  const cachedSuccess =
    accountId && userEmail
      ? readUserVerificationCache(accountId)
      : null;
  const hasCachedSuccess = cachedSuccess?.isRegistered === true;

  const [state, setState] = useState<UserRegistrationState>(() => ({
    isLoading: !hasCachedSuccess && accounts.length > 0,
    isRegistered: hasCachedSuccess ? true : null,
    accountStatus: hasCachedSuccess ? cachedSuccess?.accountStatus ?? 'active' : null,
    error: null,
    userEmail: hasCachedSuccess ? cachedSuccess?.userEmail ?? userEmail : userEmail,
  }));
  const [retryCount, setRetryCount] = useState(0);

  const retry = useCallback(() => {
    if (accountId) {
      clearUserVerificationCache(accountId);
    }
    setRetryCount((count) => count + 1);
  }, [accountId]);

  useEffect(() => {
    async function checkRegistration() {
      if (!account || !accountId) {
        setState({ isLoading: false, isRegistered: false, accountStatus: null, error: null, userEmail: null });
        return;
      }

      const resolvedEmail = userEmail || '';

      const cached = readUserVerificationCache(accountId);
      if (cached?.isRegistered === true) {
        setState({
          isLoading: false,
          isRegistered: true,
          accountStatus: cached.accountStatus,
          error: null,
          userEmail: cached.userEmail,
        });
        return;
      }

      setState((current) => ({
        ...current,
        isLoading: true,
        error: null,
        userEmail: resolvedEmail,
      }));

      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

      try {
        const token = await acquireAccessToken(instance);
        if (!token) {
          // No Entra ID token: check if the user already has a DCM account
          // so we can show a precise message instead of a cryptic one.
          const dcmStatus = resolvedEmail
            ? await fetchDcmRegistrationStatus(apiBaseUrl, resolvedEmail)
            : null;

          if (dcmStatus?.registered && dcmStatus.isActive) {
            setState({
              isLoading: false,
              isRegistered: false,
              accountStatus: 'app_reg_error',
              error:
                'You already have DCM access, but the application could not get an access token from Entra ID. ' +
                'Ask a DCM administrator to add your account to the DCM App Registration (frontend / backend) in Entra ID, then sign in again.',
              userEmail: resolvedEmail,
            });
          } else if (dcmStatus?.registered && !dcmStatus.isActive) {
            setState({
              isLoading: false,
              isRegistered: false,
              accountStatus: 'inactive',
              error: 'account_inactive',
              userEmail: resolvedEmail,
            });
          } else if (dcmStatus && !dcmStatus.registered) {
            setState({
              isLoading: false,
              isRegistered: false,
              accountStatus: 'not_registered',
              error: 'not_registered',
              userEmail: resolvedEmail,
            });
          } else {
            setState({
              isLoading: false,
              isRegistered: false,
              accountStatus: 'auth_error',
              error: 'Unable to acquire access token',
              userEmail,
            });
          }
          return;
        }

        const tokenClaims = peekJwtClaims(token);
        if (tokenClaims) {
          console.info('[AUTH] Token for /auth/me', {
            aud: tokenClaims.aud,
            iss: tokenClaims.iss,
            scope: tokenClaims.scp ?? tokenClaims.scope,
            expectedScope: import.meta.env.VITE_AZURE_SCOPE,
          });
        }

        const response = await fetch(`${apiBaseUrl}/api/v1/auth/me`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        });

        if (response.ok) {
          const currentUser = (await response.json()) as CurrentDcmUser;
          queryClient.setQueryData(currentUserQueryKeys.me(), currentUser);
          writeUserVerificationCache(accountId, {
            isRegistered: true,
            accountStatus: 'active',
            userEmail: resolvedEmail,
            verifiedAt: Date.now(),
          });
          setState({ isLoading: false, isRegistered: true, accountStatus: 'active', error: null, userEmail: resolvedEmail });
        } else if (response.status === 401) {
          const data = await response.json().catch(() => ({ message: 'Unauthorized' }));
          const tokenLooksValid = tokenClaims ? tokenAudienceMatchesScope(tokenClaims) : false;
          console.error('[AUTH] /auth/me returned 401 — not a registration issue', {
            response: data,
            tokenAud: tokenClaims?.aud,
            tokenIss: tokenClaims?.iss,
            tokenLooksValid,
          });
          const dcmStatus = resolvedEmail
            ? await fetchDcmRegistrationStatus(apiBaseUrl, resolvedEmail)
            : null;
          const hasDcmAccess = dcmStatus?.registered === true && dcmStatus.isActive;

          setState({
            isLoading: false,
            isRegistered: false,
            accountStatus: hasDcmAccess ? 'app_reg_error' : 'auth_error',
            error: hasDcmAccess
              ? (tokenLooksValid
                  ? 'You already have DCM access, but the API rejected your token (401). Ask a DCM administrator to check the backend App Registration / API Gateway configuration.'
                  : 'You already have DCM access, but your access token has the wrong audience. Ask a DCM administrator to verify the frontend App Registration (exposed API scope), then sign out and sign in again.')
              : (tokenLooksValid
                  ? 'Your token is valid but the API rejected it (401). This is a server or API Gateway configuration issue — not a missing DCM account.'
                  : 'Your access token has an unexpected audience. Sign out, clear your browser session, and sign in again.'),
            userEmail: resolvedEmail,
          });
        } else if (response.status === 403) {
          const data = await response.json().catch(() => ({ detail: 'not_registered' }));
          const detail = typeof data.detail === 'string' ? data.detail : 'not_registered';

          if (detail === 'account_pending') {
            setState({
              isLoading: false,
              isRegistered: false,
              accountStatus: 'pending',
              error: 'Votre compte est en attente d\'approbation par un administrateur DCM.',
              userEmail: resolvedEmail,
            });
          } else if (detail === 'account_inactive') {
            setState({ isLoading: false, isRegistered: false, accountStatus: 'inactive', error: detail, userEmail: resolvedEmail });
          } else {
            setState({ isLoading: false, isRegistered: false, accountStatus: 'not_registered', error: detail, userEmail: resolvedEmail });
          }
        } else {
          setState({
            isLoading: false,
            isRegistered: false,
            accountStatus: 'verification_error',
            error: `Unable to verify registration (HTTP ${response.status}). This is not an access request issue.`,
            userEmail: resolvedEmail,
          });
        }
      } catch (error) {
        console.error('[USER_REGISTRATION] Error checking registration:', error);
        setState({
          isLoading: false,
          isRegistered: false,
          accountStatus: 'verification_error',
          error: networkErrorMessage(error),
          userEmail: resolvedEmail,
        });
      }
    }

    checkRegistration();
  }, [account, accountId, instance, queryClient, retryCount, userEmail]);

  return { ...state, retry };
}
