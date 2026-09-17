/**
 * AccessRequestModal - Modal form for requesting DCM access
 */

import React, { useState } from 'react';
import { X, Send, Loader2, CheckCircle, AlertCircle, Info, Plus, Trash2 } from 'lucide-react';
import { DcmApiError, submitAccessRequest } from '../api/dcmApiClient';

interface AccessRequestModalProps {
  userEmail: string | null;
  displayName: string | null;
  entraOid: string | null;
  /** Landing page: let visitors type email + name before SSO */
  allowGuestIdentity?: boolean;
  onClose: () => void;
}

function buildJustification(
  businessJustification: string,
  landingZoneText: string,
  additionalEmails: string[],
): string {
  const parts: string[] = [];

  if (landingZoneText.trim()) {
    parts.push(`Requested landing zone(s): ${landingZoneText.trim()}`);
  }

  const extra = additionalEmails.map((item) => item.trim().toLowerCase()).filter((item) => item.includes('@'));
  if (extra.length > 0) {
    parts.push(`Also request access for: ${extra.join(', ')}`);
  }

  parts.push(`Business justification:\n${businessJustification.trim()}`);
  return parts.join('\n\n');
}

export const AccessRequestModal: React.FC<AccessRequestModalProps> = ({
  userEmail,
  displayName,
  entraOid,
  allowGuestIdentity = false,
  onClose,
}) => {
  const isGuest = allowGuestIdentity && !userEmail;
  const [guestEmail, setGuestEmail] = useState('');
  const [guestDisplayName, setGuestDisplayName] = useState('');
  const [landingZoneText, setLandingZoneText] = useState('');
  const [additionalEmails, setAdditionalEmails] = useState<string[]>(['']);
  const [justification, setJustification] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [pendingRequestInfo, setPendingRequestInfo] = useState<string | null>(null);

  const resolvedEmail = (userEmail ?? guestEmail).trim().toLowerCase();
  const resolvedDisplayName = (displayName ?? guestDisplayName).trim() || resolvedEmail;

  const updateAdditionalEmail = (index: number, value: string) => {
    setAdditionalEmails((current) => current.map((item, i) => (i === index ? value : item)));
  };

  const addAdditionalEmail = () => {
    setAdditionalEmails((current) => [...current, '']);
  };

  const removeAdditionalEmail = (index: number) => {
    setAdditionalEmails((current) => current.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!resolvedEmail || !resolvedEmail.includes('@')) {
      setSubmitError('Please enter a valid professional email address');
      return;
    }

    if (justification.trim().length < 10) {
      setSubmitError('Justification must contain at least 10 characters');
      return;
    }

    const invalidExtra = additionalEmails
      .map((item) => item.trim())
      .filter((item) => item.length > 0 && !item.includes('@'));
    if (invalidExtra.length > 0) {
      setSubmitError('One or more additional email addresses are invalid');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setPendingRequestInfo(null);

    try {
      await submitAccessRequest({
        email: resolvedEmail,
        display_name: resolvedDisplayName,
        entra_oid: entraOid || undefined,
        justification: buildJustification(justification, landingZoneText, additionalEmails),
        requested_lz_ids: [],
      });

      setSubmitSuccess(true);
      window.setTimeout(onClose, 3000);
    } catch (error) {
      console.error('[AccessRequestModal] Submit error:', error);

      if (error instanceof DcmApiError && error.statusCode === 409) {
        setPendingRequestInfo(
          'You already have a pending access request. Please wait for administrator approval. You will be notified by email once your access is granted.',
        );
      } else {
        setSubmitError(error instanceof Error ? error.message : 'Error submitting request');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const canSubmit =
    justification.trim().length >= 10
    && (!isGuest || (guestEmail.trim().includes('@') && guestDisplayName.trim().length > 0));

  if (submitSuccess) {
    return (
      <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-2xl">
          <div className="mb-4 flex justify-center">
            <div className="rounded-full bg-green-100 p-3">
              <CheckCircle className="h-12 w-12 text-green-600" />
            </div>
          </div>
          <h3 className="mb-2 text-center text-xl font-bold text-slate-900">Request submitted!</h3>
          <p className="text-center text-sm text-slate-600">
            An administrator will review your request and contact you by email.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[65] flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 p-6">
          <h2 className="text-xl font-bold text-slate-900">Request DCM Access</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            disabled={isSubmitting}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6">
          <div className="space-y-5">
            {isGuest ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-2 block text-sm font-semibold text-slate-700">
                    Full name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={guestDisplayName}
                    onChange={(e) => setGuestDisplayName(e.target.value)}
                    placeholder="Jane Doe"
                    className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                    disabled={isSubmitting}
                    required
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-semibold text-slate-700">
                    Professional email <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="email"
                    value={guestEmail}
                    onChange={(e) => setGuestEmail(e.target.value)}
                    placeholder="jane.doe@totalenergies.com"
                    className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                    disabled={isSubmitting}
                    required
                  />
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-900">
                  Your Identity
                </p>
                <p className="text-sm font-medium text-blue-900">{displayName || userEmail}</p>
                <p className="text-xs text-blue-700">{userEmail}</p>
              </div>
            )}

            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">
                Landing zone (optional)
              </label>
              <input
                type="text"
                value={landingZoneText}
                onChange={(e) => setLandingZoneText(e.target.value)}
                placeholder="e.g. lz-aws-prod, my-azure-lz, or a group distribution list"
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                disabled={isSubmitting}
              />
              <p className="mt-1 text-xs text-slate-500">
                Type the landing zone name or ID. Leave empty if you are not sure yet.
              </p>
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <label className="block text-sm font-semibold text-slate-700">
                  Additional emails (optional)
                </label>
                <button
                  type="button"
                  onClick={addAdditionalEmail}
                  className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-[#0055A4] transition hover:bg-blue-50"
                  disabled={isSubmitting}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add email
                </button>
              </div>
              <p className="mb-3 text-xs text-slate-500">
                Request access for teammates or a shared mailbox — one submission for several people.
              </p>
              <div className="space-y-2">
                {additionalEmails.map((value, index) => (
                  <div key={`extra-email-${index}`} className="flex gap-2">
                    <input
                      type="email"
                      value={value}
                      onChange={(e) => updateAdditionalEmail(index, e.target.value)}
                      placeholder="colleague@totalenergies.com"
                      className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                      disabled={isSubmitting}
                    />
                    {additionalEmails.length > 1 && (
                      <button
                        type="button"
                        onClick={() => removeAdditionalEmail(index)}
                        className="rounded-xl border border-slate-200 px-3 text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
                        disabled={isSubmitting}
                        aria-label="Remove email"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">
                Business Justification <span className="text-red-500">*</span>
              </label>
              <textarea
                value={justification}
                onChange={(e) => setJustification(e.target.value)}
                placeholder="Explain why you need access to DCM (e.g., data pipeline monitoring, cloud cost tracking, security alert analysis...)"
                rows={4}
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                disabled={isSubmitting}
                required
              />
              <p className="mt-1 text-xs text-slate-500">Minimum 10 characters</p>
            </div>

            {submitError && (
              <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
                <AlertCircle className="h-5 w-5 flex-shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            {pendingRequestInfo && (
              <div className="flex items-start gap-2 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
                <Info className="h-5 w-5 flex-shrink-0" />
                <span>{pendingRequestInfo}</span>
              </div>
            )}

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-600">
              <p className="mb-1 font-semibold text-slate-700">Approval Process</p>
              <ul className="ml-4 list-disc space-y-1">
                <li>Your request is sent to DCM administrators via the Teams channel</li>
                <li>An admin will review your justification</li>
                <li>You will receive an email once access is granted</li>
                <li>By default, you will have read-only access (viewer role)</li>
              </ul>
            </div>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-slate-300 bg-white px-4 py-3 font-medium text-slate-700 transition-colors hover:bg-slate-50"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-3 font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={isSubmitting || !canSubmit}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Submitting...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Submit Request
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
