/**
 * Microsoft Entra ID (MSAL.js) configuration for DCM Frontend.
 *
 * The App Registration referenced here is the DCM Frontend client, NOT the
 * POC App Registration.  The backend scope must match the Lambda Authorizer
 * audience configured on API Gateway.
 */

import { Configuration, LogLevel, RedirectRequest } from '@azure/msal-browser';

const tenantId = import.meta.env.VITE_AZURE_TENANT_ID;
const clientId = import.meta.env.VITE_AZURE_CLIENT_ID;
const redirectUri = import.meta.env.VITE_REDIRECT_URI;
const backendScope = import.meta.env.VITE_AZURE_SCOPE;

// Strict validation
if (!tenantId || !clientId || !redirectUri || !backendScope) {
  // Missing environment variables for Azure AD configuration
  throw new Error('Incomplete Azure AD configuration. Check the .env file');
}


export const msalConfig: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri,
    postLogoutRedirectUri: redirectUri,
  },
  cache: {
    cacheLocation: 'sessionStorage',
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        if (level === LogLevel.Error) console.error('[MSAL]', message);
      },
      piiLoggingEnabled: false,
    },
  },
};

/** Scopes requested on login (Entra ID user identity). */
export const loginRequest: RedirectRequest = {
  scopes: ['User.Read'],
  prompt: 'select_account',
};

/** Scope for acquiring tokens sent to dcm-backend via API Gateway. */
export const dcmApiScopes = [backendScope];
