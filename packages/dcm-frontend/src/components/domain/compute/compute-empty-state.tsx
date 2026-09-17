import { cn } from '../../../lib/utils';

export function ComputeEmptyState({
  title = 'No results',
  description,
  className,
}: {
  title?: string;
  description?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] px-5 py-14 text-center shadow-[var(--card-shadow)]',
        className
      )}
    >
      <div className="text-sm font-semibold text-foreground">{title}</div>
      {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
    </div>
  );
}
