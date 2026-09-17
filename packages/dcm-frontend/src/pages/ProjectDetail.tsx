import { ArrowLeft, Loader2, ShieldAlert, ShieldCheck, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import {
  DcmApiError,
  getDcmApiErrorMessage,
  listAccessRequestLandingZones,
} from '../api/dcmApiClient';
import { PageError } from '../components/domain';
import { RejectWithReason } from '../components/RejectWithReason';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
} from '../components/layout/content';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { FieldLabel, Input, Select, Textarea } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_DEFAULT_MS } from '../hooks/query-config';
import { useCurrentDcmUser } from '../hooks/useCurrentDcmUser';
import { useDatabricksWorkspacesList } from '../hooks/useDatabricksWorkspacesList';
import {
  useProjectActions,
  useProjectDetail,
  useProjectJoinRequests,
  useProjectMembers,
} from '../hooks/useProjectsQueries';
import { useToast } from '../hooks/useToast';
import {
  isProjectAdmin,
  projectRoleLabel,
  projectScopeTypeLabel,
  projectStatusLabel,
  projectStatusVariant,
} from '../lib/role-access';
import type {
  ProjectRole,
  ProjectScopeRequestItemPayload,
  ProjectScopeType,
} from '../types/api';

function MembersSection({ projectId, canAdmin }: { projectId: string; canAdmin: boolean }) {
  const toast = useToast();
  const membersQuery = useProjectMembers(projectId);
  const { addMember, changeMemberRole, removeMember } = useProjectActions();
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState<ProjectRole>('viewer');
  const [adding, setAdding] = useState(false);
  const members = membersQuery.data ?? [];

  const handleAddMember = async () => {
    const email = newEmail.trim();
    if (!email || adding) return;
    setAdding(true);
    try {
      await addMember(projectId, { email, role: newRole });
      toast.showSuccess('Member added', `${email} now has access to this project.`);
      setNewEmail('');
      setNewRole('viewer');
    } catch (error) {
      if (error instanceof DcmApiError && error.statusCode === 409) {
        toast.showError('Already a member', 'This person already belongs to the project.');
      } else {
        toast.showError('Unable to add member', getDcmApiErrorMessage(error, 'Please retry.'));
      }
    } finally {
      setAdding(false);
    }
  };

  const handleRoleChange = async (userId: string, role: ProjectRole) => {
    setBusyUserId(userId);
    try {
      await changeMemberRole(projectId, userId, role);
      toast.showSuccess('Role updated');
    } catch (error) {
      if (error instanceof DcmApiError && error.statusCode === 409) {
        toast.showError('Cannot demote the last admin', 'Promote another member first.');
      } else {
        toast.showError('Unable to update role', getDcmApiErrorMessage(error, 'Please retry.'));
      }
    } finally {
      setBusyUserId(null);
    }
  };

  const handleRemove = async (userId: string) => {
    setBusyUserId(userId);
    try {
      await removeMember(projectId, userId);
      toast.showSuccess('Member removed');
    } catch (error) {
      if (error instanceof DcmApiError && error.statusCode === 409) {
        toast.showError('Cannot remove the last admin', 'Promote another member first.');
      } else {
        toast.showError('Unable to remove member', getDcmApiErrorMessage(error, 'Please retry.'));
      }
    } finally {
      setBusyUserId(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
        <CardDescription>
          {canAdmin ? 'Manage roles and membership.' : 'People with access to this project.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {canAdmin && (
          <div className="mb-4 flex flex-col gap-3 rounded-xl border border-border/60 p-3 sm:flex-row sm:items-end">
            <label className="flex flex-1 flex-col gap-1.5">
              <FieldLabel>Add member by email</FieldLabel>
              <Input
                type="email"
                aria-label="New member email"
                placeholder="user@domain.com"
                value={newEmail}
                disabled={adding}
                onChange={(e) => setNewEmail(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <FieldLabel>Role</FieldLabel>
              <Select
                aria-label="New member role"
                value={newRole}
                disabled={adding}
                onChange={(e) => setNewRole(e.target.value as ProjectRole)}
                className="h-9 w-40"
              >
                <option value="viewer">{projectRoleLabel('viewer')}</option>
                <option value="admin">{projectRoleLabel('admin')}</option>
              </Select>
            </label>
            <Button onClick={() => void handleAddMember()} disabled={!newEmail.trim() || adding}>
              {adding && <Loader2 className="animate-spin" />}
              Add member
            </Button>
          </div>
        )}
        {membersQuery.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : membersQuery.isError ? (
          <PageError message="Unable to load members." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Member</TableHead>
                <TableHead>Role</TableHead>
                {canAdmin && <TableHead>Actions</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <TableRow key={member.userId}>
                  <TableCell className="font-medium" title={member.userId}>
                    {member.displayName}
                  </TableCell>
                  <TableCell>
                    {canAdmin ? (
                      <Select
                        aria-label={`Role for ${member.displayName}`}
                        value={member.role}
                        disabled={busyUserId === member.userId}
                        onChange={(e) =>
                          void handleRoleChange(member.userId, e.target.value as ProjectRole)
                        }
                        className="h-8 w-40"
                      >
                        <option value="viewer">{projectRoleLabel('viewer')}</option>
                        <option value="admin">{projectRoleLabel('admin')}</option>
                      </Select>
                    ) : (
                      <Badge variant="outline">{projectRoleLabel(member.role)}</Badge>
                    )}
                  </TableCell>
                  {canAdmin && (
                    <TableCell>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busyUserId === member.userId}
                        onClick={() => void handleRemove(member.userId)}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

function JoinRequestsSection({ projectId }: { projectId: string }) {
  const toast = useToast();
  const joinRequestsQuery = useProjectJoinRequests(projectId);
  const { decideJoin } = useProjectActions();
  const [busyId, setBusyId] = useState<string | null>(null);
  const requests = (joinRequestsQuery.data ?? []).filter((r) => r.status === 'pending');

  const handleDecision = async (
    requestId: string,
    decision: 'approved' | 'rejected',
    reason?: string
  ) => {
    setBusyId(requestId);
    try {
      await decideJoin(projectId, requestId, { decision, reason });
      toast.showSuccess(decision === 'approved' ? 'Member added' : 'Join request rejected');
    } catch (error) {
      toast.showError(
        'Unable to decide join request',
        getDcmApiErrorMessage(error, 'Please retry.')
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Join requests</CardTitle>
        <CardDescription>Pending requests to join this project.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {joinRequestsQuery.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : requests.length === 0 ? (
          <span className="text-sm text-muted-foreground">No pending join request.</span>
        ) : (
          requests.map((request) => (
            <div
              key={request.id}
              className="flex items-center justify-between gap-3 rounded-xl border border-border/60 p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium" title={request.userId}>
                  {request.displayName}
                </p>
                <p className="truncate text-[11px] text-muted-foreground">
                  Requested {projectRoleLabel(request.requestedRole)}
                  {request.justification ? ` · ${request.justification}` : ''}
                </p>
              </div>
              <div className="flex shrink-0 items-start gap-2">
                <Button
                  size="sm"
                  disabled={busyId === request.id}
                  onClick={() => void handleDecision(request.id, 'approved')}
                >
                  Approve
                </Button>
                <RejectWithReason
                  subject={request.displayName}
                  busy={busyId === request.id}
                  onReject={(reason) => handleDecision(request.id, 'rejected', reason)}
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Ask for scope extensions — several at once.
 *
 * A team that needs three landing zones and a workspace used to file four
 * look-alike requests a platform admin approved one by one. Everything picked
 * here travels as one submission (`items`), and what the project already has is
 * filtered out of the pickers so a granted scope cannot be requested again.
 */
function ScopeRequestSection({
  projectId,
  lzScope,
  dbxScope,
}: {
  projectId: string;
  lzScope: string[];
  dbxScope: string[];
}) {
  const toast = useToast();
  const { requestScope } = useProjectActions();
  const referenceQuery = useQuery({
    queryKey: ['projects', 'reference', 'landing-zones'],
    queryFn: listAccessRequestLandingZones,
    staleTime: QUERY_STALE_DEFAULT_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });
  const workspacesQuery = useDatabricksWorkspacesList();

  const [items, setItems] = useState<ProjectScopeRequestItemPayload[]>([]);
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const labelFor = useMemo(() => {
    const labels = new Map<string, string>();
    for (const lz of referenceQuery.data?.items ?? []) {
      labels.set(`lz:${lz.lz_id}`, lz.lz_name || lz.lz_id);
    }
    for (const ws of workspacesQuery.data?.items ?? []) {
      labels.set(`dbx_workspace:${ws.workspace_id}`, ws.display_name || ws.workspace_id);
    }
    return labels;
  }, [referenceQuery.data, workspacesQuery.data]);

  const optionsFor = (scopeType: ProjectScopeType) => {
    const granted = scopeType === 'lz' ? lzScope : dbxScope;
    const source =
      scopeType === 'lz'
        ? (referenceQuery.data?.items ?? []).map((lz) => lz.lz_id)
        : (workspacesQuery.data?.items ?? []).map((ws) => ws.workspace_id);
    return source
      .filter(
        (ref) =>
          !granted.includes(ref) &&
          !items.some((item) => item.scopeType === scopeType && item.scopeRef === ref)
      )
      .map((ref) => ({ value: ref, label: labelFor.get(`${scopeType}:${ref}`) ?? ref }));
  };

  const addItem = (scopeType: ProjectScopeType, scopeRef: string) => {
    if (!scopeRef) return;
    setItems((current) =>
      current.some((item) => item.scopeType === scopeType && item.scopeRef === scopeRef)
        ? current
        : [...current, { scopeType, scopeRef }]
    );
  };

  const removeItem = (scopeType: ProjectScopeType, scopeRef: string) => {
    setItems((current) =>
      current.filter((item) => !(item.scopeType === scopeType && item.scopeRef === scopeRef))
    );
  };

  const handleSubmit = async () => {
    if (items.length === 0 || submitting) return;
    setSubmitting(true);
    try {
      const created = await requestScope(projectId, {
        items,
        justification: justification.trim() || undefined,
      });
      toast.showSuccess(
        created.length === 1 ? 'Scope request sent' : `${created.length} scope items requested`,
        'A platform admin will review them as one request.'
      );
      setItems([]);
      setJustification('');
    } catch (error) {
      toast.showError('Unable to request scope', getDcmApiErrorMessage(error, 'Please retry.'));
    } finally {
      setSubmitting(false);
    }
  };

  const lzOptions = optionsFor('lz');
  const dbxOptions = optionsFor('dbx_workspace');

  return (
    <Card>
      <CardHeader>
        <CardTitle>Request scope extension</CardTitle>
        <CardDescription>
          Pick every Landing Zone and Databricks workspace the project is missing — they travel as a
          single request.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-4 sm:flex-row">
          <label className="flex flex-1 flex-col gap-1.5">
            <FieldLabel>Add a Landing Zone</FieldLabel>
            <Select
              aria-label="Add a Landing Zone"
              value=""
              disabled={submitting || lzOptions.length === 0}
              onChange={(e) => addItem('lz', e.target.value)}
            >
              <option value="">
                {lzOptions.length === 0 ? 'Nothing left to request' : 'Select…'}
              </option>
              {lzOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-1 flex-col gap-1.5">
            <FieldLabel>Add a Databricks workspace</FieldLabel>
            <Select
              aria-label="Add a Databricks workspace"
              value=""
              disabled={submitting || dbxOptions.length === 0}
              onChange={(e) => addItem('dbx_workspace', e.target.value)}
            >
              <option value="">
                {dbxOptions.length === 0 ? 'Nothing left to request' : 'Select…'}
              </option>
              {dbxOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </label>
        </div>

        <div className="flex flex-col gap-1.5">
          <FieldLabel>Requested items ({items.length})</FieldLabel>
          {items.length === 0 ? (
            <span className="text-sm text-muted-foreground">
              Nothing selected yet — pick at least one item above.
            </span>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {items.map((item) => (
                <Badge
                  key={`${item.scopeType}:${item.scopeRef}`}
                  variant="secondary"
                  className="gap-1.5"
                >
                  {projectScopeTypeLabel(item.scopeType)}:{' '}
                  {labelFor.get(`${item.scopeType}:${item.scopeRef}`) ?? item.scopeRef}
                  <button
                    type="button"
                    aria-label={`Remove ${projectScopeTypeLabel(item.scopeType)} ${item.scopeRef}`}
                    className="text-muted-foreground hover:text-destructive"
                    disabled={submitting}
                    onClick={() => removeItem(item.scopeType, item.scopeRef)}
                  >
                    <X size={11} aria-hidden="true" />
                  </button>
                </Badge>
              ))}
            </div>
          )}
        </div>

        <label className="flex flex-col gap-1.5">
          <FieldLabel>Justification</FieldLabel>
          <Textarea
            aria-label="Scope justification"
            value={justification}
            disabled={submitting}
            onChange={(e) => setJustification(e.target.value)}
          />
        </label>
        <div>
          <Button onClick={() => void handleSubmit()} disabled={items.length === 0 || submitting}>
            {submitting && <Loader2 className="animate-spin" />}
            Send request
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ProjectDetail() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { user } = useCurrentDcmUser();
  const detailQuery = useProjectDetail(projectId);
  const canAdmin = isProjectAdmin(user, projectId);
  const project = detailQuery.data;

  return (
    <Content>
      <ContentHeader>
        <ContentDescription>
          {project ? (
            <span className="flex items-center gap-2">
              <strong className="text-foreground">{project.name}</strong>
              <Badge variant={projectStatusVariant(project.status)}>
                {projectStatusLabel(project.status)}
              </Badge>
              {canAdmin && (
                <Badge variant="info" className="gap-1">
                  <ShieldCheck size={11} /> Project admin
                </Badge>
              )}
            </span>
          ) : (
            'Project details'
          )}
        </ContentDescription>
        <ContentActions>
          <Button variant="outline" onClick={() => navigate('/projects')}>
            <ArrowLeft size={16} /> All projects
          </Button>
        </ContentActions>
      </ContentHeader>

      <ContentMain>
        {detailQuery.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : detailQuery.isError || !project ? (
          <PageError message="Unable to load this project." />
        ) : (
          <>
            {project.status === 'rejected' && (
              <Alert variant="destructive">
                <ShieldAlert />
                <AlertTitle>Project rejected</AlertTitle>
                <AlertDescription>
                  {project.decisionReason ?? 'No reason was recorded.'}
                </AlertDescription>
              </Alert>
            )}

            <Card>
              <CardHeader>
                <CardTitle>Scope</CardTitle>
                <CardDescription>Landing Zones and Databricks workspaces in scope.</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <FieldLabel>Landing Zones</FieldLabel>
                  <div className="flex flex-wrap gap-1.5">
                    {project.lzScope.length === 0 && (
                      <span className="text-sm text-muted-foreground">None</span>
                    )}
                    {project.lzScope.map((lz) => (
                      <Badge key={lz} variant="outline">
                        {lz}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="flex flex-col gap-1.5">
                  <FieldLabel>Databricks workspaces</FieldLabel>
                  <div className="flex flex-wrap gap-1.5">
                    {project.dbxScope.length === 0 && (
                      <span className="text-sm text-muted-foreground">None</span>
                    )}
                    {project.dbxScope.map((ws) => (
                      <Badge key={ws} variant="outline">
                        {ws}
                      </Badge>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            <MembersSection projectId={projectId} canAdmin={canAdmin} />

            {canAdmin && (
              <>
                <JoinRequestsSection projectId={projectId} />
                <ScopeRequestSection
                  projectId={projectId}
                  lzScope={project.lzScope}
                  dbxScope={project.dbxScope}
                />
              </>
            )}
          </>
        )}
      </ContentMain>
    </Content>
  );
}
