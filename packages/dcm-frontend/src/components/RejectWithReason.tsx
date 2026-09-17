import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Button } from './ui/button';
import { FieldLabel, Textarea } from './ui/input';

interface RejectWithReasonProps {
  /** What is being rejected — used to build unique accessible labels. */
  subject: string;
  /** Called with the trimmed, non-empty reason. */
  onReject: (reason: string) => Promise<void>;
  label?: string;
  busy?: boolean;
  className?: string;
}

/**
 * Reject button that expands into a mandatory-reason form.
 *
 * Every rejection route (project creation, join request, scope request) refuses a
 * blank reason with a 422: the requester is told why instead of seeing their
 * request silently disappear. Enforcing it here means the user finds out before
 * the round-trip.
 */
export function RejectWithReason({
  subject,
  onReject,
  label = 'Reject',
  busy = false,
  className,
}: RejectWithReasonProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');

  const close = () => {
    setOpen(false);
    setReason('');
  };

  const handleConfirm = async () => {
    const trimmed = reason.trim();
    if (!trimmed || busy) return;
    await onReject(trimmed);
    close();
  };

  if (!open) {
    return (
      <Button
        size="sm"
        variant="outline"
        // Several queues sit on the same page — name the button by what it
        // rejects so the target is never ambiguous.
        aria-label={`${label} ${subject}`}
        disabled={busy}
        onClick={() => setOpen(true)}
      >
        {label}
      </Button>
    );
  }

  return (
    <div
      className={`flex flex-col gap-2 rounded-xl border border-border/60 bg-muted/30 p-3 ${className ?? ''}`}
    >
      <label className="flex flex-col gap-1.5">
        <FieldLabel>Reason (required)</FieldLabel>
        <Textarea
          autoFocus
          rows={2}
          aria-label={`Rejection reason for ${subject}`}
          placeholder="Explain the refusal — the requester sees it."
          value={reason}
          disabled={busy}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" disabled={busy} onClick={close}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={busy || !reason.trim()}
          onClick={() => void handleConfirm()}
        >
          {busy && <Loader2 className="animate-spin" />}
          Confirm rejection
        </Button>
      </div>
    </div>
  );
}
