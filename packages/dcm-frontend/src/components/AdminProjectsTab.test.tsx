import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import type { ProjectJoinRequest, ProjectScopeRequest, ProjectSummary } from '../types/api';
import { AdminProjectsTab } from './AdminProjectsTab';

vi.mock('../api/dcmApiClient', async () => {
  const actual = await vi.importActual<typeof import('../api/dcmApiClient')>('../api/dcmApiClient');
  return {
    ...actual,
    listProjects: vi.fn(),
    listScopeRequests: vi.fn(),
    listAllJoinRequests: vi.fn(),
    validateProject: vi.fn(),
    rejectProject: vi.fn(),
    decideScopeRequest: vi.fn(),
    decideProjectJoinRequest: vi.fn(),
    deleteProject: vi.fn(),
  };
});

import {
  decideProjectJoinRequest,
  decideScopeRequest,
  deleteProject,
  listAllJoinRequests,
  listProjects,
  listScopeRequests,
  rejectProject,
  validateProject,
} from '../api/dcmApiClient';

const mockListProjects = vi.mocked(listProjects);
const mockListScopeRequests = vi.mocked(listScopeRequests);
const mockListAllJoinRequests = vi.mocked(listAllJoinRequests);
const mockValidateProject = vi.mocked(validateProject);
const mockRejectProject = vi.mocked(rejectProject);
const mockDecideScopeRequest = vi.mocked(decideScopeRequest);
const mockDecideJoinRequest = vi.mocked(decideProjectJoinRequest);
const mockDeleteProject = vi.mocked(deleteProject);

const pendingProject: ProjectSummary = {
  id: 'Payments',
  name: 'Payments monitoring',
  businessAppId: 'Payments',
  status: 'pending_validation',
  role: null,
  lzScope: ['lz-001', 'lz-002', 'lz-003'],
  effectiveLzScope: ['lz-001', 'lz-002', 'lz-003'],
  dbxScope: ['ws-1'],
  memberCount: 4,
};

const scopeRequest: ProjectScopeRequest = {
  id: 'req-1',
  projectId: 'Payments',
  scopeType: 'lz',
  scopeRef: 'lz-001',
  status: 'pending',
  justification: null,
  requestedBy: 'user-1',
  requestedAt: '2026-01-01T00:00:00Z',
};

const joinRequest: ProjectJoinRequest = {
  id: 'jr-1',
  projectId: 'Payments',
  userId: 'user-9',
  displayName: 'New Joiner',
  requestedRole: 'viewer',
  status: 'pending',
  justification: 'Need the Payments scope',
  requestedAt: '2026-01-01T00:00:00Z',
};

const projectDetail = {
  ...pendingProject,
  status: 'active' as const,
  createdBy: 'user-1',
  createdAt: '2026-01-01T00:00:00Z',
  validatedBy: 'admin-1',
  validatedAt: '2026-01-02T00:00:00Z',
  decisionReason: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockListProjects.mockResolvedValue([pendingProject]);
  mockListScopeRequests.mockResolvedValue([scopeRequest]);
  mockListAllJoinRequests.mockResolvedValue([joinRequest]);
});

describe('AdminProjectsTab', () => {
  it('lists projects and validates a pending one', async () => {
    mockValidateProject.mockResolvedValue(projectDetail);

    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });
    const user = userEvent.setup();

    expect(await screen.findByText('Payments monitoring')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^validate$/i }));

    await waitFor(() => expect(mockValidateProject).toHaveBeenCalledWith('Payments'));
  });

  it('shows what a project grants: both scope dimensions and the member count', async () => {
    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });

    expect(await screen.findByText('lz-001')).toBeInTheDocument();
    expect(screen.getByText('ws-1')).toBeInTheDocument();
    // Third LZ collapses into a "+1" badge listing the full scope on hover.
    expect(screen.getByTitle('lz-001, lz-002, lz-003')).toHaveTextContent('+1');
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('rejects a project only once a reason is given', async () => {
    mockRejectProject.mockResolvedValue({ ...projectDetail, status: 'rejected' });

    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Reject Payments monitoring' }));

    // The backend 422s on a blank reason — the confirm button stays disabled.
    const confirm = screen.getByRole('button', { name: /confirm rejection/i });
    expect(confirm).toBeDisabled();

    await user.type(
      screen.getByLabelText('Rejection reason for Payments monitoring'),
      'Duplicate initiative'
    );
    await user.click(confirm);

    await waitFor(() =>
      expect(mockRejectProject).toHaveBeenCalledWith('Payments', { reason: 'Duplicate initiative' })
    );
  });

  it('deletes a project only after the confirmation, whatever its status', async () => {
    mockListProjects.mockResolvedValue([{ ...pendingProject, status: 'active' }]);
    mockDeleteProject.mockResolvedValue(undefined);

    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });
    const user = userEvent.setup();

    // An active project has no Validate/Reject pair, but it can still be deleted.
    await user.click(await screen.findByRole('button', { name: 'Delete project Payments monitoring' }));
    expect(mockDeleteProject).not.toHaveBeenCalled();
    // The confirmation states what goes with the project.
    expect(
      screen.getByText(/4 memberships, 3 landing zones, 1 workspace and any open request/)
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Confirm deletion of Payments monitoring' }));

    await waitFor(() => expect(mockDeleteProject).toHaveBeenCalledWith('Payments'));
  });

  it('approves a pending scope extension request', async () => {
    mockDecideScopeRequest.mockResolvedValue({ ...scopeRequest, status: 'approved' });

    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole('button', { name: 'Approve Landing Zone lz-001 for Payments' })
    );

    await waitFor(() =>
      expect(mockDecideScopeRequest).toHaveBeenCalledWith('req-1', {
        decision: 'approved',
        reason: undefined,
      })
    );
  });

  it('groups a multi-item scope request into one decision', async () => {
    // Same project, requester and requestedAt: one submission, two rows.
    const second: ProjectScopeRequest = {
      ...scopeRequest,
      id: 'req-2',
      scopeType: 'dbx_workspace',
      scopeRef: 'ws-9',
    };
    mockListScopeRequests.mockResolvedValue([scopeRequest, second]);
    mockDecideScopeRequest.mockResolvedValue({ ...scopeRequest, status: 'approved' });

    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });
    const user = userEvent.setup();

    const approveAll = await screen.findByRole('button', {
      name: 'Approve 2 scope items for Payments',
    });
    expect(screen.getByText('Landing Zone: lz-001')).toBeInTheDocument();
    expect(screen.getByText('Databricks workspace: ws-9')).toBeInTheDocument();

    await user.click(approveAll);

    // One click, one decision per underlying row.
    await waitFor(() => expect(mockDecideScopeRequest).toHaveBeenCalledTimes(2));
    expect(mockDecideScopeRequest).toHaveBeenCalledWith('req-1', {
      decision: 'approved',
      reason: undefined,
    });
    expect(mockDecideScopeRequest).toHaveBeenCalledWith('req-2', {
      decision: 'approved',
      reason: undefined,
    });
  });

  it('drains the platform-wide join request queue', async () => {
    mockDecideJoinRequest.mockResolvedValue({ ...joinRequest, status: 'approved' });

    renderWithProviders(<AdminProjectsTab />, { route: '/admin' });
    const user = userEvent.setup();

    expect(await screen.findByText('New Joiner')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Approve New Joiner on Payments' }));

    await waitFor(() =>
      expect(mockDecideJoinRequest).toHaveBeenCalledWith('jr-1', {
        decision: 'approved',
        reason: undefined,
      })
    );
  });
});
