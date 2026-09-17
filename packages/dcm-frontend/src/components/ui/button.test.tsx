import { describe, expect, it, vi } from 'vitest';
import { render, screen, userEvent } from '../../test/render';
import { Button } from './button';

describe('Button', () => {
  it('defaults to type button to avoid accidental form submits', () => {
    render(<Button>Refresh</Button>);

    expect(screen.getByRole('button', { name: 'Refresh' })).toHaveAttribute('type', 'button');
  });

  it('forwards click handlers and variant metadata', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();

    render(
      <Button variant="secondary" size="sm" onClick={onClick}>
        Filter
      </Button>,
    );

    const button = screen.getByRole('button', { name: 'Filter' });
    await user.click(button);

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(button).toHaveAttribute('data-variant', 'secondary');
    expect(button).toHaveAttribute('data-size', 'sm');
  });
});

