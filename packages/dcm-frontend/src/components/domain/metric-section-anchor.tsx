import type { ReactNode } from 'react';
import { cn } from '../../lib/utils';

export interface MetricSectionAnchorProps {
  sectionId: string;
  isActive: boolean;
  children: ReactNode;
  className?: string;
  sectionRef?: (node: HTMLElement | null) => void;
}

export function MetricSectionAnchor({
  sectionId,
  isActive,
  children,
  className,
  sectionRef,
}: MetricSectionAnchorProps) {
  return (
    <div
      id={sectionId}
      ref={sectionRef}
      tabIndex={-1}
      aria-current={isActive ? 'true' : undefined}
      className={cn(
        'scroll-mt-28 rounded-[1.75rem] outline-none transition-shadow duration-300',
        isActive && 'ring-2 ring-primary/45 ring-offset-2 ring-offset-background',
        className,
      )}
    >
      {children}
    </div>
  );
}
