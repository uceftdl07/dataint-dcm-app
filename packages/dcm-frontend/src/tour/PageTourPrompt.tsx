import { CircleHelp, X } from 'lucide-react';
import React from 'react';
import { Button } from '../components/ui/button';

interface PageTourPromptProps {
  tourKey: string;
  onStart: () => void;
  onDismiss: () => void;
}

const PAGE_LABELS: Record<string, string> = {
  dashboard: 'Home',
  datafactory: 'Data Factory',
  pipelines: 'Pipelines',
  databricks: 'Databricks',
  databases: 'Databases',
  clusters: 'Clusters',
  costs: 'Global FinOps',
  alerts: 'Global Alerts',
  security: 'Cloud security',
  governance: 'Standard Checks',
  users: 'Users',
  'talk-to-data': 'Talk to Data',
  status: 'Collection status',
  settings: 'Settings',
  admin: 'Administration',
};

function labelForKey(tourKey: string): string {
  if (PAGE_LABELS[tourKey]) return PAGE_LABELS[tourKey];
  const base = tourKey.split('-')[0];
  return PAGE_LABELS[base] ?? 'this page';
}

export const PageTourPrompt: React.FC<PageTourPromptProps> = ({ tourKey, onStart, onDismiss }) => (
  <div
    className="dcm-tour-page-prompt fixed bottom-6 left-1/2 z-[90] w-[min(24rem,calc(100vw-2rem))] -translate-x-1/2"
    role="status"
    aria-live="polite"
  >
    <div className="flex items-start gap-3 rounded-2xl border border-border bg-card/95 p-4 shadow-xl backdrop-blur-md">
      <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <CircleHelp size={20} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">New on {labelForKey(tourKey)}?</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Take a short guided tour — hover highlights show you where to click.
        </p>
        <div className="mt-3 flex gap-2">
          <Button size="sm" onClick={onStart}>
            Start tour
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 rounded-lg p-1 text-muted-foreground hover:bg-muted"
        aria-label="Dismiss page tour prompt"
      >
        <X size={16} />
      </button>
    </div>
  </div>
);
