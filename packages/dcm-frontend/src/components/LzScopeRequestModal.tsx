import { AlertCircle, CheckCircle, Loader2, Send, X } from 'lucide-react';
import { useState } from 'react';
import { DcmApiError, submitLzScopeRequest } from '../api/dcmApiClient';
import type { LandingZoneAccessOverviewItem } from '../types/api';

interface LzScopeRequestModalProps {
  landingZone: LandingZoneAccessOverviewItem;
  onClose: () => void;
}

export function LzScopeRequestModal({ landingZone, onClose }: LzScopeRequestModalProps) {
  const [justification, setJustification] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [pendingInfo, setPendingInfo] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (justification.trim().length < 10) {
      setSubmitError('Justification must contain at least 10 characters');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setPendingInfo(null);

    try {
      await submitLzScopeRequest({
        requested_lz_ids: [landingZone.lz_id],
        justification: justification.trim(),
      });
      setSubmitSuccess(true);
      setTimeout(onClose, 2500);
    } catch (error) {
      if (error instanceof DcmApiError && error.statusCode === 409) {
        setPendingInfo('A pending request already exists for this landing zone.');
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Unable to submit request');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitSuccess) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-2xl">
          <div className="mb-4 flex justify-center">
            <div className="rounded-full bg-green-100 p-3">
              <CheckCircle className="h-12 w-12 text-green-600" />
            </div>
          </div>
          <h3 className="mb-2 text-center text-xl font-bold text-slate-900">Request sent</h3>
          <p className="text-center text-sm text-slate-600">
            Administrators were notified on Teams to add this landing zone to your scope.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 p-6">
          <h2 className="text-xl font-bold text-slate-900">Request landing zone access</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            disabled={isSubmitting}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 p-6">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Landing zone</p>
            <p className="mt-1 text-sm font-medium text-slate-900">
              {landingZone.lz_name || landingZone.lz_id}
            </p>
            <p className="font-mono text-xs text-slate-600">{landingZone.lz_id}</p>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">
              Business justification <span className="text-red-500">*</span>
            </label>
            <textarea
              value={justification}
              onChange={(event) => setJustification(event.target.value)}
              rows={4}
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              placeholder="Explain why you need access to this landing zone..."
              disabled={isSubmitting}
              required
            />
          </div>

          {submitError && (
            <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <span>{submitError}</span>
            </div>
          )}

          {pendingInfo && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
              {pendingInfo}
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 font-medium text-slate-700"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white disabled:opacity-50"
              disabled={isSubmitting || justification.trim().length < 10}
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Send to admin
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
