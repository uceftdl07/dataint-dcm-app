import React from 'react';
import { useLocation } from 'react-router-dom';
import { ROUTE_PERMISSIONS } from '../config/role-permissions';
import { useRolePermissions } from '../hooks/useRolePermissions';
import { PageAccessGate } from './AccessGate';
import { PageError } from './domain/states';

interface RoutePermissionWrapperProps {
  children: React.ReactNode;
}

function resolvePermissionKey(pathname: string): string | null {
  if (ROUTE_PERMISSIONS[pathname]) {
    return ROUTE_PERMISSIONS[pathname];
  }
  const basePath = `/${pathname.split('/').filter(Boolean)[0] ?? ''}`;
  return ROUTE_PERMISSIONS[basePath] ?? null;
}

function pageLabelFromPath(pathname: string): string {
  const segment = pathname.split('/').filter(Boolean)[0] ?? 'this page';
  return segment.replace(/-/g, ' ');
}

export const RoutePermissionWrapper: React.FC<RoutePermissionWrapperProps> = ({ children }) => {
  const location = useLocation();
  const { canAccess, loading, ready, error } = useRolePermissions();
  const permissionKey = resolvePermissionKey(location.pathname);

  if (loading) {
    return (
      <div className="min-h-[40vh]" role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only">Loading your access profile…</span>
      </div>
    );
  }

  if (!ready || error) {
    return (
      <div className="p-8">
        <PageError message={error ?? 'Unable to load your access profile. Verify the DCM API is running, then refresh.'} />
      </div>
    );
  }

  if (!permissionKey) {
    return <>{children}</>;
  }

  const allowed = canAccess(permissionKey);
  return (
    <PageAccessGate allowed={allowed} pageLabel={pageLabelFromPath(location.pathname)}>
      {children}
    </PageAccessGate>
  );
};
