/**
 * NotRegisteredMessage - Friendly error screen for access issues
 *
 * Distinct UI per cause (two separate layers):
 * 1. Authentication — Entra ID / App Registration (Microsoft SSO + token)
 * 2. Authorization — DCM account in dcm_app_users (business access)
 *
 * - not_registered → request DCM access form
 * - inactive → reactivation form
 * - app_reg_error → has DCM rights, admin must fix App Registration (no form)
 * - auth_error → auth failed, unknown DCM status → admin + optional DCM request form
 * - verification_error → backend/network issue
 */

import React from 'react';
import { ShieldAlert, Mail, LogOut, UserX, KeyRound, RefreshCw } from 'lucide-react';
import { useMsal } from '@azure/msal-react';
import { clearUserVerificationCache } from '../lib/userVerificationCache';
import type { AccountStatus } from '../hooks/useUserRegistration';

interface NotRegisteredMessageProps {
  userEmail: string | null;
  accountStatus: Extract<AccountStatus, 'inactive' | 'not_registered' | 'auth_error' | 'app_reg_error' | 'verification_error'> | null;
  errorMessage?: string | null;
  onRetry?: () => void;
}

export const NotRegisteredMessage: React.FC<NotRegisteredMessageProps> = ({
  userEmail,
  accountStatus,
  errorMessage,
  onRetry,
}) => {
  const { instance, accounts } = useMsal();

  const handleLogout = () => {
    clearUserVerificationCache(accounts[0]?.localAccountId);
    instance.logoutRedirect({
      postLogoutRedirectUri: import.meta.env.VITE_REDIRECT_URI || window.location.origin,
    });
  };

  const isInactive = accountStatus === 'inactive';
  const isNotRegistered = accountStatus === 'not_registered';
  const isAuthError = accountStatus === 'auth_error';
  const isAppRegError = accountStatus === 'app_reg_error';
  const isVerificationError = accountStatus === 'verification_error';
  const isRegistrationIssue = isInactive || isNotRegistered;

  const isBackendUnreachable = isVerificationError
    && Boolean(errorMessage?.toLowerCase().includes('cannot reach the dcm backend'));

  const title = isInactive
    ? 'Account Disabled'
    : isBackendUnreachable
      ? 'Backend Unreachable'
      : isAppRegError
        ? 'DCM Access OK — Connection Setup Incomplete'
        : isAuthError
          ? 'Authentication Failed'
          : isVerificationError
            ? 'Verification Failed'
            : 'Access Denied';

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-blue-50 to-slate-100 p-6">
      <div className="w-full max-w-md">
        <div className="rounded-2xl border border-amber-200 bg-white p-8 shadow-xl">
          <div className="mb-6 flex justify-center">
            <img
              src="/images/compagny-logo.png"
              alt="TotalEnergies"
              className="h-16 w-auto object-contain"
            />
          </div>

          <div className="mb-6 flex justify-center">
            <div className={`rounded-full p-4 ${isRegistrationIssue || isAppRegError ? 'bg-amber-100' : 'bg-red-100'}`}>
              {isInactive ? (
                <UserX className="h-12 w-12 text-amber-600" />
              ) : isRegistrationIssue ? (
                <ShieldAlert className="h-12 w-12 text-amber-600" />
              ) : isAppRegError ? (
                <KeyRound className="h-12 w-12 text-amber-600" />
              ) : (
                <KeyRound className="h-12 w-12 text-red-600" />
              )}
            </div>
          </div>

          <h1 className="mb-3 text-center text-2xl font-bold text-slate-900">{title}</h1>

          <div className="mb-6 space-y-3 text-center text-sm text-slate-700">
            <p className="font-medium">
              {isInactive ? (
                <>
                  Your account <span className="text-blue-600">{userEmail || 'user'}</span> is currently disabled.
                </>
              ) : isNotRegistered ? (
                <>
                  Your account <span className="text-blue-600">{userEmail || 'user'}</span> is not registered in DCM yet.
                  Microsoft sign-in worked, but you do not have DCM authorization.
                </>
              ) : isBackendUnreachable ? (
                <>
                  Signed in as <span className="text-blue-600">{userEmail || 'user'}</span>. Your DCM account is fine — the API is not responding.
                </>
              ) : isAppRegError ? (
                <>
                  Good news: <span className="text-blue-600">{userEmail || 'your account'}</span> already has DCM authorization.
                  Only the Entra ID App Registration setup is blocking authentication.
                </>
              ) : isAuthError ? (
                <>
                  Signed in as <span className="text-blue-600">{userEmail || 'user'}</span>, but authentication could not be completed
                  (access token missing or invalid).
                </>
              ) : (
                <>
                  Signed in as <span className="text-blue-600">{userEmail || 'user'}</span>, but DCM could not verify your access.
                </>
              )}
            </p>
            <p>
              {isInactive
                ? 'To reactivate your DCM authorization, contact an administrator or submit a reactivation request below.'
                : isNotRegistered
                  ? 'You need DCM authorization (admin adds you in Access Control). Use the button below to submit a DCM access request.'
                  : isAppRegError
                    ? errorMessage
                    : isAuthError
                      ? (errorMessage ||
                        'This is an authentication (App Registration) issue. Contact a DCM administrator. If you never had DCM access, also submit a DCM access request below.')
                      : errorMessage ||
                        'Try signing out and back in, or contact support if the problem persists.'}
            </p>

            {(isNotRegistered || isAppRegError || isAuthError) && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-left text-xs text-slate-600">
                <p className="mb-2 font-semibold text-slate-800">Two separate steps to access DCM</p>
                <ol className="list-decimal space-y-1 pl-4">
                  <li>
                    <span className="font-medium">Authentication</span> — Microsoft SSO + Entra ID App Registration
                    (frontend + backend). Required to connect.
                  </li>
                  <li>
                    <span className="font-medium">DCM authorization</span> — your account in DCM
                    (<span className="font-mono">dcm_app_users</span> + landing zones). Required to see data.
                  </li>
                </ol>
              </div>
            )}
          </div>

          <div className={`mb-6 rounded-xl p-4 ${isRegistrationIssue ? 'bg-blue-50' : isAppRegError ? 'bg-amber-50' : 'bg-red-50'}`}>
            <div className="flex items-start gap-2">
              {isRegistrationIssue ? (
                <Mail className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600" />
              ) : isAppRegError ? (
                <KeyRound className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-600" />
              ) : (
                <KeyRound className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600" />
              )}
              <div className="text-sm text-slate-800">
                <p className="mb-1 font-semibold">
                  {isInactive
                    ? 'How to reactivate my account?'
                    : isNotRegistered
                      ? 'How to get access?'
                      : isAppRegError
                        ? 'How to complete my access?'
                        : 'What to do?'}
                </p>
                <p className="text-slate-700">
                  {isInactive ? (
                    <>Contact a DCM administrator or use the button below to submit a reactivation request.</>
                  ) : isNotRegistered ? (
                    <>
                      Submit a <span className="font-semibold">DCM access request</span> below, or ask a DCM administrator
                      to add you in
                      <span className="font-mono text-xs"> Administration &gt; Access Control</span>.
                      App Registration is handled separately by admins.
                    </>
                  ) : isAppRegError ? (
                    <>
                      1. Contact a DCM administrator — ask them to add your account to the
                      <span className="font-mono text-xs"> DCM App Registration </span>
                      in Entra ID (frontend scope + backend API).
                      <br />
                      2. Do <span className="font-semibold">not</span> submit a DCM access request — your DCM authorization is already OK.
                      <br />
                      3. After the admin fix, sign out and sign in again.
                    </>
                  ) : isAuthError ? (
                    <>
                      1. Contact a DCM administrator for the Entra ID App Registration (authentication layer).
                      <br />
                      2. If you never had DCM access, submit a <span className="font-semibold">DCM access request</span> below (authorization layer).
                    </>
                  ) : isBackendUnreachable ? (
                    <>
                      1. Start or restart <span className="font-mono text-xs">dcm-backend</span> on port 8000.
                      <br />
                      2. Click Retry below — no need to sign out.
                    </>
                  ) : (
                    <>
                      1. Sign out and sign in again.
                      <br />
                      2. If it persists, contact a DCM administrator — your account may already be registered and the API configuration needs fixing.
                    </>
                  )}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            {(isVerificationError || isAuthError || isAppRegError) && onRetry && (
              <button
                onClick={onRetry}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white transition-colors hover:bg-blue-700"
              >
                <RefreshCw className="h-4 w-4" />
                Retry
              </button>
            )}

            <button
              onClick={handleLogout}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              <LogOut className="h-4 w-4" />
              Sign Out
            </button>
          </div>

          <p className="mt-6 text-center text-xs text-slate-500">
            Data Connect Monitoring &middot; TotalEnergies
          </p>
        </div>
      </div>

    </div>
  );
};
