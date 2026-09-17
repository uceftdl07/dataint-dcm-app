import { ShieldAlert } from 'lucide-react';
import React from 'react';
import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';
import { isPlatformAdmin, platformRoleLabel } from '../lib/role-access';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Skeleton } from './ui/skeleton';

interface RequireAdminProps {
  children: React.ReactNode;
}

const RequireAdmin: React.FC<RequireAdminProps> = ({ children }) => {
  const { user, loading, error, reload } = useCurrentDcmUser();

  if (loading) {
    return (
      <div className="p-6">
        <Card>
          <CardHeader>
            <CardTitle>Checking admin access</CardTitle>
            <CardDescription>Loading your DCM role and Landing Zone scope.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-8 rounded-xl" />
            <Skeleton className="h-8 rounded-xl" />
          </CardContent>
        </Card>
      </div>
    );
  }

  // Gate on the platform tier, not on the lifecycle role: the administration API
  // is guarded by `platform_role`, so keying the UI off `role` would show pages
  // whose every call comes back 403.
  if (error || !isPlatformAdmin(user)) {
    return (
      <div className="p-6">
        <Card className="mx-auto max-w-2xl">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex size-11 items-center justify-center rounded-2xl bg-danger-subtle text-danger">
                <ShieldAlert size={22} />
              </div>
              <div>
                <CardTitle>Administration access required</CardTitle>
                <CardDescription>
                  {error ??
                    `Your platform tier is ${platformRoleLabel(user?.platform_role)}; administration requires a platform admin.`}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <Button variant="secondary" onClick={reload}>Retry role check</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
};

export default RequireAdmin;
