import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent, waitFor } from '../test/render';
import type { ReferenceBusinessApplication } from '../types/api';
import { ProjectRegisterRequestModal } from './ProjectRegisterRequestModal';

vi.mock('../api/dcmApiClient', async () => {
  const actual = await vi.importActual<typeof import('../api/dcmApiClient')>('../api/dcmApiClient');
  return {
    ...actual,
    listReferenceBusinessApplications: vi.fn(),
    registerProjectPublic: vi.fn(),
  };
});

import {
  DcmApiError,
  listReferenceBusinessApplications,
  registerProjectPublic,
} from '../api/dcmApiClient';

const mockListReference = vi.mocked(listReferenceBusinessApplications);
const mockRegister = vi.mocked(registerProjectPublic);

const businessApplications: ReferenceBusinessApplication[] = [
  {
    businessApplicationId: 'ba-payments',
    businessApplicationName: 'Payments',
  },
  {
    businessApplicationId: 'ba-risk',
    businessApplicationName: 'Risk',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockListReference.mockResolvedValue({
    items: businessApplications,
    total: businessApplications.length,
  });
});

describe('ProjectRegisterRequestModal', () => {
  it('submits the register payload without client-side scope lists', async () => {
    mockRegister.mockResolvedValue({
      id: 'ba-payments',
      name: 'My project',
      businessAppId: 'ba-payments',
      status: 'pending_validation',
      requesterEmail: 'jane.doe@totalenergies.com',
      memberCount: 1,
    });
    const user = userEvent.setup();
    renderWithProviders(<ProjectRegisterRequestModal onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/your email/i), 'Jane.Doe@totalenergies.com');
    await user.type(screen.getByLabelText(/project name/i), 'My project');

    await user.click(screen.getByRole('combobox', { name: /business application/i }));
    await user.click(await screen.findByRole('option', { name: 'Payments' }));

    await user.click(screen.getByRole('button', { name: /add member/i }));
    await user.type(screen.getByLabelText(/member 1 email/i), 'teammate@totalenergies.com');
    await user.selectOptions(screen.getByLabelText(/member 1 role/i), 'admin');

    await user.click(screen.getByRole('button', { name: /register project/i }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        businessAppId: 'ba-payments',
        name: 'My project',
        members: [{ email: 'teammate@totalenergies.com', role: 'admin' }],
        lzScope: [],
        dbxScope: [],
      });
    });
  });

  it('surfaces the conflict message and offers to join on 409', async () => {
    mockRegister.mockRejectedValue(new DcmApiError(409, 'conflict', null));
    const onSwitchToJoin = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <ProjectRegisterRequestModal onClose={vi.fn()} onSwitchToJoin={onSwitchToJoin} />
    );

    await user.type(screen.getByLabelText(/your email/i), 'jane.doe@totalenergies.com');
    await user.type(screen.getByLabelText(/project name/i), 'My project');
    await user.click(screen.getByRole('combobox', { name: /business application/i }));
    await user.click(await screen.findByRole('option', { name: 'Payments' }));

    await user.click(screen.getByRole('button', { name: /register project/i }));

    const joinButton = await screen.findByRole('button', { name: /join the existing project/i });
    await user.click(joinButton);
    expect(onSwitchToJoin).toHaveBeenCalled();
  });

  it('filters the Business Application options with the search box', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ProjectRegisterRequestModal onClose={vi.fn()} />);

    await user.click(screen.getByRole('combobox', { name: /business application/i }));

    // Both BAs are listed initially.
    expect(await screen.findByRole('option', { name: 'Payments' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Risk' })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/type a business application name/i), 'risk');

    expect(screen.queryByRole('option', { name: 'Payments' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Risk' })).toBeInTheDocument();
  });
});
