import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Card, CardContent } from '../../ui/card';
import { ComputeInfoTip } from './compute-info-tip';
import { cn } from '../../../lib/utils';

type KpiTone = 'info' | 'success' | 'warning' | 'purple' | 'danger';

const toneStyles: Record<
  KpiTone,
  { header: string; value: string; iconWrap: string; icon: string }
> = {
  info: {
    header: 'bg-info-subtle',
    value: 'text-info',
    iconWrap: 'bg-card text-info ring-info-border',
    icon: 'text-info',
  },
  success: {
    header: 'bg-success-subtle',
    value: 'text-success',
    iconWrap: 'bg-card text-success ring-success-border',
    icon: 'text-success',
  },
  warning: {
    header: 'bg-warning-subtle',
    value: 'text-warning',
    iconWrap: 'bg-card text-warning ring-warning-border',
    icon: 'text-warning',
  },
  purple: {
    header: 'bg-purple-subtle',
    value: 'text-purple',
    iconWrap: 'bg-card text-purple ring-purple-border',
    icon: 'text-purple',
  },
  danger: {
    header: 'bg-danger-subtle',
    value: 'text-danger',
    iconWrap: 'bg-card text-danger ring-danger-border',
    icon: 'text-danger',
  },
};

export function ComputeKpiCard({
  title,
  description,
  value,
  subtitle,
  tone = 'info',
  icon: Icon,
}: {
  title: string;
  description: string;
  value: ReactNode;
  subtitle?: ReactNode;
  tone?: KpiTone;
  icon: LucideIcon;
}) {
  const styles = toneStyles[tone];

  return (
    <Card className="h-full">
      <div
        className={cn(
          'flex items-center justify-between gap-3 border-b border-border/60 px-[var(--card-padding-x)] py-3',
          styles.header
        )}
      >
        <p className="inline-flex min-w-0 items-center gap-1.5 text-[10px] font-black uppercase tracking-[1.2px] text-foreground">
          {title}
          <ComputeInfoTip description={description} label={`${title} KPI description`} />
        </p>
        <div
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-xl shadow-sm ring-1',
            styles.iconWrap
          )}
        >
          <Icon className={cn('size-4', styles.icon)} aria-hidden />
        </div>
      </div>

      <CardContent className="space-y-1 py-4">
        <p
          className={cn(
            'text-[length:var(--card-value-size)] font-semibold leading-7 tracking-[-0.02em]',
            styles.value
          )}
        >
          {value}
        </p>
        {subtitle ? <p className="text-xs leading-5 text-muted-foreground">{subtitle}</p> : null}
      </CardContent>
    </Card>
  );
}
