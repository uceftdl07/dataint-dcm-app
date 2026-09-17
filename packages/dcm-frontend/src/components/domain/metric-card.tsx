import * as React from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Skeleton } from '../ui/skeleton';

export type MetricTone = 'default' | 'cost' | 'danger' | 'success' | 'warning' | 'purple';

const metricToneClass: Record<MetricTone, { surface: string; icon: string; value: string }> = {
  default: {
    surface: 'bg-info-subtle',
    icon: 'bg-card text-info shadow-sm ring-1 ring-info-border',
    value: 'text-info',
  },
  cost: {
    surface: 'bg-info-subtle',
    icon: 'bg-card text-info shadow-sm ring-1 ring-info-border',
    value: 'text-info',
  },
  danger: {
    surface: 'bg-danger-subtle',
    icon: 'bg-card text-danger shadow-sm ring-1 ring-danger-border',
    value: 'text-danger',
  },
  success: {
    surface: 'bg-success-subtle',
    icon: 'bg-card text-success shadow-sm ring-1 ring-success-border',
    value: 'text-success',
  },
  warning: {
    surface: 'bg-warning-subtle',
    icon: 'bg-card text-warning shadow-sm ring-1 ring-warning-border',
    value: 'text-warning',
  },
  purple: {
    surface: 'bg-purple-subtle',
    icon: 'bg-card text-purple shadow-sm ring-1 ring-purple-border',
    value: 'text-purple',
  },
};

export interface MetricCardProps {
  label: string;
  value: string | number;
  description?: string;
  icon: React.ReactNode;
  tone?: MetricTone;
  active?: boolean;
  badge?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

export function MetricCard({
  label,
  value,
  description,
  icon,
  tone = 'default',
  active = false,
  badge,
  footer,
  className = '',
  onClick,
}: MetricCardProps) {
  const styles = metricToneClass[tone];

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!onClick || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    onClick();
  };

  return (
    <Card
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      interactive={Boolean(onClick)}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      aria-pressed={onClick ? active : undefined}
      className={`group h-full ${onClick ? 'cursor-pointer' : ''} ${active ? 'border-primary/60 bg-primary/5 ring-2 ring-primary/35' : ''} ${className}`}
    >
      <div
        className={`border-b border-border/60 px-[var(--card-padding-x)] py-3.5 ${styles.surface}`}
      >
        <div className="grid grid-cols-[minmax(0,1fr)_2.25rem] items-center gap-3">
          <div className="min-w-0 space-y-1">
            <p className="max-w-full break-words text-xs font-semibold uppercase leading-5 tracking-[0.14em] text-foreground sm:tracking-[0.18em]">
              {label}
            </p>
            {(badge || active) && (
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                {badge}
                {active && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 font-medium text-primary-foreground">
                    <CheckCircle2 size={12} />
                    Active filter
                  </span>
                )}
              </div>
            )}
          </div>
          <div
            className={`flex size-9 shrink-0 items-center justify-center justify-self-end rounded-xl transition-transform duration-200 group-hover:scale-105 ${styles.icon}`}
          >
            {icon}
          </div>
        </div>
      </div>
      <CardContent className="space-y-2">
        <p
          className={`text-[length:var(--card-value-size)] font-semibold leading-7 tracking-[-0.02em] ${styles.value}`}
        >
          {value}
        </p>
        {description && <p className="text-xs leading-5 text-muted-foreground">{description}</p>}
        {footer && <div className="pt-2 text-xs text-muted-foreground">{footer}</div>}
      </CardContent>
    </Card>
  );
}

export function MetricGrid({
  loading,
  skeletonCount = 4,
  children,
  className = 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4',
}: {
  loading: boolean;
  skeletonCount?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      {loading
        ? Array.from({ length: skeletonCount }).map((_, index) => (
            <Skeleton key={index} className="h-32" />
          ))
        : children}
    </div>
  );
}
