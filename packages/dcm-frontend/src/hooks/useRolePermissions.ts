import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { getDcmPermissions, getDcmApiErrorMessage } from '../api/dcmApiClient';
import { buildPermissionsForRole } from '../lib/role-access';
import { useCurrentDcmUser } from './useCurrentDcmUser';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from './query-config';
import { currentUserQueryKeys } from './query-keys';
import type { DcmPermissions } from '../types/api';

export function useRolePermissions() {
  const { user, loading: userLoading, error: userError } = useCurrentDcmUser();

  const query = useQuery({
    queryKey: currentUserQueryKeys.permissions(),
    queryFn: getDcmPermissions,
    enabled: Boolean(user),
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
    retry: 1,
  });

  const permissions = useMemo<DcmPermissions>(() => {
    if (!user?.role) {
      return buildPermissionsForRole('pending');
    }
    // Enforce client matrix from /auth/me role — never show more than role allows.
    const enforced = buildPermissionsForRole(user.role);
    if (!query.data || query.data.role !== user.role) {
      return enforced;
    }
    // API may only narrow access, not widen it.
    const enforcedSet = new Set(enforced.allowed);
    const apiAllowed = query.data.allowed.filter((key) => enforcedSet.has(key));
    return {
      role: user.role,
      pages: apiAllowed.filter((k) => k.startsWith('page:')),
      widgets: apiAllowed.filter((k) => k.startsWith('widget:')),
      features: apiAllowed.filter((k) => k.startsWith('feature:')),
      allowed: apiAllowed,
    };
  }, [query.data, user?.role]);

  const allowed = useMemo(() => new Set(permissions.allowed), [permissions.allowed]);
  const canAccess = (resourceKey: string) => allowed.has(resourceKey);

  return {
    permissions,
    canAccess,
    loading: userLoading || (Boolean(user) && query.isLoading),
    ready: !userLoading && (Boolean(user) || Boolean(userError)),
    error: userError
      ?? (query.error ? getDcmApiErrorMessage(query.error, 'Unable to load role permissions.') : null),
    reload: () => {
      void query.refetch();
    },
  };
}
