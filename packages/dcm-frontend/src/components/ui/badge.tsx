import * as React from 'react';
import { cn } from '../../lib/utils';

type BadgeVariant =
  | 'default'
  | 'secondary'
  | 'destructive'
  | 'outline'
  | 'success'
  | 'warning'
  | 'info';

const variants: Record<BadgeVariant, string> = {
  default: 'border-transparent bg-primary text-primary-foreground',
  secondary: 'border-transparent bg-secondary text-secondary-foreground',
  destructive: 'border-transparent bg-danger text-danger-foreground',
  outline: 'border-border text-foreground',
  success: 'border-transparent bg-success text-success-foreground',
  warning: 'border-transparent bg-warning text-warning-foreground',
  info: 'border-transparent bg-info text-info-foreground',
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      data-slot="badge"
      data-variant={variant}
      className={cn(
        'inline-flex w-fit shrink-0 items-center justify-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
        '[&_svg]:size-3',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
