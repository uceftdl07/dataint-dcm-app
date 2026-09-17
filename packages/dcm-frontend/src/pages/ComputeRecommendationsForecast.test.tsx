import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  computeForecastFixture,
  computeRecommendationsFixture,
  computeRecommendationsSummaryFixture,
} from '../test/fixtures/compute-recommendations';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import ComputeRecommendationsForecast from './ComputeRecommendationsForecast';

vi.mock('../api/dcmApiClient', () => ({
  getComputeRecommendations: vi.fn(),
  getComputeRecommendationsSummary: vi.fn(),
  getComputeForecast: vi.fn(),
  listDatabricksWorkspaces: vi.fn(),
}));

import {
  getComputeForecast,
  getComputeRecommendations,
  getComputeRecommendationsSummary,
  listDatabricksWorkspaces,
} from '../api/dcmApiClient';

const apiMocks = {
  getComputeRecommendations: vi.mocked(getComputeRecommendations),
  getComputeRecommendationsSummary: vi.mocked(getComputeRecommendationsSummary),
  getComputeForecast: vi.mocked(getComputeForecast),
  listDatabricksWorkspaces: vi.mocked(listDatabricksWorkspaces),
};

describe('ComputeRecommendationsForecast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.getComputeRecommendationsSummary.mockResolvedValue(
      computeRecommendationsSummaryFixture
    );
    apiMocks.getComputeRecommendations.mockResolvedValue(computeRecommendationsFixture);
    apiMocks.getComputeForecast.mockResolvedValue(computeForecastFixture);
    apiMocks.listDatabricksWorkspaces.mockResolvedValue({ items: [] });
  });

  it('renders KPI cards and recommendations table', async () => {
    renderWithProviders(<ComputeRecommendationsForecast />, {
      route: '/databricks/compute/recommendations',
    });

    expect(
      await screen.findByRole('heading', { name: /Recommendations & Forecast/i })
    ).toBeInTheDocument();
    expect(await screen.findByText('Open recommendations')).toBeInTheDocument();
    expect(await screen.findByText('Potential savings')).toBeInTheDocument();
    expect(await screen.findByText('Actual cost (period)')).toBeInTheDocument();
    expect(await screen.findByText('sap_datasphere_run')).toBeInTheDocument();
    expect(await screen.findByText('wh_datascience_adhoc')).toBeInTheDocument();
    expect(screen.getByText('Forecast')).toBeInTheDocument();
  });

  it('defaults status filter to OPEN', async () => {
    renderWithProviders(<ComputeRecommendationsForecast />, {
      route: '/databricks/compute/recommendations',
    });

    await screen.findByText('sap_datasphere_run');

    await waitFor(() => {
      expect(apiMocks.getComputeRecommendations).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'OPEN' })
      );
    });
    expect(screen.getByRole('button', { name: 'Open' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows empty state when filters match no rows', async () => {
    renderWithProviders(<ComputeRecommendationsForecast />, {
      route: '/databricks/compute/recommendations',
    });

    await screen.findByText('sap_datasphere_run');

    apiMocks.getComputeRecommendations.mockResolvedValue({
      ...computeRecommendationsFixture,
      items: [],
      total: 0,
    });

    await userEvent.click(screen.getByRole('button', { name: 'Warehouses' }));
    await userEvent.selectOptions(screen.getByLabelText('Filter by category'), 'GOVERNANCE');

    await waitFor(() => {
      expect(apiMocks.getComputeRecommendations).toHaveBeenCalledWith(
        expect.objectContaining({ object_type: 'WAREHOUSE', category: 'GOVERNANCE' })
      );
    });

    expect(await screen.findByText('No recommendations match this filter')).toBeInTheDocument();
  });

  it('opens mini-drawer with cross-nav CTA on row click', async () => {
    renderWithProviders(<ComputeRecommendationsForecast />, {
      route: '/databricks/compute/recommendations',
    });

    await userEvent.click(await screen.findByText('sap_datasphere_run'));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent('Upgrade to DBR 14.3 LTS');
    expect(screen.getByRole('link', { name: /Open full cluster record/i })).toHaveAttribute(
      'href',
      '/databricks/cluster'
    );
  });

  it('loads forecast with selected metric', async () => {
    renderWithProviders(<ComputeRecommendationsForecast />, {
      route: '/databricks/compute/recommendations',
    });

    await screen.findByText('Forecast');

    await userEvent.selectOptions(screen.getByLabelText('Forecast metric'), 'dbu_quantity');

    await waitFor(() => {
      expect(apiMocks.getComputeForecast).toHaveBeenCalledWith(
        expect.objectContaining({ metric_name: 'dbu_quantity' })
      );
    });
  });
});
