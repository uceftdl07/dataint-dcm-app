import {
  ArrowDown,
  ArrowRight,
  Box,
  Cloud,
  Database,
  KeyRound,
  Lock,
  Server,
  Shield,
} from 'lucide-react';
import { cn } from '../lib/utils';
import {
  DCM_ECR_BY_ENV,
  GUIDE_BB_RESOURCES,
  GUIDE_IMAGE_FLOW,
  type GuideBbResource,
} from '../lib/lz-onboarding-guide-data';

const RESOURCE_STYLES: Record<GuideBbResource['color'], string> = {
  slate: 'border-slate-300 bg-slate-50 dark:border-slate-600 dark:bg-slate-900/60',
  emerald: 'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40',
  blue: 'border-blue-300 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/40',
  amber: 'border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40',
  violet: 'border-violet-300 bg-violet-50 dark:border-violet-800 dark:bg-violet-950/40',
};

function ResourceChip({ resource }: { resource: GuideBbResource }) {
  return (
    <div className={cn('rounded-xl border-2 p-3 shadow-sm', RESOURCE_STYLES[resource.color])}>
      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
        {resource.name}
      </p>
      <p className="mt-1 font-mono text-xs font-semibold text-foreground">{resource.pattern}</p>
      <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">e.g. {resource.example}</p>
      <p className="mt-2 text-xs leading-snug text-muted-foreground">{resource.note}</p>
    </div>
  );
}

/** Visual architecture — client Azure LZ + central ECR + DCM Core */
export function LzArchitectureVisual() {
  return (
    <div className="space-y-4">
      {/* ECR pull source — dev + prod */}
      <div className="flex flex-col items-stretch gap-3 lg:flex-row lg:items-center">
        <div className="grid flex-1 gap-3 sm:grid-cols-2">
          {(['dev', 'prod'] as const).map((envKey) => {
            const ecr = DCM_ECR_BY_ENV[envKey];
            const isDev = envKey === 'dev';
            return (
              <div
                key={envKey}
                className={cn(
                  'rounded-2xl border-2 border-dashed p-4',
                  isDev
                    ? 'border-orange-300 bg-gradient-to-br from-orange-50 to-amber-50 dark:border-orange-800 dark:from-orange-950/30 dark:to-amber-950/20'
                    : 'border-rose-300 bg-gradient-to-br from-rose-50 to-red-50 dark:border-rose-800 dark:from-rose-950/30 dark:to-red-950/20'
                )}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Box
                      className={cn('size-4', isDev ? 'text-orange-600' : 'text-rose-600')}
                      aria-hidden
                    />
                    <span
                      className={cn(
                        'text-xs font-bold uppercase tracking-widest',
                        isDev
                          ? 'text-orange-800 dark:text-orange-300'
                          : 'text-rose-800 dark:text-rose-300'
                      )}
                    >
                      ECR {envKey}
                    </span>
                  </div>
                  <span className="rounded-full bg-white/80 px-2 py-0.5 font-mono text-[9px] dark:bg-black/30">
                    {ecr.accountId}
                  </span>
                </div>
                <p className="text-[10px] font-medium text-muted-foreground">{ecr.accountName}</p>
                <p className="mt-1 font-mono text-[10px] leading-relaxed">
                  {ecr.registry}
                  <br />/{ecr.defaultRepo}:latest
                </p>
              </div>
            );
          })}
        </div>

        <div className="flex shrink-0 flex-col items-center justify-center gap-1 px-2 text-center">
          <span className="rounded-full bg-orange-100 px-2 py-0.5 text-[10px] font-bold uppercase text-orange-800 dark:bg-orange-900/50 dark:text-orange-200">
            Step 6 — docker pull
          </span>
          <p className="max-w-[8rem] text-[10px] text-muted-foreground">
            Registry = GitHub env (dev or prod)
          </p>
          <ArrowRight className="hidden size-5 text-orange-500 lg:block" aria-hidden />
          <ArrowDown className="size-5 text-orange-500 lg:hidden" aria-hidden />
        </div>

        {/* Client LZ box — unchanged start */}
        <div className="flex-[2] overflow-hidden rounded-2xl border-2 border-emerald-400/60 bg-gradient-to-b from-emerald-50/80 to-white shadow-md dark:border-emerald-700 dark:from-emerald-950/20 dark:to-slate-950">
          <div className="border-b border-emerald-200/80 bg-emerald-100/80 px-4 py-2.5 dark:border-emerald-800 dark:bg-emerald-900/40">
            <div className="flex items-center gap-2">
              <Shield className="size-4 text-emerald-700 dark:text-emerald-400" aria-hidden />
              <p className="text-sm font-bold text-emerald-900 dark:text-emerald-100">
                Client Azure Landing Zone
              </p>
            </div>
            <p className="text-xs text-emerald-800/70 dark:text-emerald-300/70">
              Your subscription — created by azr-iac-bb-dataint-dcm (Step 4)
            </p>
          </div>

          <div className="space-y-3 p-4">
            <div className="rounded-xl border border-emerald-200 bg-white/80 p-3 dark:border-emerald-800 dark:bg-slate-900/50">
              <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                Resource group · azr{'{env}'}rg{'{appcode}'}04-dcm
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50/50 p-3 dark:border-emerald-700 dark:bg-emerald-950/30">
                  <div className="flex items-center gap-2">
                    <KeyRound className="size-4 text-emerald-600" aria-hidden />
                    <span className="text-xs font-bold">Key Vault</span>
                  </div>
                  <p className="mt-1 font-mono text-[11px]">
                    azr{'{env}'}kv{'{app}'} -dcm
                  </p>
                  <p className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
                    <Lock className="size-3" aria-hidden />
                    Private Endpoint → PE subnet
                  </p>
                  <p className="mt-1 text-[10px] text-muted-foreground">4× dcm-* secrets</p>
                </div>

                <div className="rounded-lg border-2 border-blue-300 bg-blue-50/50 p-3 dark:border-blue-700 dark:bg-blue-950/30">
                  <div className="flex items-center gap-2">
                    <Server className="size-4 text-blue-600" aria-hidden />
                    <span className="text-xs font-bold">App Service</span>
                  </div>
                  <p className="mt-1 font-mono text-[11px]">
                    azr{'{env}'}fn{'{app}'} -dcm
                  </p>
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    P0v3 · System-assigned MI
                  </p>
                  <p className="mt-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">
                    Empty after Terraform — image in Step 6
                  </p>
                </div>
              </div>

              <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 dark:border-amber-800 dark:bg-amber-950/20">
                <Database className="size-4 shrink-0 text-amber-600" aria-hidden />
                <p className="font-mono text-[10px] text-amber-900 dark:text-amber-100">
                  Storage azr{'{env}'}st{'{app}'} -dcm
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-violet-200 bg-violet-50/40 p-3 dark:border-violet-800 dark:bg-violet-950/20">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-violet-700 dark:text-violet-300">
                Landing Zone VNet (pre-existing)
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="rounded-lg border border-violet-300 bg-white/70 px-3 py-2 dark:border-violet-700 dark:bg-slate-900/40">
                  <p className="text-xs font-semibold">Integration subnet</p>
                  <p className="text-[10px] text-muted-foreground">Created by BB (/28)</p>
                  <p className="mt-1.5 rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[10px] font-medium text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-100">
                    ↗ Outbound HTTPS — open 6 FQDNs here (prerequisite)
                  </p>
                </div>
                <div className="rounded-lg border border-violet-300 bg-white/70 px-3 py-2 dark:border-violet-700 dark:bg-slate-900/40">
                  <p className="text-xs font-semibold">PE subnet</p>
                  <p className="text-[10px] text-muted-foreground">Pre-existing in LZ</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Metrics flow to core */}
      <div className="flex flex-col items-center gap-2 py-1">
        <div className="flex items-center gap-2 rounded-full bg-tdf-blue/10 px-4 py-1.5 text-xs font-semibold text-tdf-blue">
          <span>HTTPS metrics (ADF, Databricks, cost, …)</span>
        </div>
        <ArrowDown className="size-5 text-tdf-blue" aria-hidden />
        <div className="w-full max-w-2xl rounded-2xl border-2 border-tdf-blue/40 bg-gradient-to-r from-tdf-blue-subtle/50 to-sky-50 p-4 text-center dark:from-tdf-blue/10 dark:to-slate-900">
          <div className="flex items-center justify-center gap-2">
            <Cloud className="size-5 text-tdf-blue" aria-hidden />
            <p className="font-bold text-foreground">DCM Core (central)</p>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Apigee ingestion → Lambda → SQS → DCM backend → this web app
          </p>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Not deployed in your LZ — shared platform for all collectors
          </p>
        </div>
      </div>
    </div>
  );
}

export function LzBbResourceGrid() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {GUIDE_BB_RESOURCES.map((resource) => (
        <ResourceChip key={resource.name} resource={resource} />
      ))}
    </div>
  );
}

export function LzImageFlowVisual() {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {(['dev', 'prod'] as const).map((envKey) => {
          const ecr = GUIDE_IMAGE_FLOW[envKey];
          return (
            <div
              key={envKey}
              className="rounded-xl border bg-muted/40 p-3 font-mono text-[10px] dark:bg-muted/20"
            >
              <p className="mb-1 font-sans text-xs font-bold uppercase text-muted-foreground">
                GitHub env: {envKey}
              </p>
              <p>
                {ecr.accountName} · {ecr.accountId}
              </p>
              <p className="mt-1 break-all">
                {ecr.registry}/{ecr.defaultRepo}
              </p>
            </div>
          );
        })}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-orange-200 bg-gradient-to-br from-orange-50/80 to-white p-4 dark:border-orange-900 dark:from-orange-950/20">
          <p className="mb-1 text-xs font-bold uppercase tracking-widest text-orange-700 dark:text-orange-300">
            Push — {GUIDE_IMAGE_FLOW.pushWorkflow}
          </p>
          <p className="mb-3 text-sm text-muted-foreground">
            Target ECR depends on GitHub environment (dev / prod)
          </p>
          <ol className="space-y-2">
            {GUIDE_IMAGE_FLOW.pushSteps.map((step, i) => (
              <li key={step} className="flex gap-2 text-sm">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-orange-200 text-[10px] font-bold text-orange-900 dark:bg-orange-900 dark:text-orange-100">
                  {i + 1}
                </span>
                <span className="text-muted-foreground">{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50/80 to-white p-4 dark:border-blue-900 dark:from-blue-950/20">
          <p className="mb-1 text-xs font-bold uppercase tracking-widest text-blue-700 dark:text-blue-300">
            Pull — {GUIDE_IMAGE_FLOW.deployWorkflow}
          </p>
          <p className="mb-3 text-sm text-muted-foreground">Per client LZ App Service</p>
          <ol className="space-y-2">
            {GUIDE_IMAGE_FLOW.pullSteps.map((step, i) => (
              <li key={step} className="flex gap-2 text-sm">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-blue-200 text-[10px] font-bold text-blue-900 dark:bg-blue-900 dark:text-blue-100">
                  {i + 1}
                </span>
                <span className="text-muted-foreground">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
