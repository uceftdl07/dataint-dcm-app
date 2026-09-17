import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../test/render';
import { LandingRequestChooserModal } from './LandingRequestChooserModal';

describe('LandingRequestChooserModal', () => {
  it('offers register and join, and no landing-zone registration', () => {
    renderWithProviders(
      <LandingRequestChooserModal onClose={vi.fn()} onChoose={vi.fn()} />,
    );

    expect(screen.getByRole('heading', { name: /join or register a project/i })).toBeInTheDocument();
    expect(screen.getByText(/^Register a project$/)).toBeInTheDocument();
    expect(screen.getByText(/^Join a project$/)).toBeInTheDocument();
    expect(screen.queryByText(/register a landing zone/i)).not.toBeInTheDocument();
  });

  it('emits the chosen kind', async () => {
    const onChoose = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(<LandingRequestChooserModal onClose={vi.fn()} onChoose={onChoose} />);

    await user.click(screen.getByText(/^Register a project$/));
    expect(onChoose).toHaveBeenCalledWith('project_register');

    await user.click(screen.getByText(/^Join a project$/));
    expect(onChoose).toHaveBeenCalledWith('project_join');
  });
});
