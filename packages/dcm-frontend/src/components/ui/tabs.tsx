import * as React from 'react';
import { cn } from '../../lib/utils';

export function Tabs({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="tabs" className={cn('flex flex-col gap-2', className)} {...props} />;
}

export function TabsList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="tabs-list"
      role="tablist"
      className={cn('inline-flex w-fit items-center justify-start gap-1 border-b text-muted-foreground', className)}
      {...props}
    />
  );
}

export interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  active?: boolean;
}

export function TabsTrigger({ className, active = false, type = 'button', ...props }: TabsTriggerProps) {
  return (
    <button
      data-slot="tabs-trigger"
      data-state={active ? 'active' : 'inactive'}
      role="tab"
      aria-selected={active}
      type={type}
      className={cn(
        'relative inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-transparent px-3 py-1 text-sm font-medium transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
        active
          ? 'text-primary after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-primary'
          : 'text-muted-foreground hover:text-primary',
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="tabs-content" className={cn('flex-1 outline-none', className)} {...props} />;
}
