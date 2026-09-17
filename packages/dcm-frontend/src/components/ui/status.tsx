import { CheckCircle, Clock, XCircle, AlertTriangle } from 'lucide-react';
import type { ReactNode } from 'react';
import { Badge } from './badge';

type StatusTone = 'success' | 'warning' | 'destructive' | 'info' | 'secondary';

const statusMap: Record<string, { label: string; tone: StatusTone; icon: ReactNode }> = {
  succeeded: { label: 'Success', tone: 'success', icon: <CheckCircle /> },
  compliant: { label: 'Compliant', tone: 'success', icon: <CheckCircle /> },
  running: { label: 'Running', tone: 'info', icon: <Clock /> },
  active: { label: 'Active', tone: 'destructive', icon: <AlertTriangle /> },
  failed: { label: 'Failed', tone: 'destructive', icon: <XCircle /> },
  no_compliant: { label: 'Non-compliant', tone: 'destructive', icon: <XCircle /> },
  non_compliant: { label: 'Non-compliant', tone: 'destructive', icon: <XCircle /> },
  critical: { label: 'Critical', tone: 'destructive', icon: <AlertTriangle /> },
  high: { label: 'High', tone: 'warning', icon: <AlertTriangle /> },
  medium: { label: 'Medium', tone: 'warning', icon: <AlertTriangle /> },
  low: { label: 'Low', tone: 'info', icon: <AlertTriangle /> },
  resolved: { label: 'Resolved', tone: 'success', icon: <CheckCircle /> },
  cancelled: { label: 'Cancelled', tone: 'secondary', icon: <XCircle /> },
  terminated: { label: 'Stopped', tone: 'secondary', icon: <XCircle /> },
  unknown: { label: 'Unknown', tone: 'secondary', icon: <Clock /> },
};

export function StatusBadge({ value }: { value: string | null | undefined }) {
  const key = (value ?? 'unknown').toLowerCase();
  const status = statusMap[key] ?? { label: value ?? 'Unknown', tone: 'secondary' as const, icon: <Clock /> };

  return (
    <Badge variant={status.tone === 'destructive' ? 'destructive' : status.tone} className="capitalize">
      {status.icon}
      {status.label}
    </Badge>
  );
}
