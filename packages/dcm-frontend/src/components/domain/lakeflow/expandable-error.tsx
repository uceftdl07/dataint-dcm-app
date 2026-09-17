import { useState } from 'react';
import { cn } from '../../../lib/utils';

/** Truncated error with expand to full message. */
export function ExpandableError({
  message,
  className,
  maxChars = 90,
}: {
  message: string | null | undefined;
  className?: string;
  maxChars?: number;
}) {
  const [open, setOpen] = useState(false);
  if (!message) return <span className="text-muted-foreground">—</span>;
  const long = message.length > maxChars;
  return (
    <div className={cn('max-w-[320px] text-xs text-danger', className)}>
      <p className={open || !long ? 'whitespace-pre-wrap break-words' : 'truncate'} title={message}>
        {message}
      </p>
      {long ? (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-0.5 text-[10px] font-bold text-muted-foreground underline hover:text-foreground"
        >
          {open ? 'Réduire' : 'Voir tout'}
        </button>
      ) : null}
    </div>
  );
}
