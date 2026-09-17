import { BarChart3, ChevronRight, Cloud, Copy, Server } from 'lucide-react';
import { useCallback, useState, type ReactNode } from 'react';
import { Badge } from './ui/badge';
import { Card, CardContent } from './ui/card';
import { cn } from '../lib/utils';
import {
  GUIDE_CHECKLIST,
  GUIDE_JOURNEY,
  GUIDE_NETWORK_EGRESS,
  GUIDE_NETWORK_EGRESS_NOTES,
  GUIDE_OVERVIEW_PILLARS,
  GUIDE_PREREQUISITES,
  ROLE_LABELS,
  type GuidePhase,
  type GuideRole,
} from '../lib/lz-onboarding-guide-data';

export function RoleBadge({ role }: { role: GuideRole }) {
  const styles: Record<GuideRole, string> = {
    you: 'bg-emerald-500/10 text-emerald-800 border-emerald-200',
    agent: 'bg-violet-500/10 text-violet-800 border-violet-200',
    devops: 'bg-amber-500/10 text-amber-900 border-amber-200',
  };
  return (
    <Badge
      variant="outline"
      className={cn('text-[10px] font-bold uppercase tracking-wide', styles[role])}
    >
      {ROLE_LABELS[role]}
    </Badge>
  );
}

export function CodeBlock({ code, label }: { code: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }, [code]);

  return (
    <div className="relative rounded-xl border border-slate-800 bg-slate-950 text-slate-100">
      {label ? (
        <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
          {label}
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 hover:bg-slate-800"
          >
            <Copy size={12} />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      ) : null}
      <pre className="overflow-x-auto p-4 text-xs leading-relaxed">{code}</pre>
    </div>
  );
}

export function SectionIntro({
  step,
  title,
  description,
}: {
  step?: string;
  title: string;
  description: string;
}) {
  return (
    <div className="space-y-2 border-b border-border pb-6">
      {step ? (
        <p className="text-xs font-bold uppercase tracking-widest text-tdf-blue">{step}</p>
      ) : null}
      <h2 className="text-xl font-bold tracking-tight sm:text-2xl">{title}</h2>
      <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>
    </div>
  );
}

export function GuideProgressCard({
  done,
  total,
  pct,
}: {
  done: number;
  total: number;
  pct: number;
}) {
  return (
    <div className="rounded-xl border border-tdf-blue/20 bg-gradient-to-br from-tdf-blue-subtle/40 to-transparent p-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Your progress
      </p>
      <p className="mt-1 text-2xl font-black tabular-nums text-foreground">
        {done}
        <span className="text-base font-medium text-muted-foreground">/{total}</span>
      </p>
      <div className="mt-3 h-2 rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-gradient-to-r from-tdf-teal to-tdf-blue transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {pct === 100
          ? 'Ready to validate with DCM team.'
          : 'Check items as you complete each phase.'}
      </p>
    </div>
  );
}

export function GuideSidebarNav({
  items,
  activeId,
  onSelect,
}: {
  items: readonly { id: string; label: string; hint: string }[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="space-y-1" aria-label="Guide sections">
      {items.map((item, index) => {
        const active = activeId === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            className={cn(
              'flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition',
              active ? 'bg-tdf-blue text-white shadow-sm' : 'text-foreground hover:bg-muted'
            )}
          >
            <span
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold',
                active ? 'bg-white/20' : 'bg-muted text-muted-foreground'
              )}
            >
              {index + 1}
            </span>
            <span>
              <span className="block text-sm font-semibold leading-tight">{item.label}</span>
              <span
                className={cn(
                  'mt-0.5 block text-[11px] leading-snug',
                  active ? 'text-white/80' : 'text-muted-foreground'
                )}
              >
                {item.hint}
              </span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

export function GuideChecklistPanel({
  checks,
  onToggle,
  compact,
}: {
  checks: Record<string, boolean>;
  onToggle: (id: string) => void;
  compact?: boolean;
}) {
  const items = compact
    ? GUIDE_CHECKLIST.filter((item) => !checks[item.id]).slice(0, 4)
    : GUIDE_CHECKLIST;

  return (
    <div className="space-y-1">
      {compact && items.length === 0 ? (
        <p className="rounded-lg bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-800">
          All checklist items done.
        </p>
      ) : null}
      {items.map((item) => (
        <label
          key={item.id}
          className="flex cursor-pointer items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-muted/60"
        >
          <input
            type="checkbox"
            checked={!!checks[item.id]}
            onChange={() => onToggle(item.id)}
            className="mt-0.5 size-4 shrink-0 accent-tdf-blue"
          />
          <span
            className={cn(
              'flex flex-col gap-1 text-sm leading-snug',
              checks[item.id] && 'text-muted-foreground line-through'
            )}
          >
            {!compact ? <RoleBadge role={item.role} /> : null}
            <span>{item.text}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

export function StepTimeline({
  steps,
  expandedId,
  onToggle,
  renderExtra,
}: {
  steps: GuidePhase[];
  expandedId: string | null;
  onToggle: (id: string) => void;
  renderExtra?: (step: GuidePhase) => ReactNode;
}) {
  return (
    <ol className="relative space-y-0">
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1;
        const expanded = expandedId === step.id;
        const isCritical = step.id === 's6';

        return (
          <li key={step.id} className="relative flex gap-4 pb-8">
            {!isLast ? (
              <span
                className="absolute left-[15px] top-8 h-[calc(100%-1rem)] w-px bg-border"
                aria-hidden
              />
            ) : null}

            <button
              type="button"
              onClick={() => onToggle(step.id)}
              className={cn(
                'relative z-[1] flex size-8 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold transition',
                expanded
                  ? 'border-tdf-blue bg-tdf-blue text-white'
                  : isCritical
                    ? 'border-amber-500 bg-amber-50 text-amber-900'
                    : 'border-border bg-card text-muted-foreground hover:border-tdf-blue/50'
              )}
              aria-expanded={expanded}
            >
              {index + 1}
            </button>

            <div className="min-w-0 flex-1">
              <button
                type="button"
                onClick={() => onToggle(step.id)}
                className="flex w-full items-start justify-between gap-2 text-left"
              >
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-foreground">{step.title}</p>
                    <RoleBadge role={step.role} />
                    {isCritical ? (
                      <Badge className="bg-amber-500 text-[10px] text-white hover:bg-amber-500">
                        Often missed
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{step.step}</p>
                </div>
                <ChevronRight
                  className={cn(
                    'mt-1 size-4 shrink-0 text-muted-foreground transition',
                    expanded && 'rotate-90'
                  )}
                  aria-hidden
                />
              </button>

              {expanded ? (
                <Card
                  className={cn(
                    'mt-3 border-l-4',
                    isCritical ? 'border-l-amber-500' : 'border-l-tdf-blue'
                  )}
                >
                  <CardContent className="space-y-3 p-4">
                    <p className="text-sm leading-relaxed text-muted-foreground">{step.body}</p>
                    {renderExtra?.(step)}
                  </CardContent>
                </Card>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function ReferenceAccordion({
  title,
  summary,
  children,
  defaultOpen,
}: {
  title: string;
  summary: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className="group rounded-xl border border-border bg-card shadow-sm open:shadow-md"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 marker:content-none [&::-webkit-details-marker]:hidden">
        <div>
          <p className="font-semibold text-foreground">{title}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">{summary}</p>
        </div>
        <ChevronRight
          className="size-5 shrink-0 text-muted-foreground transition group-open:rotate-90"
          aria-hidden
        />
      </summary>
      <div className="border-t border-border px-4 pb-4 pt-2">{children}</div>
    </details>
  );
}

const PILLAR_ICONS = {
  subscription: Server,
  collector: Cloud,
  metrics: BarChart3,
} as const;

export function GuidePillarGrid() {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {GUIDE_OVERVIEW_PILLARS.map((pillar) => {
        const Icon = PILLAR_ICONS[pillar.icon];
        return (
          <div key={pillar.title} className="rounded-xl border bg-card p-4 shadow-sm">
            <div className="flex size-9 items-center justify-center rounded-lg bg-tdf-blue/10 text-tdf-blue">
              <Icon className="size-4" aria-hidden />
            </div>
            <p className="mt-3 font-semibold leading-snug">{pillar.title}</p>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {pillar.description}
            </p>
          </div>
        );
      })}
    </div>
  );
}

export function GuidePrerequisitesPanel() {
  return (
    <ul className="space-y-2">
      {GUIDE_PREREQUISITES.map((item) => (
        <li
          key={item.id}
          className={cn(
            'flex gap-3 rounded-xl border px-3 py-3',
            item.requestEarly
              ? 'border-rose-300/80 bg-rose-50/50 dark:border-rose-900 dark:bg-rose-950/20'
              : 'border-border bg-muted/20'
          )}
        >
          <span
            className={cn(
              'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold',
              item.blocking ? 'bg-tdf-blue text-white' : 'bg-muted text-muted-foreground'
            )}
            aria-hidden
          >
            {item.blocking ? '!' : '·'}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium leading-snug">{item.title}</p>
              <RoleBadge role={item.owner} />
              {item.requestEarly ? (
                <Badge className="bg-rose-600 text-[10px] text-white hover:bg-rose-600">
                  Request early
                </Badge>
              ) : null}
            </div>
            <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function GuideNetworkEgressTable() {
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              <th className="p-2 font-semibold">Destination (FQDN)</th>
              <th className="p-2 font-semibold">Usage</th>
              <th className="p-2 font-semibold">When</th>
              <th className="p-2 font-semibold">Env</th>
            </tr>
          </thead>
          <tbody>
            {GUIDE_NETWORK_EGRESS.map((row) => (
              <tr key={row.destination} className="border-b border-border/50">
                <td className="p-2 font-mono text-[11px]">{row.destination}</td>
                <td className="p-2">{row.usage}</td>
                <td className="p-2 capitalize text-muted-foreground">{row.when}</td>
                <td className="p-2 capitalize text-muted-foreground">{row.env ?? 'all'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        {GUIDE_NETWORK_EGRESS_NOTES.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

export function GuideJourneyStrip({ onOpenWalkthrough }: { onOpenWalkthrough?: () => void }) {
  return (
    <div className="space-y-3">
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {GUIDE_JOURNEY.map((item) => (
          <li
            key={item.step}
            className={cn(
              'rounded-xl border bg-card p-3 text-center shadow-sm',
              item.step === '6' && 'border-amber-400/70 bg-amber-50/40 dark:bg-amber-950/20'
            )}
          >
            <span className="text-lg font-black tabular-nums text-tdf-blue">{item.step}</span>
            <p className="mt-1 text-xs font-semibold leading-snug">{item.title}</p>
            <div className="mt-1.5 flex justify-center">
              <RoleBadge role={item.who} />
            </div>
          </li>
        ))}
      </ol>
      {onOpenWalkthrough ? (
        <button
          type="button"
          onClick={onOpenWalkthrough}
          className="inline-flex items-center gap-1 text-sm font-semibold text-tdf-blue hover:underline"
        >
          Open detailed walkthrough
          <ChevronRight className="size-4" aria-hidden />
        </button>
      ) : null}
    </div>
  );
}
