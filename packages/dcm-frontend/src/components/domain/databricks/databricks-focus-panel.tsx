import { Copy, Link2, X } from 'lucide-react';
import { useCallback, useState } from 'react';
import {
  DATABRICKS_FOCUS_VIEW_DESCRIPTIONS,
  DATABRICKS_FOCUS_VIEW_LABELS,
  type DatabricksFocusView,
} from '../../../lib/databricks/focus-view';
import type { DatabricksFocusViewData } from '../../../lib/databricks/view-data';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../ui/card';
import { ClustersFocusView } from './views/clusters-focus-view';
import { CostsFocusView } from './views/costs-focus-view';
import { GovernanceFocusView } from './views/governance-focus-view';
import { JobsFocusView } from './views/jobs-focus-view';
import { SecurityAlertsFocusView } from './views/security-alerts-focus-view';
import { WorkspacesFocusView } from './views/workspaces-focus-view';

export function DatabricksFocusPanel({
  view,
  data,
  onClear,
}: {
  view: DatabricksFocusView;
  data: DatabricksFocusViewData;
  onClear: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const copyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, []);

  return (
    <Card className="overflow-hidden rounded-[1.75rem] border-primary/20 shadow-[var(--card-shadow)]">
      <CardHeader className="border-b border-border/60 bg-muted/20">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="bg-background/80">
                <Link2 size={12} />
                Focus view
              </Badge>
              <Badge variant="secondary">{view}</Badge>
            </div>
            <CardTitle>{DATABRICKS_FOCUS_VIEW_LABELS[view]}</CardTitle>
            <CardDescription>{DATABRICKS_FOCUS_VIEW_DESCRIPTIONS[view]}</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void copyLink()}>
              <Copy size={14} />
              {copied ? 'Link copied' : 'Copy link'}
            </Button>
            <Button variant="secondary" size="sm" onClick={onClear}>
              <X size={14} />
              Close
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-6">
        {view === 'clusters' && <ClustersFocusView data={data} />}
        {view === 'jobs' && <JobsFocusView data={data} />}
        {view === 'costs' && <CostsFocusView data={data} />}
        {view === 'workspaces' && <WorkspacesFocusView data={data} />}
        {view === 'security-alerts' && <SecurityAlertsFocusView data={data} />}
        {view === 'governance' && <GovernanceFocusView data={data} />}
      </CardContent>
    </Card>
  );
}

export function DatabricksFocusPlaceholder() {
  return (
    <Card className="rounded-[1.75rem] border-dashed border-border/80 bg-muted/10">
      <CardContent className="py-12 text-center">
        <p className="text-base font-medium text-foreground">Select a metric card to explore details</p>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          Click Clusters, Job runs, Costs, or another KPI above. The URL updates automatically — share links like{' '}
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">/databricks?view=jobs</code> with your team.
        </p>
      </CardContent>
    </Card>
  );
}
