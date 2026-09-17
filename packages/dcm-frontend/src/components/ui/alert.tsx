import * as React from 'react';
import { cn } from '../../lib/utils';

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'destructive';
}

export function Alert({ className, variant = 'default', ...props }: AlertProps) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(
        'grid w-full grid-cols-[0_1fr] items-start gap-x-3 gap-y-0.5 rounded-lg border px-4 py-3 text-sm has-[>svg]:grid-cols-[1rem_1fr]',
        '[&>svg]:mt-0.5 [&>svg]:size-4',
        variant === 'destructive'
          ? 'border-danger-border bg-danger-subtle text-danger'
          : 'bg-card text-card-foreground',
        className,
      )}
      {...props}
    />
  );
}

export function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="alert-title" className={cn('col-start-2 font-medium', className)} {...props} />;
}

export function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="alert-description"
      className={cn('col-start-2 text-sm text-muted-foreground', className)}
      {...props}
    />
  );
}
