import { Database } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '../../test/render';
import { EmptyState, PageError, TableSkeleton } from './states';

describe('PageError', () => {
  it('renders an accessible error alert', () => {
    render(<PageError message="API indisponible" />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Loading error')).toBeInTheDocument();
    expect(screen.getByText('API indisponible')).toBeInTheDocument();
  });
});

describe('TableSkeleton', () => {
  it('renders the requested number of skeleton rows', () => {
    const { container } = render(<TableSkeleton rows={4} />);

    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(4);
  });
});

describe('EmptyState', () => {
  it('renders title and description', () => {
    render(
      <EmptyState
        icon={<Database />}
        title="No database found"
        description="Adjust your filters to broaden the search."
      />,
    );

    expect(screen.getByText('No database found')).toBeInTheDocument();
    expect(screen.getByText('Adjust your filters to broaden the search.')).toBeInTheDocument();
  });
});

