import * as React from 'react';
import { AlertTriangle, Info } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '../ui/alert';
import { Badge } from '../ui/badge';
import { Skeleton } from '../ui/skeleton';

export function PageError({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <AlertTriangle />
      <AlertTitle>Loading error</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

export function PageNotice({ title, message }: { title: string; message: string }) {
  return (
    <Alert>
      <Info />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, index) => <Skeleton key={index} className="h-14" />)}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl bg-muted/60 px-6 py-12 text-center">
      <div className="mb-3 text-tdf-green">{icon}</div>
      <p className="font-semibold text-foreground">{title}</p>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

type PageVerdictTone = 'success' | 'warning' | 'danger' | 'info';

const pageVerdictToneClass: Record<PageVerdictTone, string> = {
  danger: 'border-danger-border bg-danger-subtle text-danger',
  info: 'border-info-border bg-info-subtle text-info',
  success: 'border-success-border bg-success-subtle text-success',
  warning: 'border-warning-border bg-warning-subtle text-warning',
};

export function PageVerdict({
  title,
  description,
  tone = 'info',
  icon,
  badge,
}: {
  title: string;
  description: string;
  tone?: PageVerdictTone;
  icon: React.ReactNode;
  badge?: string;
}) {
  return (
    <div className={`flex flex-col gap-3 rounded-2xl border px-4 py-3 sm:flex-row sm:items-start sm:justify-between ${pageVerdictToneClass[tone]}`}>
      <div className="flex min-w-0 gap-3">
        <div className="mt-0.5 shrink-0">{icon}</div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        </div>
      </div>
      {badge && <Badge variant={tone === 'danger' ? 'destructive' : tone}>{badge}</Badge>}
    </div>
  );
}
