import * as React from 'react';
import { cn } from '../../lib/utils';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
}

export function Card({ className, interactive = false, ...props }: CardProps) {
  return (
    <div
      data-slot="card"
      className={cn(
        'flex flex-col overflow-hidden rounded-[var(--card-radius)] border border-border/70 bg-[var(--card-background)] text-card-foreground shadow-[var(--card-shadow)]',
        'transition-[border-color,box-shadow,transform,background-color] duration-200 ease-out',
        interactive && 'hover:-translate-y-1 hover:border-primary/30 hover:shadow-[var(--card-hover-shadow)] active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-header" className={cn('grid gap-1 px-[var(--card-padding-x)] py-[var(--card-padding-y)]', className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 data-slot="card-title" className={cn('text-[length:var(--card-title-size)] font-medium leading-5 tracking-[-0.01em]', className)} {...props} />;
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p data-slot="card-description" className={cn('text-[length:var(--card-subtitle-size)] leading-5 text-muted-foreground', className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-content" className={cn('flex-1 px-[var(--card-padding-x)] py-[var(--card-padding-y)]', className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="card-footer" className={cn('flex items-center px-[var(--card-padding-x)] pb-[var(--card-padding-y)]', className)} {...props} />;
}
