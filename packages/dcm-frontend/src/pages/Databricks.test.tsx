import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLocation } from 'react-router-dom';
import { DATABRICKS_WIDGET_TARGETS } from '../lib/databricks/focus-routes';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import Databricks from './Databricks';

vi.mock('../hooks/useDatabricksPageData', () => ({
  useDatabricksPageData: vi.fn(),
}));

import { useDatabricksPageData } from '../hooks/useDatabricksPageData';

const mockUseDatabricksPageData = vi.mocked(useDatabricksPageData);

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
}

const baseMockData = {
  clusters: [],
  databricksAlerts: [],
  databricksCostUsd: 1200,
  error: null,
  errorClusters: [],
  estimatedHourlyCostUsd: 42,
  failedJobs: [{ id: 'job-1' }],
  filteredClusters: [{ compute_resource_id: 'c-1' }],
  filteredWorkloadRows: [],
  governanceScore: { global_score_pct: 88 },
  landingZones: new Set(['lz-1']),
  load: vi.fn(),
  loading: false,
  loadingDetails: false,
  nonCompliantChecks: [],
  notice: null,
  runningClusters: [{ compute_resource_id: 'c-1' }],
  runningJobs: [],
  scope: { label: 'All landing zones' },
  workloadRows: [{ id: 'w-1' }],
  workspaces: new Set(['ws-1']),
  avgCpu: 55,
  avgMem: 60,
};

describe('Databricks widget navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDatabricksPageData.mockReturnValue(baseMockData as ReturnType<typeof useDatabricksPageData>);
  });

  it('redirects every metric card click to /databricks/**', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <>
        <Databricks />
        <LocationProbe />
      </>,
      { route: '/databricks' },
    );

    const metricCards = await screen.findAllByRole('button');
    const widgetTargets: Record<string, string> = {
      'Workspaces': DATABRICKS_WIDGET_TARGETS.workspaces,
      'Landing zones': DATABRICKS_WIDGET_TARGETS.landingZones,
      'Clusters': DATABRICKS_WIDGET_TARGETS.clusters,
      'Running': DATABRICKS_WIDGET_TARGETS.running,
      'Errors': DATABRICKS_WIDGET_TARGETS.errors,
      'Job runs': DATABRICKS_WIDGET_TARGETS.jobs,
      'Security alerts': DATABRICKS_WIDGET_TARGETS.securityAlerts,
      'Governance score': DATABRICKS_WIDGET_TARGETS.governance,
      'Average CPU': DATABRICKS_WIDGET_TARGETS.averageCpu,
      'Average memory': DATABRICKS_WIDGET_TARGETS.averageMemory,
      'Databricks cost': DATABRICKS_WIDGET_TARGETS.databricksCost,
      'Cluster hourly': DATABRICKS_WIDGET_TARGETS.clusterHourly,
    };

    for (const [label, expectedPath] of Object.entries(widgetTargets)) {
      const card = metricCards.find((button) => button.textContent?.includes(label));
      expect(card, `metric card ${label}`).toBeDefined();
      await user.click(card!);
      await waitFor(() => {
        const location = screen.getByTestId('location').textContent ?? '';
        expect(location.startsWith(expectedPath.split('?')[0]!)).toBe(true);
      });
    }
  });
});
