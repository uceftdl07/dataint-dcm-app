import { ExternalLink } from 'lucide-react';
import React from 'react';

export interface DatabricksEmbeddedDashboardProps {
  title: string;
  embedUrl: string;
  directUrl: string;
  description?: string | null;
}

export const DatabricksEmbeddedDashboard: React.FC<DatabricksEmbeddedDashboardProps> = ({
  title,
  embedUrl,
  directUrl,
  description,
}) => {
  return (
    <div className="flex min-h-[calc(100vh-14rem)] flex-1 flex-col overflow-hidden rounded-lg border bg-background shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b bg-gradient-to-r from-primary/10 to-primary/5 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{title}</p>
          {description ? (
            <p className="mt-1 text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        <a
          href={directUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-8 shrink-0 items-center justify-center gap-2 rounded-full border border-border bg-card px-3 text-xs font-medium text-foreground shadow-sm transition-all hover:-translate-y-0.5 hover:bg-accent"
        >
          <ExternalLink className="h-4 w-4" />
          Open in Databricks
        </a>
      </div>
      <iframe
        title={title}
        src={embedUrl}
        className="min-h-[720px] w-full flex-1 border-0"
        allow="fullscreen"
      />
    </div>
  );
};
