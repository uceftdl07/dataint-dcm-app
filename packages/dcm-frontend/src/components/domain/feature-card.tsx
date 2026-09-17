import * as React from 'react';
import { Badge } from '../ui/badge';
import { Card, CardContent } from '../ui/card';

export type FeatureCardTone = 'blue' | 'red' | 'green' | 'purple' | 'slate' | 'orange';

const featureToneClass: Record<FeatureCardTone, { surface: string; icon: string; badge: 'default' | 'secondary' | 'outline' | 'success' | 'warning' | 'destructive' | 'info' }> = {
  blue: {
    surface: 'bg-info-subtle',
    icon: 'bg-card text-info shadow-sm ring-1 ring-info-border',
    badge: 'info',
  },
  red: {
    surface: 'bg-danger-subtle',
    icon: 'bg-card text-danger shadow-sm ring-1 ring-danger-border',
    badge: 'destructive',
  },
  green: {
    surface: 'bg-success-subtle',
    icon: 'bg-card text-success shadow-sm ring-1 ring-success-border',
    badge: 'success',
  },
  purple: {
    surface: 'bg-purple-subtle',
    icon: 'bg-card text-purple shadow-sm ring-1 ring-purple-border',
    badge: 'secondary',
  },
  slate: {
    surface: 'bg-muted',
    icon: 'bg-card text-foreground shadow-sm ring-1 ring-border',
    badge: 'outline',
  },
  orange: {
    surface: 'bg-warning-subtle',
    icon: 'bg-card text-warning shadow-sm ring-1 ring-warning-border',
    badge: 'warning',
  },
};

export interface FeatureCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  tone?: FeatureCardTone;
  badge?: string;
  meta?: string;
  actionLabel?: string;
  className?: string;
  children?: React.ReactNode;
}

export function FeatureCard({
  title,
  description,
  icon,
  tone = 'blue',
  badge,
  meta,
  actionLabel = 'Open',
  className = '',
  children,
}: FeatureCardProps) {
  const styles = featureToneClass[tone];

  return (
    <Card interactive className={`group h-full text-left ${className}`}>
      <div className={`border-b border-border/60 px-[var(--card-padding-x)] py-4 ${styles.surface}`}>
        <div className="flex items-center gap-3">
          <div className={`flex size-12 shrink-0 items-center justify-center rounded-2xl transition-transform duration-200 group-hover:scale-105 ${styles.icon}`}>
            {icon}
          </div>
          <div className="min-w-0">
            <h3 className="text-[length:var(--card-title-size)] font-semibold leading-5 tracking-[-0.01em] text-foreground">{title}</h3>
            {meta && <p className="mt-1 text-[11px] font-medium uppercase tracking-[0.18em] text-foreground">{meta}</p>}
          </div>
        </div>
      </div>
      <CardContent className="flex flex-1 flex-col justify-between gap-5">
        <div className="space-y-4">
          <p className="text-sm leading-6 text-muted-foreground">{description}</p>
          {children}
        </div>
        <div className="flex items-center justify-between gap-3">
          {badge ? <Badge variant={styles.badge}>{badge}</Badge> : <span />}
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-primary transition-transform duration-200 group-hover:translate-x-1">
            {actionLabel}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
