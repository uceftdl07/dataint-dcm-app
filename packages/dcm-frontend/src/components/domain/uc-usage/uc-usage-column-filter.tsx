import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Filter } from 'lucide-react';
import { Button } from '../../ui/button';
import type { UcUsageColumnDefinition } from '../../../lib/uc-usage/column-filters';

export function UcUsageColumnFilter({
  label,
  definition,
  value,
  onChange,
}: {
  label: string;
  definition: UcUsageColumnDefinition;
  value?: string;
  onChange: (value: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [operator, setOperator] = useState('contains');
  const [lower, setLower] = useState('');
  const [upper, setUpper] = useState('');
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLFormElement>(null);
  const id = useId();
  const scale = definition.scale ?? 1;
  const numeric = definition.kind === 'number';
  const missing = operator === 'isnull' || operator === 'notnull';
  const valid =
    missing ||
    (lower.trim() !== '' &&
      (!numeric ||
        (Number.isFinite(Number(lower) * scale) &&
          (operator !== 'between' ||
            (upper.trim() !== '' &&
              Number.isFinite(Number(upper) * scale) &&
              Number(lower) <= Number(upper))))));
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    const move = () => {
      const rect = trigger.current?.getBoundingClientRect();
      if (rect)
        setPosition({
          top: Math.max(8, Math.min(rect.bottom + 5, window.innerHeight - 320)),
          left: Math.max(8, Math.min(rect.right - 280, window.innerWidth - 288)),
        });
    };
    const outside = (event: MouseEvent) => {
      if (
        !panel.current?.contains(event.target as Node) &&
        !trigger.current?.contains(event.target as Node)
      )
        setOpen(false);
    };
    move();
    panel.current?.querySelector('select')?.focus();
    window.addEventListener('resize', move);
    document.addEventListener('scroll', move, true);
    document.addEventListener('mousedown', outside);
    return () => {
      window.removeEventListener('resize', move);
      document.removeEventListener('scroll', move, true);
      document.removeEventListener('mousedown', outside);
    };
  }, [open]);
  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-label={`Filter ${label}${value ? ' (active)' : ''}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? id : undefined}
        className={`inline-flex size-5 shrink-0 items-center justify-center rounded ${value ? 'text-primary' : 'text-muted-foreground'} focus-visible:ring-2 focus-visible:ring-primary`}
        onClick={(event) => {
          event.stopPropagation();
          const split = value?.indexOf(':') ?? -1;
          const op = split >= 0 ? value!.slice(0, split) : numeric ? 'gte' : 'contains';
          const raw = split >= 0 ? value!.slice(split + 1) : '';
          const parts = numeric ? raw.split(',') : [raw];
          setOperator(op);
          setLower(parts[0] ? (numeric ? String(Number(parts[0]) / scale) : parts[0]) : '');
          setUpper(parts[1] ? String(Number(parts[1]) / scale) : '');
          setOpen(!open);
        }}
      >
        <Filter size={13} aria-hidden />
      </button>
      {open &&
        createPortal(
          <form
            ref={panel}
            id={id}
            role="dialog"
            aria-label={`Filter ${label}`}
            className="fixed z-[9998] w-[280px] max-w-[calc(100vw-16px)] space-y-3 rounded-lg border border-border bg-popover p-4 text-xs text-popover-foreground shadow-lg"
            style={position}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                close();
              }
            }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!valid) return;
              const raw = missing
                ? ''
                : numeric
                  ? [lower, ...(operator === 'between' ? [upper] : [])]
                      .map((v) => String(Number(v) * scale))
                      .join(',')
                  : lower.trim();
              onChange(`${operator}:${raw}`);
              close();
            }}
          >
            <p className="font-semibold">{label}</p>
            <label className="block">
              Condition
              <select
                className="mt-1 h-8 w-full rounded border border-border bg-card px-2"
                value={operator}
                onChange={(e) => setOperator(e.target.value)}
              >
                {numeric ? (
                  <>
                    <option value="gte">At least</option>
                    <option value="lte">At most</option>
                    <option value="between">Between</option>
                  </>
                ) : (
                  <option value="contains">Contains</option>
                )}
                <option value="eq">Equals</option>
                <option value="isnull">Not measured / missing</option>
                <option value="notnull">Has a value</option>
              </select>
            </label>
            {!missing && (
              <label className="block">
                {operator === 'between' ? 'Minimum' : 'Value'}
                {definition.unit ? ` (${definition.unit})` : ''}
                <input
                  required
                  type={numeric ? 'number' : 'text'}
                  step="any"
                  value={lower}
                  onChange={(e) => setLower(e.target.value)}
                  className="mt-1 h-8 w-full rounded border border-border bg-card px-2"
                />
              </label>
            )}
            {operator === 'between' && (
              <label className="block">
                Maximum{definition.unit ? ` (${definition.unit})` : ''}
                <input
                  required
                  type="number"
                  step="any"
                  value={upper}
                  onChange={(e) => setUpper(e.target.value)}
                  className="mt-1 h-8 w-full rounded border border-border bg-card px-2"
                />
              </label>
            )}
            <p className="text-[11px] text-muted-foreground">
              Filters all matching rows across the selected period. Charts keep the applied scope.
            </p>
            <div className="flex justify-between gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  onChange(null);
                  close();
                }}
              >
                Clear
              </Button>
              <Button type="submit" size="sm" disabled={!valid}>
                Apply filter
              </Button>
            </div>
          </form>,
          document.body
        )}
    </>
  );
}
