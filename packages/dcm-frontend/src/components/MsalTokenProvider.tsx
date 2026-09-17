/**
 * MsalTokenProvider — Registers the token getter for API calls.
 * 
 * This component must be rendered inside MsalProvider to access
 * the MSAL instance via useMsal().
 */

import { useEffect } from 'react';
import { useMsal } from '@azure/msal-react';
import { registerTokenGetter } from '../api/dcmApiClient';
import { acquireAccessToken } from '../lib/auth';

export const MsalTokenProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { instance } = useMsal();

  useEffect(() => {
    // Register the token getter for API calls with forceRefresh support
    registerTokenGetter((forceRefresh = false) => acquireAccessToken(instance, forceRefresh));
  }, [instance]);

  return <>{children}</>;
};

export default MsalTokenProvider;
