import type {
  UcUsageRecommendationAgeBucket,
  UcUsageRecommendationCharts,
  UcUsageSeverityDistribution,
} from '../../../types/api';
import { formatNumber } from '../../../lib/compute/format';
import { ucUsageCategoryLabel } from '../../../lib/uc-usage/labels';
import {
  AGE_LABELS,
  GOVERNANCE_SEVERITIES,
  governanceIdentity,
  type UcRecommendationFocus,
} from './uc-governance-chart-utils';
import {
  GovernanceChartCard,
  GovernanceChartStatus,
  GovernanceEmpty,
  GovernanceInteractiveBars,
  GovernanceSeverityLegend,
  type GovernanceChartState,
} from './uc-governance-chart-frame';

function distributionRows(rows: UcUsageSeverityDistribution[], label: (key: string) => string) {
  return rows.map((row) => ({
    key: row.bucket,
    label: label(row.bucket),
    total: row.total,
    description: `${label(row.bucket)} : ${GOVERNANCE_SEVERITIES.map((s) => `${row[s.key]} ${s.label}`).join(', ')}. Filter recommendations.`,
    segments: GOVERNANCE_SEVERITIES.map((s) => ({ value: row[s.key], color: s.color })),
  }));
}

export function UcRecommendationChartsPanel(
  props: GovernanceChartState<UcUsageRecommendationCharts> & {
    onFocus: (focus: UcRecommendationFocus) => void;
  }
) {
  const { data, loading, error, onFocus } = props;
  if (loading || error || !data) return <GovernanceChartStatus {...props} />;
  const categories = [...data.categories].sort(
    (a, b) => b.total - a.total || a.bucket.localeCompare(b.bucket)
  );
  const ages = data.ages.filter((row) => row.bucket !== 'unknown' || row.total > 0);
  const priorityMax = Math.max(1, ...data.priorities.map((p) => p.open_total));
  return (
    <div className="grid gap-4 lg:grid-cols-2" aria-label="Recommendation charts">
      <GovernanceChartCard
        title="Recommendation categories & severity"
        subtitle="Which issues dominate across the selected tables?"
        note={`${formatNumber(data.summary.open_total)} open recommendations across ${formatNumber(data.summary.affected_tables)} distinct tables. One table can have multiple recommendations.`}
      >
        {data.summary.open_total ? (
          <>
            <GovernanceInteractiveBars
              ariaLabel="Recommendations by category and severity"
              rows={distributionRows(categories, ucUsageCategoryLabel)}
              onSelect={(category) => onFocus({ label: ucUsageCategoryLabel(category), category })}
            />
            <GovernanceSeverityLegend unknown={categories.some((row) => row.UNKNOWN > 0)} />
          </>
        ) : (
          <GovernanceEmpty>No open recommendations for these tables.</GovernanceEmpty>
        )}
      </GovernanceChartCard>
      <GovernanceChartCard
        title="Age of open recommendations"
        subtitle="Which important issues remain unresolved?"
        note="Age since the current episode was first detected. Reopening starts a new episode; this chart does not measure time to resolution."
      >
        <div className="mb-4 flex items-baseline gap-2">
          <strong className="text-2xl font-semibold tabular-nums">
            {formatNumber(data.summary.old_high)}
          </strong>
          <span className="text-xs text-muted-foreground">
            High recommendations open for more than 30 days
          </span>
        </div>
        {data.summary.open_total ? (
          <>
            <GovernanceInteractiveBars
              ariaLabel="Recommendations by age"
              rows={distributionRows(
                ages,
                (key) => AGE_LABELS[key as UcUsageRecommendationAgeBucket] ?? key
              )}
              onSelect={(key) => {
                const ageBucket = key as UcUsageRecommendationAgeBucket;
                onFocus({ label: `Age: ${AGE_LABELS[ageBucket] ?? key}`, ageBucket });
              }}
            />
            <GovernanceSeverityLegend unknown={ages.some((row) => row.UNKNOWN > 0)} />
          </>
        ) : (
          <GovernanceEmpty>No open recommendations for these tables.</GovernanceEmpty>
        )}
      </GovernanceChartCard>
      <GovernanceChartCard
        title="Tables to prioritise"
        wide
        subtitle="Top 5 by High count, then oldest High recommendation, then observed downstream links."
        note="Bars show open recommendations by severity. Only tables with at least one High recommendation are ranked. Click a table to inspect its recommendations."
      >
        {data.priorities.length ? (
          <>
            <ol className="space-y-4" aria-label="Priority tables">
              {data.priorities.map((row, index) => {
                const values = [row.open_high, row.open_medium, row.open_low, row.open_unknown];
                return (
                  <li key={governanceIdentity(row.cloud_provider, row.table_full_name)}>
                    <button
                      type="button"
                      onClick={() =>
                        onFocus({
                          label: `${row.table_full_name} · all clouds`,
                          table: row.table_full_name,
                        })
                      }
                      aria-label={`${row.table_full_name} · ${row.cloud_provider ?? ''} : ${row.open_high} High, oldest ${formatNumber(row.oldest_high_days)} days. View recommendations.`}
                      className="grid min-h-11 w-full grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-3 rounded-md text-left hover:bg-muted/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring sm:grid-cols-[24px_minmax(0,1.3fr)_minmax(70px,1fr)_auto]"
                    >
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="min-w-0 break-all text-xs font-semibold text-foreground">
                        {row.table_full_name}
                        <span className="mt-1 block text-[11px] font-normal text-muted-foreground">
                          {row.cloud_provider ? `${row.cloud_provider} · ` : ''}
                          {row.open_high} High · oldest: {formatNumber(row.oldest_high_days)} days ·{' '}
                          {formatNumber(row.downstream_fanout)} downstream links
                        </span>
                      </span>
                      <span
                        className="col-start-2 row-start-2 flex h-3 overflow-hidden rounded-[3px] bg-muted sm:col-start-auto sm:row-start-auto"
                        aria-hidden
                      >
                        {GOVERNANCE_SEVERITIES.map((severity, i) => (
                          <span
                            key={severity.key}
                            className="h-full"
                            style={{
                              width: `${(100 * values[i]) / priorityMax}%`,
                              background: severity.color,
                            }}
                          />
                        ))}
                      </span>
                      <span className="col-start-3 row-start-1 text-xs font-semibold tabular-nums sm:col-start-auto sm:row-start-auto">
                        {formatNumber(row.open_total)} open
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
            <GovernanceSeverityLegend
              unknown={data.priorities.some((row) => row.open_unknown > 0)}
            />
          </>
        ) : (
          <GovernanceEmpty>No High recommendations for these tables.</GovernanceEmpty>
        )}
      </GovernanceChartCard>
    </div>
  );
}
