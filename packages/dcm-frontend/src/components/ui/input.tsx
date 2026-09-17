import * as React from 'react';
import { cn } from '../../lib/utils';

const controlBaseClass =
  'w-full rounded-2xl border border-border/70 bg-card px-3 text-sm font-medium text-foreground shadow-sm shadow-slate-950/5 transition-colors placeholder:text-muted-foreground hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      data-slot="input"
      className={cn(
        'flex h-10 py-1',
        controlBaseClass,
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = 'Input';

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      data-slot="select"
      className={cn(
        'flex h-10 py-1',
        controlBaseClass,
        className,
      )}
      {...props}
    />
  );
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      data-slot="textarea"
      className={cn(
        'min-h-24 resize-y py-2 leading-6',
        controlBaseClass,
        className,
      )}
      {...props}
    />
  ),
);

Textarea.displayName = 'Textarea';

export function FieldLabel({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      data-slot="field-label"
      className={cn('text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground', className)}
      {...props}
    />
  );
}
