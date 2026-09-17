import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../../test/render';
import {
  ucGovernanceChartsFixture,
  ucRecommendationChartsFixture,
} from '../../../test/fixtures/uc-governance-charts';
import { UcGovernanceChartsPanel } from './uc-governance-charts';
import { UcRecommendationChartsPanel } from './uc-recommendation-charts';
import { UcGovernanceScatter } from './uc-governance-scatter';

describe('Governance chart states', () => {
  it('filtre les tags absents en conservant le compte distinct des métadonnées inconnues', async () => {
    const focus = vi.fn();
    renderWithProviders(
      <UcGovernanceChartsPanel
        data={ucGovernanceChartsFixture}
        loading={false}
        error={null}
        onRetry={vi.fn()}
        onFocus={focus}
      />
    );
    expect(screen.getByText(/1 missing · 1 unknown/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Tag Classification present/ }));
    expect(focus).toHaveBeenCalledWith({
      label: 'Tag Classification absent',
      missingTag: 'classification',
    });
  });

  it('transforme la matrice en profils de tables lorsqu’un seul schéma est retenu', async () => {
    const focus = vi.fn();
    const point = ucGovernanceChartsFixture.scatter.points[0];
    renderWithProviders(
      <UcGovernanceChartsPanel
        data={{
          ...ucGovernanceChartsFixture,
          matrix: {
            mode: 'table',
            total_rows: 1,
            limit: 25,
            rows: [
              {
                ...ucGovernanceChartsFixture.matrix.rows[0],
                cloud_provider: point.cloud_provider,
                table_full_name: point.table_full_name,
                table_name: point.table_name,
              },
            ],
          },
        }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
        onFocus={focus}
      />
    );
    expect(screen.getByRole('region', { name: 'Signals by table' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /main.sales.orders · Critical/ }));
    expect(focus.mock.lastCall?.[0]).toMatchObject({
      scope: { tables: ['main.sales.orders'] },
      signal: 'critical',
    });
  });

  it('ne place jamais une lecture inconnue à zéro jour dans le nuage', () => {
    renderWithProviders(
      <UcGovernanceScatter
        points={[
          {
            ...ucGovernanceChartsFixture.scatter.points[0],
            days_since_last_read: null,
          },
        ]}
        onSelect={vi.fn()}
      />
    );
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText(/No tables with both an observed read/)).toBeInTheDocument();
  });

  it('affiche un état vide sans barres de couverture à zéro sur un périmètre vide', () => {
    renderWithProviders(
      <UcGovernanceChartsPanel
        data={{
          ...ucGovernanceChartsFixture,
          summary: {
            tracked_tables: 0,
            unused_tables: 0,
            critical_tables: 0,
            stale_but_consumed_tables: 0,
            orphan_tables: 0,
            unused_critical_tables: 0,
          },
          matrix: { mode: 'schema', total_rows: 0, limit: 25, rows: [] },
          scatter: { total: 0, limit: 300, unobserved_reads: 0, points: [] },
          tag_coverage: [],
          inactivity: [],
        }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
        onFocus={vi.fn()}
      />
    );
    expect(screen.getAllByText('No tables in this scope.')).toHaveLength(3);
    expect(
      screen.queryByRole('list', { name: 'Unity Catalog tag coverage' })
    ).not.toBeInTheDocument();
  });

  it('garde les dates non exploitables sélectionnables sans leur inventer un âge', async () => {
    const focus = vi.fn();
    renderWithProviders(
      <UcRecommendationChartsPanel
        data={{
          ...ucRecommendationChartsFixture,
          ages: [{ bucket: 'unknown', HIGH: 0, MEDIUM: 0, LOW: 0, UNKNOWN: 1, total: 1 }],
          priorities: [],
        }}
        loading={false}
        error={null}
        onRetry={vi.fn()}
        onFocus={focus}
      />
    );
    await userEvent.click(
      screen.getByRole('button', { name: /Date unavailable.*Filter recommendations/ })
    );
    expect(focus).toHaveBeenCalledWith({
      label: 'Age: Date unavailable',
      ageBucket: 'unknown',
    });
    expect(screen.getByText('No High recommendations for these tables.')).toBeInTheDocument();
  });
});
