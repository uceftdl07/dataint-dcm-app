import { Link2, ExternalLink, LayoutDashboard, Plus, Save, Trash2 } from 'lucide-react';
import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createAdminEmbeddedDashboard,
  deleteAdminEmbeddedDashboard,
  getDcmApiErrorMessage,
  listAdminEmbeddedDashboards,
  updateAdminEmbeddedDashboard,
  type AdminEmbeddedDashboard,
  type AdminEmbeddedDashboardCreate,
} from '../api/dcmApiClient';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { FieldLabel, Input, Select, Textarea } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { QUERY_GC_ADMIN_MS, QUERY_STALE_ADMIN_MS } from '../hooks/query-config';
import { embeddedDashboardsQueryKeys } from '../hooks/query-keys';
import { useToast } from '../hooks/useToast';
import { parseDatabricksDashboardUrl, type ParsedDatabricksDashboardUrl } from '../lib/databricks/parse-dashboard-url';

const emptyForm: AdminEmbeddedDashboardCreate = {
  dashboard_slug: '',
  title: '',
  description: '',
  workspace_host: 'https://',
  workspace_id: '',
  dashboard_id: '',
  scope: 'global',
  source_lz_id: '',
  menu_group: 'insights',
  sort_order: 0,
  enabled: true,
};

function toFormState(item: AdminEmbeddedDashboard): AdminEmbeddedDashboardCreate {
  return {
    dashboard_slug: item.dashboard_slug,
    title: item.title,
    description: item.description ?? '',
    workspace_host: item.workspace_host,
    workspace_id: item.workspace_id,
    dashboard_id: item.dashboard_id,
    scope: item.scope,
    source_lz_id: item.source_lz_id ?? '',
    menu_group: item.menu_group,
    sort_order: item.sort_order,
    enabled: item.enabled,
  };
}

function applyParsedUrlToForm(
  form: AdminEmbeddedDashboardCreate,
  value: ParsedDatabricksDashboardUrl,
  options: { overwriteSlug?: boolean },
): AdminEmbeddedDashboardCreate {
  return {
    ...form,
    workspace_host: value.workspace_host,
    workspace_id: value.workspace_id,
    dashboard_id: value.dashboard_id,
    dashboard_slug: options.overwriteSlug || !form.dashboard_slug.trim()
      ? value.suggested_slug
      : form.dashboard_slug,
  };
}

interface DashboardUrlImportProps {
  onApply: (url: string) => boolean;
}

const DashboardUrlImport: React.FC<DashboardUrlImportProps> = ({ onApply }) => {
  const [dashboardUrl, setDashboardUrl] = useState('');

  return (
    <div className="grid gap-2 rounded-xl border border-dashed border-primary/30 bg-primary/5 p-3 md:col-span-2 xl:col-span-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="grid min-w-0 flex-1 gap-1">
          <FieldLabel>Databricks dashboard URL</FieldLabel>
          <Input
            value={dashboardUrl}
            onChange={(event) => setDashboardUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                if (onApply(dashboardUrl)) {
                  setDashboardUrl('');
                }
              }
            }}
            placeholder="https://dbc-….cloud.databricks.com/dashboardsv3/…/published?o=…"
          />
        </label>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => {
            if (onApply(dashboardUrl)) {
              setDashboardUrl('');
            }
          }}
        >
          <Link2 />
          Fill from URL
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Paste the published or embed URL from Databricks. DCM extracts host, workspace ID and dashboard ID automatically.
      </p>
    </div>
  );
};

export const AdminEmbeddedDashboardsTab: React.FC = () => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [createForm, setCreateForm] = useState<AdminEmbeddedDashboardCreate>(emptyForm);
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<AdminEmbeddedDashboardCreate | null>(null);

  const dashboardsQuery = useQuery({
    queryKey: [...embeddedDashboardsQueryKeys.all, 'admin'] as const,
    queryFn: () => listAdminEmbeddedDashboards(),
    staleTime: QUERY_STALE_ADMIN_MS,
    gcTime: QUERY_GC_ADMIN_MS,
  });

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: embeddedDashboardsQueryKeys.all }),
    ]);
  };

  const applyDashboardUrl = (
    rawUrl: string,
    setForm: React.Dispatch<React.SetStateAction<AdminEmbeddedDashboardCreate>>,
    options: { overwriteSlug?: boolean } = {},
  ) => {
    const parsed = parseDatabricksDashboardUrl(rawUrl);
    if (!parsed.ok) {
      toast.showError('URL parse failed', parsed.error);
      return false;
    }

    setForm((prev) => applyParsedUrlToForm(prev, parsed.value, {
      overwriteSlug: options.overwriteSlug,
    }));
    toast.showSuccess('Dashboard URL parsed', `${parsed.value.workspace_host} · ${parsed.value.dashboard_id.slice(0, 8)}…`);
    return true;
  };

  const createMutation = useMutation({
    mutationFn: () => createAdminEmbeddedDashboard({
      ...createForm,
      description: createForm.description?.trim() || null,
      source_lz_id: createForm.source_lz_id?.trim() || null,
    }),
    onSuccess: async (_data, _variables, _context) => {
      toast.showSuccess('Embedded dashboard created', createForm.title);
      setCreateForm(emptyForm);
      await invalidate();
    },
    onError: (error) => {
      toast.showError('Create failed', getDcmApiErrorMessage(error, 'Unable to create dashboard'));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ slug, payload }: { slug: string; payload: AdminEmbeddedDashboardCreate }) =>
      updateAdminEmbeddedDashboard(slug, {
        title: payload.title,
        description: payload.description?.trim() || null,
        workspace_host: payload.workspace_host,
        workspace_id: payload.workspace_id,
        dashboard_id: payload.dashboard_id,
        scope: payload.scope,
        source_lz_id: payload.source_lz_id?.trim() || null,
        menu_group: payload.menu_group,
        sort_order: payload.sort_order,
        enabled: payload.enabled,
      }),
    onSuccess: async () => {
      toast.showSuccess('Embedded dashboard updated', editingSlug ?? '');
      setEditingSlug(null);
      setEditForm(null);
      await invalidate();
    },
    onError: (error) => {
      toast.showError('Update failed', getDcmApiErrorMessage(error, 'Unable to update dashboard'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (slug: string) => deleteAdminEmbeddedDashboard(slug),
    onSuccess: async () => {
      toast.showSuccess('Embedded dashboard deleted', 'Removed from DCM Insights');
      await invalidate();
    },
    onError: (error) => {
      toast.showError('Delete failed', getDcmApiErrorMessage(error, 'Unable to delete dashboard'));
    },
  });

  const error = dashboardsQuery.error
    ? getDcmApiErrorMessage(dashboardsQuery.error, 'Error while loading embedded dashboards')
    : null;

  const items = dashboardsQuery.data?.items ?? [];
  const mutating = createMutation.isPending || updateMutation.isPending || deleteMutation.isPending;

  const scopeOptions = useMemo(
    () => [
      { value: 'global', label: 'Global' },
      { value: 'workspace', label: 'Workspace' },
      { value: 'landing_zone', label: 'Landing zone' },
    ],
    [],
  );

  const renderFormFields = (
    form: AdminEmbeddedDashboardCreate,
    setForm: React.Dispatch<React.SetStateAction<AdminEmbeddedDashboardCreate>>,
    options: { slugReadOnly?: boolean; showUrlImport?: boolean; overwriteSlugOnImport?: boolean },
  ) => (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {options.showUrlImport ? (
        <DashboardUrlImport onApply={(url) => applyDashboardUrl(url, setForm, { overwriteSlug: options.overwriteSlugOnImport })} />
      ) : null}
      <label className="grid gap-1">
        <FieldLabel>Slug</FieldLabel>
        <Input
          value={form.dashboard_slug}
          readOnly={options.slugReadOnly}
          onChange={(event) => setForm((prev) => ({ ...prev, dashboard_slug: event.target.value }))}
          placeholder="genie-obs"
        />
      </label>
      <label className="grid gap-1">
        <FieldLabel>Title</FieldLabel>
        <Input value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} />
      </label>
      <label className="grid gap-1">
        <FieldLabel>Menu group</FieldLabel>
        <Input value={form.menu_group} onChange={(event) => setForm((prev) => ({ ...prev, menu_group: event.target.value }))} />
      </label>
      <label className="grid gap-1 md:col-span-2 xl:col-span-3">
        <FieldLabel>Description</FieldLabel>
        <Textarea value={form.description ?? ''} onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))} />
      </label>
      <label className="grid gap-1 md:col-span-2 xl:col-span-3">
        <FieldLabel>Workspace host</FieldLabel>
        <Input value={form.workspace_host} onChange={(event) => setForm((prev) => ({ ...prev, workspace_host: event.target.value }))} />
      </label>
      <label className="grid gap-1">
        <FieldLabel>Workspace ID</FieldLabel>
        <Input value={form.workspace_id} onChange={(event) => setForm((prev) => ({ ...prev, workspace_id: event.target.value }))} />
      </label>
      <label className="grid gap-1 md:col-span-2">
        <FieldLabel>Dashboard ID</FieldLabel>
        <Input value={form.dashboard_id} onChange={(event) => setForm((prev) => ({ ...prev, dashboard_id: event.target.value }))} />
      </label>
      <label className="grid gap-1">
        <FieldLabel>Scope</FieldLabel>
        <Select value={form.scope} onChange={(event) => setForm((prev) => ({ ...prev, scope: event.target.value }))}>
          {scopeOptions.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </Select>
      </label>
      <label className="grid gap-1">
        <FieldLabel>Source LZ ID</FieldLabel>
        <Input value={form.source_lz_id ?? ''} onChange={(event) => setForm((prev) => ({ ...prev, source_lz_id: event.target.value }))} placeholder="optional" />
      </label>
      <label className="grid gap-1">
        <FieldLabel>Sort order</FieldLabel>
        <Input type="number" value={form.sort_order ?? 0} onChange={(event) => setForm((prev) => ({ ...prev, sort_order: Number(event.target.value) }))} />
      </label>
      <label className="grid gap-1">
        <FieldLabel>Enabled</FieldLabel>
        <Select
          value={form.enabled ? 'true' : 'false'}
          onChange={(event) => setForm((prev) => ({ ...prev, enabled: event.target.value === 'true' }))}
        >
          <option value="true">Enabled</option>
          <option value="false">Disabled</option>
        </Select>
      </label>
    </div>
  );

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LayoutDashboard className="h-5 w-5 text-primary" />
            Embedded Databricks dashboards
          </CardTitle>
          <CardDescription>
            Register AI/BI dashboards to embed in DCM Insights. Paste a Databricks URL to pre-fill host, workspace and dashboard IDs.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? <p className="text-sm text-destructive">{error}</p> : null}

          <div className="rounded-2xl border border-border/70 bg-card p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p className="font-medium">Add dashboard</p>
                <p className="text-sm text-muted-foreground">Paste the Databricks URL, adjust slug/title, then create.</p>
              </div>
              <Button size="sm" onClick={() => createMutation.mutate()} disabled={mutating || !createForm.dashboard_slug || !createForm.title}>
                <Plus />
                Create
              </Button>
            </div>
            {renderFormFields(createForm, setCreateForm, { slugReadOnly: false, showUrlImport: true, overwriteSlugOnImport: true })}
          </div>

          {dashboardsQuery.isLoading ? (
            <Skeleton className="h-48 rounded-xl" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dashboard</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.dashboard_slug}>
                    <TableCell>
                      <div className="space-y-1">
                        <p className="font-medium">{item.title}</p>
                        <p className="text-xs text-muted-foreground">{item.dashboard_slug}</p>
                      </div>
                    </TableCell>
                    <TableCell>{item.scope}</TableCell>
                    <TableCell>
                      <Badge variant={item.enabled ? 'success' : 'secondary'}>
                        {item.enabled ? 'Enabled' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/databricks/insights/${item.dashboard_slug}`}
                          className="inline-flex h-8 items-center rounded-full border border-border px-3 text-xs font-medium hover:bg-accent"
                        >
                          <ExternalLink className="mr-1 h-3.5 w-3.5" />
                          Preview
                        </Link>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditingSlug(item.dashboard_slug);
                            setEditForm(toFormState(item));
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={mutating}
                          onClick={() => {
                            if (window.confirm(`Delete embedded dashboard "${item.title}"?`)) {
                              deleteMutation.mutate(item.dashboard_slug);
                            }
                          }}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {editingSlug && editForm ? (
        <Card>
          <CardHeader>
            <CardTitle>Edit {editingSlug}</CardTitle>
            <CardDescription>Update embed settings. Paste a new Databricks URL to refresh host and IDs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {renderFormFields(editForm, (updater) => {
              setEditForm((prev) => {
                if (!prev) return prev;
                return typeof updater === 'function' ? updater(prev) : updater;
              });
            }, { slugReadOnly: true, showUrlImport: true, overwriteSlugOnImport: false })}
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => updateMutation.mutate({ slug: editingSlug, payload: editForm })}
                disabled={mutating}
              >
                <Save />
                Save
              </Button>
              <Button size="sm" variant="outline" onClick={() => { setEditingSlug(null); setEditForm(null); }}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
};
