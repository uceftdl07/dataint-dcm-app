import { Shield } from 'lucide-react';
import type { SecurityAlert } from '../../types/api';
import { getAlertSeverityBarClass } from '../../lib/domain/alerts';
import { formatDateTime } from '../../lib/domain/formatters';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { AlertSeverityBadge, AlertStatusBadge } from './badges';
import { EmptyState, TableSkeleton } from './states';

export function SecurityAlertsTable({
  alerts,
  allAlertsCount,
  loading,
  title = 'Security alerts',
  description = 'Azure security alerts for the selected scope.',
  emptyTitle,
  emptyDescription,
  resourceFallback,
  rows = 6,
}: {
  alerts: SecurityAlert[];
  allAlertsCount: number;
  loading: boolean;
  title?: string;
  description?: string;
  emptyTitle: string;
  emptyDescription: string;
  resourceFallback: string;
  rows?: number;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
          <Badge variant={alerts.length === 0 ? 'success' : 'secondary'}>
            {alerts.length === 0 ? 'No alerts' : `${alerts.length} alerts`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {loading ? (
          <TableSkeleton rows={rows} />
        ) : alerts.length === 0 ? (
          <EmptyState
            icon={<Shield size={32} />}
            title={emptyTitle}
            description={allAlertsCount === 0 ? 'No alerts detected for this period. If collection is active, the selected scope is clear.' : emptyDescription}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Alert</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Resource</TableHead>
                <TableHead>Detection</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {alerts.map((alert) => (
                <TableRow key={alert.alert_id} className="hover:bg-red-50/50">
                  <TableCell className="max-w-[420px] whitespace-normal">
                    <div className="flex gap-3">
                      <span className={`mt-1 h-10 w-1.5 shrink-0 rounded-full shadow-lg ${getAlertSeverityBarClass(alert.severity)}`} />
                      <div>
                        <p className="font-medium text-foreground">{alert.title}</p>
                        {alert.description && (
                          <p className="mt-1 text-xs text-muted-foreground">{alert.description}</p>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <AlertSeverityBadge severity={alert.severity} />
                  </TableCell>
                  <TableCell>
                    <AlertStatusBadge status={alert.status} />
                  </TableCell>
                  <TableCell className="max-w-[260px] whitespace-normal">
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-medium text-foreground">{alert.resource_id ?? resourceFallback}</span>
                      {alert.resource_type && <span className="text-xs text-muted-foreground">{alert.resource_type}</span>}
                    </div>
                  </TableCell>
                  <TableCell>{formatDateTime(alert.detected_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
