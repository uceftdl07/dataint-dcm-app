import { useCallback, useRef, useState, type FocusEvent, type MouseEvent } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';
import { cn } from '../../../lib/utils';

export function ComputeInfoTip({
  description,
  className,
  label = 'Field description',
}: {
  description: string;
  className?: string;
  label?: string;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });

  const updatePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({
      top: rect.top - 8,
      left: rect.left + rect.width / 2,
    });
  }, []);

  const show = () => {
    updatePosition();
    setOpen(true);
  };

  const hide = () => setOpen(false);

  const onMouseEnter = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    show();
  };

  const onFocus = (event: FocusEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    show();
  };

  const tooltip =
    open && typeof document !== 'undefined'
      ? createPortal(
          <span
            role="tooltip"
            className="pointer-events-none fixed z-[9999] w-56 -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-popover px-2.5 py-2 text-[11px] font-normal normal-case leading-snug tracking-normal text-popover-foreground shadow-lg"
            style={{ top: position.top, left: position.left }}
          >
            {description}
          </span>,
          document.body
        )
      : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={cn(
          'inline-flex size-4 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tdf-blue/40',
          className
        )}
        aria-label={label}
        onMouseEnter={onMouseEnter}
        onMouseLeave={hide}
        onFocus={onFocus}
        onBlur={hide}
      >
        <Info className="size-3.5" aria-hidden />
      </button>
      {tooltip}
    </>
  );
}
