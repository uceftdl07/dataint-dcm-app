/**
 * Users — inventory of multi-cloud identities (Databricks SCIM, AWS IAM, Azure AD).
 *
 * Shows the current user_metrics state (latest snapshot by user_id).
 * Flags users inactive for more than 90 days.
 */

import { AlertTriangle, CheckCircle, Search, UserX, Users as UsersIcon } from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useUsersPageData } from '../hooks/useUsersPageData';
import { EmptyState, FilterField, FilterPanel, FilterSelect, HeaderTags, headerTagsDescriptionClass, MetricCard, MetricGrid, PageError, TableSkeleton } from '../components/domain';
import { Content, ContentDescription, ContentHeader, ContentMain, ContentTitle } from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import type { UserMetric, UserType, UsersResponse } from '../types/api';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const USER_TYPE_LABELS: Record<UserType, string> = {
  databricks: 'Databricks',
  aws_iam: 'AWS IAM',
  azure_ad: 'Azure AD',
};

function daysSince(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const ms = Date.now() - new Date(dateStr).getTime();
  return Math.floor(ms / (1000 * 60 * 60 * 24));
}

function lastActivityDisplay(dateStr: string | null): React.ReactNode {
  if (!dateStr) return <span className="text-muted-foreground">—</span>;
  const days = daysSince(dateStr);
  if (days === null) return <span className="text-muted-foreground">—</span>;
  const dateLabel = new Date(dateStr).toLocaleDateString('en-GB');
  if (days > 90) {
    return (
      <div className="flex items-center gap-1">
        <span className="text-xs text-danger">{dateLabel}</span>
        <Badge variant="destructive">
          <AlertTriangle size={10} />
          {days}d
        </Badge>
      </div>
    );
  }
  return <span className="text-xs text-muted-foreground">{dateLabel}</span>;
}

// ─── Summary cards ────────────────────────────────────────────────────────────

interface SummaryProps {
  data: UsersResponse;
}

const SummaryCards: React.FC<SummaryProps> = ({ data }) => (
  <MetricGrid loading={false}>
    <MetricCard label="Total users" value={data.total.toLocaleString('en-GB')} description="Tracked multi-cloud identities" icon={<UsersIcon />} />
    <MetricCard label="Active" value={data.active_count.toLocaleString('en-GB')} description="Identities active" icon={<CheckCircle />} tone="success" />
    <MetricCard label="Inactive" value={data.inactive_count.toLocaleString('en-GB')} description="Review or clean up" icon={<UserX />} tone={data.inactive_count > 0 ? 'warning' : 'success'} />
    <MetricCard label="Inactive > 90 days" value="—" description="Filter by inactive users to investigate" icon={<AlertTriangle />} tone="danger" />
  </MetricGrid>
);

// ─── User row ─────────────────────────────────────────────────────────────────

const UserRow: React.FC<{ user: UserMetric }> = ({ user }) => {
  const days = daysSince(user.last_activity_at);
  const isStale = !user.is_active || (days !== null && days > 90);

  return (
    <TableRow className={isStale ? 'bg-danger-subtle/40 hover:bg-danger-subtle/60' : undefined}>
      <TableCell>
        <div>
          <p className="text-sm font-medium text-foreground">{user.user_name}</p>
          {user.display_name && user.display_name !== user.user_name && (
            <p className="text-xs text-muted-foreground">{user.display_name}</p>
          )}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant="outline">{USER_TYPE_LABELS[user.user_type] ?? user.user_type}</Badge>
      </TableCell>
      <TableCell className="text-xs capitalize text-muted-foreground">{user.cloud_provider}</TableCell>
      <TableCell className="text-xs text-muted-foreground">{user.source_lz_id}</TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {user.subscription_or_account_id ?? '—'}
      </TableCell>
      <TableCell>
        <Badge variant={user.is_active ? 'success' : 'secondary'}>{user.is_active ? 'Active' : 'Inactive'}</Badge>
      </TableCell>
      <TableCell>{lastActivityDisplay(user.last_activity_at)}</TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {user.groups.length > 0 ? (
          <span title={user.groups.join(', ')}>{user.groups.length} group{user.groups.length > 1 ? 's' : ''}</span>
        ) : (
          '—'
        )}
      </TableCell>
    </TableRow>
  );
};

// ─── Page ────────────────────────────────────────────────────────────────────

const Users: React.FC = () => {
  const { getDisplayRange } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const [typeFilter, setTypeFilter] = useState<UserType | ''>('');
  const [activeFilter, setActiveFilter] = useState<'' | 'true' | 'false'>('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [offset, setOffset] = useState(0);

  const LIMIT = 50;

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [search]);

  const scopedParams = getScopedParams({
    cloudProvider: true,
    sourceLzId: true,
    subscriptionOrAccountId: true,
  });

  const queryParams = useMemo(
    () => ({
      cloud_provider: scopedParams.cloud_provider,
      source_lz_id: scopedParams.source_lz_id,
      subscription_or_account_id: scopedParams.subscription_or_account_id,
      user_type: typeFilter || undefined,
      is_active: activeFilter === '' ? undefined : activeFilter === 'true',
      search: debouncedSearch || undefined,
      limit: LIMIT,
      offset,
    }),
    [
      activeFilter,
      debouncedSearch,
      offset,
      scopedParams.cloud_provider,
      scopedParams.source_lz_id,
      scopedParams.subscription_or_account_id,
      typeFilter,
    ],
  );

  const usersQuery = useUsersPageData(queryParams);
  const data = usersQuery.data ?? null;
  const loading = usersQuery.isLoading || usersQuery.isFetching;
  const error = usersQuery.error instanceof Error ? usersQuery.error.message : usersQuery.error ? 'Error' : null;

  const load = useCallback((newOffset = 0) => {
    setOffset(newOffset);
  }, []);

  useEffect(() => {
    setOffset(0);
  }, [typeFilter, activeFilter, debouncedSearch]);

  const display = getDisplayRange();
  const hasActiveFilters = Boolean(typeFilter || activeFilter || search.trim());

  return (
    <Content>
      <ContentHeader>
        <div>
          <ContentTitle>Users</ContentTitle>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`Period: ${display.startDate} to ${display.endDate} — current snapshot by identity — ${scope.label}`}
              tags={[
                { value: 'Identities', icon: <UsersIcon size={14} />, tone: 'primary' },
                { label: 'View', value: 'Current snapshot' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
                { label: 'Scope', value: scope.label },
              ]}
            />
          </ContentDescription>
        </div>
      </ContentHeader>

      {error && <PageError message={error} />}

      <ContentMain>
        {loading && !data ? <TableSkeleton rows={4} /> : data ? <SummaryCards data={data} /> : null}

        <FilterPanel
          title="Identity filters"
          description="Refine the inventory with the same controls used across DCM monitoring pages."
          icon={<Search size={18} />}
          resultCount={data?.total ?? 0}
          activeFilterCount={[typeFilter, activeFilter, search.trim()].filter(Boolean).length}
          emptyLabel="No filter active"
          resetDisabled={!hasActiveFilters}
          onReset={() => {
            setTypeFilter('');
            setActiveFilter('');
            setSearch('');
          }}
        >
          <FilterField label="Identity type" htmlFor="user-type">
            <FilterSelect id="user-type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as UserType | '')}>
              <option value="">All types</option>
              <option value="databricks">Databricks</option>
              <option value="aws_iam">AWS IAM</option>
              <option value="azure_ad">Azure AD</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Status" htmlFor="user-status">
            <FilterSelect id="user-status" value={activeFilter} onChange={(e) => setActiveFilter(e.target.value as '' | 'true' | 'false')}>
              <option value="">All statuses</option>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Search" htmlFor="user-search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="user-search"
                type="text"
                placeholder="Search for a user..."
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </FilterField>
        </FilterPanel>

        <Card>
          <CardHeader>
            <CardTitle>Users inventory</CardTitle>
            <CardDescription>
              {(data?.items.length ?? 0).toLocaleString('en-GB')} visible identities in the current page.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Cloud</TableHead>
                  <TableHead>Landing Zone</TableHead>
                  <TableHead>Workspace / Account</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last activity</TableHead>
                  <TableHead>Groups</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 8 }).map((_, index) => (
                    <TableRow key={index}>
                      <TableCell colSpan={8}>
                        <div className="h-4 animate-pulse rounded bg-muted" />
                      </TableCell>
                    </TableRow>
                  ))
                ) : data && data.items.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-8">
                      <EmptyState
                        icon={<UsersIcon size={28} />}
                        title={hasActiveFilters ? 'No users match these filters' : 'No users available'}
                        description={
                          hasActiveFilters
                            ? 'Clear the filters or change the global scope to check whether identities exist outside this view.'
                            : 'DCM did not receive user inventory for this scope yet. Check collection status before treating this as an empty estate.'
                        }
                      />
                    </TableCell>
                  </TableRow>
                ) : data?.items.map((user) => (
                  <UserRow key={`${user.user_id}--${user.source_lz_id}`} user={user} />
                ))}
              </TableBody>
            </Table>

            {data && (
              <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  {data.total === 0 ? '0' : `${offset + 1}-${Math.min(offset + LIMIT, data.total)}`} on {data.total.toLocaleString('en-GB')} users
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={offset === 0 || loading}
                    onClick={() => load(Math.max(0, offset - LIMIT))}
                  >
                    Prev
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={offset + LIMIT >= data.total || loading}
                    onClick={() => load(offset + LIMIT)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex items-start gap-2 text-xs text-muted-foreground">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-danger" />
          <span>
            Rows highlighted in red indicate inactive accounts or accounts whose last activity is older than 90 days.
            These accounts are candidates for deactivation or access review.
          </span>
        </div>
      </ContentMain>
    </Content>
  );
};

export default Users;
