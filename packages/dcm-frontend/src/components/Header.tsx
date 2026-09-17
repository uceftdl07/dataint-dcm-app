import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, CalendarDays, Cloud, FolderKanban, Workflow } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  monitoringScopeDefaults,
  useMonitoringScope,
  type MonitoringScope,
} from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { getPageMeta } from '../config/navigation';
import { showsHeaderBackButton } from '../lib/page-navigation';
import {
  showsDatabricksWorkspaceFilter,
  showsGlobalHeaderDateRange,
  showsGlobalHeaderFilters,
  showsGlobalHeaderTimePresets,
  showsLandingZoneFilter,
} from '../lib/databricks/routes';
import { canonicalWorkspaceId, dedupeWorkspacesById } from '../lib/databricks/workspace-label';
import { getSelectedLzIds } from '../lib/monitoring-scope-filter';
import { cn } from '../lib/utils';
import { useDatabricksWorkspacesList } from '../hooks/useDatabricksWorkspacesList';
import { useLandingZonesList } from '../hooks/useLandingZonesList';
import { useProjectsList } from '../hooks/useProjectsQueries';
import { HeaderDatabricksWorkspaceFilter } from './HeaderDatabricksWorkspaceFilter';
import { HeaderLandingZoneFilter } from './HeaderLandingZoneFilter';
import { HeaderNotificationBell } from './HeaderNotificationBell';
import { HeaderProjectFilter } from './HeaderProjectFilter';
import { Input } from './ui/input';
import { DcmGuideButton } from './DcmGuideButton';
import type { ProjectSummary } from '../types/api';

function formatFilterDate(dateValue: string) {
  const [year, month, day] = dateValue.split('-');
  if (!year || !month || !day) return dateValue;

  return `${day}/${month}/${year}`;
}

const dateRangePresets = [
  { label: '30d', days: 30, description: '30 days' },
  { label: '90d', days: 90, description: '90 days' },
  { label: '6m', days: 180, description: '6 months' },
  { label: '1y', days: 365, description: '1 year' },
];

const filterLabelClass = 'sr-only';
const filterControlClass =
  'h-10 min-w-0 rounded-2xl border-tdf-blue-border/20 bg-card px-3 text-sm font-medium text-foreground shadow-sm shadow-slate-950/5 transition hover:border-tdf-blue-border hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tdf-blue-border';
const filterTextClass = 'font-sans text-sm leading-none';
const scopeFieldClass =
  'grid min-w-[10rem] flex-1 basis-[10rem] gap-0.5 sm:basis-[11rem] md:w-44 md:flex-none';
const filterFieldClass = 'grid min-w-[10rem] flex-1 basis-[10rem] gap-0.5 md:w-40 md:flex-none';
const rangeFieldClass = 'grid min-w-[13rem] flex-1 basis-[13rem] gap-0.5 md:w-52 md:flex-none';
const hiddenDateInputClass = 'pointer-events-none absolute left-0 top-0 size-px opacity-0';

type DateInputWithPicker = HTMLInputElement & { showPicker?: () => void };

/**
 * The landing zones a project was granted, as a header scope.
 *
 * Selecting a project has to *apply* its scope, not merely narrow the option
 * lists: leaving the LZ filter on "all" would send no `source_lz_id` at all, and
 * a platform admin would keep seeing the whole platform through a project filter
 * that claims otherwise.
 *
 * Built from `effectiveLzScope`, never from `lzScope`: the registered value can
 * be a subscription id, and a workspace-only project registers no LZ at all — in
 * both cases the raw column sends an id no monitoring row carries, so every page
 * came back empty.
 */
function projectLzScope(project: ProjectSummary): MonitoringScope {
  const sourceLzIds = project.effectiveLzScope;
  // Nothing resolved: a landing zone the monitoring data has not reached yet, or
  // a workspace missing from the reference dimension. An empty list is a
  // `1 = 0` on every page, so leave the LZ filter open and let the server-side
  // project scope do the narrowing — it applies with or without this filter.
  if (sourceLzIds.length === 0) return monitoringScopeDefaults.all;

  return {
    kind: 'landing-zones',
    label: sourceLzIds.length === 1 ? sourceLzIds[0] : `${sourceLzIds.length} landing zones`,
    sourceLzIds,
  };
}

function openNativeDatePicker(input: HTMLInputElement | null) {
  if (!input) return;

  input.focus();
  try {
    const pickerInput = input as DateInputWithPicker;
    if (pickerInput.showPicker) {
      pickerInput.showPicker();
      return;
    }
  } catch {
    // Some browsers only allow showPicker from a direct user gesture.
  }
  input.click();
}

const Header: React.FC = () => {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const pageMeta = getPageMeta(pathname);
  const showGlobalFilters = showsGlobalHeaderFilters(pathname);
  const showGlobalDateRange = showsGlobalHeaderDateRange(pathname);
  const showGlobalTimePresets = showsGlobalHeaderTimePresets(pathname);
  const showDatabricksWorkspaceFilter = showsDatabricksWorkspaceFilter(pathname);
  const showLandingZoneFilter = showsLandingZoneFilter(pathname);
  const {
    scope,
    setScope,
    databricksWorkspaceIds,
    setDatabricksWorkspaceIds,
    projectId,
    setProjectId,
  } = useMonitoringScope();
  const { timeRange, updateTimeRange } = useGlobalTimeRange();
  const landingZonesQuery = useLandingZonesList(showLandingZoneFilter);
  const workspacesQuery = useDatabricksWorkspacesList(showDatabricksWorkspaceFilter);
  const projectsQuery = useProjectsList(showGlobalFilters);
  // Only an active project grants anything: a pending creation carries a scope
  // that nobody may query yet.
  const activeProjects = useMemo(
    () => (projectsQuery.data ?? []).filter((project) => project.status === 'active'),
    [projectsQuery.data]
  );
  const selectedProject = useMemo(
    () => activeProjects.find((project) => project.id === projectId) ?? null,
    [activeProjects, projectId]
  );
  /**
   * A selected project turns the two other filters into pickers over its own
   * scope — its landing zones on one side, its Databricks workspaces on the
   * other. Narrowing the lists is what makes the pruning effects below drop any
   * selection inherited from a wider scope.
   */
  const landingZones = useMemo(() => {
    const items = landingZonesQuery.data?.items ?? [];
    if (!selectedProject) return items;

    // `effectiveLzScope` speaks the `lz_id` vocabulary this list is keyed on;
    // intersecting with the registered `lzScope` emptied the selector whenever a
    // grant was stored as a subscription id or came from a workspace only.
    const granted = new Set(selectedProject.effectiveLzScope);
    if (granted.size === 0) return items;

    return items.filter((landingZone) => granted.has(landingZone.lz_id));
  }, [landingZonesQuery.data?.items, selectedProject]);
  const workspaces = useMemo(() => {
    const items = workspacesQuery.data?.items ?? [];
    if (!selectedProject) return items;

    const granted = new Set(selectedProject.dbxScope.map(canonicalWorkspaceId));
    return items.filter((workspace) => granted.has(canonicalWorkspaceId(workspace.workspace_id)));
  }, [workspacesQuery.data?.items, selectedProject]);
  const loadingScopes = showLandingZoneFilter && landingZonesQuery.isLoading;
  const loadingWorkspaces = showDatabricksWorkspaceFilter && workspacesQuery.isLoading;
  const scopeError = showLandingZoneFilter && landingZonesQuery.isError;
  const workspaceError = showDatabricksWorkspaceFilter && workspacesQuery.isError;
  const [customStartDate, setCustomStartDate] = useState(timeRange.startDate);
  const [customEndDate, setCustomEndDate] = useState(timeRange.endDate);
  const [customDateError, setCustomDateError] = useState<string | null>(null);
  const startDateInputRef = useRef<HTMLInputElement>(null);
  const endDateInputRef = useRef<HTMLInputElement>(null);
  const [openHeaderFilter, setOpenHeaderFilter] = useState<'project' | 'lz' | 'workspace' | null>(
    null
  );
  const appliedProjectIdRef = useRef<string | null>(projectId);
  // Nothing to pick from is not worth a control: an account with no project (a
  // legacy unrestricted role, during the transition) sees the header it always had.
  const showProjectFilter = showGlobalFilters && activeProjects.length > 0;

  useEffect(() => {
    if (!showGlobalFilters) {
      setCustomDateError(null);
    }
  }, [showGlobalFilters]);

  /**
   * A project that disappeared — deleted, archived, membership revoked — must
   * stop narrowing the header, otherwise the filters stay locked on a scope the
   * caller no longer holds.
   */
  useEffect(() => {
    if (projectId === null || projectsQuery.isLoading || projectsQuery.isError) return;
    if (activeProjects.some((project) => project.id === projectId)) return;

    setProjectId(null);
  }, [activeProjects, projectId, projectsQuery.isError, projectsQuery.isLoading, setProjectId]);

  /**
   * Apply the project scope when the selection changes: its landing zones become
   * the LZ selection, and its Databricks workspaces become the workspace
   * selection — narrowed to exactly what the project was granted, matching the
   * dropdown's own narrowed list above. `null` here would mean "no workspace
   * filter at all" at the API layer (every workspace the caller can see across
   * every project), not "all of this project's workspaces". The previous
   * selection belonged to another scope, so keeping any of it would be arbitrary.
   */
  useEffect(() => {
    if (appliedProjectIdRef.current === projectId) return;
    // A project id set before the list resolved: wait for its scope.
    if (projectId !== null && selectedProject === null) return;

    appliedProjectIdRef.current = projectId;
    setScope(selectedProject ? projectLzScope(selectedProject) : monitoringScopeDefaults.all);
    setDatabricksWorkspaceIds(
      selectedProject ? selectedProject.dbxScope.map(canonicalWorkspaceId) : null
    );
  }, [projectId, selectedProject, setDatabricksWorkspaceIds, setScope]);

  useEffect(() => {
    if (!showDatabricksWorkspaceFilter) {
      setDatabricksWorkspaceIds(null);
    }
  }, [showDatabricksWorkspaceFilter, setDatabricksWorkspaceIds]);

  /**
   * Narrow the workspace filter to the selected landing zones — but never on an
   * *unknown* landing zone. The live `gold_dbx_workflow_runs` (system-tables
   * path) carries no `source_lz_id`, so a workspace that only appears there has
   * none: dropping it emptied the whole Databricks workspace filter as soon as a
   * project applied its LZ selection. Such a workspace is already inside the
   * caller's scope — the API only returned it because it is granted — so keep it
   * rather than hide a scope the user does hold.
   *
   * Where the LZ filter is hidden the selection is left alone but stops
   * narrowing anything: a list cut down by a control the page does not show is
   * an invisible filter, and the user has no way to widen it back.
   */
  const visibleWorkspaces = useMemo(() => {
    const selectedLzIds = showLandingZoneFilter ? getSelectedLzIds(scope) : null;
    const filtered =
      selectedLzIds === null
        ? workspaces
        : selectedLzIds.length === 0
          ? []
          : workspaces.filter(
              (workspace) =>
                !workspace.source_lz_id || selectedLzIds.includes(workspace.source_lz_id)
            );
    return dedupeWorkspacesById(filtered);
  }, [scope, showLandingZoneFilter, workspaces]);
  // Only worth telling the user to widen a selection they can actually reach.
  const lzSelectionEmpty = showLandingZoneFilter && getSelectedLzIds(scope)?.length === 0;

  useEffect(() => {
    // Nothing to prune against on a page that never shows (or fetches) the
    // workspace filter — `visibleWorkspaces` is permanently empty there, not
    // "everything just got deselected". Pruning anyway wiped a project's
    // correctly-narrowed workspace scope back to `[]` on every non-Databricks
    // page (e.g. Home), which the API reads as "match nothing".
    if (!showDatabricksWorkspaceFilter) return;
    if (databricksWorkspaceIds === null) return;

    const allowed = new Set(visibleWorkspaces.map((workspace) => workspace.workspace_id));
    const next = databricksWorkspaceIds.filter((workspaceId) => allowed.has(workspaceId));
    if (next.length === databricksWorkspaceIds.length) return;

    if (next.length === 0) {
      setDatabricksWorkspaceIds([]);
      return;
    }
    if (next.length === visibleWorkspaces.length) {
      setDatabricksWorkspaceIds(null);
      return;
    }
    setDatabricksWorkspaceIds(next);
  }, [
    databricksWorkspaceIds,
    setDatabricksWorkspaceIds,
    showDatabricksWorkspaceFilter,
    visibleWorkspaces,
  ]);

  useEffect(() => {
    setCustomStartDate(timeRange.startDate);
    setCustomEndDate(timeRange.endDate);
  }, [timeRange.endDate, timeRange.startDate]);

  const showBackButton = showsHeaderBackButton(pathname);

  useEffect(() => {
    // Nothing may rewrite a selection the current page hides: the user would
    // carry the change back to the pages that do read it.
    if (!showLandingZoneFilter) return;
    if (landingZones.length === 0) return;

    const allowed = new Set(landingZones.map((landingZone) => landingZone.lz_id));
    const selected = getSelectedLzIds(scope);
    if (selected === null || selected.length === 0) return;

    const next = selected.filter((lzId) => allowed.has(lzId));
    if (next.length === 0) {
      setScope(monitoringScopeDefaults.all);
      return;
    }

    if (next.length === selected.length) return;

    setScope({
      kind: 'landing-zones',
      label: next.length === 1 ? next[0] : `${next.length} landing zones`,
      sourceLzIds: next,
    });
  }, [landingZones, scope, setScope, showLandingZoneFilter]);

  const goBack = () => {
    if (window.history.length > 1) {
      navigate(-1);
      return;
    }

    navigate('/dashboard');
  };

  const applyPresetRange = (days: number, description: string) => {
    const endDate = new Date();
    const startDate = new Date(endDate.getTime() - days * 24 * 60 * 60 * 1000);
    const formattedStartDate = startDate.toISOString().split('T')[0];
    const formattedEndDate = endDate.toISOString().split('T')[0];

    setCustomDateError(null);
    updateTimeRange(formattedStartDate, formattedEndDate, description);
  };

  const updateCustomDateRange = (startDateValue: string, endDateValue: string) => {
    const startDate = new Date(`${startDateValue}T00:00:00`);
    const endDate = new Date(`${endDateValue}T00:00:00`);
    const today = new Date();
    today.setHours(23, 59, 59, 999);

    if (!startDateValue || !endDateValue) {
      setCustomDateError('Choose a start and end date.');
      return;
    }

    if (
      Number.isNaN(startDate.getTime()) ||
      Number.isNaN(endDate.getTime()) ||
      startDate > endDate
    ) {
      setCustomDateError('Start date must be before end date.');
      return;
    }

    if (endDate > today) {
      setCustomDateError('End date cannot be in the future.');
      return;
    }

    setCustomDateError(null);
    updateTimeRange(startDateValue, endDateValue, `${startDateValue} - ${endDateValue}`);
  };

  return (
    <header className="sticky top-0 z-40 overflow-visible bg-background/90 px-4 py-2 backdrop-blur-xl sm:px-5 lg:px-6">
      <div className="mx-auto grid w-full max-w-screen-2xl gap-1.5">
        <div className="flex min-w-0 flex-col gap-1.5 md:flex-row md:items-end md:justify-between">
          <div className="flex min-w-0 shrink-0 items-center gap-2.5 md:pt-1">
            {showBackButton && (
              <button
                type="button"
                onClick={goBack}
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-full text-muted-foreground transition hover:-translate-x-0.5 hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Go back to previous page"
                title="Go back to previous page"
              >
                <ArrowLeft size={18} />
              </button>
            )}
            <h1 className="min-w-0 truncate text-lg font-semibold leading-tight tracking-[-0.03em] text-foreground">
              {pageMeta.title}
            </h1>
          </div>

          {showGlobalFilters ? (
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2 overflow-visible rounded-2xl bg-card/60 p-1.5 shadow-sm shadow-slate-950/5 md:flex-1 md:justify-end">
              <DcmGuideButton />
              <div className="grid shrink-0 gap-0.5" data-tour="notifications">
                <span className={filterLabelClass}>Notifications</span>
                <HeaderNotificationBell
                  buttonClassName={cn(
                    filterControlClass,
                    'inline-flex size-10 shrink-0 items-center justify-center p-0 text-tdf-blue hover:text-tdf-blue'
                  )}
                />
              </div>
              {showProjectFilter && (
                <div className={scopeFieldClass} data-tour="project-filter">
                  <span className={filterLabelClass}>
                    <FolderKanban size={12} className="text-tdf-blue" />
                    Project
                  </span>
                  <HeaderProjectFilter
                    projects={activeProjects}
                    loading={projectsQuery.isLoading}
                    error={projectsQuery.isError}
                    projectId={projectId}
                    setProjectId={setProjectId}
                    open={openHeaderFilter === 'project'}
                    onOpenChange={(open) => setOpenHeaderFilter(open ? 'project' : null)}
                    buttonClassName={cn(filterControlClass, filterTextClass)}
                  />
                </div>
              )}

              {showLandingZoneFilter && (
                <div className={scopeFieldClass} data-tour="landing-zone-filter">
                  <span className={filterLabelClass}>
                    <Cloud size={12} className="text-tdf-blue" />
                    Landing zones
                  </span>
                  <HeaderLandingZoneFilter
                    landingZones={landingZones}
                    loading={loadingScopes}
                    error={scopeError}
                    scope={scope}
                    setScope={setScope}
                    open={openHeaderFilter === 'lz'}
                    onOpenChange={(open) => setOpenHeaderFilter(open ? 'lz' : null)}
                    buttonClassName={cn(filterControlClass, filterTextClass)}
                  />
                </div>
              )}

              {showDatabricksWorkspaceFilter && (
                <div className={scopeFieldClass} data-tour="workspace-filter">
                  <span className={filterLabelClass}>
                    <Workflow size={12} className="text-tdf-blue" />
                    Workspace
                  </span>
                  <HeaderDatabricksWorkspaceFilter
                    workspaces={visibleWorkspaces}
                    loading={loadingWorkspaces}
                    error={workspaceError}
                    workspaceIds={databricksWorkspaceIds}
                    setWorkspaceIds={setDatabricksWorkspaceIds}
                    lzSelectionEmpty={lzSelectionEmpty}
                    onRequestOpenLandingZones={() => setOpenHeaderFilter('lz')}
                    open={openHeaderFilter === 'workspace'}
                    onOpenChange={(open) => setOpenHeaderFilter(open ? 'workspace' : null)}
                    buttonClassName={cn(filterControlClass, filterTextClass)}
                  />
                </div>
              )}

              {/* Masqué là où aucun tableau ne lit une plage libre : un sélecteur
                  de dates qui ne filtre rien est pire qu'absent — il fait chercher
                  une cause côté données à un écran qui n'a simplement pas bougé. */}
              {showGlobalDateRange && (
                <>
                  <label className={filterFieldClass} htmlFor="period-start-date">
                    <span className={filterLabelClass}>
                      <CalendarDays size={12} className="text-tdf-blue" />
                      Start
                    </span>
                    <div className="relative">
                      <button
                        type="button"
                        aria-label="Open start date picker"
                        className={cn(
                          filterControlClass,
                          filterTextClass,
                          'flex w-full cursor-pointer items-center gap-1.5 py-0 text-left'
                        )}
                        onClick={() => openNativeDatePicker(startDateInputRef.current)}
                      >
                        <span className="shrink-0 text-muted-foreground">From</span>
                        <span className="min-w-0 truncate text-foreground">
                          {formatFilterDate(customStartDate)}
                        </span>
                      </button>
                      <Input
                        ref={startDateInputRef}
                        id="period-start-date"
                        type="date"
                        aria-label="Start date"
                        value={customStartDate}
                        onChange={(event) => {
                          const nextStartDate = event.target.value;
                          setCustomStartDate(nextStartDate);
                          updateCustomDateRange(nextStartDate, customEndDate);
                        }}
                        className={hiddenDateInputClass}
                        tabIndex={-1}
                        title={`From ${formatFilterDate(customStartDate)}`}
                      />
                    </div>
                  </label>
                  <label className={filterFieldClass} htmlFor="period-end-date">
                    <span className={filterLabelClass}>
                      <CalendarDays size={12} className="text-tdf-blue" />
                      End
                    </span>
                    <div className="relative">
                      <button
                        type="button"
                        aria-label="Open end date picker"
                        className={cn(
                          filterControlClass,
                          filterTextClass,
                          'flex w-full cursor-pointer items-center gap-1.5 py-0 text-left'
                        )}
                        onClick={() => openNativeDatePicker(endDateInputRef.current)}
                      >
                        <span className="shrink-0 text-muted-foreground">To</span>
                        <span className="min-w-0 truncate text-foreground">
                          {formatFilterDate(customEndDate)}
                        </span>
                      </button>
                      <Input
                        ref={endDateInputRef}
                        id="period-end-date"
                        type="date"
                        aria-label="End date"
                        value={customEndDate}
                        onChange={(event) => {
                          const nextEndDate = event.target.value;
                          setCustomEndDate(nextEndDate);
                          updateCustomDateRange(customStartDate, nextEndDate);
                        }}
                        className={hiddenDateInputClass}
                        tabIndex={-1}
                        title={`To ${formatFilterDate(customEndDate)}`}
                      />
                    </div>
                  </label>
                </>
              )}
              {showGlobalTimePresets ? (
                <div className={rangeFieldClass} data-tour="date-range">
                  <span className={filterLabelClass}>
                    <CalendarDays size={12} className="text-tdf-blue" />
                    Range
                  </span>
                  <div className="flex h-10 w-full items-center justify-end gap-1.5">
                    {dateRangePresets.map((preset) => {
                      const active = timeRange.description === preset.description;

                      return (
                        <button
                          key={preset.label}
                          type="button"
                          aria-pressed={active}
                          onClick={() => applyPresetRange(preset.days, preset.description)}
                          className={cn(
                            'relative inline-flex h-8 min-w-9 items-center justify-center overflow-hidden rounded-full border px-2 text-xs font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                            active
                              ? 'scale-105 border-transparent bg-gradient-to-br from-tdf-blue to-tdf-teal text-white shadow-lg shadow-tdf-blue/25 ring-2 ring-tdf-blue/15'
                              : 'border-border/60 bg-card/85 text-muted-foreground shadow-sm shadow-slate-950/5 hover:-translate-y-0.5 hover:rotate-[-3deg] hover:border-tdf-blue-border hover:bg-tdf-blue-subtle hover:text-tdf-blue hover:shadow-md'
                          )}
                        >
                          {preset.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="flex shrink-0 items-center gap-2 md:ml-auto md:pt-1">
              <DcmGuideButton />
              <div data-tour="notifications">
                <HeaderNotificationBell
                  buttonClassName={cn(
                    filterControlClass,
                    'inline-flex size-10 shrink-0 items-center justify-center p-0 text-tdf-blue hover:text-tdf-blue'
                  )}
                />
              </div>
            </div>
          )}

          {showGlobalFilters && (customDateError || scopeError) && (
            <div className="flex flex-wrap gap-2 md:justify-end">
              {customDateError && (
                <span className="inline-flex items-center rounded-full border border-warning-border bg-warning-subtle px-3 py-1 text-[11px] font-semibold text-warning">
                  {customDateError}
                </span>
              )}
              {scopeError && (
                <span className="inline-flex items-center rounded-full border border-warning-border bg-warning-subtle px-3 py-1 text-[11px] font-semibold text-warning">
                  Landing Zone metadata unavailable.
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export default Header;
