import type { ReactNode } from 'react';
import { cn } from '../../../lib/utils';

/**
 * The figures of the hovered point, floated above an inline-SVG chart.
 *
 * Purely visual — `aria-hidden`: the charts expose their series as text next to the
 * picture, and a live region firing on every point the cursor crosses would announce
 * a stream of noise. The parent must be positioned (`relative`).
 */
export function ChartHoverTooltip({
  index,
  count,
  children,
  className,
}: {
  /** Index of the hovered point, used to sit the readout above it. */
  index: number;
  count: number;
  children: ReactNode;
  className?: string;
}) {
  // A point near an edge cannot be centred on its band without overflowing the
  // card, so it anchors to that edge instead.
  const center = count > 0 ? (index + 0.5) / count : 0.5;
  const edge = center < 0.2 ? 'start' : center > 0.8 ? 'end' : 'center';
  const style =
    edge === 'start' ? { left: 0 } : edge === 'end' ? { right: 0 } : { left: `${center * 100}%` };

  return (
    <div
      aria-hidden
      data-testid="chart-hover-tooltip"
      style={style}
      className={cn(
        'pointer-events-none absolute bottom-full z-20 mb-1 whitespace-nowrap rounded-[var(--radius)] border border-border bg-[var(--card-background)] px-2 py-1 text-[11px] font-semibold text-foreground shadow-[var(--card-shadow)]',
        edge === 'center' ? '-translate-x-1/2' : '',
        className
      )}
    >
      {children}
    </div>
  );
}
