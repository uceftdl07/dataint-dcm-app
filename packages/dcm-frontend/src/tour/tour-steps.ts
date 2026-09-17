import type { DriveStep } from 'driver.js';
import { pageHasGlobalFilters, pageHasWorkspaceFilter } from './resolve-tour-key';

type TourCopy = { title: string; description: string };

const PAGE_COPY: Record<string, TourCopy> = {
  dashboard: {
    title: 'Operational overview',
    description:
      'KPI cards summarise health across Data Factory, Databricks, databases, costs, and alerts. Click any card to drill into a module.',
  },
  datafactory: {
    title: 'Azure Data Factory',
    description:
      'Monitor ADF pipeline runs, failures, and throughput. Use Refresh to pull the latest snapshot for your landing zones.',
  },
  'datafactory-focus': {
    title: 'Data Factory detail view',
    description: 'Focused breakdown for a single pipeline or activity. Switch views with the tabs above the table.',
  },
  pipelines: {
    title: 'Pipelines',
    description: 'Browse all pipeline runs. Sort and filter failures, then open a row for run history and error details.',
  },
  'pipelines-focus': {
    title: 'Pipeline focus',
    description: 'Deep-dive on one pipeline: recent runs, duration trends, and linked alerts.',
  },
  'datafactory-alerts': {
    title: 'Data Factory alerts',
    description: 'ADF-specific alerts ranked by severity. Expand a row to see remediation context.',
  },
  'datafactory-finops': {
    title: 'Data Factory FinOps',
    description: 'Azure Data Factory spend broken down by factory, pipeline, and activity type.',
  },
  'datafactory-governance': {
    title: 'Data Factory governance',
    description: 'Standard checks and compliance signals for your ADF estates.',
  },
  databricks: {
    title: 'Databricks dashboard',
    description:
      'Jobs, clusters, and workspace health at a glance. Filter by workspace in the header when you manage several estates.',
  },
  'databricks-focus': {
    title: 'Databricks detail view',
    description: 'Focused metrics for clusters, jobs, costs, or governance depending on the active tab.',
  },
  'databricks-alerts': {
    title: 'Databricks alerts',
    description: 'Workspace-level alerts: failed jobs, cluster issues, and policy violations.',
  },
  'databricks-finops': {
    title: 'Databricks FinOps',
    description: 'DBU and infrastructure costs per workspace, cluster policy, and job.',
  },
  'databricks-governance': {
    title: 'Databricks governance',
    description: 'Unity Catalog policies, tagging compliance, and standard checks for Databricks.',
  },
  'unity-catalog': {
    title: 'Unity Catalog explorer',
    description: 'Browse catalogs, schemas, and tables. Search assets and review governance metadata.',
  },
  'data-product-usage': {
    title: 'Data product usage',
    description: 'Track consumption of curated data products across workspaces and teams.',
  },
  'data-product-usage-focus': {
    title: 'Data product detail',
    description: 'Usage trends and top consumers for a single data product.',
  },
  'monitoring-reports': {
    title: 'Monitoring reports',
    description: 'Scheduled and on-demand observability reports generated from DCM data.',
  },
  databases: {
    title: 'Database dashboard',
    description: 'Azure SQL, PostgreSQL, RDS, and other managed databases — performance, size, and availability.',
  },
  'databases-focus': {
    title: 'Database detail view',
    description: 'Metrics and alerts for one database instance. Use tabs to switch between perf, security, and cost.',
  },
  'database-alerts': {
    title: 'Database alerts',
    description: 'Storage, connectivity, and security alerts across all database landing zones.',
  },
  'database-finops': {
    title: 'Database FinOps',
    description: 'Database spend by engine, tier, and landing zone.',
  },
  'database-governance': {
    title: 'Database governance',
    description: 'Encryption, backup, and tagging compliance for database assets.',
  },
  clusters: {
    title: 'Clusters',
    description: 'Compute clusters (EMR, HDInsight, etc.) — status, utilisation, and cost drivers.',
  },
  'clusters-focus': {
    title: 'Cluster detail',
    description: 'Single-cluster view with node metrics and linked jobs.',
  },
  costs: {
    title: 'Global FinOps',
    description: 'Consolidated Azure + AWS spend. Compare services, landing zones, and trends over time.',
  },
  'costs-focus': {
    title: 'Cost detail view',
    description: 'Drill-down for one service or resource group within the selected period.',
  },
  alerts: {
    title: 'Global alerts',
    description: 'Cross-platform alert feed. Filter by severity, platform, and landing zone.',
  },
  'alerts-focus': {
    title: 'Alert detail',
    description: 'Full context for a single alert including history and related resources.',
  },
  security: {
    title: 'Cloud security',
    description: 'Security findings from Azure Defender, AWS Security Hub, and related sources.',
  },
  governance: {
    title: 'Standard checks',
    description: 'Organisation-wide compliance scorecards and failing checks by landing zone.',
  },
  users: {
    title: 'Users',
    description:
      'Multi-cloud identity inventory. Inactive users beyond 90 days are highlighted for cleanup review.',
  },
  'talk-to-data': {
    title: 'Talk to Data',
    description:
      'Ask questions in plain English. Powered by Databricks Genie on your DCM data — costs, pipelines, alerts, governance.',
  },
  status: {
    title: 'Collection status',
    description:
      'End-to-end pipeline health: cloud agents → ingestion → Databricks → Unity Catalog → backend. Use when data looks stale.',
  },
  settings: {
    title: 'Settings',
    description: 'Theme, backend connectivity test, notification preferences, and guided tour controls.',
  },
  admin: {
    title: 'Administration',
    description: 'Super-admin tools: landing zone scope management and platform configuration.',
  },
  generic: {
    title: 'Page content',
    description: 'Charts, tables, and actions for the current module appear in this area.',
  },
};

/**
 * Whether a control is on screen right now. The tour key cannot answer for the
 * landing-zone filter: it collapses every `/databricks/**` page into
 * `databricks-focus`, while `showsLandingZoneFilter` keeps the control only on
 * the few whose tables are LZ-keyed. Callers run this after layout has painted.
 */
function isOnScreen(selector: string): boolean {
  return document.querySelector(selector) !== null;
}

function shellSteps(tourKey: string): DriveStep[] {
  const steps: DriveStep[] = [
    {
      element: '[data-tour="sidebar"]',
      popover: {
        title: 'Navigation',
        description:
          'Move between modules from the sidebar. Expand Data Factory, Databricks, or Databases for sub-pages.',
        side: 'right',
        align: 'start',
      },
    },
  ];

  if (pageHasGlobalFilters(tourKey)) {
    steps.push({
      element: '[data-tour="notifications"]',
      popover: {
        title: 'Notifications',
        description: 'Recent alerts appear here. Configure which domains you see in Settings.',
        side: 'bottom',
        align: 'end',
      },
    });

    if (isOnScreen('[data-tour="landing-zone-filter"]')) {
      steps.push({
        element: '[data-tour="landing-zone-filter"]',
        popover: {
          title: 'Landing zone filter',
          description: 'Scope all charts to one or more landing zones. Hover the control to preview your selection.',
          side: 'bottom',
          align: 'center',
        },
      });
    }

    if (pageHasWorkspaceFilter(tourKey)) {
      steps.push({
        element: '[data-tour="workspace-filter"]',
        popover: {
          title: 'Databricks workspace filter',
          description: 'Narrow Databricks metrics to specific workspaces linked to your landing zones.',
          side: 'bottom',
          align: 'center',
        },
      });
    }

    steps.push({
      element: '[data-tour="date-range"]',
      popover: {
        title: 'Time range',
        description:
          'Pick custom dates or use presets (30d, 90d, 6m, 1y). All widgets update reactively when the range changes.',
        side: 'bottom',
        align: 'end',
      },
    });
  }

  steps.push({
    element: '[data-tour="page-content"]',
    popover: {
      title: PAGE_COPY[tourKey]?.title ?? PAGE_COPY.generic.title,
      description: PAGE_COPY[tourKey]?.description ?? PAGE_COPY.generic.description,
      side: 'top',
      align: 'start',
    },
  });

  if (tourKey !== 'talk-to-data' && tourKey !== 'admin') {
    steps.push({
      element: '[data-tour="tour-help"]',
      popover: {
        title: 'Replay anytime',
        description: 'Click the guide button in the header to replay this page tour whenever you need a refresher.',
        side: 'bottom',
        align: 'end',
      },
    });
  }

  return steps;
}

/** First-visit welcome tour on Home — slightly longer intro. */
export function getWelcomeTourSteps(): DriveStep[] {
  return [
    {
      element: '[data-tour="sidebar"]',
      popover: {
        title: 'Welcome to Data connect',
        description:
          'This is your multi-cloud observability hub. Let us walk through the essentials — it takes about one minute.',
        side: 'right',
        align: 'start',
      },
    },
    ...shellSteps('dashboard').slice(1),
    {
      element: '[data-tour="dataiq-assistant"]',
      popover: {
        title: 'Talk to your data',
        description:
          'Open the DataIQ assistant to ask questions in natural language — costs, pipelines, security, and more.',
        side: 'left',
        align: 'end',
      },
    },
  ];
}

export function getPageTourSteps(tourKey: string): DriveStep[] {
  return shellSteps(tourKey);
}
