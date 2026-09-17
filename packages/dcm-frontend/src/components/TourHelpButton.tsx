import { CircleHelp } from 'lucide-react';
import React from 'react';
import { useTour } from '../tour/TourContext';
import { cn } from '../lib/utils';

interface TourHelpButtonProps {
  className?: string;
}

export const TourHelpButton: React.FC<TourHelpButtonProps> = ({ className }) => {
  const { startPageTour } = useTour();

  return (
    <button
      type="button"
      data-tour="tour-help"
      onClick={() => startPageTour()}
      className={cn(
        'group relative inline-flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-tdf-blue-border/20 bg-card text-tdf-blue shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-tdf-blue-border hover:bg-tdf-blue-subtle hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
      aria-label="Start guided tour for this page"
      title="Guided tour"
    >
      <CircleHelp
        size={18}
        className="transition-transform duration-500 group-hover:rotate-12 group-active:scale-90"
      />
      <span className="pointer-events-none absolute inset-0 rounded-2xl bg-gradient-to-br from-tdf-blue/0 to-tdf-teal/0 transition-opacity duration-300 group-hover:from-tdf-blue/10 group-hover:to-tdf-teal/10" />
    </button>
  );
};
