/**
 * PendingApprovalMessage — shown after first Entra login while admin approves access.
 */

import { Clock, FolderPlus, LogIn, LogOut, RefreshCw } from 'lucide-react';
import React, { useState } from 'react';
import { useMsal } from '@azure/msal-react';
import { clearUserVerificationCache } from '../lib/userVerificationCache';
import { ProjectRegisterRequestModal } from './ProjectRegisterRequestModal';
import { ProjectJoinRequestModal } from './ProjectJoinRequestModal';

interface PendingApprovalMessageProps {
  userEmail: string | null;
  onRetry?: () => void;
}

export const PendingApprovalMessage: React.FC<PendingApprovalMessageProps> = ({
  userEmail,
  onRetry,
}) => {
  const { instance, accounts } = useMsal();
  const [onboarding, setOnboarding] = useState<'register' | 'join' | null>(null);
  const requesterEmail = userEmail ?? undefined;

  const handleLogout = () => {
    clearUserVerificationCache(accounts[0]?.localAccountId);
    instance.logoutRedirect({
      postLogoutRedirectUri: import.meta.env.VITE_REDIRECT_URI || window.location.origin,
    });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-amber-50/40 to-slate-100 p-6">
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
            <div className="rounded-full bg-amber-100 p-4">
              <Clock className="h-12 w-12 text-amber-600" />
            </div>
          </div>

          <h1 className="mb-3 text-center text-2xl font-bold text-slate-900">
            Account pending approval
          </h1>

          <div className="mb-6 space-y-3 text-center text-sm text-slate-700">
            <p>
              Your account <span className="font-medium text-blue-600">{userEmail || 'user'}</span> was
              created in DCM after your Microsoft sign-in.
            </p>
            <p>
              You get access to DCM through a project. Create your Business Application project or
              join an existing one — an administrator validates the request.
            </p>
            <p className="text-xs text-slate-500">
              A Teams notification was sent to the DCM admin channel. No action is required from you right now.
            </p>
          </div>

          <div className="space-y-3">
            <button
              onClick={() => setOnboarding('register')}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white transition-colors hover:bg-blue-700"
            >
              <FolderPlus className="h-4 w-4" />
              Create a project
            </button>

            <button
              onClick={() => setOnboarding('join')}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 font-medium text-blue-700 transition-colors hover:bg-blue-100"
            >
              <LogIn className="h-4 w-4" />
              Join a project
            </button>

            {onRetry && (
              <button
                onClick={onRetry}
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-3 font-medium text-slate-700 transition-colors hover:bg-slate-50"
              >
                <RefreshCw className="h-4 w-4" />
                Check again
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
            Data Connect Monitoring · TotalEnergies
          </p>
        </div>
      </div>

      {onboarding === 'register' && (
        <ProjectRegisterRequestModal
          defaultRequesterEmail={requesterEmail}
          onClose={() => setOnboarding(null)}
          onSwitchToJoin={() => setOnboarding('join')}
        />
      )}
      {onboarding === 'join' && (
        <ProjectJoinRequestModal
          defaultRequesterEmail={requesterEmail}
          onClose={() => setOnboarding(null)}
          onSwitchToRegister={() => setOnboarding('register')}
        />
      )}
    </div>
  );
};
