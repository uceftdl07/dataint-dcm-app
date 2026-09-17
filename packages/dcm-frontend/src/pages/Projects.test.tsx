import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import type { CurrentDcmUser, ReferenceBusinessApplication, ReferenceProject } from '../types/api';
import Projects from './Projects';

vi.mock('../api/dcmApiClient', async () => {
  const actual = await vi.importActual<typeof import('../api/dcmApiClient')>('../api/dcmApiClient');
  return {
    ...actual,
    getCurrentDcmUser: vi.fn(),
    listProjects: vi.fn(),
    listScopeRequests: vi.fn(),
    listReferenceBusinessApplications: vi.fn(),
    listReferenceProjects: vi.fn(),
    registerProjectPublic: vi.fn(),
    requestJoinProjectPublic: vi.fn(),
  };
});

import {
  getCurrentDcmUser,
  listProjects,
  listReferenceBusinessApplications,
  listReferenceProjects,
  listScopeRequests,
  registerProjectPublic,
} from '../api/dcmApiClient';

const mockGetCurrentDcmUser = vi.mocked(getCurrentDcmUser);
const mockListProjects = vi.mocked(listProjects);
const mockListScopeRequests = vi.mocked(listScopeRequests);
const mockListReferenceBusinessApps = vi.mocked(listReferenceBusinessApplications);
const mockListReferenceProjects = vi.mocked(listReferenceProjects);
const mockRegisterProject = vi.mocked(registerProjectPublic);

function makeUser(overrides: Partial<CurrentDcmUser> = {}): CurrentDcmUser {
  return {
    id: 'user-1',
    entra_oid: 'oid-1',
    email: 'user@example.com',
    display_name: 'Test User',
    role: 'viewer',
    is_active: true,
    lz_ids: [],
    platform_role: 'user',
    projects: [],
    ...overrides,
  };
}

const businessApplication: ReferenceBusinessApplication = {
  businessApplicationId: 'Payments',
  businessApplicationName: 'Payments',
};

const referenceProject: ReferenceProject = {
  id: 'Payments',
  name: 'Payments monitoring',
  businessAppId: 'Payments',
  status: 'active',
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCurrentDcmUser.mockResolvedValue(makeUser());
  mockListProjects.mockResolvedValue([]);
  mockListScopeRequests.mockResolvedValue([]);
  mockListReferenceBusinessApps.mockResolvedValue({ items: [businessApplication], total: 1 });
  mockListReferenceProjects.mockResolvedValue({ items: [referenceProject], total: 1 });
});

describe('Projects page', () => {
  it('shows a navigable empty state when the user has no project', async () => {
    renderWithProviders(<Projects />, { route: '/projects' });

    expect(await screen.findByText('No project yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create a project/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /join a project/i })).toBeInTheDocument();
  });

  it('registers a project through the same modal as the login page', async () => {
    mockRegisterProject.mockResolvedValue({
      id: 'Payments',
      name: 'Payments monitoring',
      businessAppId: 'Payments',
      status: 'pending_validation',
      requesterEmail: 'user@example.com',
      memberCount: 1,
    });

    renderWithProviders(<Projects />, { route: '/projects' });
    const user = userEvent.setup();

    await user.click((await screen.findAllByRole('button', { name: /create project/i }))[0]);

    // Signed in: the requester email comes from /auth/me and cannot be edited.
    const email = await screen.findByLabelText(/your email/i);
    expect(email).toHaveValue('user@example.com');
    expect(email).toHaveAttribute('readonly');

    await user.type(screen.getByLabelText(/project name/i), 'Payments monitoring');
    await user.click(screen.getByRole('combobox', { name: /business application/i }));
    await user.click(await screen.findByRole('option', { name: 'Payments' }));
    await user.click(screen.getByRole('button', { name: /register project/i }));

    // Scopes are resolved server-side from the BA — not sent from the public catalog.
    await waitFor(() =>
      expect(mockRegisterProject).toHaveBeenCalledWith({
        businessAppId: 'Payments',
        name: 'Payments monitoring',
        members: [],
        lzScope: [],
        dbxScope: [],
      })
    );
  });

  it('opens the login-page join form, searchable by project or Business Application', async () => {
    renderWithProviders(<Projects />, { route: '/projects' });
    const user = userEvent.setup();

    await user.click((await screen.findAllByRole('button', { name: /join project/i }))[0]);

    expect(await screen.findByRole('heading', { name: 'Join a project' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /by business application/i })).toBeInTheDocument();
    await user.click(screen.getByRole('combobox', { name: /project/i }));
    expect(await screen.findByRole('option', { name: 'Payments monitoring' })).toBeInTheDocument();
  });

  it('no longer renders the platform administration queue (moved to Administration)', async () => {
    mockGetCurrentDcmUser.mockResolvedValue(makeUser({ platform_role: 'super_admin' }));
    mockListProjects.mockResolvedValue([
      {
        id: 'Payments',
        name: 'Payments monitoring',
        businessAppId: 'Payments',
        status: 'pending_validation',
        role: null,
        lzScope: [],
        effectiveLzScope: [],
        dbxScope: [],
        memberCount: 0,
      },
    ]);

    renderWithProviders(<Projects />, { route: '/projects' });

    // Pending projects are validated from the Administration page now, so the
    // queue must not appear here and the pending project is filtered out.
    expect(await screen.findByText('No project yet')).toBeInTheDocument();
    expect(screen.queryByText('Platform administration')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^validate$/i })).not.toBeInTheDocument();
  });
});
