export type FilterTone = 'blue' | 'red';

export const filterToneClass: Record<FilterTone, { icon: string; badge: string; control: string }> = {
  blue: {
    icon: 'bg-info-subtle text-info',
    badge: 'border-info-border bg-info-subtle/80 text-info',
    control: 'border-tdf-blue-border/40 hover:border-tdf-blue-border focus-visible:ring-tdf-blue-border',
  },
  red: {
    icon: 'bg-danger-subtle text-danger',
    badge: 'border-danger-border bg-danger-subtle/80 text-danger',
    control: 'border-danger-border/40 hover:border-danger-border focus-visible:ring-danger-border/70',
  },
};

export function getFilterControlClass(tone: FilterTone = 'blue') {
  return `h-10 w-full rounded-2xl border bg-card px-3.5 py-0 text-sm font-medium text-foreground shadow-sm shadow-slate-950/5 outline-none transition placeholder:text-muted-foreground hover:bg-accent/30 focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${filterToneClass[tone].control}`;
}
