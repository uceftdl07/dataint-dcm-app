import * as React from 'react';
import { cn } from '../../lib/utils';

export type HeaderTagTone = 'primary' | 'danger' | 'neutral';

export type HeaderTag = {
  label?: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  tone?: HeaderTagTone;
};

const headerTagClasses: Record<HeaderTagTone, string> = {
  primary: 'border-tdf-blue-border/30 bg-tdf-blue-subtle text-tdf-blue',
  danger: 'border-danger-border/40 bg-danger-subtle/80 text-danger',
  neutral: 'border-border/70 bg-card/85 text-foreground',
};

export function HeaderTags({ description, tags }: { description: React.ReactNode; tags: HeaderTag[] }) {
  return (
    <>
      <span className="sr-only">{description}</span>
      {tags.map((tag, index) => (
        <span
          key={`${String(tag.label ?? 'tag')}-${index}`}
          aria-hidden="true"
          className={cn(
            'inline-flex h-8 items-center gap-2 rounded-full border px-3 text-xs font-medium shadow-sm [&_svg]:size-3.5',
            headerTagClasses[tag.tone ?? 'neutral'],
          )}
        >
          {tag.icon}
          {tag.label && <span className="text-muted-foreground">{tag.label}</span>}
          <strong className="font-semibold">{tag.value}</strong>
        </span>
      ))}
    </>
  );
}
