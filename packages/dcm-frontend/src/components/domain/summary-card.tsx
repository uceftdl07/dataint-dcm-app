import * as React from 'react';
import { Badge } from '../ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';

export function SummaryCard({
  title,
  description,
  icon,
  badge,
  children,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  badge?: string | number;
  children: React.ReactNode;
}) {
  return (
    <Card className="h-full">
      <CardHeader className="border-b border-border/60 bg-muted/60">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-2xl bg-card text-primary shadow-sm ring-1 ring-border">
              {icon}
            </div>
            <div>
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </div>
          </div>
          {badge !== undefined && <Badge variant="outline">{badge}</Badge>}
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function MutedCardMessage({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/50 px-6 py-10 text-center">
      <div className="mb-3 rounded-2xl bg-background p-3 text-muted-foreground shadow-sm ring-1 ring-border">{icon}</div>
      <p className="font-semibold text-foreground">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </div>
  );
}
