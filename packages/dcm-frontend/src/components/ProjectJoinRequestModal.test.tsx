import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import type { ReferenceBusinessApplication, ReferenceProject } from '../types/api';
import { ProjectJoinRequestModal } from './ProjectJoinRequestModal';

vi.mock('../api/dcmApiClient', async () => {
  const actual = await vi.importActual<typeof import('../api/dcmApiClient')>('../api/dcmApiClient');
  return {
    ...actual,
    listReferenceProjects: vi.fn(),
    listReferenceBusinessApplications: vi.fn(),
    requestJoinProjectPublic: vi.fn(),
  };
});

import {
  listReferenceBusinessApplications,
  listReferenceProjects,
  requestJoinProjectPublic,
} from '../api/dcmApiClient';

const mockListReference = vi.mocked(listReferenceProjects);
const mockListBusinessApps = vi.mocked(listReferenceBusinessApplications);
const mockJoin = vi.mocked(requestJoinProjectPublic);

const projects: ReferenceProject[] = [
  {
    id: 'proj-payments',
    name: 'Payments',
    businessAppId: 'ba-payments',
    status: 'active',
  },
];

const businessApplications: ReferenceBusinessApplication[] = [
  {
    businessApplicationId: 'ba-payments',
    businessApplicationName: 'Payments Platform',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockListReference.mockResolvedValue({
    items: projects,
    total: projects.length,
  });
  mockListBusinessApps.mockResolvedValue({
    items: businessApplications,
    total: businessApplications.length,
  });
});

describe('ProjectJoinRequestModal', () => {
  it('submits a join request for the selected project', async () => {
    mockJoin.mockResolvedValue({
      requestId: 'req-1',
      projectId: 'proj-payments',
      status: 'pending',
      routedTo: 'admins',
      recipientIds: ['admin-1'],
    });
    const user = userEvent.setup();
    renderWithProviders(<ProjectJoinRequestModal onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/your email/i), 'Jane.Doe@totalenergies.com');
    await user.click(screen.getByRole('combobox', { name: /^project/i }));
    await user.click(await screen.findByRole('option', { name: 'Payments' }));

    await user.click(screen.getByRole('button', { name: /request to join/i }));

    await waitFor(() => {
      expect(mockJoin).toHaveBeenCalledWith({
        projectId: 'proj-payments',
        justification: undefined,
      });
    });
  });

  it('resolves the project id from the Business Application lookup', async () => {
    mockJoin.mockResolvedValue({
      requestId: 'req-2',
      projectId: 'proj-payments',
      status: 'pending',
      routedTo: 'admins',
      recipientIds: ['admin-1'],
    });
    const user = userEvent.setup();
    renderWithProviders(<ProjectJoinRequestModal onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/your email/i), 'jane.doe@totalenergies.com');
    await user.click(screen.getByRole('button', { name: /by business application/i }));
    await user.click(screen.getByRole('combobox', { name: /business application/i }));
    await user.click(await screen.findByRole('option', { name: 'Payments Platform' }));

    await user.click(screen.getByRole('button', { name: /request to join/i }));

    await waitFor(() => {
      expect(mockJoin).toHaveBeenCalledWith({
        projectId: 'proj-payments',
        justification: undefined,
      });
    });
  });
});
