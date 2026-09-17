/** Resolve Databricks query profile URL — never expose statement text in UI. */
export function resolveQueryProfileUrl(params: {
  query_profile_url?: string | null;
  workspace_id: string;
  statement_id: string;
}): string | null {
  const fromApi = params.query_profile_url?.trim();
  if (fromApi) return fromApi;
  if (!params.workspace_id || !params.statement_id) return null;
  const qs = new URLSearchParams({ statementId: params.statement_id });
  return `https://accounts.cloud.databricks.com/sql/history?${qs.toString()}&o=${encodeURIComponent(params.workspace_id)}`;
}
