import { CheckCircle2 } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '../../test/render';
import { MetricCard, MetricGrid } from './metric-card';

describe('MetricCard', () => {
  it('renders label, value and description', () => {
    render(
      <MetricCard
        label="Pipelines"
        value={42}
        description="Runs over the period"
        icon={<CheckCircle2 />}
      />,
    );

    expect(screen.getByText('Pipelines')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Runs over the period')).toBeInTheDocument();
  });

  it('acts as a keyboard-accessible button when clickable', () => {
    const onClick = vi.fn();

    render(
      <MetricCard
        label="Alerts"
        value={3}
        icon={<CheckCircle2 />}
        active
        onClick={onClick}
      />,
    );

    const card = screen.getByRole('button', { pressed: true });
    fireEvent.keyDown(card, { key: 'Enter' });
    fireEvent.keyDown(card, { key: ' ' });

    expect(onClick).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Active filter')).toBeInTheDocument();
  });
});

describe('MetricGrid', () => {
  it('renders skeletons while loading', () => {
    const { container } = render(
      <MetricGrid loading skeletonCount={3}>
        <MetricCard label="Loaded" value="1" icon={<CheckCircle2 />} />
      </MetricGrid>,
    );

    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(3);
    expect(screen.queryByText('Loaded')).not.toBeInTheDocument();
  });
});

