import {
  ArrowRight,
  BookOpen,
  Bot,
  CheckCircle2,
  ExternalLink,
  Sparkles,
  UserCircle,
  Wrench,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  LzArchitectureVisual,
  LzBbResourceGrid,
  LzImageFlowVisual,
} from '../components/LzOnboardingArchitecture';
import {
  CodeBlock,
  GuideChecklistPanel,
  GuideJourneyStrip,
  GuideNetworkEgressTable,
  GuidePillarGrid,
  GuidePrerequisitesPanel,
  GuideProgressCard,
  GuideSidebarNav,
  ReferenceAccordion,
  RoleBadge,
  SectionIntro,
  StepTimeline,
} from '../components/LzOnboardingGuideParts';
import {
  Content,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Badge } from '../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { cn } from '../lib/utils';
import {
  AZURE_LZ_ARCHITECTURE_NOTES,
  BB_INSTALL_DOC_URL,
  COPILOT_MESSAGE_TEMPLATE,
  COPILOT_PARAMS,
  DCM_ECR_BY_ENV,
  GUIDE_HERO,
  GUIDE_IMAGE_FLOW,
  GUIDE_OVERVIEW_INTRO,
  GUIDE_STEPS,
  GUIDE_TROUBLESHOOT,
  LZ_ONBOARDING_DOC_URL,
  LZ_ONBOARDING_STORAGE_KEY,
  type GuidePhase,
} from '../lib/lz-onboarding-guide-data';

/** User journeys — overview first (architecture + prerequisites) */
const GUIDE_NAV = [
  { id: 'overview', label: 'Overview', hint: 'Architecture, prerequisites, network' },
  { id: 'start', label: 'Get started', hint: 'Your role & Copilot agent' },
  { id: 'walkthrough', label: 'Step by step', hint: '7 phases to complete' },
  { id: 'reference', label: 'Technical reference', hint: 'ECR flow & resources' },
  { id: 'help', label: 'Help & FAQ', hint: 'Troubleshooting' },
] as const;

type GuideNavId = (typeof GUIDE_NAV)[number]['id'];

const ROLE_CARDS = [
  {
    role: 'you' as const,
    icon: UserCircle,
    title: 'LZ / business team',
    action: 'Gather subscription details, run @dp-dcm-lz-client, store secrets.',
    scrollTo: 'start',
  },
  {
    role: 'devops' as const,
    icon: Wrench,
    title: 'DevOps / Infra',
    action: 'Apply Terraform (Step 4), open firewall (Overview), deploy image (Step 6).',
    scrollTo: 'overview',
  },
  {
    role: 'agent' as const,
    icon: Bot,
    title: 'AI agent',
    action: 'Entra SP, ingest validation, automated checks.',
    scrollTo: 'walkthrough',
  },
];

function renderStepExtra(step: GuidePhase) {
  if (step.id === 's2') {
    return (
      <div className="space-y-3">
        <CodeBlock label="Message for @dp-dcm-lz-client" code={COPILOT_MESSAGE_TEMPLATE} />
        <details className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
          <summary className="cursor-pointer font-medium">Placeholder meanings</summary>
          <ul className="mt-2 space-y-2 pl-1">
            {COPILOT_PARAMS.map((row) => (
              <li key={row.placeholder} className="text-muted-foreground">
                <code className="text-foreground">{row.placeholder}</code> — {row.meaning}
              </li>
            ))}
          </ul>
        </details>
        <CodeBlock
          code={`cd dataint-dcm-app
./packages/dcm-agent/install.sh --global
# then: az login → select YOUR client LZ subscription`}
        />
      </div>
    );
  }

  if (step.id === 's6') {
    return (
      <div className="space-y-3">
        <LzImageFlowVisual />
        <div className="grid gap-2 sm:grid-cols-2">
          {(['dev', 'prod'] as const).map((envKey) => (
            <div key={envKey} className="rounded-lg border bg-muted/40 p-3 font-mono text-[10px]">
              <p className="mb-1 font-sans text-xs font-bold">github_environment = {envKey}</p>
              <p>{DCM_ECR_BY_ENV[envKey].registry}</p>
            </div>
          ))}
        </div>
        <CodeBlock
          label="Verify deployment"
          code={`az webapp show -g <RESOURCE_GROUP> -n <APP_SERVICE> \\
  --query "{state:state, image:siteConfig.linuxFxVersion}" -o table

az webapp log tail -g <RESOURCE_GROUP> -n <APP_SERVICE>`}
        />
      </div>
    );
  }

  return null;
}

const LzOnboardingGuide: React.FC = () => {
  const [activeNav, setActiveNav] = useState<GuideNavId>('overview');
  const [expandedStepId, setExpandedStepId] = useState<string | null>('s1');
  const [checks, setChecks] = useState<Record<string, boolean>>({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LZ_ONBOARDING_STORAGE_KEY);
      if (raw) setChecks(JSON.parse(raw) as Record<string, boolean>);
    } catch {
      /* ignore */
    }
  }, []);

  const toggleCheck = useCallback((id: string) => {
    setChecks((prev) => {
      const next = { ...prev, [id]: !prev[id] };
      localStorage.setItem(LZ_ONBOARDING_STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const progress = useMemo(() => {
    const total = 9;
    const done = Object.values(checks).filter(Boolean).length;
    return { done, total, pct: Math.round((done / total) * 100) };
  }, [checks]);

  const toggleStep = useCallback((id: string) => {
    setExpandedStepId((prev) => (prev === id ? null : id));
  }, []);

  const goToNav = useCallback((id: GuideNavId) => {
    setActiveNav(id);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  return (
    <Content className="max-w-6xl">
      <ContentHeader>
        <div className="space-y-3">
          <ContentTitle>LZ onboarding guide</ContentTitle>
          <div className="flex flex-wrap gap-2">
            <Badge className="gap-1 bg-tdf-blue text-white hover:bg-tdf-blue">
              <Sparkles className="size-3" aria-hidden />
              {GUIDE_HERO.eyebrow}
            </Badge>
            <Badge variant="outline" className="text-muted-foreground">
              Azure IASP client LZ only
            </Badge>
          </div>
          <div className="flex items-start gap-3">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-tdf-blue to-sky-600 text-white shadow-lg">
              <BookOpen className="size-5" aria-hidden />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight text-foreground sm:text-3xl">
                {GUIDE_HERO.title}
              </h1>
              <ContentDescription className="mt-2 max-w-2xl text-base leading-relaxed">
                {GUIDE_HERO.subtitle}
              </ContentDescription>
            </div>
          </div>
        </div>
        <Link
          to="/dashboard"
          className="inline-flex h-8 shrink-0 items-center rounded-full border border-border bg-card px-3 text-xs font-medium shadow-sm hover:bg-accent"
        >
          Back to dashboard
        </Link>
      </ContentHeader>

      {/* Mobile nav */}
      <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
        {GUIDE_NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => goToNav(item.id)}
            className={cn(
              'shrink-0 rounded-full px-4 py-2 text-xs font-semibold transition',
              activeNav === item.id ? 'bg-tdf-blue text-white' : 'bg-muted text-muted-foreground'
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(220px,260px)_1fr] lg:items-start">
        {/* Sidebar — desktop */}
        <aside className="hidden space-y-5 lg:sticky lg:top-6 lg:block">
          <GuideProgressCard done={progress.done} total={progress.total} pct={progress.pct} />
          <GuideSidebarNav
            items={GUIDE_NAV}
            activeId={activeNav}
            onSelect={(id) => goToNav(id as GuideNavId)}
          />
          <div className="rounded-xl border bg-card p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-widest text-muted-foreground">
              Next up
            </p>
            <GuideChecklistPanel checks={checks} onToggle={toggleCheck} compact />
          </div>
        </aside>

        <ContentMain className="min-w-0 gap-8">
          {/* ── 0. OVERVIEW ── */}
          {activeNav === 'overview' ? (
            <div className="space-y-6 animate-in fade-in duration-300">
              <SectionIntro
                step="Start here"
                title={GUIDE_OVERVIEW_INTRO.title}
                description={GUIDE_OVERVIEW_INTRO.description}
              />

              <GuidePillarGrid />

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Architecture at a glance</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <LzArchitectureVisual />
                  <ul className="space-y-2 text-sm">
                    {AZURE_LZ_ARCHITECTURE_NOTES.map((note) => (
                      <li key={note} className="flex gap-2">
                        <span className="text-tdf-teal">✓</span>
                        <span>{note}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>

              <Card className="border-rose-300/60 dark:border-rose-900">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Prerequisites — before you deploy</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="mb-4 text-sm text-muted-foreground">
                    Validate these before Step 4 (Terraform). Items marked{' '}
                    <strong className="text-foreground">Request early</strong> often block progress
                    for weeks if started too late.
                  </p>
                  <GuidePrerequisitesPanel />
                </CardContent>
              </Card>

              <Card className="border-amber-400/70 bg-amber-50/30 dark:bg-amber-950/10">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    Network egress — open these flows first
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    The collector App Service uses{' '}
                    <strong className="text-foreground">VNet integration</strong> on the BB-created
                    subnet. Outbound HTTPS (443) must reach Entra ID, Azure Resource Manager,
                    Apigee, and central AWS ECR. Without these rules, Terraform may succeed but the
                    collector will fail at startup or image pull.
                  </p>
                  <GuideNetworkEgressTable />
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-amber-500/50 bg-white px-4 py-2 text-xs font-semibold hover:bg-amber-50 dark:bg-transparent dark:hover:bg-amber-950/30">
                    <input
                      type="checkbox"
                      checked={!!checks.c5b}
                      onChange={() => toggleCheck('c5b')}
                      className="size-3.5 accent-tdf-blue"
                    />
                    Mark firewall egress as requested
                  </label>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">7 phases — bird&apos;s eye view</CardTitle>
                </CardHeader>
                <CardContent>
                  <GuideJourneyStrip onOpenWalkthrough={() => goToNav('walkthrough')} />
                </CardContent>
              </Card>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => goToNav('start')}
                  className="inline-flex items-center gap-2 rounded-full bg-tdf-blue px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
                >
                  Choose your role & start
                  <ArrowRight className="size-4" aria-hidden />
                </button>
                <button
                  type="button"
                  onClick={() => goToNav('walkthrough')}
                  className="inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold hover:bg-accent"
                >
                  Jump to step-by-step
                </button>
              </div>

              <Card>
                <CardContent className="p-4">
                  <p className="rounded-lg border border-amber-200/80 bg-amber-50/60 p-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
                    {GUIDE_HERO.disclaimer}
                  </p>
                </CardContent>
              </Card>
            </div>
          ) : null}

          {/* ── 1. GET STARTED ── */}
          {activeNav === 'start' ? (
            <div className="space-y-6 animate-in fade-in duration-300">
              <SectionIntro
                step="Phase 0"
                title="Who are you in this onboarding?"
                description="Pick your hat — everyone follows the same 7 steps, but you only care about yours. When in doubt, start with the Copilot agent."
              />

              <div className="grid gap-3 md:grid-cols-3">
                {ROLE_CARDS.map(({ role, icon: Icon, title, action, scrollTo }) => (
                  <button
                    key={role}
                    type="button"
                    onClick={() => goToNav(scrollTo as GuideNavId)}
                    className="group flex flex-col rounded-xl border bg-card p-4 text-left shadow-sm transition hover:border-tdf-blue/40 hover:shadow-md"
                  >
                    <div className="flex items-center justify-between">
                      <Icon className="size-5 text-tdf-blue" aria-hidden />
                      <RoleBadge role={role} />
                    </div>
                    <p className="mt-3 font-semibold">{title}</p>
                    <p className="mt-1 flex-1 text-sm text-muted-foreground">{action}</p>
                    <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-tdf-blue">
                      Continue
                      <ArrowRight
                        className="size-3 transition group-hover:translate-x-0.5"
                        aria-hidden
                      />
                    </span>
                  </button>
                ))}
              </div>

              <Card className="border-tdf-blue/30 bg-gradient-to-br from-tdf-blue-subtle/30 to-transparent">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Bot className="size-4 text-tdf-blue" />
                    Recommended first action
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Install the agent once, <code className="rounded bg-muted px-1">az login</code>{' '}
                    on your client subscription, then paste this message in Copilot with{' '}
                    <strong>your</strong> values.
                  </p>
                  <CodeBlock label="@dp-dcm-lz-client" code={COPILOT_MESSAGE_TEMPLATE} />
                  <button
                    type="button"
                    onClick={() => goToNav('walkthrough')}
                    className="inline-flex items-center gap-2 rounded-full bg-tdf-blue px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
                  >
                    Open full walkthrough
                    <ArrowRight className="size-4" aria-hidden />
                  </button>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4 text-sm leading-relaxed text-muted-foreground">
                  <p className="rounded-lg border border-amber-200/80 bg-amber-50/60 p-3 text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
                    {GUIDE_HERO.disclaimer}
                  </p>
                </CardContent>
              </Card>

              {/* Mobile checklist */}
              <Card className="lg:hidden">
                <CardHeader>
                  <CardTitle className="text-base">Checklist</CardTitle>
                </CardHeader>
                <CardContent>
                  <GuideChecklistPanel checks={checks} onToggle={toggleCheck} />
                </CardContent>
              </Card>
            </div>
          ) : null}

          {/* ── 2. WALKTHROUGH ── */}
          {activeNav === 'walkthrough' ? (
            <div className="space-y-6 animate-in fade-in duration-300">
              <SectionIntro
                step="Phases 1–7"
                title="Complete these steps in order"
                description="Click a step to expand instructions. Step 6 is the most commonly skipped — without it, your App Service stays empty and DCM receives no metrics."
              />

              <div className="rounded-xl border border-amber-300/60 bg-amber-50/50 px-4 py-3 text-sm dark:bg-amber-950/20">
                <strong>Remember:</strong> Terraform (Step 4) creates an empty App Service. The
                collector Docker image is installed separately in Step 6 via GitHub Actions +
                central AWS ECR.
              </div>

              <StepTimeline
                steps={GUIDE_STEPS}
                expandedId={expandedStepId}
                onToggle={toggleStep}
                renderExtra={renderStepExtra}
              />

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Full checklist</CardTitle>
                </CardHeader>
                <CardContent>
                  <GuideChecklistPanel checks={checks} onToggle={toggleCheck} />
                </CardContent>
              </Card>
            </div>
          ) : null}

          {/* ── 3. REFERENCE ── */}
          {activeNav === 'reference' ? (
            <div className="space-y-4 animate-in fade-in duration-300">
              <SectionIntro
                step="Deep dive"
                title="Technical reference"
                description="Resource naming, ECR push/pull, and full resource grid. The overview tab covers architecture and network prerequisites."
              />

              <ReferenceAccordion
                title="BB resources created in your subscription"
                summary="Naming patterns from azr-iac-bb-dataint-dcm (Step 4)"
                defaultOpen
              >
                <LzBbResourceGrid />
              </ReferenceAccordion>

              <ReferenceAccordion
                title="Collector image — push & pull (ECR)"
                summary="Central AWS registry: dev 551656632516 · prod 884068385310"
              >
                <div className="space-y-4">
                  <LzImageFlowVisual />
                  <p className="text-sm text-muted-foreground">
                    Workflows:{' '}
                    <code className="rounded bg-muted px-1">{GUIDE_IMAGE_FLOW.pushWorkflow}</code>{' '}
                    then{' '}
                    <code className="rounded bg-muted px-1">{GUIDE_IMAGE_FLOW.deployWorkflow}</code>
                    . ECR token expires ~12h — re-run deploy if image pull fails.
                  </p>
                </div>
              </ReferenceAccordion>

              <ReferenceAccordion
                title="Network egress (full table)"
                summary="Same FQDN list as Overview — copy for firewall ticket"
              >
                <GuideNetworkEgressTable />
              </ReferenceAccordion>
            </div>
          ) : null}

          {/* ── 4. HELP ── */}
          {activeNav === 'help' ? (
            <div className="space-y-6 animate-in fade-in duration-300">
              <SectionIntro
                step="Support"
                title="FAQ & troubleshooting"
                description="Common blockers during onboarding. If you are stuck, check the symptom that matches your situation."
              />

              <div className="grid gap-3 sm:grid-cols-2">
                {GUIDE_TROUBLESHOOT.map((row) => (
                  <Card key={row.symptom} className="h-full">
                    <CardContent className="p-4">
                      <p className="font-semibold leading-snug">{row.symptom}</p>
                      <p className="mt-2 text-sm text-muted-foreground">{row.action}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CheckCircle2 className="size-4 text-tdf-teal" />
                    Further reading
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                  <a
                    href={BB_INSTALL_DOC_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-9 items-center gap-2 rounded-full border px-4 text-xs font-medium hover:bg-accent"
                  >
                    BB installation.md
                    <ExternalLink size={14} />
                  </a>
                  <a
                    href={LZ_ONBOARDING_DOC_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-9 items-center gap-2 rounded-full border px-4 text-xs font-medium hover:bg-accent"
                  >
                    Team doc (docs/07-lz-onboarding)
                    <ExternalLink size={14} />
                  </a>
                </CardContent>
              </Card>
            </div>
          ) : null}
        </ContentMain>
      </div>
    </Content>
  );
};

export default LzOnboardingGuide;
