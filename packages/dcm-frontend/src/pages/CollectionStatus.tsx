/**
 * CollectionStatus — operational view of the DCM collection chain.
 *
 * Shows the health endpoint and explains the collection pipeline.
 * Calls GET /api/v1/health to verify connectivity to dcm-backend and Unity Catalog.
 */

import {
  Activity,
  AlertCircle,
  CheckCircle,
  Clock,
  Database,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { type ReactNode, useMemo } from 'react';
import { HEALTH_POLL_MS, useHealthQuery } from '../hooks/useHealthQuery';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';

interface StatusRowProps {
  label: string;
  status: 'ok' | 'degraded' | 'unknown';
  detail?: string;
  icon: ReactNode;
}

const pipelineSteps = [
  { label: 'Agents cloud', sub: 'Azure WebJob + AWS ECS Fargate', tone: 'info' },
  { label: 'Ingestion API', sub: 'API Gateway / Lambda', tone: 'warning' },
  { label: 'File tampon', sub: 'SQS Queue', tone: 'default' },
  { label: 'Databricks Jobs', sub: 'Ingestion + transformations', tone: 'purple' },
  { label: 'Unity Catalog', sub: 'Tables curated / gold', tone: 'success' },
  { label: 'Backend & Frontend', sub: 'SQL Warehouse + dcm-backend', tone: 'info' },
] as const;

const schedules = [
  ['Azure WebJob', 'Boucle asyncio 5 min', 'Metric collection for ADF, Databricks, DB Azure'],
  [
    'AWS ECS Fargate (one-shot)',
    'EventBridge */5 * * * *',
    'Metric collection for Glue, EMR, RDS, Redshift, Cost Explore',
  ],
  ['Lambda Ingestion', 'POST /ingest (push)', 'Validation + publication SQS'],
  ['Databricks Ingestion Job', '*/5 * * * *', 'SQS → tables Unity Catalog'],
  ['Databricks Transform Job', '2-57/5 * * * *', 'Transformations in Unity Catalog'],
  ['Databricks Gold Job', '4-59/5 * * * *', 'Gold aggregations consumed by SQL Warehouse'],
];

const statusLabels = {
  ok: 'Connected',
  degraded: 'Indisponible',
  unknown: 'En attente',
} as const;

function getStepToneClass(tone: (typeof pipelineSteps)[number]['tone']) {
  const tones = {
    default: 'bg-muted text-muted-foreground ring-border/70',
    info: 'bg-info-subtle text-info ring-info-border',
    warning: 'bg-warning-subtle text-warning ring-warning-border',
    purple: 'bg-purple-subtle text-purple ring-purple-border',
    success: 'bg-success-subtle text-success ring-success-border',
  };

  return tones[tone];
}

function formatDateTime(value: Date | string | null): string {
  if (!value) {
    return 'Not verified';
  }

  const date = typeof value === 'string' ? new Date(value) : value;

  if (Number.isNaN(date.getTime())) {
    return 'Date unknown';
  }

  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function StatusRow({ label, status, detail, icon }: StatusRowProps) {
  const statusIcon = {
    ok: <CheckCircle size={18} className="text-success" />,
    degraded: <AlertCircle size={18} className="text-danger" />,
    unknown: <Clock size={18} className="text-muted-foreground" />,
  }[status];

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card/70 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{label}</p>
          {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
        </div>
      </div>
      <div className="flex items-center gap-2 self-start sm:self-center">
        {statusIcon}
        <span className="text-sm font-medium">{statusLabels[status]}</span>
      </div>
    </div>
  );
}

const CollectionStatus: React.FC = () => {
  const { health, loading, error, lastChecked, refetch, isFetching } = useHealthQuery({
    pollIntervalMs: HEALTH_POLL_MS,
    fallbackOnError: true,
  });

  const isOperational = health?.status === 'ok' && health.database === 'ok';
  const isPending = loading && !health;
  const overallStatus = isPending ? 'pending' : isOperational ? 'ok' : 'degraded';
  const serviceChecks = useMemo(
    () =>
      [
        {
          label: 'API Backend (ECS Fargate)',
          status: health?.status ?? 'unknown',
          detail: health?.service ?? 'dcm-backend',
          icon: <Server size={18} />,
        },
        {
          label: 'Databricks SQL Warehouse',
          status: health?.database === 'ok' ? 'ok' : health ? 'degraded' : 'unknown',
          detail:
            health?.database === 'ok'
              ? 'Unity Catalog accessible (SPN/TLS)'
              : 'Unity Catalog not confirmed',
          icon: <Database size={18} />,
        },
      ] satisfies StatusRowProps[],
    [health]
  );

  return (
    <Content className="mx-auto w-full max-w-[1600px]">
      <ContentHeader>
        <div>
          <div className="sr-only">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
              <Activity size={24} />
            </div>
            <ContentTitle>Status de collecte</ContentTitle>
          </div>
          <ContentDescription className="mt-0">
            Nexti de bout en bout : agents cloud, ingestion, Databricks, Unity Catalog and backend.
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Badge
            variant={
              overallStatus === 'ok'
                ? 'success'
                : overallStatus === 'pending'
                  ? 'secondary'
                  : 'destructive'
            }
            className="h-8 px-3"
          >
            {overallStatus === 'ok'
              ? 'Operational'
              : overallStatus === 'pending'
                ? 'Checking...'
                : 'Degraded'}
          </Badge>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      <ContentMain>
        <section className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <Card>
            <CardHeader className="border-b border-border/60 bg-muted/40">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>dcm-backend</CardTitle>
                  <CardDescription>Real healthcheck via GET /api/v1/health</CardDescription>
                </div>
                <span className="rounded-full bg-background px-3 py-1 text-xs text-muted-foreground ring-1 ring-border/70">
                  Checked : {formatDateTime(lastChecked)}
                </span>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {isPending ? (
                <div className="space-y-3">
                  <Skeleton className="h-20 rounded-2xl" />
                  <Skeleton className="h-20 rounded-2xl" />
                </div>
              ) : (
                <>
                  {error && (
                    <div className="rounded-2xl border border-danger-border bg-danger-subtle p-4 text-sm text-danger">
                      Unable to confirm the collection chain : {error}
                    </div>
                  )}
                  <div className="grid gap-3">
                    {serviceChecks.map((check) => (
                      <StatusRow key={check.label} {...check} />
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b border-border/60 bg-muted/40">
              <CardTitle>Operational summary</CardTitle>
              <CardDescription>Quick view of collection state</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
              <div className="rounded-2xl border border-border/70 p-4">
                <div className="mb-3 flex size-9 items-center justify-center rounded-xl bg-success-subtle text-success">
                  <ShieldCheck size={18} />
                </div>
                <p className="text-xs text-muted-foreground">Global status</p>
                <p className="mt-1 text-lg font-semibold">
                  {isOperational ? 'Operational' : isPending ? 'Checking' : 'Degraded'}
                </p>
              </div>
              <div className="rounded-2xl border border-border/70 p-4">
                <div className="mb-3 flex size-9 items-center justify-center rounded-xl bg-info-subtle text-info">
                  <Zap size={18} />
                </div>
                <p className="text-xs text-muted-foreground">UI frequency</p>
                <p className="mt-1 text-lg font-semibold">60 s</p>
              </div>
              <div className="rounded-2xl border border-border/70 p-4">
                <div className="mb-3 flex size-9 items-center justify-center rounded-xl bg-purple-subtle text-purple">
                  <Clock size={18} />
                </div>
                <p className="text-xs text-muted-foreground">Timestamp API</p>
                <p className="mt-1 text-sm font-semibold">
                  {formatDateTime(health?.timestamp ?? null)}
                </p>
              </div>
            </CardContent>
          </Card>
        </section>

        <Card>
          <CardHeader className="border-b border-border/60 bg-muted/40">
            <CardTitle>Collection architecture</CardTitle>
            <CardDescription>
              The flow is grouped into blocks to remain readable on every screen size.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {pipelineSteps.map((step, index) => (
                <li
                  key={step.label}
                  className={`rounded-2xl p-4 ring-1 ${getStepToneClass(step.tone)}`}
                >
                  <div className="flex items-start gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-background text-xs font-semibold ring-1 ring-current/10">
                      {index + 1}
                    </span>
                    <div>
                      <p className="font-medium">{step.label}</p>
                      <p className="mt-1 text-xs">{step.sub}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border/60 bg-muted/40">
            <CardTitle>Job scheduling</CardTitle>
            <CardDescription>
              Expected cadence for collectors, ingestion, and transformations.
            </CardDescription>
          </CardHeader>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Component</TableHead>
                  <TableHead>Trigger</TableHead>
                  <TableHead>Role</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {schedules.map(([component, trigger, role]) => (
                  <TableRow key={component}>
                    <TableCell className="min-w-56 font-medium text-foreground">
                      {component}
                    </TableCell>
                    <TableCell className="min-w-48 font-mono text-xs text-muted-foreground">
                      {trigger}
                    </TableCell>
                    <TableCell className="min-w-72 text-xs text-muted-foreground">{role}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>
      </ContentMain>
    </Content>
  );
};

export default CollectionStatus;
