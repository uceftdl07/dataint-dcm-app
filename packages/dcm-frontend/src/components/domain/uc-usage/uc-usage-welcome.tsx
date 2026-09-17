import {
  Archive,
  ArrowUp,
  BarChart3,
  CheckCircle2,
  DollarSign,
  Flag,
  ShieldAlert,
  Table2,
  Users,
  type LucideIcon,
} from 'lucide-react';
import clsx from 'clsx';
import { Button } from '../../ui/button';

/**
 * Deux pages partagent cet accueil, avec le même geste — choisir un périmètre
 * puis Appliquer — mais pas les mêmes étapes : l'usage dépend de la période du
 * header, la gouvernance décrit un état courant qui l'ignore.
 */
export type UcUsageWelcomeVariant = 'usage' | 'governance';

interface WelcomeContent {
  description: string;
  steps: Array<{ title: string; description: string }>;
  capabilities: Array<{ icon: LucideIcon; title: string; description: string }>;
}

const CONTENT: Record<UcUsageWelcomeVariant, WelcomeContent> = {
  usage: {
    description:
      'Choose a scope to explore the activity, consumers and estimated costs of your Unity Catalog tables.',
    steps: [
      {
        title: 'Choose a scope',
        description: 'Choose a catalog, schema or selection of tables in the filters above.',
      },
      { title: 'Check the period', description: 'Adjust the dates in the application header.' },
      { title: 'Start the analysis', description: 'Click Apply to display metrics and charts.' },
    ],
    capabilities: [
      {
        icon: BarChart3,
        title: 'Track usage',
        description: 'Identify the most used tables and changes in activity.',
      },
      {
        icon: Users,
        title: 'Understand consumers',
        description: 'See who uses your tables and how their usage evolves.',
      },
      {
        icon: DollarSign,
        title: 'Understand costs',
        description: 'Compare estimated costs and identify the tables driving them.',
      },
    ],
  },
  governance: {
    description:
      'Choose a scope to review the lifecycle, ownership tags and open recommendations of your Unity Catalog tables.',
    steps: [
      {
        title: 'Choose a scope',
        description: 'Choose a catalog, schema or selection of tables in the filters above.',
      },
      {
        title: 'Start the analysis',
        description:
          'Click Apply to display the registry and its recommendations. This state ignores the period in the header.',
      },
    ],
    capabilities: [
      {
        icon: Archive,
        title: 'Spot unused tables',
        description: 'Find tables with no recent read, and tables that are stale but still read.',
      },
      {
        icon: ShieldAlert,
        title: 'Check ownership',
        description: 'See which tables are missing their owner, domain or cost center tags.',
      },
      {
        icon: Flag,
        title: 'Prioritise actions',
        description: 'Review open recommendations by severity and by age.',
      },
    ],
  },
};

/** Accueil avant toute analyse : aucune mesure ou courbe de démonstration. */
export function UcUsageWelcome({
  hasScope,
  onChooseScope,
  variant = 'usage',
}: {
  hasScope: boolean;
  onChooseScope: () => void;
  variant?: UcUsageWelcomeVariant;
}) {
  const { description, steps, capabilities } = CONTENT[variant];
  return (
    <section
      aria-labelledby="uc-usage-welcome-title"
      className="overflow-hidden rounded-[var(--card-radius)] border border-border bg-[var(--card-background)] shadow-[var(--card-shadow)]"
    >
      <div className="px-5 py-7 sm:p-8">
        <div className="mb-5 flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Table2 size={23} aria-hidden />
        </div>
        <p className="text-[10px] font-black uppercase tracking-[1.2px] text-primary">
          Your analysis starts here
        </p>
        <h2
          id="uc-usage-welcome-title"
          className="mt-2 text-xl font-semibold text-foreground sm:text-2xl"
        >
          Which tables would you like to analyse?
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>

        <ol
          className={clsx(
            'mt-7 grid gap-5',
            steps.length === 2 ? 'md:grid-cols-2' : 'md:grid-cols-3'
          )}
        >
          {steps.map(({ title, description: stepDescription }, index) => (
            <li key={title} className="flex items-start gap-3">
              <span
                className="flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-secondary-foreground"
                aria-hidden
              >
                {index + 1}
              </span>
              <div>
                <h3 className="text-sm font-semibold">{title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {stepDescription}
                </p>
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-6" role="status" aria-live="polite">
          {hasScope ? (
            <p className="flex items-center gap-2 text-sm font-medium text-primary">
              <CheckCircle2 size={17} className="shrink-0" aria-hidden />
              Your selection is ready. Click Apply to display the analysis.
            </p>
          ) : (
            <Button variant="outline" onClick={onChooseScope}>
              <ArrowUp aria-hidden />
              Choose my scope
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-5 border-t border-border bg-muted/20 px-5 py-5 sm:px-8 md:grid-cols-3">
        {capabilities.map(({ icon: Icon, title, description: capabilityDescription }) => (
          <div key={title} className="flex gap-3">
            <Icon size={17} className="mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
            <div>
              <h3 className="text-xs font-semibold text-foreground">{title}</h3>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {capabilityDescription}
              </p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
