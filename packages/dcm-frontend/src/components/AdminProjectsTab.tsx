import { Loader2, ShieldCheck, Trash2, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { getDcmApiErrorMessage } from '../api/dcmApiClient';
import {
  useAllJoinRequests,
  useProjectActions,
  useProjectsList,
  useScopeRequests,
} from '../hooks/useProjectsQueries';
import { useToast } from '../hooks/useToast';
import {
  projectRoleLabel,
  projectScopeTypeLabel,
  projectStatusLabel,
  projectStatusVariant,
} from '../lib/role-access';
import { RejectWithReason } from './RejectWithReason';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { FieldLabel } from './ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import type { ProjectScopeRequest, ProjectSummary } from '../types/api';

/** How many scope entries to show inline before collapsing into a "+N" badge. */
const SCOPE_PREVIEW_COUNT = 2;

/** Scope cell: a couple of ids inline, the rest behind a "+N" with a full tooltip. */
function ScopeCell({ values, emptyHint }: { values: string[]; emptyHint: string }) {
  if (values.length === 0) {
    return <span className="text-xs text-muted-foreground">{emptyHint}</span>;
  }
  const shown = values.slice(0, SCOPE_PREVIEW_COUNT);
  const hidden = values.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((value) => (
        <Badge key={value} variant="outline" className="font-mono text-[10px]">
          {value}
        </Badge>
      ))}
      {hidden > 0 && (
        <Badge variant="secondary" className="text-[10px]" title={values.join(', ')}>
          +{hidden}
        </Badge>
      )}
    </div>
  );
}

/** One submission of scope items: the rows the backend wrote for a single request. */
interface ScopeRequestBatch {
  key: string;
  projectId: string;
  justification: string | null;
  requests: ProjectScopeRequest[];
}

/**
 * Rebuild the submissions the pending rows came from.
 *
 * A scope request can carry several items, and the backend stores one row per
 * item sharing `(project, requester, requestedAt)`. Grouping on that triple gives
 * the admin one card and one decision per request instead of N look-alike cards.
 */
function groupScopeRequests(requests: ProjectScopeRequest[]): ScopeRequestBatch[] {
  const batches = new Map<string, ScopeRequestBatch>();
  for (const request of requests) {
    const key = `${request.projectId}|${request.requestedBy}|${request.requestedAt}`;
    const batch = batches.get(key);
    if (batch) {
      batch.requests.push(request);
      continue;
    }
    batches.set(key, {
      key,
      projectId: request.projectId,
      justification: request.justification,
      requests: [request],
    });
  }
  return [...batches.values()];
}

/** How a batch is named in buttons and labels — a single item keeps its own name. */
function scopeBatchSummary(batch: ScopeRequestBatch): string {
  const [first] = batch.requests;
  return batch.requests.length === 1
    ? `${projectScopeTypeLabel(first.scopeType)} ${first.scopeRef}`
    : `${batch.requests.length} scope items`;
}

/** `3 members` / `1 member` — the confirmation states counts, so it must read right. */
function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

/**
 * Delete button that expands into a confirmation naming what disappears.
 *
 * Deletion drops the project's scope, its memberships and its open requests, and
 * Delta offers no undo — too much for a single click. Rejection only refuses a
 * *pending* creation, so this is the only exit for a project activated by mistake.
 */
function DeleteProjectButton({
  project,
  busy,
  onDelete,
}: {
  project: ProjectSummary;
  busy: boolean;
  onDelete: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button
        size="sm"
        variant="ghost"
        className="text-destructive hover:text-destructive"
        aria-label={`Delete project ${project.name}`}
        disabled={busy}
        onClick={() => setOpen(true)}
      >
        <Trash2 size={14} aria-hidden="true" />
        Delete
      </Button>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-3 text-left">
      <p className="text-xs text-muted-foreground">
        Delete <span className="font-medium text-foreground">{project.name}</span> and everything
        attached to it: {countLabel(project.memberCount, 'membership')},{' '}
        {countLabel(project.lzScope.length, 'landing zone')},{' '}
        {countLabel(project.dbxScope.length, 'workspace')} and any open request. Members keep their
        DCM account, and the Business Application becomes free again.
      </p>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="destructive"
          aria-label={`Confirm deletion of ${project.name}`}
          disabled={busy}
          onClick={() => void onDelete()}
        >
          {busy && <Loader2 className="animate-spin" />}
          Delete permanently
        </Button>
      </div>
    </div>
  );
}

/**
 * Platform-admin project governance surface (feature 015). Moved out of the
 * "My Projects" page so validation lives with the other super-admin controls:
 * lists every project with what it grants (both scope dimensions and the member
 * count), decides pending creations, and drains the platform-wide queues of join
 * and scope-extension requests.
 */
export function AdminProjectsTab() {
  const toast = useToast();
  const { validate, reject, remove, decideJoin, decideScope } = useProjectActions();
  const projectsQuery = useProjectsList();
  const joinRequestsQuery = useAllJoinRequests();
  const scopeRequestsQuery = useScopeRequests();
  const [busyId, setBusyId] = useState<string | null>(null);

  const projects = projectsQuery.data ?? [];
  const joinRequests = (joinRequestsQuery.data ?? []).filter((r) => r.status === 'pending');
  const scopeBatches = groupScopeRequests(
    (scopeRequestsQuery.data ?? []).filter((r) => r.status === 'pending')
  );
  const pendingProjects = projects.filter((p) => p.status === 'pending_validation').length;

  const handleValidate = async (projectId: string) => {
    setBusyId(projectId);
    try {
      await validate(projectId);
      toast.showSuccess('Project activated', 'The creator is now a project admin.');
    } catch (error) {
      toast.showError('Unable to validate project', getDcmApiErrorMessage(error, 'Please retry.'));
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (projectId: string, reason: string) => {
    setBusyId(projectId);
    try {
      await reject(projectId, { reason });
      toast.showSuccess(
        'Project rejected',
        'Its Business Application is free again for another request.'
      );
    } catch (error) {
      toast.showError('Unable to reject project', getDcmApiErrorMessage(error, 'Please retry.'));
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (project: ProjectSummary) => {
    setBusyId(project.id);
    try {
      await remove(project.id);
      toast.showSuccess(
        'Project deleted',
        `${project.name} and its scope are gone. Its members keep their DCM account.`
      );
    } catch (error) {
      toast.showError('Unable to delete project', getDcmApiErrorMessage(error, 'Please retry.'));
    } finally {
      setBusyId(null);
    }
  };

  const handleJoinDecision = async (
    projectId: string,
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

  /**
   * Decide a whole submission. Each item is its own row on the backend, so the
   * decision is applied per row — sequentially, to keep the warehouse writes
   * ordered and to stop at the first failure rather than half-granting silently.
   */
  const handleScopeDecision = async (
    batch: ScopeRequestBatch,
    decision: 'approved' | 'rejected',
    reason?: string
  ) => {
    setBusyId(batch.key);
    try {
      for (const request of batch.requests) {
        await decideScope(request.id, { decision, reason });
      }
      const count = batch.requests.length;
      toast.showSuccess(
        decision === 'approved' ? 'Scope granted' : 'Scope request rejected',
        count === 1 ? undefined : `${count} items in this request.`
      );
    } catch (error) {
      toast.showError(
        'Unable to decide scope request',
        getDcmApiErrorMessage(error, 'Please retry.')
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck size={16} /> Projects
            {pendingProjects > 0 && <Badge variant="warning">{pendingProjects} to validate</Badge>}
          </CardTitle>
          <CardDescription>
            Every project across the platform with the Landing Zones and Databricks workspaces it
            grants. Validate a creation request before its scope becomes active, reject it to free
            the Business Application, or delete a project that should no longer exist.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {projectsQuery.isLoading ? (
            <span className="text-sm text-muted-foreground">Loading projects…</span>
          ) : projects.length === 0 ? (
            <span className="text-sm text-muted-foreground">No project registered yet.</span>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Business application</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Landing Zones</TableHead>
                  <TableHead>Databricks workspaces</TableHead>
                  <TableHead className="text-right">Members</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map((project) => (
                  <TableRow key={project.id}>
                    <TableCell>
                      <Link
                        to={`/projects/${encodeURIComponent(project.id)}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {project.name}
                      </Link>
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-muted-foreground">
                      {project.businessAppId}
                    </TableCell>
                    <TableCell>
                      <Badge variant={projectStatusVariant(project.status)}>
                        {projectStatusLabel(project.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <ScopeCell values={project.lzScope} emptyHint="No LZ" />
                    </TableCell>
                    <TableCell>
                      <ScopeCell values={project.dbxScope} emptyHint="No workspace" />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <span className="inline-flex items-center gap-1 text-muted-foreground">
                        <Users size={12} aria-hidden="true" />
                        {project.memberCount}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-col items-end gap-2">
                        {project.status === 'pending_validation' && (
                          <div className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              onClick={() => void handleValidate(project.id)}
                              disabled={busyId === project.id}
                            >
                              {busyId === project.id && <Loader2 className="animate-spin" />}
                              Validate
                            </Button>
                            <RejectWithReason
                              subject={project.name}
                              busy={busyId === project.id}
                              onReject={(reason) => handleReject(project.id, reason)}
                            />
                          </div>
                        )}
                        <DeleteProjectButton
                          project={project}
                          busy={busyId === project.id}
                          onDelete={() => handleDelete(project)}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Join requests</CardTitle>
          <CardDescription>
            Pending requests across every project. A platform admin can decide them so a request
            never waits on a project admin who never signs in.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <FieldLabel>Pending requests</FieldLabel>
          {joinRequestsQuery.isLoading ? (
            <span className="text-sm text-muted-foreground">Loading join requests…</span>
          ) : joinRequests.length === 0 ? (
            <span className="text-sm text-muted-foreground">No pending join request.</span>
          ) : (
            joinRequests.map((request) => (
              <div
                key={request.id}
                className="flex flex-col gap-2 rounded-xl border border-border/60 p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium" title={request.userId}>
                    {request.displayName}
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    <span className="font-mono">{request.projectId}</span> ·{' '}
                    {projectRoleLabel(request.requestedRole)}
                    {request.justification ? ` · ${request.justification}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 items-start gap-2">
                  <Button
                    size="sm"
                    aria-label={`Approve ${request.displayName} on ${request.projectId}`}
                    disabled={busyId === request.id}
                    onClick={() => void handleJoinDecision(request.projectId, request.id, 'approved')}
                  >
                    Approve
                  </Button>
                  <RejectWithReason
                    subject={`${request.displayName} on ${request.projectId}`}
                    busy={busyId === request.id}
                    onReject={(reason) =>
                      handleJoinDecision(request.projectId, request.id, 'rejected', reason)
                    }
                  />
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Scope extension requests</CardTitle>
          <CardDescription>Grant additional landing zones or Databricks workspaces.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <FieldLabel>Pending requests</FieldLabel>
          {scopeBatches.length === 0 && (
            <span className="text-sm text-muted-foreground">No pending scope request.</span>
          )}
          {scopeBatches.map((batch) => (
            <div
              key={batch.key}
              className="flex flex-col gap-2 rounded-xl border border-border/60 p-3 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="min-w-0 flex flex-col gap-1.5">
                {/* One badge per item: a batch is decided as a whole, but the
                    admin still sees everything it grants. */}
                <div className="flex flex-wrap gap-1.5">
                  {batch.requests.map((request) => (
                    <Badge key={request.id} variant="outline" className="text-[10px]">
                      {projectScopeTypeLabel(request.scopeType)}: {request.scopeRef}
                    </Badge>
                  ))}
                </div>
                <p className="truncate font-mono text-[11px] text-muted-foreground">
                  {batch.projectId}
                  {batch.justification ? (
                    <span className="font-sans"> · {batch.justification}</span>
                  ) : null}
                </p>
              </div>
              <div className="flex shrink-0 items-start gap-2">
                <Button
                  size="sm"
                  aria-label={`Approve ${scopeBatchSummary(batch)} for ${batch.projectId}`}
                  onClick={() => void handleScopeDecision(batch, 'approved')}
                  disabled={busyId === batch.key}
                >
                  {busyId === batch.key && <Loader2 className="animate-spin" />}
                  {batch.requests.length === 1 ? 'Approve' : `Approve all (${batch.requests.length})`}
                </Button>
                <RejectWithReason
                  subject={scopeBatchSummary(batch)}
                  label={batch.requests.length === 1 ? 'Reject' : 'Reject all'}
                  busy={busyId === batch.key}
                  onReject={(reason) => handleScopeDecision(batch, 'rejected', reason)}
                />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
