import type { UcUsageGovernanceCharts } from '../../../types/api';
import { formatNumber, formatPct } from '../../../lib/compute/format';
import { Button } from '../../ui/button';
import { sequentialFill } from '../compute/compute-chart-colors';
import {
  GOVERNANCE_SIGNALS,
  INACTIVITY_LABELS,
  TAG_LABELS,
  governanceIdentity,
  type UcGovernanceFocus,
} from './uc-governance-chart-utils';
import {
  GovernanceChartCard,
  GovernanceChartStatus,
  GovernanceEmpty,
  GovernanceInteractiveBars,
  type GovernanceChartState,
} from './uc-governance-chart-frame';
import { UcGovernanceScatter } from './uc-governance-scatter';

export function UcGovernanceChartsPanel(
  props: GovernanceChartState<UcUsageGovernanceCharts> & {
    onFocus: (focus: UcGovernanceFocus) => void;
  }
) {
  const { data, loading, error, onFocus } = props;
  if (loading || error || !data) return <GovernanceChartStatus {...props} />;
  const total = data.summary.tracked_tables;
  const tableMatrix = data.matrix.mode === 'table';
  return (
    <div className="grid gap-4 lg:grid-cols-2" aria-label="Governance charts">
      <GovernanceChartCard
        title="Inactivity & dependencies"
        subtitle="Which unused tables still have observed downstream dependencies?"
        note={
          <>
            {formatNumber(data.scatter.points.length)} / {formatNumber(data.scatter.total)} tables
            with observed reads and downstream links.
            {data.scatter.total > data.scatter.points.length
              ? ` Display limited to ${data.scatter.limit} points, prioritising signals to review.`
              : ''}{' '}
            Links reflect the latest observed day, rather than a complete dependency graph.
          </>
        }
      >
        <div className="mb-2 flex flex-wrap items-baseline gap-2">
          <strong className="text-2xl font-semibold tabular-nums">
            {formatNumber(data.summary.unused_critical_tables)}
          </strong>
          <span className="text-xs text-muted-foreground">unused and critical tables</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onFocus({ label: 'Unused and critical', signal: 'unused_critical' })}
          >
            Review these tables
          </Button>
        </div>
        <UcGovernanceScatter
          points={data.scatter.points}
          onSelect={(point) =>
            onFocus({
              label: `${point.table_full_name} · all clouds`,
              scope: { tables: [point.table_full_name] },
            })
          }
        />
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 h-auto max-w-full whitespace-normal text-left"
          onClick={() => onFocus({ label: 'No read observed', inactivity: 'unobserved' })}
        >
          {formatNumber(data.scatter.unobserved_reads)} tables with no observed read → registry
        </Button>
      </GovernanceChartCard>

      <GovernanceChartCard
        title={`Signals by ${tableMatrix ? 'table' : 'schema'}`}
        subtitle={
          tableMatrix
            ? 'Table profiles within the selected schema.'
            : 'Compare the share of affected tables in each schema.'
        }
        note={
          <>
            {data.matrix.rows.length} / {formatNumber(data.matrix.total_rows)}{' '}
            {tableMatrix ? 'tables' : 'schemas'} shown.
            {data.matrix.rows.length < data.matrix.total_rows
              ? ' Signals to review determine the order; narrow the filters to see other tables.'
              : ''}{' '}
            Columns can overlap. Missing tags means owner, domain and cost_center are all absent.
          </>
        }
      >
        {data.matrix.rows.length ? (
          <div className="overflow-x-auto">
            <table
              className="w-full min-w-[340px] border-separate border-spacing-1 text-xs"
              aria-label="Governance signal matrix"
            >
              <thead>
                <tr>
                  <th className="w-1/3 text-left font-medium">
                    {tableMatrix ? 'Table' : 'Schema'}
                  </th>
                  {GOVERNANCE_SIGNALS.map((signal) => (
                    <th
                      key={signal.key}
                      className="max-w-20 px-1 pb-2 text-center text-[11px] font-medium text-muted-foreground"
                    >
                      {signal.key === 'orphan' ? 'Missing tags' : signal.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.matrix.rows.map((row) => {
                  const name = row.table_full_name ?? `${row.catalog ?? '—'}.${row.schema ?? '—'}`;
                  return (
                    <tr key={governanceIdentity(row.cloud_provider, name)}>
                      <th
                        scope="row"
                        className="max-w-44 break-words pr-2 text-left font-medium"
                        title={name}
                      >
                        {tableMatrix ? row.table_name || name : row.schema || 'Unknown schema'}
                        <span className="mt-0.5 block break-all text-[11px] font-normal text-muted-foreground">
                          {row.catalog}
                          {row.cloud_provider ? ` · ${row.cloud_provider}` : ''} ·{' '}
                          {formatNumber(row.table_count)} tables
                        </span>
                      </th>
                      {GOVERNANCE_SIGNALS.map((signal) => {
                        const count = row.signals[signal.key];
                        const ratio = row.table_count ? count / row.table_count : 0;
                        return (
                          <td key={signal.key} className="p-0">
                            <button
                              type="button"
                              className="min-h-11 w-full rounded-md p-1 text-center text-xs font-medium tabular-nums text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                              style={{ background: count ? sequentialFill(ratio) : 'var(--muted)' }}
                              title={`${formatNumber(count)} / ${formatNumber(row.table_count)} tables`}
                              aria-label={`${name} · ${signal.label} : ${count} of ${row.table_count}. Filter the registry.`}
                              onClick={() =>
                                onFocus({
                                  label: `${name} · ${signal.label}${tableMatrix ? ' · all clouds' : ''}`,
                                  scope:
                                    tableMatrix && row.table_full_name
                                      ? { tables: [row.table_full_name] }
                                      : {
                                          catalog: row.catalog ?? undefined,
                                          schema: row.schema ?? undefined,
                                        },
                                  signal: signal.key,
                                })
                              }
                            >
                              {tableMatrix ? (count ? 'Yes' : '—') : formatPct(ratio * 100, 0)}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-3 flex items-center justify-end gap-2 text-[11px] text-muted-foreground">
              <span>0 %</span>
              {[0, 0.5, 1].map((ratio) => (
                <span
                  key={ratio}
                  aria-hidden
                  className="h-3 w-6 rounded-sm"
                  style={{ background: ratio ? sequentialFill(ratio) : 'var(--muted)' }}
                />
              ))}
              <span>100 %</span>
            </div>
          </div>
        ) : (
          <GovernanceEmpty>No tables in this scope.</GovernanceEmpty>
        )}
      </GovernanceChartCard>

      <GovernanceChartCard
        title="How long since tables were last read?"
        subtitle="Distribution of last observed reads across the applied scope."
        note="Table count per interval. Click to find the corresponding tables in the registry."
      >
        {total ? (
          <GovernanceInteractiveBars
            ariaLabel="Inactivity distribution"
            rows={data.inactivity.map((row) => ({
              key: row.bucket,
              label: INACTIVITY_LABELS[row.bucket],
              total: row.count,
              description: `${INACTIVITY_LABELS[row.bucket]} : ${row.count} tables. Filter the registry.`,
              segments: [
                {
                  value: row.count,
                  color: sequentialFill(
                    row.count / Math.max(1, ...data.inactivity.map((item) => item.count)),
                    100
                  ),
                },
              ],
            }))}
            onSelect={(key) => {
              const row = data.inactivity.find((item) => item.bucket === key);
              if (row) onFocus({ label: INACTIVITY_LABELS[row.bucket], inactivity: row.bucket });
            }}
          />
        ) : (
          <GovernanceEmpty>No tables in this scope.</GovernanceEmpty>
        )}
      </GovernanceChartCard>

      <GovernanceChartCard
        title="Are tables documented?"
        subtitle="Presence of Unity Catalog tags; this does not assess their quality."
        note="Percentages cover all tables in scope. Click to filter missing tags; unavailable metadata remains distinct from an absent tag."
      >
        {total ? (
          <GovernanceInteractiveBars
            ariaLabel="Unity Catalog tag coverage"
            max={100}
            rows={data.tag_coverage.map((row) => ({
              key: row.tag,
              label: TAG_LABELS[row.tag],
              total: row.coverage_pct ?? 0,
              valueLabel: formatPct(row.coverage_pct, 0),
              sublabel: `${formatNumber(row.present_count)} / ${formatNumber(row.total_count)} present · ${formatNumber(row.missing_count)} missing${row.unknown_count ? ` · ${formatNumber(row.unknown_count)} unknown` : ''}`,
              description: `Tag ${TAG_LABELS[row.tag]} present on ${row.present_count} tables out of ${row.total_count}. View the ${row.missing_count} tables missing this tag.`,
              segments: [{ value: row.coverage_pct ?? 0, color: 'var(--tdf-teal)' }],
            }))}
            onSelect={(key) => {
              const row = data.tag_coverage.find((item) => item.tag === key);
              if (row) onFocus({ label: `Tag ${TAG_LABELS[row.tag]} absent`, missingTag: row.tag });
            }}
          />
        ) : (
          <GovernanceEmpty>No tables in this scope.</GovernanceEmpty>
        )}
      </GovernanceChartCard>
    </div>
  );
}
