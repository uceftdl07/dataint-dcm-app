import * as React from 'react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { filterToneClass, getFilterControlClass, type FilterTone } from '../../lib/domain/filter-styles';

export function FilterPanel({
  title,
  description,
  icon,
  resultCount,
  activeFilterCount,
  emptyLabel,
  activeLabel = 'filter',
  tone = 'blue',
  resetDisabled,
  onReset,
  children,
  className = 'grid grid-cols-1 items-end gap-5 md:grid-cols-4',
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  resultCount: number;
  activeFilterCount: number;
  emptyLabel: string;
  activeLabel?: string;
  tone?: FilterTone;
  resetDisabled?: boolean;
  onReset: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  const styles = filterToneClass[tone];

  return (
    <Card className="overflow-hidden rounded-[2rem] bg-card/95 shadow-[0_18px_45px_rgb(15_23_42_/_8%)]">
      <CardHeader className="px-6 pb-5 pt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className={`flex size-10 items-center justify-center rounded-full ${styles.icon}`}>{icon}</div>
              <CardTitle className="text-xl font-semibold tracking-[-0.03em]">{title}</CardTitle>
            </div>
            <CardDescription className="mt-2 text-base">{description}</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${styles.badge}`}>
              {resultCount} result{resultCount > 1 ? 's' : ''}
            </Badge>
            <Badge variant={activeFilterCount > 0 ? 'warning' : 'secondary'} className="rounded-full px-3.5 py-1.5 text-sm font-semibold">
              {activeFilterCount > 0
                ? `${activeFilterCount} ${activeLabel}${activeFilterCount > 1 ? 's' : ''} active${activeFilterCount > 1 ? 's' : ''}`
                : emptyLabel}
            </Badge>
            <Button variant="ghost" size="sm" onClick={onReset} disabled={resetDisabled ?? activeFilterCount === 0} className="h-9 rounded-full px-4 text-sm">
              Reset
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className={`px-6 pb-6 pt-0 ${className}`}>{children}</CardContent>
    </Card>
  );
}

export function FilterField({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid min-w-0 gap-1" htmlFor={htmlFor}>
      <span className="truncate whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

export function FilterSelect({
  tone = 'blue',
  className = '',
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { tone?: FilterTone }) {
  return <select className={`${getFilterControlClass(tone)} ${className}`} {...props} />;
}
