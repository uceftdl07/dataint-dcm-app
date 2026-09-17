import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  FileText,
  Gauge,
  Handshake,
  LineChart,
  RefreshCw,
  ShieldCheck,
  Target,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { DATABRICKS_MODULE_FOCUS_PATHS } from '../lib/databricks/focus-routes';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { queryUnityCatalogTableGeneric } from '../api/dcmApiClient';
import {
  EmptyState,
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
  PageError,
  PageNotice,
  TableSkeleton,
} from '../components/domain';
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
import { Input, Select } from '../components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { getApiLzParams } from '../lib/monitoring-scope-filter';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useMonitoringReportsQueries } from '../hooks/useMonitoringReportsQueries';
import { useRolePermissions } from '../hooks/useRolePermissions';
import { formatCurrency, formatPercentage } from '../lib/domain/formatters';
import {
  buildComplianceChartData,
  buildCostChartData,
  buildMonitoringReportCsv,
  buildMonitoringReportFileName,
  getDefaultMonitoringReportFilters,
  summarizeMonitoringReport,
  type DataProductScoreDatum,
  type HealthStatus,
  type MonitoringReportItem,
  type MonitoringReportFilters,
  type MonitoringSummary,
} from '../lib/domain/monitoring-report';
import type {
  ComputeMetric,
  PipelineRun,
  UnityCatalogCellValue,
  UnityCatalogQueryResult,
} from '../types/api';

const LEGACY_MONITORING_LIMIT = 50000;
// Catalog and schema are left to the server: the monitoring schema is
// environment-specific (`…__d` in dev, `…__p` in prod), so naming it here would
// make this panel read another environment's data. The resolved location comes
// back as `FullTableName`.
const LEGACY_MONITORING_TABLE = {
  tableName: 'curated_activity_runs',
} as const;
const LEGACY_MONITORING_ORDER_BY = 'collected_at DESC';

const healthBadgeVariant: Record<
  HealthStatus,
  'success' | 'warning' | 'destructive' | 'secondary'
> = {
  Healthy: 'success',
  Warning: 'warning',
  Critical: 'destructive',
  Unknown: 'secondary',
};

function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat('en-GB').format(value ?? 0);
}

function formatCompact(value: number | null | undefined) {
  return new Intl.NumberFormat('en-GB', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value ?? 0);
}

function formatNullablePercentage(value: number | null | undefined) {
  return value === null || value === undefined ? '-' : formatPercentage(value, 0);
}

function downloadTextFile(fileName: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

const ChartEmptyState: React.FC<{ title: string }> = ({ title }) => (
  <div className="flex h-full items-center justify-center rounded-xl border border-dashed text-sm text-muted-foreground">
    {title}
  </div>
);

const StatusBadge: React.FC<{ status: HealthStatus }> = ({ status }) => (
  <Badge variant={healthBadgeVariant[status]}>{status}</Badge>
);

const decisionCardTone: Record<
  HealthStatus,
  {
    border: string;
    icon: string;
    value: string;
    bar: string;
    header: string;
    arrow: string;
    score: number;
    scoreLabel: string;
  }
> = {
  Healthy: {
    border: 'hover:border-success-border',
    icon: 'bg-success text-success-foreground shadow-success/20',
    value: 'text-success',
    bar: 'bg-success',
    header: 'bg-success-subtle text-success',
    arrow: 'bg-success text-success-foreground',
    score: 100,
    scoreLabel: 'Maitrise',
  },
  Warning: {
    border: 'hover:border-warning/45',
    icon: 'bg-warning text-warning-foreground shadow-warning/20',
    value: 'text-warning',
    bar: 'bg-warning',
    header: 'bg-warning-subtle text-warning',
    arrow: 'bg-warning text-warning-foreground',
    score: 62,
    scoreLabel: 'Attention',
  },
  Critical: {
    border: 'hover:border-danger-border',
    icon: 'bg-danger text-danger-foreground shadow-danger/20',
    value: 'text-danger',
    bar: 'bg-danger',
    header: 'bg-danger-subtle text-danger',
    arrow: 'bg-danger text-danger-foreground',
    score: 28,
    scoreLabel: 'Prioritaire',
  },
  Unknown: {
    border: 'hover:border-tdf-grey/35',
    icon: 'bg-tdf-grey text-tdf-grey-foreground shadow-tdf-grey/20',
    value: 'text-tdf-grey',
    bar: 'bg-tdf-grey',
    header: 'bg-muted text-muted-foreground',
    arrow: 'bg-tdf-grey text-tdf-grey-foreground',
    score: 12,
    scoreLabel: 'A qualifier',
  },
};

const chartColor = {
  info: 'var(--info)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
} as const;

function getHealthDatumColor(name: string): string {
  if (name === 'Failed' || name === 'Error') return chartColor.danger;
  if (name === 'Success' || name === 'Active') return chartColor.success;
  return chartColor.warning;
}

interface ReportSection {
  title: string;
  route: string;
  status: HealthStatus;
  summary: string;
  evidence: string;
  cta: string;
}

interface PriorityAction {
  id: string;
  title: string;
  impact: string;
  route: string;
}

interface BusinessImpactCard {
  title: string;
  persona: string;
  route: string;
  status: HealthStatus;
  value: string;
  meaning: string;
  action: string;
  icon: React.ReactNode;
}

interface LegacyMonitoringRecord {
  nom_script: string;
  nom_table: string;
  date_maj: string;
  nombre_ligne: number;
  statut: string;
  statut_log: string;
  start_time: string;
  end_time: string;
  job_name: string;
  job_id: string;
  run_id: string;
}

interface OperationalMetrics {
  globalHealth: HealthStatus;
  totalCostUsd: number;
  failedChecks: number;
  warningChecks: number;
  activeAlerts: number;
  criticalAlerts: number;
  failedJobs: number;
  successfulJobs: number;
  runningJobs: number;
  cancelledJobs: number;
  slowJobs: number;
  runningClusters: number;
  idleClusters: number;
  activeClusters: number;
  errorClusters: number;
  highCpuClusters: number;
  staleSignals: number;
  missingUcSignals: number;
  piiNonCompliantTables: number;
  missingOwnerSignals: number;
  costDriftSignals: number;
  maxCostTrendPercent: number | null;
  averageCpu: number | null;
  lastCollectedAt: string | null;
  conclusionReasons: string[];
}

function getReportStatus(severity: number): HealthStatus {
  if (severity >= 3) return 'Critical';
  if (severity >= 1) return 'Warning';
  return 'Healthy';
}

function buildOperationalMetrics(
  items: MonitoringReportItem[],
  computes: ComputeMetric[],
  pipelines: PipelineRun[],
  apiCostTotalUsd: number | null
): OperationalMetrics {
  const failedChecks = items.reduce((sum, item) => sum + item.failedChecks, 0);
  const warningChecks = items.reduce((sum, item) => sum + item.warningChecks, 0);
  const activeAlerts = items.reduce((sum, item) => sum + item.incidents, 0);
  const criticalAlerts = items.reduce(
    (sum, item) =>
      sum +
      item.alertDetails.filter(
        (alert) => alert.severity === 'critical' || alert.severity === 'high'
      ).length,
    0
  );
  const failedJobs = pipelines.filter((pipeline) => pipeline.status === 'failed').length;
  const successfulJobs = pipelines.filter((pipeline) => pipeline.status === 'succeeded').length;
  const runningJobs = pipelines.filter((pipeline) => pipeline.status === 'running').length;
  const cancelledJobs = pipelines.filter((pipeline) => pipeline.status === 'cancelled').length;
  const slowJobs = pipelines.filter(
    (pipeline) => (pipeline.duration_seconds ?? 0) >= 60 * 60
  ).length;
  const runningClusters = computes.filter((compute) => compute.state === 'running').length;
  const idleClusters = computes.filter(
    (compute) => compute.state === 'running' && (compute.avg_cpu_utilization_pct ?? 100) < 10
  ).length;
  const errorClusters = computes.filter((compute) => compute.state === 'error').length;
  const highCpuClusters = computes.filter(
    (compute) => compute.state === 'running' && (compute.avg_cpu_utilization_pct ?? 0) > 85
  ).length;
  const staleSignals = items.filter((item) => item.freshnessStatus === 'Stale').length;
  const missingUcSignals = items.filter((item) => item.unityCatalogAssets.length === 0).length;
  const missingOwnerSignals = items.filter((item) => !item.owner).length;
  const costDriftItems = items.filter((item) => (item.costTrendPercent ?? 0) > 15);
  const piiNonCompliantTables = items.reduce(
    (sum, item) =>
      sum +
      item.failedCheckDetails.filter((check) =>
        isPiiCheck(check.check_name, check.resource_name, check.resource_type)
      ).length,
    0
  );
  const maxCostTrendPercent = costDriftItems.length
    ? Math.max(...costDriftItems.map((item) => item.costTrendPercent ?? 0))
    : null;
  const averageCpu = average(computes.map((compute) => compute.avg_cpu_utilization_pct));
  const lastCollectedAt = maxIsoDate([
    ...computes.map((compute) => compute.collected_at),
    ...pipelines.map((pipeline) => pipeline.end_time ?? pipeline.start_time),
    ...items.map((item) => item.lastUsedAt),
  ]);
  const hasAnySignal = items.length > 0 || computes.length > 0 || pipelines.length > 0;
  const globalHealth: HealthStatus = !hasAnySignal
    ? 'Unknown'
    : failedJobs > 0 || failedChecks > 0 || criticalAlerts > 0 || errorClusters > 0
      ? 'Critical'
      : activeAlerts > 0 ||
          warningChecks > 0 ||
          staleSignals > 0 ||
          costDriftItems.length > 0 ||
          idleClusters > 0 ||
          highCpuClusters > 0 ||
          missingUcSignals > 0 ||
          missingOwnerSignals > 0
        ? 'Warning'
        : 'Healthy';
  const conclusionReasons = [
    failedJobs > 0 ? `${failedJobs} job(s) ont failed` : null,
    maxCostTrendPercent !== null ? `cost +${maxCostTrendPercent}%` : null,
    piiNonCompliantTables > 0 ? `${piiNonCompliantTables} table(s) PII no conformes` : null,
    highCpuClusters > 0 ? `${highCpuClusters} cluster(s) surconsomment` : null,
    idleClusters > 0 ? `${idleClusters} cluster(s) idle` : null,
    failedChecks > 0 ? `${failedChecks} check(s) failed` : null,
    criticalAlerts > 0 ? `${criticalAlerts} alert(s) critical` : null,
    staleSignals > 0 ? `${staleSignals} late freshness` : null,
    missingUcSignals > 0 ? `${missingUcSignals} mapping(s) Unity Catalog manquants` : null,
  ]
    .filter((reason): reason is string => Boolean(reason))
    .slice(0, 5);

  return {
    globalHealth,
    totalCostUsd: apiCostTotalUsd ?? items.reduce((sum, item) => sum + item.costUsd, 0),
    failedChecks,
    warningChecks,
    activeAlerts,
    criticalAlerts,
    failedJobs,
    successfulJobs,
    runningJobs,
    cancelledJobs,
    slowJobs,
    runningClusters,
    idleClusters,
    activeClusters: Math.max(0, runningClusters - idleClusters),
    errorClusters,
    highCpuClusters,
    staleSignals,
    missingUcSignals,
    piiNonCompliantTables,
    missingOwnerSignals,
    costDriftSignals: costDriftItems.length,
    maxCostTrendPercent,
    averageCpu,
    lastCollectedAt,
    conclusionReasons,
  };
}

function buildReportSections(metrics: OperationalMetrics): ReportSection[] {
  const computeStatus = getReportStatus(
    metrics.errorClusters > 0 ? 3 : metrics.highCpuClusters + metrics.idleClusters > 0 ? 1 : 0
  );
  const jobsStatus = getReportStatus(
    metrics.failedJobs > 0 ? 3 : metrics.slowJobs > 0 || metrics.runningJobs > 0 ? 1 : 0
  );

  return [
    {
      title: 'Compute Databricks',
      route: '/databricks',
      status: computeStatus,
      summary: 'Idle clusters, errors, high/low CPU, and active resources.',
      evidence: `${metrics.activeClusters} active(s), ${metrics.idleClusters} idle, ${metrics.errorClusters} in error. Average CPU ${metrics.averageCpu === null ? 'n/a' : `${Math.round(metrics.averageCpu)}%`}.`,
      cta: 'View compute',
    },
    {
      title: 'Jobs and pipelines',
      route: '/pipelines',
      status: jobsStatus,
      summary: 'Failed runs, successes, slowdowns, and pipelines still running.',
      evidence: `${metrics.failedJobs} failed, ${metrics.successfulJobs} success, ${metrics.slowJobs} slow.`,
      cta: 'View pipelines',
    },
    {
      title: 'Governance Databricks',
      route: DATABRICKS_MODULE_FOCUS_PATHS.governance,
      status: getReportStatus(metrics.failedChecks > 0 ? 3 : metrics.warningChecks > 0 ? 1 : 0),
      summary: 'Standard checks, compliance, and remediation evidence.',
      evidence: `${metrics.failedChecks} check(s) failed, ${metrics.warningChecks} warning(s).`,
      cta: 'View checks',
    },
    {
      title: 'FinOps Databricks',
      route: DATABRICKS_MODULE_FOCUS_PATHS.costs,
      status: getReportStatus(metrics.costDriftSignals > 0 ? 1 : 0),
      summary: 'Global cost, trend and main drifts.',
      evidence: `${formatCurrency(metrics.totalCostUsd)} over the period, ${metrics.costDriftSignals} cost drift(s).`,
      cta: 'View FinOps',
    },
    {
      title: 'Unity Catalog',
      route: '/unitycatalogexplorer',
      status: getReportStatus(
        metrics.piiNonCompliantTables > 0
          ? 3
          : metrics.missingUcSignals > 0 || metrics.missingOwnerSignals > 0
            ? 1
            : 0
      ),
      summary: 'Ungoverned tables, PII, missing owners, and missing tags.',
      evidence: `${metrics.missingUcSignals} missing UC mapping(s), ${metrics.piiNonCompliantTables} no-compliant PII item(s).`,
      cta: 'View Unity Catalog',
    },
    {
      title: 'Security',
      route: DATABRICKS_MODULE_FOCUS_PATHS.alerts,
      status: getReportStatus(metrics.criticalAlerts > 0 ? 3 : metrics.activeAlerts > 0 ? 1 : 0),
      summary: 'Critical or operational active alerts.',
      evidence: `${metrics.activeAlerts} alert(s) active(s), including ${metrics.criticalAlerts} critical/high.`,
      cta: 'View alerts',
    },
    {
      title: 'Impact Data Products',
      route: '/data-product-usage',
      status: getReportStatus(metrics.staleSignals > 0 ? 1 : 0),
      summary: 'Freshness and aggregated business impact, without detailed inventory.',
      evidence: `${metrics.staleSignals} late freshness, ${metrics.missingOwnerSignals} missing owner(s).`,
      cta: 'View usage',
    },
  ];
}

function buildPriorityActions(
  items: MonitoringReportItem[],
  computes: ComputeMetric[],
  pipelines: PipelineRun[]
): PriorityAction[] {
  const actions: PriorityAction[] = [];
  const failedPipeline = pipelines.find((pipeline) => pipeline.status === 'failed');
  const idleCluster = computes.find(
    (compute) => compute.state === 'running' && (compute.avg_cpu_utilization_pct ?? 100) < 10
  );
  const highCpuCluster = computes.find(
    (compute) => compute.state === 'running' && (compute.avg_cpu_utilization_pct ?? 0) > 85
  );
  const piiItem = items.find((item) =>
    item.failedCheckDetails.some((check) =>
      isPiiCheck(check.check_name, check.resource_name, check.resource_type)
    )
  );
  const costDriftItem = items.find((item) => (item.costTrendPercent ?? 0) > 15);
  const alertItem = items.find((item) =>
    item.alertDetails.some((alert) => alert.severity === 'critical' || alert.severity === 'high')
  );
  const staleItem = items.find((item) => item.freshnessStatus === 'Stale');
  const failedCheckItem = items.find((item) => item.failedChecks > 0);

  if (failedPipeline) {
    actions.push({
      id: `job-${failedPipeline.run_id}`,
      title: `Fix job ${failedPipeline.pipeline_name} failed`,
      impact: failedPipeline.error_message ?? 'Run failed over the filtered period.',
      route: '/pipelines',
    });
  }

  if (idleCluster) {
    actions.push({
      id: `idle-${idleCluster.compute_resource_id}`,
      title: `Stop or resize cluster idle ${idleCluster.resource_name}`,
      impact: `CPU ${idleCluster.avg_cpu_utilization_pct ?? 0}% on ${idleCluster.num_workers ?? 'n/a'} worker(s).`,
      route: '/databricks',
    });
  }

  if (piiItem) {
    const piiCheck = piiItem.failedCheckDetails.find((check) =>
      isPiiCheck(check.check_name, check.resource_name, check.resource_type)
    );
    actions.push({
      id: `pii-${piiItem.dataProductId}`,
      title: `Check table PII ${piiCheck?.resource_name ?? piiItem.dataProductName}`,
      impact: 'Classification, owner, or no-compliant governance rule.',
      route: DATABRICKS_MODULE_FOCUS_PATHS.governance,
    });
  }

  if (costDriftItem) {
    actions.push({
      id: `cost-${costDriftItem.dataProductId}-${costDriftItem.landingZoneId}`,
      title: `Investigate cost ${costDriftItem.landingZoneName} +${costDriftItem.costTrendPercent}%`,
      impact: `${formatCurrency(costDriftItem.costUsd)} consumed over the filtered period.`,
      route: DATABRICKS_MODULE_FOCUS_PATHS.costs,
    });
  }

  if (highCpuCluster) {
    actions.push({
      id: `cpu-${highCpuCluster.compute_resource_id}`,
      title: `Analyze cluster ${highCpuCluster.resource_name} with high CPU`,
      impact: `CPU ${Math.round(highCpuCluster.avg_cpu_utilization_pct ?? 0)}%, risk of saturation or unsuitable sizing.`,
      route: '/databricks',
    });
  }

  if (alertItem) {
    actions.push({
      id: `alert-${alertItem.dataProductId}`,
      title: `Handle security alert ${alertItem.alertDetails[0]?.title ?? alertItem.dataProductName}`,
      impact: `${alertItem.incidents} alert(s) active(s) on ${alertItem.landingZoneName}.`,
      route: DATABRICKS_MODULE_FOCUS_PATHS.alerts,
    });
  }

  if (
    failedCheckItem &&
    !actions.some((action) => action.route === DATABRICKS_MODULE_FOCUS_PATHS.governance)
  ) {
    actions.push({
      id: `check-${failedCheckItem.dataProductId}`,
      title: `Fix ${failedCheckItem.failedChecks} Standard Check(s) failed`,
      impact:
        failedCheckItem.statusReasons.join(', ') ||
        'Databricks compliance below the expected threshold.',
      route: DATABRICKS_MODULE_FOCUS_PATHS.governance,
    });
  }

  if (staleItem) {
    actions.push({
      id: `freshness-${staleItem.dataProductId}`,
      title: `Rerun freshness for ${staleItem.dataProductName}`,
      impact: `Last usage/refresh: ${staleItem.lastUsedAt ? new Date(staleItem.lastUsedAt).toLocaleString('en-GB') : 'unknown'}.`,
      route: '/data-product-usage',
    });
  }

  return actions.slice(0, 5);
}

function buildBusinessImpactCards(
  metrics: OperationalMetrics,
  summary: MonitoringSummary
): BusinessImpactCard[] {
  const dataTrustStatus = getReportStatus(
    metrics.piiNonCompliantTables > 0 || metrics.failedChecks > 0
      ? 3
      : metrics.staleSignals + metrics.missingOwnerSignals + metrics.warningChecks > 0
        ? 1
        : 0
  );
  const reportingStatus = getReportStatus(metrics.staleSignals > 0 ? 1 : 0);
  const costStatus = getReportStatus(metrics.costDriftSignals > 0 ? 1 : 0);
  const securityStatus = getReportStatus(
    metrics.criticalAlerts > 0 || metrics.piiNonCompliantTables > 0
      ? 3
      : metrics.activeAlerts > 0
        ? 1
        : 0
  );
  const opsStatus = getReportStatus(
    metrics.failedJobs > 0 || metrics.errorClusters > 0
      ? 3
      : metrics.highCpuClusters + metrics.idleClusters + metrics.slowJobs > 0
        ? 1
        : 0
  );
  const ownershipStatus = getReportStatus(
    metrics.missingOwnerSignals > 0 || metrics.missingUcSignals > 0 ? 1 : 0
  );
  const prioritySignals = [
    metrics.failedJobs,
    metrics.failedChecks,
    metrics.criticalAlerts,
    metrics.piiNonCompliantTables,
    metrics.costDriftSignals,
    metrics.staleSignals,
  ].filter((value) => value > 0).length;

  return [
    {
      title: 'Data trust',
      persona: 'Business / analyst',
      route: '/data-product-usage',
      status: dataTrustStatus,
      value: dataTrustStatus,
      meaning:
        metrics.staleSignals > 0 || metrics.failedChecks > 0
          ? `${formatNumber(metrics.staleSignals)} delayed freshness signal(s) and ${formatNumber(metrics.failedChecks)} check(s) failed may weaken analyses.`
          : `${formatNumber(summary.total)} summarized signal(s) without a major trust blocker.`,
      action: 'View impacted data products',
      icon: <ShieldCheck size={20} />,
    },
    {
      title: 'PO priority',
      persona: 'PO / lead data',
      route:
        metrics.criticalAlerts > 0
          ? DATABRICKS_MODULE_FOCUS_PATHS.alerts
          : DATABRICKS_MODULE_FOCUS_PATHS.governance,
      status: metrics.globalHealth,
      value: prioritySignals > 0 ? `${prioritySignals} topic(s)` : 'RAS',
      meaning:
        metrics.conclusionReasons.length > 0
          ? `Prioritize: ${metrics.conclusionReasons.slice(0, 3).join(', ')}.`
          : 'No blocking action detected in the filtered scope.',
      action: 'Open the first investigation',
      icon: <Target size={20} />,
    },
    {
      title: 'Impact reporting',
      persona: 'Business',
      route: '/data-product-usage',
      status: reportingStatus,
      value: `${formatNumber(metrics.staleSignals)} late`,
      meaning:
        metrics.staleSignals > 0
          ? 'Reports may rely on data that is less fresh than expected.'
          : 'No delayed freshness signal in the available usage data.',
      action: 'Check freshness',
      icon: <Clock3 size={20} />,
    },
    {
      title: 'Budget Databricks',
      persona: 'FinOps / PO',
      route: DATABRICKS_MODULE_FOCUS_PATHS.costs,
      status: costStatus,
      value: formatCurrency(metrics.totalCostUsd),
      meaning:
        metrics.maxCostTrendPercent !== null
          ? `Maximum drift detected: +${metrics.maxCostTrendPercent}%.`
          : 'No cost drift detected on consolidated signals.',
      action: 'Analyze cost drifts',
      icon: <LineChart size={20} />,
    },
    {
      title: 'Security risk',
      persona: 'Governance / security',
      route:
        metrics.piiNonCompliantTables > 0
          ? DATABRICKS_MODULE_FOCUS_PATHS.governance
          : DATABRICKS_MODULE_FOCUS_PATHS.alerts,
      status: securityStatus,
      value: `${formatNumber(metrics.criticalAlerts + metrics.piiNonCompliantTables)} critical`,
      meaning:
        metrics.criticalAlerts > 0 || metrics.piiNonCompliantTables > 0
          ? `${formatNumber(metrics.criticalAlerts)} alert(s) high/critical and ${formatNumber(metrics.piiNonCompliantTables)} table(s) no-compliant PII item(s).`
          : `${formatNumber(metrics.activeAlerts)} alert(s) active(s), with no consolidated critical signal.`,
      action: 'Handle risks',
      icon: <AlertTriangle size={20} />,
    },
    {
      title: 'Ownership & action',
      persona: 'Data owner',
      route: '/unitycatalogexplorer',
      status: ownershipStatus,
      value: `${formatNumber(metrics.missingOwnerSignals)} owner(s)`,
      meaning:
        metrics.missingOwnerSignals > 0 || metrics.missingUcSignals > 0
          ? `${formatNumber(metrics.missingOwnerSignals)} owner(s) and ${formatNumber(metrics.missingUcSignals)} mapping(s) Unity Catalog to complete.`
          : 'Available signals have actionable ownership for investigation.',
      action: 'Find the owner',
      icon: <Handshake size={20} />,
    },
    {
      title: 'Ops Databricks',
      persona: 'Data engineer',
      route: metrics.failedJobs > 0 ? '/pipelines' : '/databricks',
      status: opsStatus,
      value: `${formatNumber(metrics.failedJobs + metrics.errorClusters + metrics.idleClusters + metrics.highCpuClusters)} signal(s)`,
      meaning: `${formatNumber(metrics.failedJobs)} job(s) failed, ${formatNumber(metrics.idleClusters)} cluster(s) idle, ${formatNumber(metrics.highCpuClusters)} cluster(s) high CPU.`,
      action: 'Open resources',
      icon: <Gauge size={20} />,
    },
  ];
}

function buildPipelineChartData(metrics: OperationalMetrics): DataProductScoreDatum[] {
  return [
    { name: 'Success', value: metrics.successfulJobs },
    { name: 'Failed', value: metrics.failedJobs },
    { name: 'Running', value: metrics.runningJobs },
    { name: 'Cancelled', value: metrics.cancelledJobs },
  ].filter((item) => item.value > 0);
}

function buildClusterChartData(metrics: OperationalMetrics): DataProductScoreDatum[] {
  return [
    { name: 'Active', value: metrics.activeClusters },
    { name: 'Idle', value: metrics.idleClusters },
    { name: 'Error', value: metrics.errorClusters },
  ].filter((item) => item.value > 0);
}

function buildTopAnomalyData(metrics: OperationalMetrics): DataProductScoreDatum[] {
  return [
    { name: 'Jobs failed', value: metrics.failedJobs },
    { name: 'Checks failed', value: metrics.failedChecks },
    { name: 'Active alerts', value: metrics.activeAlerts },
    { name: 'Clusters idle', value: metrics.idleClusters },
    { name: 'PII no conforme', value: metrics.piiNonCompliantTables },
    { name: 'Freshness late', value: metrics.staleSignals },
    { name: 'Cost drifts', value: metrics.costDriftSignals },
  ].filter((item) => item.value > 0);
}

function buildConclusion(metrics: OperationalMetrics): string {
  if (metrics.globalHealth === 'Unknown') {
    return 'Databricks is Unknown: no usable data in the filtered scope.';
  }

  if (metrics.globalHealth === 'Healthy') {
    return 'Databricks is Healthy: no blocking signal detected in the filtered scope.';
  }

  return `Databricks is ${metrics.globalHealth} parce que : ${metrics.conclusionReasons.join(', ')}.`;
}

function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString('en-GB') : '-';
}

function formatLegacyValue(value: UnityCatalogCellValue | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  return String(value);
}

function parseLegacyNumber(value: UnityCatalogCellValue | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeLegacyStatus(value: UnityCatalogCellValue | undefined): string {
  const status = formatLegacyValue(value);
  return ['ok', 'success', 'succeeded', 'completed'].includes(status.toLowerCase())
    ? 'OK'
    : status || 'Unknown';
}

function getLegacyRows(
  result: UnityCatalogQueryResult
): Array<Record<string, UnityCatalogCellValue>> {
  if (result.data?.rows) return result.data.rows;
  if (result.Rows) return result.Rows;

  return result.Data.map((row) =>
    Object.fromEntries(result.Columns.map((column, index) => [column, row[index] ?? null]))
  );
}

function normalizeLegacyMonitoringRecords(
  result: UnityCatalogQueryResult
): LegacyMonitoringRecord[] {
  return getLegacyRows(result).map((row) => ({
    nom_script:
      formatLegacyValue(
        row.nom_script ?? row.pipeline_name ?? row.activity_name ?? row.activity_run_id
      ) || 'Unknown',
    nom_table:
      formatLegacyValue(row.nom_table ?? row.activity_type ?? row.pipeline_name) || 'Unknown',
    date_maj: formatLegacyValue(row.date_maj ?? row.dt_jour ?? row.collected_at ?? row.start_time),
    nombre_ligne: parseLegacyNumber(row.nombre_ligne ?? row.rows_read ?? row.rows_written),
    statut: normalizeLegacyStatus(row.statut ?? row.status),
    statut_log: formatLegacyValue(row.erreur ?? row.statut_log ?? row.error_message),
    start_time: formatLegacyValue(row.dt_debt_traitement ?? row.start_time),
    end_time: formatLegacyValue(row.dt_fin_traitement ?? row.end_time),
    job_name:
      formatLegacyValue(row.job_name ?? row.pipeline_name ?? row.activity_name) || 'unknown',
    job_id: formatLegacyValue(row.job_id ?? row.pipeline_run_id),
    run_id: formatLegacyValue(row.run_id ?? row.activity_run_id),
  }));
}

function buildLegacyStatusData(records: LegacyMonitoringRecord[]): DataProductScoreDatum[] {
  const okCount = records.filter((record) => record.statut === 'OK').length;
  const nonOkCount = records.length - okCount;
  return [
    { name: 'OK', value: okCount },
    { name: 'Non OK', value: nonOkCount },
  ].filter((item) => item.value > 0);
}

function buildLegacyDateData(records: LegacyMonitoringRecord[]): DataProductScoreDatum[] {
  const counts = records
    .filter((record) => record.statut === 'OK' && record.date_maj)
    .reduce<Record<string, number>>((acc, record) => {
      const parsedDate = new Date(record.date_maj);
      const dateKey = Number.isNaN(parsedDate.getTime())
        ? 'Date inconnue'
        : (parsedDate.toISOString().split('T')[0] ?? 'Date inconnue');
      acc[dateKey] = (acc[dateKey] ?? 0) + 1;
      return acc;
    }, {});

  return Object.entries(counts)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => a.name.localeCompare(b.name))
    .slice(-10);
}

function isPiiCheck(...values: Array<string | null>): boolean {
  return values.some(
    (value) => value?.toLowerCase().includes('pii') || value?.toLowerCase().includes('personal')
  );
}

function maxIsoDate(values: Array<string | null | undefined>): string | null {
  const sortedValues = values.filter((value): value is string => Boolean(value)).sort();
  return sortedValues.length > 0 ? sortedValues[sortedValues.length - 1] : null;
}

function average(values: Array<number | null | undefined>): number | null {
  const numericValues = values.filter((value): value is number => typeof value === 'number');
  if (numericValues.length === 0) return null;
  return numericValues.reduce((sum, value) => sum + value, 0) / numericValues.length;
}

const MonitoringReports: React.FC = () => {
  const { getApiParams, getDisplayRange } = useGlobalTimeRange();
  const { scope, getScopedParams } = useMonitoringScope();
  const { canAccess } = useRolePermissions();
  const canAccessUnityCatalog = canAccess('page:unity-catalog');
  const [legacyRecords, setLegacyRecords] = useState<LegacyMonitoringRecord[]>([]);
  const [legacyFullTableName, setLegacyFullTableName] = useState<string | null>(null);
  const [legacyLoading, setLegacyLoading] = useState(true);
  const [legacyError, setLegacyError] = useState<string | null>(null);
  const [legacyDateStart, setLegacyDateStart] = useState('');
  const [legacyDateEnd, setLegacyDateEnd] = useState('');
  const [legacyStatusFilter, setLegacyStatusFilter] = useState<'all' | 'OK' | 'Non OK'>('all');
  const [legacyTab, setLegacyTab] = useState<'notebooks' | 'workflows'>('notebooks');

  const scopedParams = getScopedParams({
    cloudProvider: true,
    subscriptionOrAccountId: true,
    sourceLzId: true,
  });
  const lzParams = getApiLzParams(scope);
  const requestStartDate = getApiParams().start_date;
  const requestEndDate = getApiParams().end_date;
  const requestCloudProvider = scopedParams.cloud_provider;
  const requestLandingZoneLabel =
    scopedParams.source_lz_ids?.join(', ') ?? scopedParams.source_lz_id ?? '';

  const monitoringQueryParams = useMemo(
    () => ({
      start_date: requestStartDate,
      end_date: requestEndDate,
      cloud_provider: requestCloudProvider,
      subscription_or_account_id: scopedParams.subscription_or_account_id,
      ...lzParams,
    }),
    [
      lzParams,
      requestCloudProvider,
      requestEndDate,
      requestStartDate,
      scopedParams.subscription_or_account_id,
    ]
  );

  const {
    data: monitoringData,
    isLoading: loading,
    error: queryError,
    isFetching,
    refetch,
  } = useMonitoringReportsQueries(monitoringQueryParams);

  const items = monitoringData?.items ?? [];
  const usageTrends = useMemo(
    () => monitoringData?.usageTrends ?? [],
    [monitoringData?.usageTrends]
  );
  const computes = useMemo(() => monitoringData?.computes ?? [], [monitoringData?.computes]);
  const pipelines = useMemo(() => monitoringData?.pipelines ?? [], [monitoringData?.pipelines]);
  const apiCostTotalUsd = monitoringData?.apiCostTotalUsd ?? null;
  const error =
    queryError instanceof Error ? queryError.message : queryError ? 'Loading error unknown' : null;

  const loadLegacyMonitoring = useCallback(() => {
    // This panel reads a raw Unity Catalog table, which carries no project scope:
    // the backend reserves it for unrestricted callers. Skip the doomed request —
    // the notice below says why, instead of a 403 dressed up as a loading error.
    if (!canAccessUnityCatalog) {
      setLegacyRecords([]);
      setLegacyFullTableName(null);
      setLegacyLoading(false);
      setLegacyError(null);
      return;
    }
    setLegacyLoading(true);
    setLegacyError(null);

    queryUnityCatalogTableGeneric({
      ...LEGACY_MONITORING_TABLE,
      orderBy: LEGACY_MONITORING_ORDER_BY,
      limit: LEGACY_MONITORING_LIMIT,
      offset: 0,
    })
      .then((response) => {
        setLegacyRecords(normalizeLegacyMonitoringRecords(response));
        setLegacyFullTableName(response.FullTableName);
      })
      .catch((err: unknown) =>
        setLegacyError(
          err instanceof Error ? err.message : `Unable to load ${LEGACY_MONITORING_TABLE.tableName}`
        )
      )
      .finally(() => setLegacyLoading(false));
  }, [canAccessUnityCatalog]);

  useEffect(() => {
    loadLegacyMonitoring();
  }, [loadLegacyMonitoring]);

  const filteredItems = items;
  const summary = useMemo(() => summarizeMonitoringReport(filteredItems), [filteredItems]);
  const metrics = useMemo(
    () => buildOperationalMetrics(filteredItems, computes, pipelines, apiCostTotalUsd),
    [apiCostTotalUsd, computes, filteredItems, pipelines]
  );
  const costChartData = useMemo(
    () => buildCostChartData(filteredItems, usageTrends),
    [filteredItems, usageTrends]
  );
  const complianceChartData = useMemo(
    () => buildComplianceChartData(filteredItems),
    [filteredItems]
  );
  const pipelineChartData = useMemo(() => buildPipelineChartData(metrics), [metrics]);
  const clusterChartData = useMemo(() => buildClusterChartData(metrics), [metrics]);
  const topAnomalyData = useMemo(() => buildTopAnomalyData(metrics), [metrics]);
  const priorityActions = useMemo(
    () => buildPriorityActions(filteredItems, computes, pipelines),
    [computes, filteredItems, pipelines]
  );
  const reportSections = useMemo(() => buildReportSections(metrics), [metrics]);
  const businessImpactCards = useMemo(
    () => buildBusinessImpactCards(metrics, summary),
    [metrics, summary]
  );
  const legacyFilteredRecords = useMemo(
    () =>
      legacyRecords.filter((record) => {
        if (legacyDateStart && record.date_maj < legacyDateStart) return false;
        if (legacyDateEnd && record.date_maj > legacyDateEnd) return false;
        if (legacyStatusFilter === 'OK' && record.statut !== 'OK') return false;
        if (legacyStatusFilter === 'Non OK' && record.statut === 'OK') return false;
        return true;
      }),
    [legacyDateEnd, legacyDateStart, legacyRecords, legacyStatusFilter]
  );
  const legacyVisibleRecords = useMemo(
    () =>
      legacyTab === 'workflows'
        ? legacyFilteredRecords.filter(
            (record) => record.job_name && record.job_name.toLowerCase() !== 'unknown'
          )
        : legacyFilteredRecords,
    [legacyFilteredRecords, legacyTab]
  );
  const legacyStatusData = useMemo(
    () => buildLegacyStatusData(legacyVisibleRecords),
    [legacyVisibleRecords]
  );
  const legacyDateData = useMemo(
    () => buildLegacyDateData(legacyVisibleRecords),
    [legacyVisibleRecords]
  );
  const display = getDisplayRange();
  const exportFilters = useMemo<MonitoringReportFilters>(
    () => ({
      ...getDefaultMonitoringReportFilters(),
      cloudProvider:
        requestCloudProvider === 'azure' || requestCloudProvider === 'aws'
          ? requestCloudProvider
          : '',
      landingZoneId: requestLandingZoneLabel,
      dateStart: requestStartDate,
      dateEnd: requestEndDate,
    }),
    [requestCloudProvider, requestEndDate, requestLandingZoneLabel, requestStartDate]
  );

  const exportCsvReport = () => {
    const fileName = buildMonitoringReportFileName('monitoring-report', exportFilters, 'csv');
    downloadTextFile(fileName, buildMonitoringReportCsv(filteredItems), 'text/csv;charset=utf-8');
  };

  return (
    <Content className="mx-auto max-w-[1800px]">
      <ContentHeader>
        <div>
          <ContentTitle>Databricks Monitoring Report</ContentTitle>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`Databricks executive report: health, costs, governance, alerts, and Unity Catalog from ${display.startDate} to ${display.endDate} — ${scope.label}`}
              tags={[
                { value: 'Databricks report', icon: <FileText size={14} />, tone: 'primary' },
                { label: 'Coverage', value: 'Health, costs, governance, alerts' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
                { label: 'Scope', value: scope.label },
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={exportCsvReport} disabled={loading}>
            <Download />
            Export CSV
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              void refetch();
            }}
            disabled={loading || isFetching}
          >
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {error && <PageError message={error} />}

      <ContentMain>
        {!loading && (
          <Card
            className={
              metrics.globalHealth === 'Critical'
                ? 'border-danger/40 bg-danger-subtle'
                : metrics.globalHealth === 'Warning'
                  ? 'border-warning/40 bg-warning-subtle'
                  : undefined
            }
          >
            <CardHeader>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusBadge status={metrics.globalHealth} />
                    <Badge variant="outline">
                      Last collection {formatDateTime(metrics.lastCollectedAt)}
                    </Badge>
                  </div>
                  <CardTitle>Immediate conclusion</CardTitle>
                  <CardDescription className="max-w-4xl text-base text-foreground">
                    {buildConclusion(metrics)}
                  </CardDescription>
                </div>
                <div className="grid min-w-[260px] grid-cols-2 gap-2 text-sm">
                  <div className="rounded-xl border bg-card p-3">
                    <p className="text-xs text-muted-foreground">Impact cost</p>
                    <p className="font-semibold">{formatCurrency(metrics.totalCostUsd)}</p>
                  </div>
                  <div className="rounded-xl border bg-card p-3">
                    <p className="text-xs text-muted-foreground">Business impact</p>
                    <p className="font-semibold">
                      {formatNumber(metrics.staleSignals)} freshness late
                    </p>
                  </div>
                </div>
              </div>
            </CardHeader>
          </Card>
        )}

        {!loading && (
          <section className="space-y-4" aria-labelledby="decision-cards-title">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tdf-blue">
                  Business experience
                </p>
                <h2
                  id="decision-cards-title"
                  className="text-2xl font-semibold tracking-tight text-foreground"
                >
                  Investigation path
                </h2>
                <p className="max-w-3xl text-sm text-muted-foreground">
                  Each tile summarizes the signal, its control level, and the best entry point to
                  investigate without showing every detail on the first screen.
                </p>
              </div>
              <Badge
                variant="outline"
                className="border-tdf-blue-border/70 bg-tdf-blue-subtle text-tdf-blue"
              >
                {businessImpactCards.length} detail links
              </Badge>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {businessImpactCards.map((card) => {
                const tone = decisionCardTone[card.status];

                return (
                  <Link
                    key={card.title}
                    to={card.route}
                    className={`group relative flex min-h-[210px] overflow-hidden rounded-2xl border border-border/70 bg-[var(--card-background)] shadow-[var(--card-shadow)] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[var(--card-hover-shadow)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${tone.border}`}
                  >
                    <div className="flex flex-1 flex-col">
                      <div
                        className={`relative border-b border-border/60 px-4 py-4 ${tone.header}`}
                      >
                        <div className="flex items-start gap-3 pr-9">
                          <div
                            className={`flex size-10 shrink-0 items-center justify-center rounded-xl shadow-lg ring-1 ring-white/50 transition-transform group-hover:scale-105 ${tone.icon}`}
                          >
                            {card.icon}
                          </div>
                          <div className="min-w-0">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">
                              {card.persona}
                            </p>
                            <h3 className="mt-1 text-base font-semibold leading-5 text-foreground">
                              {card.title}
                            </h3>
                          </div>
                        </div>
                        <span
                          className={`absolute right-4 top-4 flex size-8 translate-x-2 items-center justify-center rounded-full opacity-0 shadow-sm transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 ${tone.arrow}`}
                          aria-hidden="true"
                        >
                          <ArrowRight size={16} />
                        </span>
                        <span className="sr-only">View details</span>
                      </div>

                      <div className="flex flex-1 flex-col p-4">
                        <div className="flex items-start justify-between gap-3">
                          <p
                            className={`text-2xl font-semibold leading-7 tracking-[-0.04em] ${tone.value}`}
                          >
                            {card.value}
                          </p>
                          <StatusBadge status={card.status} />
                        </div>

                        <p className="mt-3 line-clamp-3 text-sm leading-5 text-muted-foreground">
                          {card.meaning}
                        </p>

                        <div className="mt-4 rounded-2xl bg-background/70 p-2.5 shadow-sm">
                          <div className="flex items-center justify-between gap-3 text-xs font-semibold">
                            <span className="text-muted-foreground">Control level</span>
                            <span className={tone.value}>{tone.scoreLabel}</span>
                          </div>
                          <div className="mt-1.5 h-1.5 rounded-full bg-muted">
                            <span
                              className={`block h-full rounded-full ${tone.bar}`}
                              style={{ width: `${tone.score}%` }}
                            />
                          </div>
                        </div>

                        <div className="mt-auto flex items-center justify-between gap-3 pt-4 text-xs text-muted-foreground">
                          <Badge variant="outline" className="bg-background/70">
                            {card.action}
                          </Badge>
                          <span className="font-medium text-muted-foreground">
                            by {card.persona}
                          </span>
                        </div>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        <MetricGrid
          loading={loading}
          skeletonCount={8}
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        >
          <MetricCard
            label="Overall health"
            value={metrics.globalHealth}
            description={`${summary.critical} critical · ${summary.warning} warning · ${summary.healthy} healthy`}
            icon={<Gauge />}
            tone={
              metrics.globalHealth === 'Critical'
                ? 'danger'
                : metrics.globalHealth === 'Warning'
                  ? 'warning'
                  : metrics.globalHealth === 'Healthy'
                    ? 'success'
                    : 'default'
            }
          />
          <MetricCard
            label="Cost period"
            value={formatCurrency(metrics.totalCostUsd)}
            description={
              metrics.maxCostTrendPercent !== null
                ? `Max drift +${metrics.maxCostTrendPercent}%`
                : 'No cost drift detected'
            }
            icon={<BarChart3 />}
            tone={metrics.costDriftSignals > 0 ? 'warning' : 'purple'}
          />
          <MetricCard
            label="Active alerts"
            value={formatNumber(metrics.activeAlerts)}
            description={`${metrics.criticalAlerts} critical or high`}
            icon={<AlertTriangle />}
            tone={
              metrics.criticalAlerts > 0
                ? 'danger'
                : metrics.activeAlerts > 0
                  ? 'warning'
                  : 'success'
            }
          />
          <MetricCard
            label="Checks failed"
            value={formatNumber(metrics.failedChecks)}
            description={`Average compliance ${formatNullablePercentage(summary.averageComplianceScore)}`}
            icon={<ShieldCheck />}
            tone={
              metrics.failedChecks > 0
                ? 'danger'
                : metrics.warningChecks > 0
                  ? 'warning'
                  : 'success'
            }
          />
          <MetricCard
            label="Jobs failed"
            value={formatNumber(metrics.failedJobs)}
            description={`${metrics.successfulJobs} success · ${metrics.runningJobs} running`}
            icon={<Activity />}
            tone={
              metrics.failedJobs > 0 ? 'danger' : metrics.runningJobs > 0 ? 'warning' : 'success'
            }
          />
          <MetricCard
            label="Late freshness"
            value={formatNumber(metrics.staleSignals)}
            description="Impacted Data Products in summary"
            icon={<Database />}
            tone={metrics.staleSignals > 0 ? 'warning' : 'success'}
          />
          <MetricCard
            label="Clusters to monitor"
            value={formatNumber(
              metrics.idleClusters + metrics.errorClusters + metrics.highCpuClusters
            )}
            description={`${metrics.idleClusters} idle · ${metrics.errorClusters} error · ${metrics.highCpuClusters} high CPU`}
            icon={<Gauge />}
            tone={
              metrics.errorClusters > 0
                ? 'danger'
                : metrics.idleClusters + metrics.highCpuClusters > 0
                  ? 'warning'
                  : 'success'
            }
          />
          <MetricCard
            label="Last collection"
            value={formatDateTime(metrics.lastCollectedAt)}
            description={`${formatNumber(summary.total)} summarized signals`}
            icon={<CheckCircle2 />}
            tone="default"
          />
        </MetricGrid>

        {loading ? (
          <div className="grid gap-6 xl:grid-cols-2">
            <Card>
              <CardContent>
                <TableSkeleton rows={6} />
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <TableSkeleton rows={6} />
              </CardContent>
            </Card>
          </div>
        ) : items.length === 0 && computes.length === 0 && pipelines.length === 0 ? (
          <EmptyState
            icon={<Database size={24} />}
            title="No Databricks signal available"
            description="No usable monitoring data was returned by the DCM APIs for the active period."
          />
        ) : (
          <>
            <div className="grid gap-6 xl:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle>Databricks cost by period</CardTitle>
                  <CardDescription>
                    Consolidated FinOps trend by day/week based on available data.
                  </CardDescription>
                </CardHeader>
                <CardContent className="h-[300px] pt-0">
                  {costChartData.length === 0 ? (
                    <ChartEmptyState title="No cost to display." />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={costChartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="period" fontSize={12} />
                        <YAxis tickFormatter={formatCompact} />
                        <Tooltip formatter={(value) => formatCurrency(Number(value))} />
                        <Legend />
                        <Bar dataKey="azure" name="Azure" stackId="cost" fill={chartColor.info} />
                        <Bar dataKey="aws" name="AWS" stackId="cost" fill={chartColor.warning} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Jobs failed vs success</CardTitle>
                  <CardDescription>Immediate view of Databricks pipelines to fix.</CardDescription>
                </CardHeader>
                <CardContent className="h-[300px] pt-0">
                  {pipelineChartData.length === 0 ? (
                    <ChartEmptyState title="No job to display." />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={pipelineChartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" fontSize={12} />
                        <YAxis allowDecimals={false} />
                        <Tooltip />
                        <Bar dataKey="value" name="Runs">
                          {pipelineChartData.map((entry) => (
                            <Cell key={entry.name} fill={getHealthDatumColor(entry.name)} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Clusters idle / active / error</CardTitle>
                  <CardDescription>
                    Compute signal for stopping, resizing, or investigation.
                  </CardDescription>
                </CardHeader>
                <CardContent className="h-[300px] pt-0">
                  {clusterChartData.length === 0 ? (
                    <ChartEmptyState title="No cluster to display." />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={clusterChartData}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={54}
                          outerRadius={90}
                          label={({ name, value }) => `${name}: ${value}`}
                        >
                          {clusterChartData.map((entry) => (
                            <Cell key={entry.name} fill={getHealthDatumColor(entry.name)} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Checks passed / failed</CardTitle>
                  <CardDescription>
                    Aggregated governance summary; details remain on the Governance page.
                  </CardDescription>
                </CardHeader>
                <CardContent className="h-[300px] pt-0">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={complianceChartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" fontSize={12} />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Bar dataKey="count" name="Checks">
                        {complianceChartData.map((entry) => (
                          <Cell key={entry.name} fill={getHealthDatumColor(entry.name)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Top anomalies</CardTitle>
                  <CardDescription>Signals that explain the report status.</CardDescription>
                </CardHeader>
                <CardContent className="h-[300px] pt-0">
                  {topAnomalyData.length === 0 ? (
                    <ChartEmptyState title="No anomaly to display." />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={topAnomalyData} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" allowDecimals={false} />
                        <YAxis type="category" dataKey="name" width={130} fontSize={11} />
                        <Tooltip formatter={(value) => formatNumber(Number(value))} />
                        <Bar dataKey="value" name="Anomalies" fill={chartColor.danger} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Short impact evidence</CardTitle>
                <CardDescription>
                  Unity Catalog and Data Products remain impact signals:{' '}
                  {formatNumber(metrics.missingUcSignals)} missing UC mapping(s),{' '}
                  {formatNumber(metrics.piiNonCompliantTables)} no-compliant PII item(s),{' '}
                  {formatNumber(metrics.staleSignals)} late freshness. Details remain on the
                  dedicated pages.
                </CardDescription>
              </CardHeader>
            </Card>

            <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
              <Card>
                <CardHeader>
                  <CardTitle>Databricks summary report</CardTitle>
                  <CardDescription>
                    Non-redundant cross-domain view: each section summarizes a domain and links to
                    the detail page.
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-3 pt-0 md:grid-cols-2">
                  {reportSections.map((section) => (
                    <Link
                      key={section.title}
                      to={section.route}
                      className="rounded-2xl border border-border/70 bg-card p-4 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-foreground">{section.title}</p>
                          <p className="text-xs text-muted-foreground">{section.summary}</p>
                        </div>
                        <StatusBadge status={section.status} />
                      </div>
                      <p className="text-sm text-muted-foreground">{section.evidence}</p>
                      <p className="mt-3 text-xs font-semibold text-primary">{section.cta} →</p>
                    </Link>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Top actions</CardTitle>
                  <CardDescription>
                    Short, prioritized actions with a direct investigation link.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 pt-0">
                  {priorityActions.length === 0 ? (
                    <EmptyState
                      icon={<CheckCircle2 size={24} />}
                      title="No priority action"
                      description="No failed job, idle cluster, non-compliant PII, cost drift, or late freshness detected in this scope."
                    />
                  ) : (
                    priorityActions.map((action, index) => (
                      <Link
                        key={action.id}
                        to={action.route}
                        className="block rounded-2xl border border-border/70 p-4 transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <Badge variant={index === 0 ? 'destructive' : 'warning'}>
                            P{index + 1}
                          </Badge>
                          <Badge variant="outline">View details</Badge>
                        </div>
                        <p className="font-semibold text-foreground">{action.title}</p>
                        <p className="text-sm text-muted-foreground">{action.impact}</p>
                      </Link>
                    ))
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <CardTitle>Curated activity run coverage</CardTitle>
                    <CardDescription>
                      Activity run fields from{' '}
                      {legacyFullTableName ?? LEGACY_MONITORING_TABLE.tableName}: Script, Feature
                      Projet, Processed Table, JobId, RunId, rows, status, status log, start and end
                      time.
                    </CardDescription>
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={loadLegacyMonitoring}
                    disabled={legacyLoading}
                  >
                    <RefreshCw size={14} />
                    {legacyLoading ? 'Loading legacy data' : 'Refresh legacy data'}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-6 pt-0">
                <div className="grid gap-4 md:grid-cols-4">
                  <MetricCard
                    label="Records analyzed"
                    value={legacyRecords.length.toLocaleString('en-GB')}
                    description={`Rows loaded from ${LEGACY_MONITORING_TABLE.tableName}`}
                    icon={<Database />}
                  />
                  <MetricCard
                    label="Notebooks"
                    value={legacyFilteredRecords.length.toLocaleString('en-GB')}
                    description="All monitoring rows"
                    icon={<FileText />}
                    tone="purple"
                  />
                  <MetricCard
                    label="Workflows"
                    value={legacyFilteredRecords
                      .filter(
                        (record) => record.job_name && record.job_name.toLowerCase() !== 'unknown'
                      )
                      .length.toLocaleString('en-GB')}
                    description="Rows linked to a Databricks job"
                    icon={<Activity />}
                    tone="success"
                  />
                  <MetricCard
                    label="Displayed rows"
                    value={legacyVisibleRecords.length.toLocaleString('en-GB')}
                    description={`Active tab: ${legacyTab}`}
                    icon={<Target />}
                  />
                </div>

                <div className="rounded-2xl border border-border/70 bg-muted/30 p-4">
                  <div className="grid gap-4 md:grid-cols-4">
                    <div className="space-y-2">
                      <label htmlFor="legacy-start" className="text-sm font-medium">
                        Date start
                      </label>
                      <Input
                        id="legacy-start"
                        type="date"
                        value={legacyDateStart}
                        onChange={(event) => setLegacyDateStart(event.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="legacy-end" className="text-sm font-medium">
                        Date end
                      </label>
                      <Input
                        id="legacy-end"
                        type="date"
                        value={legacyDateEnd}
                        onChange={(event) => setLegacyDateEnd(event.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <label htmlFor="legacy-status" className="text-sm font-medium">
                        Status
                      </label>
                      <Select
                        id="legacy-status"
                        value={legacyStatusFilter}
                        onChange={(event) =>
                          setLegacyStatusFilter(event.target.value as 'all' | 'OK' | 'Non OK')
                        }
                        className="w-full"
                      >
                        <option value="all">All</option>
                        <option value="OK">OK</option>
                        <option value="Non OK">Non OK</option>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <span className="text-sm font-medium">POC tabs</span>
                      <div className="flex gap-2">
                        <Button
                          variant={legacyTab === 'notebooks' ? 'default' : 'secondary'}
                          size="sm"
                          onClick={() => setLegacyTab('notebooks')}
                        >
                          Notebooks
                        </Button>
                        <Button
                          variant={legacyTab === 'workflows' ? 'default' : 'secondary'}
                          size="sm"
                          onClick={() => setLegacyTab('workflows')}
                        >
                          Workflows
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                {!canAccessUnityCatalog && (
                  <PageNotice
                    title="Outside your project scope"
                    message={`${LEGACY_MONITORING_TABLE.tableName} is read as a raw Unity Catalog table, which carries no project scope — it is reserved for platform admins. Every other panel on this page is scoped to your project.`}
                  />
                )}
                {legacyError && <PageError message={legacyError} />}
                {legacyRecords.length >= LEGACY_MONITORING_LIMIT && (
                  <div className="rounded-2xl border border-warning/40 bg-warning-subtle p-4 text-sm text-warning">
                    Limit of {LEGACY_MONITORING_LIMIT.toLocaleString('en-GB')} records reached. As
                    in the POC, totals may be partial until "load all" is replaced by a backend
                    aggregate.
                  </div>
                )}

                {legacyLoading ? (
                  <TableSkeleton rows={8} />
                ) : (
                  <>
                    <div className="grid gap-6 lg:grid-cols-2">
                      <Card>
                        <CardHeader>
                          <CardTitle>
                            {legacyTab === 'workflows'
                              ? 'Azure DataBricks Workflows'
                              : 'Azure DataBricks Notebooks'}{' '}
                            Status
                          </CardTitle>
                          <CardDescription>OK vs Non OK, same split as the POC.</CardDescription>
                        </CardHeader>
                        <CardContent className="h-[260px] pt-0">
                          {legacyStatusData.length === 0 ? (
                            <ChartEmptyState title="No monitoring status to display." />
                          ) : (
                            <ResponsiveContainer width="100%" height="100%">
                              <PieChart>
                                <Pie
                                  data={legacyStatusData}
                                  dataKey="value"
                                  nameKey="name"
                                  outerRadius={90}
                                  label={({ name, value }) => `${name}: ${value}`}
                                >
                                  {legacyStatusData.map((entry) => (
                                    <Cell
                                      key={entry.name}
                                      fill={
                                        entry.name === 'OK' ? chartColor.success : chartColor.danger
                                      }
                                    />
                                  ))}
                                </Pie>
                                <Tooltip />
                                <Legend />
                              </PieChart>
                            </ResponsiveContainer>
                          )}
                        </CardContent>
                      </Card>
                      <Card>
                        <CardHeader>
                          <CardTitle>
                            {legacyTab === 'workflows' ? 'Workflows' : 'Notebooks'} by date (Status
                            OK)
                          </CardTitle>
                          <CardDescription>
                            Last 10 dates parsed from date_maj / dt_jour.
                          </CardDescription>
                        </CardHeader>
                        <CardContent className="h-[260px] pt-0">
                          {legacyDateData.length === 0 ? (
                            <ChartEmptyState title="No OK monitoring date to display." />
                          ) : (
                            <ResponsiveContainer width="100%" height="100%">
                              <BarChart data={legacyDateData}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" fontSize={11} />
                                <YAxis allowDecimals={false} />
                                <Tooltip />
                                <Bar dataKey="value" name="Status OK" fill={chartColor.success} />
                              </BarChart>
                            </ResponsiveContainer>
                          )}
                        </CardContent>
                      </Card>
                    </div>

                    <div className="overflow-x-auto rounded-2xl border border-border/70">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Script</TableHead>
                            <TableHead>Feature Projet</TableHead>
                            <TableHead>Processed Table</TableHead>
                            <TableHead>JobId</TableHead>
                            <TableHead>RunId</TableHead>
                            <TableHead>#Rows processed</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Status Log</TableHead>
                            <TableHead>Start Time</TableHead>
                            <TableHead>End Time</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {legacyVisibleRecords.slice(0, 100).map((record, index) => (
                            <TableRow key={`${record.nom_script}-${record.run_id}-${index}`}>
                              <TableCell className="min-w-48 font-mono">
                                {record.nom_script}
                              </TableCell>
                              <TableCell>{record.job_name}</TableCell>
                              <TableCell className="min-w-48 font-mono">
                                {record.nom_table}
                              </TableCell>
                              <TableCell className="font-mono">{record.job_id || '-'}</TableCell>
                              <TableCell className="font-mono">{record.run_id || '-'}</TableCell>
                              <TableCell>{formatNumber(record.nombre_ligne)}</TableCell>
                              <TableCell>
                                <Badge variant={record.statut === 'OK' ? 'success' : 'destructive'}>
                                  {record.statut}
                                </Badge>
                              </TableCell>
                              <TableCell className="max-w-md truncate">
                                {record.statut_log || '-'}
                              </TableCell>
                              <TableCell>{formatDateTime(record.start_time || null)}</TableCell>
                              <TableCell>{formatDateTime(record.end_time || null)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Displaying the first 100 rows out of{' '}
                      {legacyVisibleRecords.length.toLocaleString('en-GB')} filtered legacy records.
                    </p>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Report Sources and Limits</CardTitle>
                <CardDescription>
                  Data consolidated from Compute Databricks, Pipelines, Costs, Standard Checks,
                  Security Alerts, Landing Zones, available Unity Catalog, and aggregated usage.
                  Dedicated pages remain the detail views; this report helps decide what to
                  investigate first.
                </CardDescription>
              </CardHeader>
            </Card>
          </>
        )}
      </ContentMain>
    </Content>
  );
};

export default MonitoringReports;
