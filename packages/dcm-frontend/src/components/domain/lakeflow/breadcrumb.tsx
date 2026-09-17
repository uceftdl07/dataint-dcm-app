/** Compact Lakeflow breadcrumb: Jobs / job_name [/ run]. */
import { Link } from 'react-router-dom';
import { cn } from '../../../lib/utils';

export function LakeflowBreadcrumb({
  jobName,
  jobId,
  runLabel,
  className,
}: {
  jobName?: string | null;
  jobId?: string | null;
  runLabel?: string | null;
  className?: string;
}) {
  const jobPath = jobId
    ? `/databricks/workflows/${encodeURIComponent(jobId)}`
    : '/databricks/workflows';

  return (
    <nav
      aria-label="Fil d'Ariane"
      className={cn(
        'mb-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground',
        className
      )}
    >
      <Link to="/databricks/workflows" className="font-semibold hover:text-[var(--tdf-blue)]">
        Jobs
      </Link>
      {jobId ? (
        <>
          <span aria-hidden>/</span>
          {runLabel ? (
            <Link
              to={jobPath}
              className="max-w-[240px] truncate font-semibold hover:text-[var(--tdf-blue)]"
            >
              {jobName || jobId}
            </Link>
          ) : (
            <span className="max-w-[320px] truncate font-semibold text-foreground">
              {jobName || jobId}
            </span>
          )}
        </>
      ) : null}
      {runLabel ? (
        <>
          <span aria-hidden>/</span>
          <span className="max-w-[280px] truncate font-mono font-semibold text-foreground">
            {runLabel}
          </span>
        </>
      ) : null}
    </nav>
  );
}
