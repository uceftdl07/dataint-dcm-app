import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import type {
  CurrentDcmUser,
  ProjectDetail as ProjectDetailType,
  ProjectMember,
} from '../types/api';
import ProjectDetail from './ProjectDetail';

vi.mock('../api/dcmApiClient', async () => {
  const actual = await vi.importActual<typeof import('../api/dcmApiClient')>('../api/dcmApiClient');
  return {
    ...actual,
    getCurrentDcmUser: vi.fn(),
    getProject: vi.fn(),
    listProjectMembers: vi.fn(),
    listProjectJoinRequests: vi.fn(),
    addProjectMember: vi.fn(),
    listDatabricksWorkspaces: vi.fn(),
    listAccessRequestLandingZones: vi.fn(),
    createProjectScopeRequest: vi.fn(),
  };
});

import {
  addProjectMember,
  createProjectScopeRequest,
  getCurrentDcmUser,
  getProject,
  listAccessRequestLandingZones,
  listDatabricksWorkspaces,
  listProjectJoinRequests,
  listProjectMembers,
} from '../api/dcmApiClient';

const mockGetCurrentDcmUser = vi.mocked(getCurrentDcmUser);
const mockGetProject = vi.mocked(getProject);
const mockListMembers = vi.mocked(listProjectMembers);
const mockListJoinRequests = vi.mocked(listProjectJoinRequests);
const mockAddMember = vi.mocked(addProjectMember);
const mockListWorkspaces = vi.mocked(listDatabricksWorkspaces);
const mockListLandingZones = vi.mocked(listAccessRequestLandingZones);
const mockCreateScopeRequest = vi.mocked(createProjectScopeRequest);

const PROJECT_ID = 'proj-1';

function adminUser(): CurrentDcmUser {
  return {
    id: 'user-1',
    entra_oid: 'oid-1',
    email: 'admin@example.com',
    display_name: 'Admin User',
    role: 'viewer',
    is_active: true,
    lz_ids: [],
    platform_role: 'user',
    projects: [{ project_id: PROJECT_ID, name: 'Payments', role: 'admin', status: 'active' }],
  };
}

const projectDetail: ProjectDetailType = {
  id: PROJECT_ID,
  name: 'Payments',
  businessAppId: 'ba-1',
  status: 'active',
  role: 'admin',
  lzScope: ['lz-001'],
  effectiveLzScope: ['lz-001'],
  dbxScope: [],
  memberCount: 1,
  createdBy: 'user-1',
  createdAt: '2026-05-27T10:00:00Z',
  validatedBy: 'admin-1',
  validatedAt: '2026-05-28T10:00:00Z',
  decisionReason: null,
};

const existingMember: ProjectMember = {
  userId: 'user-1',
  displayName: 'Admin User',
  role: 'admin',
  addedAt: '2026-05-27T10:00:00Z',
};

function renderProjectDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/projects/:projectId" element={<ProjectDetail />} />
    </Routes>,
    { route: `/projects/${PROJECT_ID}` }
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCurrentDcmUser.mockResolvedValue(adminUser());
  mockGetProject.mockResolvedValue(projectDetail);
  mockListMembers.mockResolvedValue([existingMember]);
  mockListJoinRequests.mockResolvedValue([]);
  mockListWorkspaces.mockResolvedValue({ items: [] });
  mockListLandingZones.mockResolvedValue({ items: [], total: 0 });
  mockAddMember.mockResolvedValue({
    userId: 'user-2',
    displayName: 'New Member',
    role: 'viewer',
    addedAt: '2026-05-29T10:00:00Z',
  });
});

describe('ProjectDetail members management', () => {
  it('lets a project admin add a member by email', async () => {
    const user = userEvent.setup();
    renderProjectDetail();

    await screen.findByText('Admin User');
    await user.type(screen.getByLabelText('New member email'), 'new.member@example.com');
    await user.click(screen.getByRole('button', { name: /add member/i }));

    await waitFor(() => {
      expect(mockAddMember).toHaveBeenCalledWith(PROJECT_ID, {
        email: 'new.member@example.com',
        role: 'viewer',
      });
    });
  });

  it('sends every picked landing zone and workspace as a single scope request', async () => {
    mockListLandingZones.mockResolvedValue({
      items: [
        {
          lz_id: 'lz-001',
          lz_name: 'Granted LZ',
          cloud_provider: 'azure',
          environment: 'prod',
          ba_name: 'Payments',
        },
        {
          lz_id: 'lz-002',
          lz_name: 'Wanted LZ',
          cloud_provider: 'azure',
          environment: 'prod',
          ba_name: 'Payments',
        },
      ],
      total: 2,
    });
    mockListWorkspaces.mockResolvedValue({
      items: [
        { workspace_id: 'ws-1', display_name: 'Prod workspace', source_lz_id: 'lz-002', cluster_count: 2 },
      ],
    });
    mockCreateScopeRequest.mockResolvedValue([]);

    const user = userEvent.setup();
    renderProjectDetail();

    // Wait for the reference data to land before reading the pickers.
    await screen.findByRole('option', { name: 'Wanted LZ' });
    // lz-001 is already granted, so it is not offered again.
    expect(screen.queryByRole('option', { name: 'Granted LZ' })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Add a Landing Zone'), 'lz-002');
    await user.selectOptions(screen.getByLabelText('Add a Databricks workspace'), 'ws-1');
    await user.type(screen.getByLabelText('Scope justification'), 'New data domain');
    await user.click(screen.getByRole('button', { name: /send request/i }));

    await waitFor(() =>
      expect(mockCreateScopeRequest).toHaveBeenCalledWith(PROJECT_ID, {
        items: [
          { scopeType: 'lz', scopeRef: 'lz-002' },
          { scopeType: 'dbx_workspace', scopeRef: 'ws-1' },
        ],
        justification: 'New data domain',
      })
    );
  });

  it('hides the add-member form from non-admin members', async () => {
    mockGetCurrentDcmUser.mockResolvedValue({
      ...adminUser(),
      projects: [{ project_id: PROJECT_ID, name: 'Payments', role: 'viewer', status: 'active' }],
    });
    renderProjectDetail();

    await screen.findByText('Admin User');
    expect(screen.queryByLabelText('New member email')).not.toBeInTheDocument();
  });
});
