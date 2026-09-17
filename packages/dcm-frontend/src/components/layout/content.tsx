import * as React from 'react';
import { cn } from '../../lib/utils';

export function Content({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="content" className={cn('flex min-h-full flex-col gap-6 p-6 pb-28 lg:pb-32', className)} {...props} />;
}

export function ContentHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="content-header"
      className={cn('grid auto-rows-min grid-rows-[auto_auto] items-start gap-3 md:grid-cols-[1fr_auto]', className)}
      {...props}
    />
  );
}

export function ContentTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 data-slot="content-title" className={cn('sr-only', className)} {...props} />;
}

export function ContentDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p data-slot="content-description" className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

export function ContentActions({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="content-actions" className={cn('self-center justify-self-end gap-3', className)} {...props} />;
}

export function ContentMain({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="content-main" className={cn('flex flex-1 flex-col gap-6', className)} {...props} />;
}
