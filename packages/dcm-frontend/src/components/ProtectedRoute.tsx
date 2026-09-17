/**
 * ProtectedRoute — Component for protecting private routes.
 * 
 * Two-level security:
 * 1. Entra ID authentication (MSAL)
 * 2. DCM user registration check (dcm_app_users table)
 * 
 * If the user is not authenticated, they are redirected to / (LandingPage).
 * If authenticated but not registered in DCM, shows a friendly access denied message.
 */

import React from 'react';
import { Navigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { useUserRegistration } from '../hooks/useUserRegistration';
import { NotRegisteredMessage } from './NotRegisteredMessage';
import { PendingApprovalMessage } from './PendingApprovalMessage';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { accounts, inProgress } = useMsal();
  const enableAuth = import.meta.env.VITE_ENABLE_AUTH === 'true';
  const isAuthenticated = accounts.length > 0;
  const isMsalLoading = inProgress !== InteractionStatus.None;
  
  const { retry: retryRegistration, ...registrationState } = useUserRegistration();

  if (!enableAuth) {
    return <>{children}</>;
  }

  // Show loading state while checking MSAL authentication
  if (isMsalLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
          <p className="text-slate-600 font-medium">Verifying your identity...</p>
        </div>
      </div>
    );
  }

  // Redirect to landing page if not authenticated with Entra ID
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  // Show loading state while checking DCM registration
  if (registrationState.isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
          <p className="text-slate-600 font-medium">Checking your permissions...</p>
        </div>
      </div>
    );
  }

  if (registrationState.isRegistered === false && registrationState.accountStatus === 'pending') {
    return (
      <PendingApprovalMessage
        userEmail={registrationState.userEmail}
        onRetry={retryRegistration}
      />
    );
  }

  // Show friendly error if user is not registered in DCM or account is inactive
  if (registrationState.isRegistered === false) {
    return (
      <NotRegisteredMessage 
        userEmail={registrationState.userEmail} 
        accountStatus={registrationState.accountStatus}
        errorMessage={registrationState.error}
        onRetry={retryRegistration}
      />
    );
  }

  // Render protected content
  return <>{children}</>;
};

export default ProtectedRoute;
