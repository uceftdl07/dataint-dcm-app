/**
 * AccessGate — restricted UI stays visible but greyed/blurred with lock overlay.
 */

import { Lock, Mail } from 'lucide-react';
import React, { useState } from 'react';
import { cn } from '../lib/utils';
import { Button } from './ui/button';

interface AccessGateProps {
  allowed: boolean;
  resourceLabel?: string;
  children: React.ReactNode;
  className?: string;
  blockInteraction?: boolean;
  compact?: boolean;
}

export const AccessGate: React.FC<AccessGateProps> = ({
  allowed,
  resourceLabel = 'this section',
  children,
  className,
  blockInteraction = true,
  compact = false,
}) => {
  const [revealed, setRevealed] = useState(false);

  if (allowed) {
    return <div className={className}>{children}</div>;
  }

  return (
    <div
      className={cn('group relative overflow-hidden rounded-[inherit]', className)}
      onMouseEnter={() => setRevealed(true)}
      onMouseLeave={() => setRevealed(false)}
      onFocus={() => setRevealed(true)}
      onBlur={() => setRevealed(false)}
    >
      <div
        className={cn(
          'transition-all duration-300',
          blockInteraction && 'pointer-events-none select-none',
          'opacity-50 grayscale',
          revealed ? 'blur-[5px]' : 'blur-[2px]',
        )}
        aria-hidden="true"
      >
        {children}
      </div>

      {/* Persistent grey wash — always visible */}
      <div className="pointer-events-none absolute inset-0 bg-slate-400/20" />

      {/* Compact lock badge — always visible */}
      {!revealed && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-300/80 bg-white/85 px-3 py-1.5 text-[11px] font-semibold text-slate-600 shadow-sm">
            <Lock size={12} className="text-amber-600" />
            Restricted
          </span>
        </div>
      )}

      {/* Expanded message on hover */}
      <div
        className={cn(
          'absolute inset-0 flex items-center justify-center p-3 transition-all duration-300',
          revealed ? 'bg-slate-900/30 opacity-100' : 'pointer-events-none opacity-0',
        )}
      >
        <div
          className={cn(
            'flex max-w-xs flex-col items-center gap-2 rounded-2xl border border-white/40 bg-white/95 px-4 py-3 text-center shadow-lg',
            compact ? 'scale-95' : 'scale-100',
          )}
        >
          <div className="flex size-10 items-center justify-center rounded-full bg-amber-100 text-amber-700">
            <Lock size={18} />
          </div>
          <p className="text-sm font-semibold text-slate-900">You don&apos;t have access</p>
          <p className="text-xs leading-relaxed text-slate-600">
            Your role does not include {resourceLabel}. Contact a DCM administrator.
          </p>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-1 h-8 gap-1.5 text-xs"
            onClick={() => {
              window.location.href = 'mailto:?subject=DCM%20access%20request';
            }}
          >
            <Mail size={12} />
            Contact admin
          </Button>
        </div>
      </div>
    </div>
  );
};

interface PageAccessGateProps {
  allowed: boolean;
  pageLabel: string;
  children: React.ReactNode;
}

/** Full-page grey gate — content visible underneath, not hidden. */
export const PageAccessGate: React.FC<PageAccessGateProps> = ({
  allowed,
  pageLabel,
  children,
}) => {
  if (allowed) {
    return <>{children}</>;
  }

  return (
    <div className="relative min-h-[60vh]">
      <AccessGate allowed={false} resourceLabel={pageLabel} blockInteraction>
        <div className="min-h-[60vh]">{children}</div>
      </AccessGate>
    </div>
  );
};
