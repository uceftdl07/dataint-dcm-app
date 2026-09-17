export interface ParsedDatabricksDashboardUrl {
  workspace_host: string;
  workspace_id: string;
  dashboard_id: string;
  suggested_slug: string;
}

export type ParseDatabricksDashboardUrlResult =
  | { ok: true; value: ParsedDatabricksDashboardUrl }
  | { ok: false; error: string };

const DASHBOARD_ID_PATTERN = /\/(?:embed\/)?dashboardsv3\/([0-9a-f]{32})(?:\/|$|\?)/i;

function slugifyDashboardId(dashboardId: string): string {
  return `dashboard-${dashboardId.slice(0, 8).toLowerCase()}`;
}

export function parseDatabricksDashboardUrl(rawInput: string): ParseDatabricksDashboardUrlResult {
  const input = rawInput.trim();
  if (!input) {
    return { ok: false, error: 'Paste a Databricks dashboard URL first.' };
  }

  let url: URL;
  try {
    url = new URL(input);
  } catch {
    return { ok: false, error: 'Invalid URL. Use a full https://… URL from Databricks.' };
  }

  if (url.protocol !== 'https:') {
    return { ok: false, error: 'Dashboard URL must use https.' };
  }

  const dashboardMatch = url.pathname.match(DASHBOARD_ID_PATTERN);
  const dashboard_id = dashboardMatch?.[1];
  if (!dashboard_id) {
    return {
      ok: false,
      error: 'Could not find a dashboardsv3 ID in this URL. Open the published dashboard in Databricks and copy the browser URL.',
    };
  }

  const workspace_id = url.searchParams.get('o')?.trim();
  if (!workspace_id) {
    return {
      ok: false,
      error: 'Workspace ID missing. The URL must include ?o=<workspace_id>.',
    };
  }

  return {
    ok: true,
    value: {
      workspace_host: url.origin,
      workspace_id,
      dashboard_id,
      suggested_slug: slugifyDashboardId(dashboard_id),
    },
  };
}
